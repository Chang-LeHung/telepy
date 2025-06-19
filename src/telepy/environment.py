import argparse
import contextlib
import enum
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

from . import logger
from ._telepysys import sched_yield
from .flamegraph import FlameGraph, process_stack_trace
from .sampler import TelepySysAsyncWorkerSampler

_lock = threading.RLock()

# read only for other modules
sampler: None | TelepySysAsyncWorkerSampler = None
# read only for other modules
args: None | argparse.Namespace = None


def patch_os_fork_in_child():
    global sampler, args
    assert sampler is not None
    assert args is not None
    sampler.clear()
    # for the forkserver mode, which is a little bit magic and tricky.
    if sampler.started:
        sampler.stop()  # stop it first.
        sampler.start()  # timer was cleared in the child process we need restart it.
    sampler.child_cnt = 0
    sampler.from_fork = True
    if sampler.is_root:
        sampler.is_root = False

    if sampler.forkserver:
        sampler.start()
        sampler.forkserver = False


def patch_os_fork_in_parent():
    global sampler, args
    assert sampler is not None
    assert args is not None
    if sampler.is_root:
        sampler.child_cnt += 1


def patch_before_fork():
    global sampler, args
    assert sampler is not None
    assert args is not None


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
                # we do not launch telepy in the server process, but we will
                # hack the fork syscall to sample its child processes.
                args = args[:idx] + ["--mp", "--fork-server"] + args[idx:]
            elif "resource_tracker" not in cmd:
                # spawn mode
                args = args[:idx] + ["-m", "telepy", "--mp"] + args[idx:]
        ret = _spawnv_passfds(path, args, passfds)
        return ret

    util.spawnv_passfds = spawnv_passfds


class CodeMode(enum.Enum):
    PyFile = 0
    PyString = 1
    PyModule = 2


