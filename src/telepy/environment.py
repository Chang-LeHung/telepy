import argparse
import contextlib
import functools
import os
import site
import sys
import threading
import time
import types
from multiprocessing import util
from typing import Any

from rich.table import Table

from . import logging
from ._telepysys import sched_yield
from .flamegraph import FlameGraph, process_stack_trace
from .sampler import TelepySysAsyncWorkerSampler

_lock = threading.RLock()

# read only for other modules
sampler: None | TelepySysAsyncWorkerSampler = None
# read only for other modules
args: None | argparse.Namespace = None

main_mod = types.ModuleType("__main__")


def patch_os_fork_in_child():
    global sampler, args
    assert sampler is not None
    assert args is not None
    sampler.clear()
    sampler.stop()  # stop it first.
    sampler.start()  # timer was cleared in the child process we need restart it.
    sampler.child_cnt = 0
    sampler.from_fork = True
    if sampler.is_root:
        sampler.is_root = False


def patch_os_fork_in_parent():
    global sampler, args
    assert sampler is not None
    assert args is not None


def patch_before_fork():
    global sampler, args
    assert sampler is not None
    assert args is not None

    if sampler.is_root:
        sampler.child_cnt += 1


def patch_multiprocesssing():
    """
    Patches the multiprocessing spawn mechanism to inject telepy code to profile.
    """
    global args
    assert sampler is not None
    assert args is not None

    _spawnv_passfds = util.spawnv_passfds

    @functools.wraps(_spawnv_passfds)
    def spawnv_passfds(path, args, passfds):
        if "-c" in args:
            idx = args.index("-c")
            cmd = args[idx + 1]

            if "forkserver" in cmd:
                # forkserver mode, we need to inject telepy code to profile.
                args = args[:idx] + ["-m", "telepy", "--mp", "--fork-server"] + args[idx:]
            elif "resource_tracker" not in cmd:
                # spawn mode
                args = args[:idx] + ["-m", "telepy", "--mp"] + args[idx:]
        ret = _spawnv_passfds(path, args, passfds)
        return ret

    util.spawnv_passfds = spawnv_passfds


class Environment:
    initialized = False

    sampler_created = False

    @classmethod
    def init_telepy_environment(cls, args_: argparse.Namespace) -> dict[str, Any]:
        """
        Prepare the environment for a new process. If the process is a child process,
        `prepare_process_environment` will return directly (we have initialized the
        environment in the parent process).

        Args:
            args_ (argparse.Namespace): The arguments for the process.
        """
        global sampler, args, _lock, main_mod, filename
        args = args_
        with _lock:
            if Environment.initialized:
                return main_mod.__dict__

            sampler = TelepySysAsyncWorkerSampler(
                args.interval,
                debug=args.debug,
                ignore_frozen=args.ignore_frozen,
                ignore_self=not args.include_telepy,
                tree_mode=args.tree_mode,
            )
            sampler.adjust()
            Environment.sampler_created = True
            cls.initialized = True
            setattr(main_mod, "__file__", os.path.abspath(args.input[0].name))
            setattr(main_mod, "__builtins__", globals()["__builtins__"])
            sys.modules["__telepy_main__"] = sys.modules["__main__"]
            sys.modules["__main__"] = sys.modules["__mp_main__"] = main_mod
            old_arg = sys.argv
            setattr(sys, "telepy_argv", old_arg)
            if "--" in old_arg:
                idx = old_arg.index("--")
                sys.argv = [args.input[0].name] + old_arg[idx + 1 :]
            else:
                sys.argv = [args.input[0].name]

            os.register_at_fork(
                before=patch_before_fork,
                after_in_child=patch_os_fork_in_child,
                after_in_parent=patch_os_fork_in_parent,
            )
            patch_multiprocesssing()
            sys.path.append(os.getcwd())
            return main_mod.__dict__

    @classmethod
    def destory_telepy_enviroment(cls):
        sys.modules["__main__"] = sys.modules["__telepy_main__"]
        del sys.modules["__telepy_main__"]
        sys.argv = getattr(sys, "telepy_argv")
        delattr(sys, "telepy_argv")
        sys.path.remove(os.getcwd())
        Environment.initialized = False


