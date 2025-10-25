from __future__ import annotations

import contextlib
import enum
import functools
import os
import platform
import site
import sys
import threading
import time
import types
from multiprocessing import util
from typing import Any, Final, Union

from rich.table import Table

from . import logger
from ._telexsys import sched_yield
from .config import TeleXSamplerConfig
from .flamegraph import FlameGraph, process_stack_trace
from .sampler import (
    PyTorchProfilerMiddleware,
    TelexSysAsyncWorkerSampler,
    TelexSysSampler,
)

# Detect platform
IS_WINDOWS = sys.platform == "win32" or platform.system() == "Windows"

# Type alias for the sampler that can be either type based on platform
SamplerType = Union[TelexSysAsyncWorkerSampler, TelexSysSampler]  # noqa

# String constants
CMD_SEPARATOR: Final = "--"

MODULE_MAIN: Final = "__main__"
MODULE_TELEX_MAIN: Final = "__telex_main__"
MODULE_FILE: Final = "__file__"
MODULE_BUILTINS: Final = "__builtins__"

ERROR_SAMPLER_EXISTS: Final = "A sampler instance already exists in this process"
ERROR_ENV_INITIALIZED: Final = "telex environment has been initialized."
ERROR_ENV_NOT_INITIALIZED: Final = "telex environment is not initialized"
ERROR_INVALID_CODE_MODE: Final = "telex: invalid code mode"

MESSAGE_FORKSERVER_NO_MERGE: Final = (
    "Because you are using the multiprocessing module with "
    "the forkserver mode, we will not merge the flamegraphs."
)

TITLE: Final = "TeleX Flame Graph"
TITLE_SAMPLER_METRICS: Final = "TeleXSampler Metrics"

INTERNAL_ARGV: Final = "telex_argv"


def patch_os_fork_in_child():
    sampler = Environment.get_sampler()
    args = Environment.get_args()
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

    if sampler.forkserver:  # pragma: no cover
        sampler.start()
        sampler.forkserver = False


def patch_os_fork_in_parent():
    sampler = Environment.get_sampler()
    args = Environment.get_args()
    assert sampler is not None
    assert args is not None
    sampler.child_cnt += 1


def patch_before_fork():
    sampler = Environment.get_sampler()
    args = Environment.get_args()
    assert sampler is not None
    assert args is not None


def get_child_process_args() -> list[str]:
    args = Environment.get_args()
    assert args is not None
    return args.to_cli_args()