class Environment:
    initialized = False

    sampler_created = False

    code_mode = CodeMode.PyFile

    _sys_exit = sys.exit
    _os_exit = os._exit

    _sys_module_exit = sys.exit

    @classmethod
    def patch_sys_exit(cls, *args, **kwargs):
        """
        `telepy_finalize` will not be called when the process exits. We need to stop the
        sampler and save the data.
        """
        global sampler
        if sampler is not None and sampler.started:
            logger.log_success_panel(
                "telepy early stops in sys.exit, so we stop and save the data."
            )
            # forserver mode will not start the sampler.
            if sampler.started:
                sampler.stop()
                _do_save()
        cls._sys_exit(*args, **kwargs)

    @classmethod
    def patch_os__exit(cls, *args, **kwargs):
        """
        `telepy_finalize` will not be called when the process exits. We need to stop the
        sampler and save the data.
        """
        global sampler
        if sampler is not None and sampler.started:
            logger.log_success_panel(
                "telepy early stops in os._exit, so we stop and save the data."
            )
            # forserver mode will not start the sampler.
            if sampler.started:
                sampler.stop()
                _do_save()
        cls._os_exit(*args, **kwargs)

    @classmethod
    def init_telepy_environment(
        cls, args_: argparse.Namespace, mode: CodeMode = CodeMode.PyFile
    ) -> dict[str, Any]:
        """
        Prepare the environment for a new process. If the process is a child process,
        `prepare_process_environment` will return directly (we have initialized the
        environment in the parent process).

        Args:
            args_ (argparse.Namespace): The arguments for the process.
        """
        global sampler, args, _lock, filename
        args = args_
        cls.code_mode = mode
        with _lock:
            if cls.initialized:
                raise RuntimeError("telepy environment has been initialized.")

            sampler = TelepySysAsyncWorkerSampler(
                args.interval,
                debug=args.debug,
                ignore_frozen=args.ignore_frozen,
                ignore_self=not args.include_telepy,
                tree_mode=args.tree_mode,
                is_root=not (args.fork_server or args.mp),
                forkserver=args.fork_server,
                from_mp=args.mp,
            )
            # we do not profile the forkserver process.
            if not args.fork_server:
                sampler.start()
            sampler.adjust()
            sys.exit = cls.patch_sys_exit
            os._exit = cls.patch_os__exit
            if not cls.sampler_created:
                os.register_at_fork(
                    before=patch_before_fork,
                    after_in_child=patch_os_fork_in_child,
                    after_in_parent=patch_os_fork_in_parent,
                )
                patch_multiprocesssing()
            cls.sampler_created = True
            cls.initialized = True
            if mode == CodeMode.PyFile:
                main_mod = types.ModuleType("__main__")
                setattr(main_mod, "__file__", os.path.abspath(args.input[0].name))
                setattr(main_mod, "__builtins__", globals()["__builtins__"])
                sys.modules["__telepy_main__"] = sys.modules["__main__"]
                sys.modules["__main__"] = main_mod
                old_arg = sys.argv
                setattr(sys, "telepy_argv", old_arg)
                if "--" in old_arg:
                    idx = old_arg.index("--")
                    sys.argv = [args.input[0].name] + old_arg[idx + 1 :]
                else:
                    sys.argv = [args.input[0].name]
                sys.path.append(os.getcwd())
                return main_mod.__dict__
            elif mode == CodeMode.PyString:
                string_mod = types.ModuleType("__main__")
                setattr(string_mod, "__file__", "<string>")
                setattr(string_mod, "__builtins__", globals()["__builtins__"])
                sys.modules["__telepy_main__"] = sys.modules["__main__"]
                sys.modules["__main__"] = string_mod
                old_arg = sys.argv
                setattr(sys, "telepy_argv", old_arg)
                if "--" in old_arg:
                    idx = old_arg.index("--")
                    sys.argv = ["-c"] + old_arg[idx + 1 :]
                else:
                    sys.argv = ["-c"]
                sys.path.append(os.getcwd())
                return string_mod.__dict__
            elif mode == CodeMode.PyModule:
                old_arg = sys.argv
                setattr(sys, "telepy_argv", old_arg)
                if "--" in old_arg:
                    idx = old_arg.index("--")
                    sys.argv = [old_arg[0]] + old_arg[idx + 1 :]
                else:
                    sys.argv = [old_arg[0]]
                sys.path.append(os.getcwd())
                return {}
            raise RuntimeError("telepy: invalid code mode")

    @classmethod
    def destory_telepy_enviroment(cls):
        with _lock:
            if not cls.initialized:
                return
            sys.exit = cls._sys_exit
            os._exit = cls._os_exit
            if cls.code_mode in (CodeMode.PyFile, CodeMode.PyString):
                sys.modules["__main__"] = sys.modules["__telepy_main__"]
                del sys.modules["__telepy_main__"]
                sys.argv = getattr(sys, "telepy_argv")
                delattr(sys, "telepy_argv")
                sys.path.remove(os.getcwd())
            elif cls.code_mode == CodeMode.PyModule:
                sys.argv = getattr(sys, "telepy_argv")
                delattr(sys, "telepy_argv")
                sys.path.remove(os.getcwd())
            cls.initialized = False


@contextlib.contextmanager
def telepy_env(args: argparse.Namespace, code_mode: CodeMode = CodeMode.PyFile):
    global sampler
    global_dict = Environment.init_telepy_environment(args, code_mode)
    try:
        yield global_dict, sampler
    finally:
        Environment.destory_telepy_enviroment()


