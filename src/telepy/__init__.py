"""."""

import os as _os
import threading
from types import FrameType

from . import _telepysys  # type: ignore
from ._telepysys import sched_yield, unix_micro_time
from .monitor import TelePyMonitor
from .sampler import TelepySysAsyncSampler, TelepySysAsyncWorkerSampler, TelepySysSampler
from .shell import TelePyShell
from .thread import in_main_thread

__all__: list[str] = [
    "Profiler",
    "TelePyMonitor",
    "TelePyShell",
    "TelepySysAsyncSampler",
    "TelepySysAsyncWorkerSampler",
    "TelepySysSampler",
    "__version__",
    "current_frames",
    "current_stacks",
    "in_main_thread",
    "install_monitor",
    "profile",
    "sched_yield",
    "unix_micro_time",
    "version",
]

__version__: str = _telepysys.__version__
version: str = __version__


def current_frames() -> dict[int, FrameType]:
    """
    Returns:
        A dictionary of thread IDs to frame objects, representing
        the current stack trace for each frame.
    """
    return _telepysys.current_frames()  # pragma: no cover


def current_stacks() -> dict[int, list[str]]:
    """
    Returns:
        A dictionary of thread IDs to lists of strings, representing
        the current stack trace for each frame.
    """
    frames = _telepysys.current_frames()
    res: dict[int, list[str]] = dict()

    for tid, frame in frames.items():
        stack: list[str] = []
        while True:
            co = frame.f_code
            filename = co.co_filename
            lineno = frame.f_lineno
            qualname = co.co_qualname

            stack.append(f"{filename}:{lineno} {qualname}")
            if frame.f_back is None:
                break
            frame = frame.f_back
        res[tid] = stack
    return res


def join_current_stacks(stack_dict: dict[int, list[str]]) -> dict[int, str]:
    """
    Args:
        stack_dict:
            dict of thread id to stack
    Returns:
        dict of thread id to pretty stack
    """
    res: dict[int, str] = {}
    for f_id, stack in stack_dict.items():
        res[f_id] = "\n".join(stack)
    return res


def install_monitor(
    port: int = 8026, host: str = "127.0.0.1", log=True, in_thread: bool = False
) -> TelePyMonitor:
    """
    Install a TelePy monitor to the current process. If you want to shutdown
    the monitor gracefully, call minitor.shutdown() and monitor.close() then.
    Args:
        port (int):
            port to listen on
        host (str):
            host to listen on
        log (bool):
            whether to log
        in_thread (bool):
            whether to run in the current thread
    Returns:
        TelePyMonitor: the monitor instance
        Call monitor.close() to stop the monitor.
    """
    monitor = TelePyMonitor(port, host, log=log)
    if in_thread:
        monitor.run()
    else:
        t = threading.Thread(target=monitor.run)
        t.daemon = True
        t.start()
    return monitor


def profile(
    func=None,
    *,
    sampling_interval: int = 10,
    time: str = "cpu",
    debug: bool = False,
    ignore_frozen: bool = False,
    ignore_self: bool = True,
    tree_mode: bool = False,
    inverted: bool = False,
    focus_mode: bool = False,
    regex_patterns: list | None = None,
    verbose: bool = True,
    full_path: bool = False,
    width: int = 1200,
    file: str | None = None,
):
    """
    A decorator for profiling functions.

    This decorator can be used to profile the execution of functions.
    The decorated function will have a 'sampler' attribute that can be used to
    save profiling data.

    Args:
        sampling_interval: The interval at which the sampler will sample
        debug: Whether to print debug messages
        ignore_frozen: Whether to ignore frozen threads
        ignore_self: Whether to ignore the current thread stack trace data
        tree_mode: Whether to use the tree mode
        time: Select sampling timer source. "cpu" uses SIGPROF/ITIMER_PROF,
            "wall" uses SIGALRM/ITIMER_REAL. Default: "cpu".
        inverted: Render profiling results with root frames at the top
        focus_mode: Whether to focus on user code
        regex_patterns: List of regex patterns for filtering stack traces
        verbose: If True, print progress and completion messages when saving
        full_path: If True, display absolute file paths instead of relative paths
        width: Width in pixels for generated flame graph SVGs.
        file: If provided, automatically save profiling results to this file after
              each function execution

    Usage:
        @profile
        def my_function():
            # function code here
            pass

        # Or with parameters:
        @profile(sampling_interval=5000, verbose=False)
        def my_function():
            # function code here
            pass

        # With automatic file saving:
        @profile(file="my_profile.svg")
        def my_function():
            # function code here
            pass

        # Access the sampler to save SVG
        my_function.sampler.save("output.svg", truncate=True)
    """

    def decorator(f):
        import functools

        # Create the sampler instance
        sampler = Profiler(
            sampling_interval=sampling_interval,
            debug=debug,
            ignore_frozen=ignore_frozen,
            ignore_self=ignore_self,
            tree_mode=tree_mode,
            time=time,
            inverted=inverted,
            focus_mode=focus_mode,
            regex_patterns=regex_patterns,
            verbose=verbose,
            full_path=full_path,
            width=width,
            output=file,
        )

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            with sampler:
                result = f(*args, **kwargs)

            return result

        # Add sampler attribute to the wrapper for external access
        wrapper.sampler = sampler
        return wrapper

    if func is None:
        # Called with parameters: @profile(...)
        return decorator
    else:
        # Called without parameters: @profile
        return decorator(func)