def patch_multiprocesssing():
    """
    Patches the multiprocessing spawn mechanism to inject telex code to profile.
    """
    args = Environment.get_args()
    sampler = Environment.get_sampler()
    assert sampler is not None
    assert args is not None

    parser_args = args
    _spawnv_passfds = Environment._spawnv_passfds

    @functools.wraps(_spawnv_passfds)
    def spawnv_passfds(path, args, passfds):
        if "-c" in args:
            idx = args.index("-c")
            cmd = args[idx + 1]

            if "forkserver" in cmd:
                # forkserver mode, we need to inject telex code to profile.
                # we do not launch telex in the server process, but we will
                # hack the fork syscall to sample its child processes.
                new_args = [
                    *args[:idx],
                    "-m",
                    "telex",
                    "--fork-server",
                    "--no-merge",
                    *get_child_process_args(),
                    *args[idx : idx + 2],
                ]
                if parser_args.verbose:
                    logger.log_warning_panel(MESSAGE_FORKSERVER_NO_MERGE)
                rest = args[idx + 2 :]
                if rest:  # pragma: no cover
                    new_args += [CMD_SEPARATOR, *rest]
                args = new_args
            elif "resource_tracker" not in cmd:
                # spawn mode
                new_args = [
                    *args[:idx],
                    "-m",
                    "telex",
                    "--mp",
                    *get_child_process_args(),
                    *args[idx : idx + 2],
                ]
                rest = args[idx + 2 :]
                if rest:
                    new_args += [CMD_SEPARATOR, *rest]
                args = new_args
                sampler.child_cnt += 1
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
    _lock = threading.RLock()
    _sys_exit = sys.exit
    _os_exit = os._exit
    _spawnv_passfds = util.spawnv_passfds

    # Class attributes to store singleton instances
    _sampler: None | SamplerType = None
    _args: None | TeleXSamplerConfig = None

    def __new__(cls):
        """Prevent instantiation of Environment class."""
        raise TypeError(
            "Environment class cannot be instantiated. Use its class methods directly."
        )

    @classmethod
    def get_sampler(cls) -> None | SamplerType:
        """Get the singleton sampler instance."""
        return cls._sampler

    @classmethod
    def set_sampler(cls, sampler: SamplerType) -> None:
        """Set the singleton sampler instance."""
        if cls._sampler is not None:  # pragma: no cover
            raise RuntimeError(ERROR_SAMPLER_EXISTS)
        cls._sampler = sampler

    @classmethod
    def get_args(cls) -> None | TeleXSamplerConfig:
        """Get the singleton args instance."""
        return cls._args

    @classmethod
    def set_args(cls, args: TeleXSamplerConfig) -> None:
        """Set the singleton args instance."""
        cls._args = args

    @classmethod
    def clear_instances(cls) -> None:
        """Clear the singleton instances."""
        with cls._lock:
            cls._sampler = None
            cls._args = None
            cls.initialized = False

    @classmethod
    def _create_sampler(cls, config: TeleXSamplerConfig) -> SamplerType:
        """
        Create and configure a sampler instance based on the platform.

        On Windows, creates a TelexSysSampler (main thread only).
        On Unix platforms, creates a TelexSysAsyncWorkerSampler (worker thread).

        Args:
            config (TeleXSamplerConfig): The configuration for the sampler.

        Returns:
            SamplerType: A configured sampler instance appropriate for the platform.
        """
        # Declare sampler with explicit type annotation
        sampler: SamplerType

        if IS_WINDOWS:  # pragma: no cover
            # Windows: Use main thread sampler
            sampler = TelexSysSampler(
                config.interval,
                debug=config.debug,
                ignore_frozen=config.ignore_frozen,
                ignore_self=not config.include_telex,
                tree_mode=config.tree_mode,
                focus_mode=config.focus_mode,
                regex_patterns=config.regex_patterns,
                is_root=not (config.fork_server or config.mp),
                forkserver=config.fork_server,
                from_mp=config.mp,
                time_mode=config.time,  # Accept for consistency
            )
            sampler.adjust()
        else:
            # Unix: Use worker thread sampler
            sampler = TelexSysAsyncWorkerSampler(
                config.interval,
                debug=config.debug,
                ignore_frozen=config.ignore_frozen,
                ignore_self=not config.include_telex,
                tree_mode=config.tree_mode,
                focus_mode=config.focus_mode,
                regex_patterns=config.regex_patterns,
                is_root=not (config.fork_server or config.mp),
                forkserver=config.fork_server,
                from_mp=config.mp,
                time_mode=config.time,
            )
            sampler.adjust()

        # Register PyTorch profiler middleware if enabled
        if config.torch_profile:
            try:
                torch_middleware = PyTorchProfilerMiddleware(
                    output_dir=config.torch_output_dir,
                    activities=config.torch_activities,
                    record_shapes=config.torch_record_shapes,
                    profile_memory=config.torch_profile_memory,
                    with_stack=config.torch_with_stack,
                    export_chrome_trace=config.torch_export_chrome_trace,
                    sort_by=config.torch_sort_by,
                    row_limit=config.torch_row_limit,
                    verbose=config.verbose,
                )
                sampler.register_middleware(torch_middleware)
                if config.verbose:
                    logger.log_success_panel(
                        "PyTorch profiler middleware registered successfully"
                    )
            except ImportError:  # pragma: no cover
                if config.verbose:
                    logger.log_warning_panel(
                        "PyTorch not available. PyTorch profiler will be disabled."
                    )

        return sampler

    @classmethod
    def patch_sys_exit(cls, *_args, **kwargs):  # pragma: no cover
        """
        `telex_finalize` will not be called when the process exits. We need to stop the
        sampler and save the data.
        """
        sampler = cls.get_sampler()
        args = cls.get_args()
        if sampler is not None and sampler.started:
            if args.verbose:
                logger.log_success_panel(
                    f"Process {os.getpid()} exited early via sys.exit(), "
                    "telex saved profiling data and terminated. "
                    "(You might be using the multiprocessing module)"
                )
            # forserver mode will not start the sampler.
            if sampler.started:
                sampler.stop()
                _do_save()
        cls._sys_exit(*_args, **kwargs)

    @classmethod
    def patch_os__exit(cls, *_args, **kwargs):  # pragma: no cover
        """
        `telex_finalize` will not be called when the process exits. We need to stop the
        sampler and save the data.
        """
        sampler = cls.get_sampler()
        args = cls.get_args()
        if sampler is not None and sampler.started:
            if args.verbose:
                logger.log_success_panel(
                    f"Process {os.getpid()} exited early via os._exit(), "
                    "telex saved profiling data and terminated."
                    "(You might be using the multiprocessing module)"
                )
            # forserver mode will not start the sampler.
            if sampler.started:
                sampler.stop()
                _do_save()
        cls._os_exit(*_args, **kwargs)

    @classmethod
    def init_telex_environment(
        cls, config: TeleXSamplerConfig, mode: CodeMode = CodeMode.PyFile
    ) -> dict[str, Any]:
        """
        Initialize telex environment from TeleXSamplerConfig.

        Args:
            config (TeleXSamplerConfig): The configuration for the process.
            mode (CodeMode): The code execution mode.
        """
        cls.code_mode = mode
        with cls._lock:
            if cls.initialized:
                raise RuntimeError(ERROR_ENV_INITIALIZED)

            # Set the config
            cls.set_args(config)

            # Create and set the sampler
            sampler = cls._create_sampler(config)
            cls.set_sampler(sampler)

            sys.exit = cls.patch_sys_exit
            os._exit = cls.patch_os__exit
            if not cls.sampler_created:
                # os.register_at_fork is not available on Windows
                if hasattr(os, "register_at_fork"):
                    os.register_at_fork(
                        before=patch_before_fork,
                        after_in_child=patch_os_fork_in_child,
                        after_in_parent=patch_os_fork_in_parent,
                    )
                patch_multiprocesssing()
            cls.sampler_created = True
            cls.initialized = True
            if mode == CodeMode.PyFile:
                main_mod = types.ModuleType(MODULE_MAIN)
                # For PyFile mode, we need the input file name from config
                if config.input and len(config.input) > 0:
                    setattr(main_mod, MODULE_FILE, os.path.abspath(config.input[0].name))
                    file_name = config.input[0].name
                else:  # pragma: no cover
                    setattr(main_mod, MODULE_FILE, "<unknown>")
                    file_name = "<unknown>"
                setattr(main_mod, MODULE_BUILTINS, globals()[MODULE_BUILTINS])
                sys.modules[MODULE_TELEX_MAIN] = sys.modules[MODULE_MAIN]
                sys.modules[MODULE_MAIN] = main_mod
                old_arg = sys.argv
                setattr(sys, INTERNAL_ARGV, old_arg)
                if CMD_SEPARATOR in old_arg:
                    idx = old_arg.index(CMD_SEPARATOR)
                    sys.argv = [file_name, *old_arg[idx + 1 :]]
                else:
                    sys.argv = [file_name]
                sys.path.append(os.getcwd())
                return main_mod.__dict__
            elif mode == CodeMode.PyString:
                string_mod = types.ModuleType(MODULE_MAIN)
                setattr(string_mod, MODULE_FILE, "<string>")
                setattr(string_mod, MODULE_BUILTINS, globals()[MODULE_BUILTINS])
                sys.modules[MODULE_TELEX_MAIN] = sys.modules[MODULE_MAIN]
                sys.modules[MODULE_MAIN] = string_mod
                old_arg = sys.argv
                setattr(sys, INTERNAL_ARGV, old_arg)
                if CMD_SEPARATOR in old_arg:
                    idx = old_arg.index(CMD_SEPARATOR)
                    sys.argv = ["-c", *old_arg[idx + 1 :]]
                else:
                    sys.argv = ["-c"]
                sys.path.append(os.getcwd())
                return string_mod.__dict__
            elif mode == CodeMode.PyModule:
                old_arg = sys.argv
                setattr(sys, INTERNAL_ARGV, old_arg)
                if CMD_SEPARATOR in old_arg:
                    idx = old_arg.index(CMD_SEPARATOR)
                    sys.argv = [old_arg[0], *old_arg[idx + 1 :]]
                else:
                    sys.argv = [old_arg[0]]
                sys.path.append(os.getcwd())
                return {}
            raise RuntimeError(ERROR_INVALID_CODE_MODE)  # pragma: no cover

    @classmethod
    def destory_telex_enviroment(cls):
        """
        Cleans up and restores the environment set up by Telex.

        This method reverses the changes made during the initialization of the Telex environment.
        It restores the original `sys.exit` and `os._exit` functions, resets `sys.modules` and `sys.argv`
        if code was executed in file or string mode, and removes the current working directory from `sys.path`.
        It also marks the environment as uninitialized.

        Returns:
            None
        """  # noqa: E501
        with cls._lock:
            if not cls.initialized:
                return
            sys.exit = cls._sys_exit
            os._exit = cls._os_exit
            util.spawnv_passfds = cls._spawnv_passfds
            if cls.code_mode in (CodeMode.PyFile, CodeMode.PyString):
                sys.modules[MODULE_MAIN] = sys.modules[MODULE_TELEX_MAIN]
                del sys.modules[MODULE_TELEX_MAIN]
                sys.argv = getattr(sys, INTERNAL_ARGV)
                delattr(sys, INTERNAL_ARGV)
                sys.path.remove(os.getcwd())
            elif cls.code_mode == CodeMode.PyModule:
                sys.argv = getattr(sys, INTERNAL_ARGV)
                delattr(sys, INTERNAL_ARGV)
                sys.path.remove(os.getcwd())
            cls.initialized = False