@contextlib.contextmanager
def telepy_env(args: argparse.Namespace):
    global sampler
    global_dict = Environment.init_telepy_environment(args)
    try:
        yield global_dict, sampler
    finally:
        Environment.destory_telepy_enviroment()


class FlameGraphSaver:
    def __init__(
        self, agrs: argparse.Namespace, sampler: TelepySysAsyncWorkerSampler
    ) -> None:
        assert args is not None
        self.args = args
        self.sampler = sampler
        self.args = args
        self.site_path = site.getsitepackages()[0]
        self.work_dir = os.getcwd()
        self.title = "TelePy Flame Graph"
        self.lines = sampler.dumps().splitlines()[:-1]  # ignore last empty line
        if not self.args.full_path:  # type : ignore
            self.lines = process_stack_trace(self.lines, self.site_path, self.work_dir)

        self.timeout = False
        self.pid = os.getpid()

    def _save_svg(self, filename: str) -> None:
        fg = FlameGraph(
            self.lines,
            title="TelePy Flame Graph",
            reverse=self.args.reverse,
            command=" ".join([sys.executable, *sys.argv]),
            package_path=os.path.dirname(self.site_path),
            work_dir=self.work_dir,
        )

        fg.parse_input()
        svg_content = fg.generate_svg()
        with open(filename, "w+") as fp:
            fp.write(svg_content)

    def _save_folded(self, filename: str) -> None:
        with open(filename, "w+") as fp:
            for idx, line in enumerate(self.lines):
                if idx < len(self.lines) - 1:
                    fp.write(line + "\n")
                else:
                    fp.write(line)

    @staticmethod
    def add_pid_prefix(lines: list[str], pid: int | str) -> list[str]:
        return [f"Process({pid});" + line for line in lines]

    def _single_process_root(self) -> None:
        self._save_svg(self.args.output)
        if self.args.folded_save:
            self._save_folded(self.args.folded_file)

    def _single_process_child(self) -> None:
        # filename: pid-ppid.svg pid-ppid.folded
        if not self.args.merge:
            filename = f"{self.pid}-{os.getppid()}.svg"
            self._save_svg(filename)
            if self.args.debug:
                logging.log_success_panel(
                    f"Process {self.pid} saved profiling data to svg file {filename}"
                )
            if self.args.folded_save:
                filename = f"{self.pid}-{os.getppid()}.folded"
                self._save_folded(filename)
                if self.args.debug:
                    logging.log_success_panel(
                        f"Process {self.pid} saved profiling data to folded file {filename}"  # noqa: E501
                    )
        else:
            filename = f"{self.pid}-{os.getppid()}.folded"
            self.lines = self.add_pid_prefix(
                self.lines, f"pid-{self.pid}, ppid-{os.getppid()}"
            )
            self._save_folded(filename)
            if self.args.debug:
                logging.log_success_panel(
                    f"Process {self.pid} saved profiling data to folded file {filename}"
                )

    def _multi_process_root(self) -> None:
        if self.args.merge:
            files = os.listdir(os.getcwd())
            foldeds = [file for file in files if file.endswith(f"{self.pid}.folded")]

            self.lines = self.add_pid_prefix(self.lines, f"root, pid={self.pid}")

            def load_chidren_file():
                for file in foldeds:
                    with open(file, "r+") as fp:
                        lines = fp.readlines()
                    os.unlink(file)
                    if self.args.debug:
                        logging.log_success_panel(
                            f"Root process {self.pid} read and removed file {file}"
                        )
                    self.lines.extend([line.strip() for line in lines])

            load_chidren_file()
            self._save_svg(self.args.output)
            if self.args.debug:
                logging.log_success_panel(
                    f"Root process {self.pid} collected profiling data to svg "
                    f"file {self.args.output}"
                )
            if self.args.folded_save:
                self._save_folded(self.args.folded_file)
                if self.args.debug:
                    logging.log_success_panel(
                        f"Root process {self.pid} collected profiling data {foldeds} to"
                        f" folded file {self.args.folded_file}"
                    )
        else:
            self._save_svg(self.args.output)
            if self.args.debug:
                logging.log_success_panel(
                    f"Root process {self.pid} saved profiling data to"
                    f" svg file {self.args.output}"
                )
            if self.args.folded_save:
                self._save_folded(self.args.folded_file)
                if self.args.debug:
                    logging.log_success_panel(
                        f"Root process {self.pid} saved profiling data to"
                        f" folded file {self.args.folded_file}"
                    )

    def _multi_process_child(self) -> None:
        if self.args.merge:
            files = os.listdir(os.getcwd())
            foldeds = [file for file in files if file.endswith(f"{self.pid}.folded")]
            self.lines = self.add_pid_prefix(
                self.lines, f"pid-{self.pid}, ppid-{os.getppid()}"
            )

            def load_chidren_file():
                for file in foldeds:
                    with open(file, "r+") as fp:
                        lines = fp.readlines()
                    os.unlink(file)
                    if self.args.debug:
                        logging.log_success_panel(
                            f"Process {self.pid} read and removed file {file}"
                        )
                    self.lines.extend([line.strip() for line in lines])

            load_chidren_file()
            filename = f"{self.pid}-{os.getppid()}.folded"
            self._save_folded(filename)
            if self.args.debug:
                logging.log_success_panel(
                    f"Process {self.pid} collected profiling data {foldeds}"
                    f" to folded file {filename}"
                )
        else:
            filename = f"{self.pid}-{os.getppid()}.svg"
            self._save_svg(filename)
            if self.args.debug:
                logging.log_success_panel(
                    f"Process {self.pid} saved profiling data to svg file {filename}"
                )
            if self.args.folded_save:
                filename = f"{self.pid}-{os.getppid()}.folded"
                self._save_folded(filename)
                if self.args.debug:
                    logging.log_success_panel(
                        f"Process {self.pid} saved profiling data to folded file {filename}"  # noqa: E501
                    )

    def save(self) -> None:
        if self.sampler.child_cnt > 0:
            self.wait_children()
            if self.sampler.is_root:
                self._multi_process_root()
            else:
                self._multi_process_child()
        else:
            if self.sampler.is_root:
                self._single_process_root()
            else:
                self._single_process_child()

    def wait_children(self) -> None:
        """Wait for all child processes to exit."""
        res: list[str] = []
        begin = time.time()
        while len(res) != self.sampler.child_cnt:
            sched_yield()
            files = os.listdir(os.getcwd())
            res = [file for file in files if file.endswith(f"{self.pid}.folded")]
            if time.time() - begin > self.args.timeout:
                self.timeout = True
                break
        if self.timeout:
            logging.log_error_panel("Timeout waiting for child processes to complete")