# read only, if the sample count is less than this value, telely will print warning info.
_MIN_SAMPLE_COUNT = 50


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

        if fg.sample_count < _MIN_SAMPLE_COUNT:
            logger.log_warning_panel(
                f"Sample count {fg.sample_count} is a little bit low, "
                "you may need to decrease the sampling interval using "
                "--interval {val}."
            )

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
        logger.log_success_panel(
            f"Process {self.pid} saved the profiling data to the svg file {self.args.output}"  # noqa: E501
        )
        if self.args.folded_save:
            self._save_folded(self.args.folded_file)
            logger.log_success_panel(
                f"Process {self.pid} saved the profiling data to the folded file {self.args.folded_file}"  # noqa: E501
            )

    def _single_process_child(self) -> None:
        # filename: pid-ppid.svg pid-ppid.folded
        if not self.args.merge:
            filename = f"{self.pid}-{os.getppid()}.svg"
            self._save_svg(filename)
            if self.args.debug:
                logger.log_success_panel(
                    f"Process {self.pid} saved the profiling data to the svg file {filename}"  # noqa: E501
                )
            if self.args.folded_save:
                filename = f"{self.pid}-{os.getppid()}.folded"
                self._save_folded(filename)
                if self.args.debug:
                    logger.log_success_panel(
                        f"Process {self.pid} saved the profiling data to the folded file {filename}"  # noqa: E501
                    )
        else:
            filename = f"{self.pid}-{os.getppid()}.folded"
            self.lines = self.add_pid_prefix(
                self.lines, f"pid-{self.pid}, ppid-{os.getppid()}"
            )
            self._save_folded(filename)
            if self.args.debug:
                logger.log_success_panel(
                    f"Process {self.pid} saved the profiling data to the folded file {filename}"  # noqa: E501
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
                        logger.log_success_panel(
                            f"Root process {self.pid} read and removed file {file}"
                        )
                    self.lines.extend([line.strip() for line in lines])

            load_chidren_file()
            self._save_svg(self.args.output)
            logger.log_success_panel(
                f"Root process {self.pid} collected the profiling data to svg "
                f"file {self.args.output}"
            )
            if self.args.folded_save:
                self._save_folded(self.args.folded_file)
                logger.log_success_panel(
                    f"Root process {self.pid} collected the profiling data {foldeds} to"
                    f" the folded file {self.args.folded_file}"
                )
        else:
            self._save_svg(self.args.output)
            logger.log_success_panel(
                f"Root process {self.pid} saved the profiling data to"
                f" the svg file {self.args.output}"
            )
            if self.args.folded_save:
                self._save_folded(self.args.folded_file)
                logger.log_success_panel(
                    f"Root process {self.pid} saved the profiling data to"
                    f" the folded file {self.args.folded_file}"
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
                        logger.log_success_panel(
                            f"Process {self.pid} read and removed file {file}"
                        )
                    self.lines.extend([line.strip() for line in lines])

            load_chidren_file()
            filename = f"{self.pid}-{os.getppid()}.folded"
            self._save_folded(filename)
            if self.args.debug:
                logger.log_success_panel(
                    f"Process {self.pid} collected the profiling data {foldeds}"
                    f" to the folded file {filename}"
                )
        else:
            filename = f"{self.pid}-{os.getppid()}.svg"
            self._save_svg(filename)
            if self.args.debug:
                logger.log_success_panel(
                    f"Process {self.pid} saved the profiling data to the svg file {filename}"  # noqa: E501
                )
            if self.args.folded_save:
                filename = f"{self.pid}-{os.getppid()}.folded"
                self._save_folded(filename)
                if self.args.debug:
                    logger.log_success_panel(
                        f"Process {self.pid} saved the profiling data to the folded file {filename}"  # noqa: E501
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
            logger.log_error_panel("Timeout waiting for child processes to complete")


def telepy_finalize() -> None:
    """Stop and clean up the global sampler resource.

    This function should be called to properly finalize the telepy environment
    by stopping the global sampler instance and save the profiling data.
    """
    global sampler
    if not Environment.sampler_created:
        raise RuntimeError("telepy environment is not initialized")
    assert sampler is not None
    assert args is not None
    # forserver mode will not start the sampler.
    if sampler.started:
        sampler.stop()
        _do_save()


def _do_save():
    global args, sampler
    saver = FlameGraphSaver(args, sampler)
    saver.save()
    if args.debug:
        from .logger import console

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