@contextlib.contextmanager
def telex_env(config: TeleXSamplerConfig, code_mode: CodeMode = CodeMode.PyFile):
    """
    Context manager that prepares the TeleX environment for sampling and restores it afterwards.

    Args:
        config (TeleXSamplerConfig): The configuration object used to bootstrap TeleX.
        code_mode (CodeMode, optional): Execution mode for the profiled code. Defaults to ``CodeMode.PyFile``.

    Yields:
        Tuple[dict, Any]: The prepared globals dictionary and the active sampler instance.

    Raises:
        Any exception that occurs while initializing the environment.

    Notes:
        After the context exits, the process-wide hooks are reverted but the singleton sampler state
        remains. Explicitly call `Environment.clear_instances` (or the helper `clear_resources`)
        when you no longer need the sampler to fully release TeleX resources.
    """  # noqa: E501
    global_dict = Environment.init_telex_environment(config, code_mode)
    current_sampler = Environment.get_sampler()
    try:
        yield global_dict, current_sampler
    except Exception:
        telex_finalize()
        raise
    finally:
        Environment.destory_telex_enviroment()


# read only, if the sample count is less than this value, telely will print warning info.
_MIN_SAMPLE_COUNT = 50


class FlameGraphSaver:
    def __init__(
        self,
        sampler: SamplerType,
        *,
        full_path: bool = False,
        inverted: bool = False,
        width: int = 1200,
        output: str = "result.svg",
        verbose: bool = False,
        folded_save: bool = False,
        folded_file: str = "result.folded",
        merge: bool = True,
        debug: bool = False,
        timeout: float = 10,
    ) -> None:
        self.sampler = sampler
        self.full_path = full_path
        self.inverted = inverted
        self.width = width
        self.output = output
        self.verbose = verbose
        self.folded_save = folded_save
        self.folded_file = folded_file
        self.merge = merge
        self.debug = debug
        self.timeout_limit = timeout
        self.site_path = site.getsitepackages()[0]
        self.work_dir = os.getcwd()
        self.title = TITLE
        self.lines = sampler.dumps().splitlines()  # no more last empty line
        if not self.full_path:
            self.lines = process_stack_trace(self.lines, self.site_path, self.work_dir)

        self.timeout = False
        self.pid = os.getpid()

    def _save_svg(self, filename: str) -> None:
        fg = FlameGraph(
            self.lines,
            title=TITLE,
            command=" ".join([sys.executable, *sys.argv]),
            package_path=os.path.dirname(self.site_path),
            work_dir=self.work_dir,
            inverted=self.inverted,
            width=self.width,
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
        self._save_svg(self.output)
        if self.verbose:
            logger.log_success_panel(
                f"Process {self.pid} saved the profiling data to the svg file {self.output}"  # noqa: E501
            )
        if self.folded_save:
            self._save_folded(self.folded_file)
            if self.verbose:
                logger.log_success_panel(
                    f"Process {self.pid} saved the profiling data to the folded file {self.folded_file}"  # noqa: E501
                )

    def _single_process_child(self) -> None:
        # filename: pid-ppid.svg pid-ppid.folded
        if not self.merge:
            filename = f"{self.pid}-{os.getppid()}.svg"
            self._save_svg(filename)
            if self.debug:
                logger.log_success_panel(
                    f"Process {self.pid} saved the profiling data to the svg file {filename}"  # noqa: E501
                )
            if self.folded_save:
                filename = f"{self.pid}-{os.getppid()}.folded"
                self._save_folded(filename)
                if self.debug:
                    logger.log_success_panel(
                        f"Process {self.pid} saved the profiling data to the folded file {filename}"  # noqa: E501
                    )
        else:
            filename = f"{self.pid}-{os.getppid()}.folded"
            self.lines = self.add_pid_prefix(
                self.lines, f"pid-{self.pid}, ppid-{os.getppid()}"
            )
            self._save_folded(filename)
            if self.debug:
                logger.log_success_panel(
                    f"Process {self.pid} saved the profiling data to the folded file {filename}"  # noqa: E501
                )

    def _multi_process_root(self) -> None:
        if self.merge:
            files = os.listdir(os.getcwd())
            foldeds = [file for file in files if file.endswith(f"{self.pid}.folded")]

            self.lines = self.add_pid_prefix(self.lines, f"root, pid={self.pid}")

            def load_chidren_file():
                for file in foldeds:
                    with open(file, "r+") as fp:
                        lines = fp.readlines()
                    os.unlink(file)
                    if self.debug:
                        logger.log_success_panel(
                            f"Root process {self.pid} read and removed file {file}"
                        )
                    self.lines.extend([line.strip() for line in lines])

            load_chidren_file()
            self._save_svg(self.output)
            if self.verbose:
                logger.log_success_panel(
                    f"Root process {self.pid} collected the profiling data to svg "
                    f"file {self.output}"
                )
            if self.folded_save:
                self._save_folded(self.folded_file)
                if self.verbose:
                    logger.log_success_panel(
                        f"Root process {self.pid} collected the profiling data "
                        f"{foldeds} to the folded file {self.folded_file}"
                    )
        else:
            self._save_svg(self.output)
            if self.verbose:
                logger.log_success_panel(
                    f"Root process {self.pid} saved the profiling data to"
                    f" the svg file {self.output}"
                )
            if self.folded_save:
                self._save_folded(self.folded_file)
                if self.verbose:
                    logger.log_success_panel(
                        f"Root process {self.pid} saved the profiling data to"
                        f" the folded file {self.folded_file}"
                    )

    def _multi_process_child(self) -> None:
        if self.merge:
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
                    if self.debug:
                        logger.log_success_panel(
                            f"Process {self.pid} read and removed file {file}"
                        )
                    self.lines.extend([line.strip() for line in lines])

            load_chidren_file()
            filename = f"{self.pid}-{os.getppid()}.folded"
            self._save_folded(filename)
            if self.debug:
                logger.log_success_panel(
                    f"Process {self.pid} collected the profiling data {foldeds}"
                    f" to the folded file {filename}"
                )
        else:
            filename = f"{self.pid}-{os.getppid()}.svg"
            self._save_svg(filename)
            if self.debug:
                logger.log_success_panel(
                    f"Process {self.pid} saved the profiling data to the svg file {filename}"  # noqa: E501
                )
            if self.folded_save:
                filename = f"{self.pid}-{os.getppid()}.folded"
                self._save_folded(filename)
                if self.debug:
                    logger.log_success_panel(
                        f"Process {self.pid} saved the profiling data to the folded file {filename}"  # noqa: E501
                    )

    def save(self) -> None:
        if self.sampler.child_cnt > 0:
            self.wait_children()
            if self.sampler.is_root:
                self._multi_process_root()
            else:
                self._multi_process_child()  # pragma: no cover
        else:
            if self.sampler.is_root:
                self._single_process_root()
            else:
                self._single_process_child()

    def wait_children(self) -> None:
        """Wait for all child processes to exit."""
        if not self.merge:
            return
        res: list[str] = []
        begin = time.time()
        if self.debug:
            logger.log_success_panel(
                f"Process {self.pid} are waiting for {self.sampler.child_cnt} "
                "child processes to complete"
            )
        while len(res) != self.sampler.child_cnt:
            sched_yield()
            files = os.listdir(os.getcwd())
            res = [file for file in files if file.endswith(f"{self.pid}.folded")]
            if time.time() - begin > self.timeout_limit:  # pragma: no cover
                self.timeout = True
                break
        if self.timeout:  # pragma: no cover
            logger.log_error_panel("Timeout waiting for child processes to complete")


def clear_resources():
    """
    Clears all resource instances managed by the Environment.

    This function calls the `clear_instances` method of the `Environment` class,
    removing all currently stored or active resource instances. Use this to reset
    the environment state and release any held resources.

    This function should be called to reset the environment and free up any resources
    if you do not want to call `telex_finalize`.
    """
    Environment.clear_instances()


def telex_finalize(save: bool = True) -> None:
    """Stop and clean up the global sampler resource.

    This function should be called to properly finalize the telex environment
    by stopping the global sampler instance and save the profiling data.
    """
    if not Environment.sampler_created:
        raise RuntimeError(ERROR_ENV_NOT_INITIALIZED)

    current_sampler = Environment.get_sampler()

    # forserver mode will not start the sampler.
    if current_sampler is not None and current_sampler.started:
        current_sampler.stop()
        if save:
            _do_save()
    Environment.clear_instances()


def _do_save():
    current_args = Environment.get_args()
    current_sampler = Environment.get_sampler()
    assert current_args is not None
    assert current_sampler is not None
    saver = FlameGraphSaver(
        current_sampler,
        full_path=current_args.full_path,
        inverted=current_args.inverted,
        width=current_args.width,
        output=current_args.output,
        verbose=current_args.verbose,
        folded_save=current_args.folded_save,
        folded_file=current_args.folded_file,
        merge=current_args.merge,
        debug=current_args.debug,
        timeout=current_args.timeout,
    )
    saver.save()
    if current_args.debug:
        from .logger import console

        acc = current_sampler.acc_sampling_time
        start = current_sampler.start_time
        end = current_sampler.end_time
        title = TITLE_SAMPLER_METRICS
        if (
            current_sampler.child_cnt > 0 and current_sampler.from_fork
        ):  # pragma: no cover
            title += (
                f" pid = {os.getpid()} (with {current_sampler.child_cnt} "
                f"child process(es)) ppid = {os.getppid()}"
            )
        elif current_sampler.child_cnt > 0:
            title += (
                f" pid = {os.getpid()} (with {current_sampler.child_cnt} "
                f"child process(es))"
            )
        elif current_sampler.from_fork or current_sampler.from_mp:
            title += f" pid = {os.getpid()} ppid = {os.getppid()}"

        table = Table(title=title, expand=True)

        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", style="green")

        table.add_row("Accumulated Sampling Time (Monotonic Mircoseconds)", f"{acc}")
        table.add_row(
            "Sampling Time Rate (Versus Program Time)", f"{acc / (end - start):.2%}"
        )
        table.add_row("TeleX Sampler Start Time (Monotonic Mircoseconds)", f"{start}")
        table.add_row("TeleX Sampler End Time (Monotonic Mircoseconds)", f"{end}")
        table.add_row("Sampling Count", str(current_sampler.sampling_times))

        console.print(table)