def telepy_finalize() -> None:
    """Stop and clean up the global sampler resource.

    This function should be called to properly finalize the telepy environment
    by stopping the global sampler instance and save profiling data.
    """
    global sampler
    if not Environment.sampler_created:
        raise RuntimeError("telepy environment is not initialized")
    assert sampler is not None
    assert args is not None
    sampler.stop()

    saver = FlameGraphSaver(args, sampler)
    saver.save()

    if args.debug:
        from .logging import console

        acc = sampler.acc_sampling_time
        start = sampler.start_time
        end = sampler.end_time
        title = "TelePySampler Metrics"
        if sampler.child_cnt > 0 and (sampler.from_fork):
            title += f" pid = {os.getpid()} (with {sampler.child_cnt} child process(es)) "
            f"ppid = {os.getppid()}"
        elif sampler.child_cnt > 0:
            title += f" pid = {os.getpid()} (with {sampler.child_cnt} child process(es))"
        elif sampler.from_fork or sampler.from_mp:
            title += f" pid = {os.getpid()} ppid = {os.getppid()}"

        table = Table(title=title, expand=True)

        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", style="green")

        table.add_row("Accumulated Sampling Time (Monotonic Mircoseconds)", f"{acc}")
        table.add_row(
            "Sampling Time Rate (Versus Program Time)", f"{acc / (end - start):.2%}"
        )
        table.add_row("TelePy Sampler Start Time (Monotonic Mircoseconds)", f"{start}")
        table.add_row("TelePy Sampler End Time (Monotonic Mircoseconds)", f"{end}")
        table.add_row("Sampling Count", str(sampler.sampling_times))

        console.print(table)