class Profiler:
    """
    A sampler wrapper specifically designed for the profile decorator.

    This class wraps TelepySysAsyncWorkerSampler and provides additional
    functionality for saving flame graphs with optional truncation.
    """

    def __init__(
        self,
        *,
        verbose: bool = True,
        full_path: bool = False,
        inverted: bool = False,
        width: int = 1200,
        sampling_interval: int = 50,
        time: str = "cpu",
        debug: bool = False,
        ignore_frozen: bool = False,
        tree_mode: bool = False,
        focus_mode: bool = False,
        timeout: int = 10,
        output: str = "result.svg",
        folded_saved: bool = False,
        folded_filename: str = "result.folded",
        merge: bool = False,
        ignore_self: bool = True,
        regex_patterns: list | None = None,
    ):
        """Initialize the FunctionProfiler with TelepySysAsyncWorkerSampler.

        Args:
            verbose (bool): Enable verbose output messages during profiling.
            full_path (bool): Display absolute file path in the flamegraph.
            inverted (bool): Render flame graphs with the root frame at the top.
            width (int): SVG width in pixels for generated flamegraphs.
            sampling_interval (int): The interval at which the sampler will sample the
                current stack trace.
            time (str): Timer source selection. "cpu" uses SIGPROF/ITIMER_PROF;
                "wall" uses SIGALRM/ITIMER_REAL.
            debug (bool): Whether to print debug messages.
            ignore_frozen (bool): Whether to ignore frozen threads.
            tree_mode (bool): Whether to use the tree mode.
            focus_mode (bool): Whether to focus on user code by ignoring standard
                library and third-party packages.
            timeout (int): Timeout in seconds for waiting for the subprocess.
            output (str): Output filename for the flame graph.
            folded_saved (bool): Whether to save the folded stack file.
            folded_filename (str): Filename for the folded stack file if saved.
            merge (bool): Whether to merge samples with the same stack trace.
            ignore_self (bool): Whether to ignore telepy stack trace data.
            regex_patterns (list | None): List of regex patterns for filtering stack traces.
        """  # noqa: E501
        if width <= 0:
            raise ValueError("width must be a positive integer")
        from .config import TelePySamplerConfig
        from .environment import CodeMode, telepy_env

        config = TelePySamplerConfig(
            interval=sampling_interval,
            timeout=timeout,
            debug=debug,
            full_path=full_path,
            tree_mode=tree_mode,
            inverted=inverted,
            time=time,
            ignore_frozen=ignore_frozen,
            include_telepy=not ignore_self,
            focus_mode=focus_mode,
            output=output,
            folded_save=folded_saved,
            folded_file=folded_filename,
            merge=merge,
            width=width,
            regex_patterns=regex_patterns,
        )

        self._context_depth = 0
        self._verbose = verbose
        self._full_path = full_path
        self._output = output
        self._inverted = inverted
        self._width = width
        self._folded_saved = folded_saved
        self._folded_filename = folded_filename
        self._sampling_interval = sampling_interval
        self._time = time
        self._debug = debug
        self._ignore_frozen = ignore_frozen
        self._tree_mode = tree_mode
        self._focus_mode = focus_mode
        self._timeout = timeout
        self._merge = merge
        self._ignore_self = ignore_self
        self._regex_patterns = regex_patterns
        self._ctx = telepy_env(config, CodeMode.PyString)
        self._sampler: TelepySysAsyncWorkerSampler | None = None

    def __enter__(self):
        """Context manager entry."""
        if self._sampler is None:
            _, self._sampler = self._ctx.__enter__()
        self._context_depth += 1
        if self._context_depth == 1:
            # Only start the sampler on the first entry and if not already started
            if not self._sampler.started:
                self._sampler.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self._context_depth -= 1
        if self._context_depth == 0:
            # Only stop the sampler when all contexts have exited and if started
            if self._sampler.started:
                self._sampler.stop()
                self._ctx.__exit__(exc_type, exc_val, exc_tb)
                self._finalize()
            # Auto-save if file parameter is provided
            if self._output:
                self.save(self._output, truncate=True)
        return False

    def start(self):
        """Start the profiler."""
        if self._sampler is not None or self._sampler.started:
            raise RuntimeError(
                "Inconsistent state: sampler is already started or not initialized"
            )
        _, self._sampler = self._ctx.__enter__()
        self._sampler.start()

    def stop(self):
        """Stop the profiler."""
        if self._sampler is None or not self._sampler.started:
            raise RuntimeError(
                "Inconsistent state: sampler is not running or not initialized"
            )

        self._sampler.stop()
        self._ctx.__exit__(None, None, None)
        self._finalize()

    def _finalize(self):
        """Finalize the profiler, stopping the sampler and cleaning up."""
        from .environment import telepy_finalize

        telepy_finalize()
        self._sampler = None  # release the memory

    def clean(self):
        """
        Clean up temporary files created during profiling.
        """
        _os.unlink(self._output)
        if self._folded_saved:
            _os.unlink(self._folded_filename)
