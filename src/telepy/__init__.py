"""."""

import threading
from types import FrameType

from . import _telepysys  # type: ignore
from ._telepysys import sched_yield, unix_micro_time
from .monitor import TelePyMonitor
from .sampler import TelepySysAsyncSampler, TelepySysAsyncWorkerSampler, TelepySysSampler
from .shell import TelePyShell
from .thread import in_main_thread

__all__: list[str] = [
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


class Profiler(TelepySysAsyncWorkerSampler):
    pass


def profile(
    func=None,
    *,
    sampling_interval: int = 10_000,
    debug: bool = False,
    ignore_frozen: bool = False,
    ignore_self: bool = True,
    tree_mode: bool = False,
    focus_mode: bool = False,
    regex_patterns: list | None = None,
    verbose: bool = True,
    full_path: bool = False,
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
        focus_mode: Whether to focus on user code
        regex_patterns: List of regex patterns for filtering stack traces
        verbose: If True, print progress and completion messages when saving
        full_path: If True, display absolute file paths instead of relative paths
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
        sampler = _FunctionProfiler(
            sampling_interval=sampling_interval,
            debug=debug,
            ignore_frozen=ignore_frozen,
            ignore_self=ignore_self,
            tree_mode=tree_mode,
            focus_mode=focus_mode,
            regex_patterns=regex_patterns,
            verbose=verbose,
            full_path=full_path,
            file=file,
        )

        # Set function name for truncation
        sampler.function_name = f.__name__

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            with sampler:
                result = f(*args, **kwargs)

            if sampler._context_depth == 0:
                if sampler._file:
                    sampler.save(sampler._file, truncate=True, verbose=sampler._verbose)
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


class _FunctionProfiler:
    """
    A sampler wrapper specifically designed for the profile decorator.

    This class wraps TelepySysAsyncWorkerSampler and provides additional
    functionality for saving flame graphs with optional truncation.
    """

    def __init__(self, verbose=True, full_path=False, file=None, **kwargs):
        """Initialize the FunctionProfiler with TelepySysAsyncWorkerSampler."""
        self._sampler = TelepySysAsyncWorkerSampler(**kwargs)
        self._function_name = None
        self._context_depth = 0
        self._verbose = verbose
        self._full_path = full_path
        self._file = file

    def __enter__(self):
        """Context manager entry."""
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
            # Auto-save if file parameter is provided
            if self._file:
                self.save(self._file, truncate=True)
        return False

    def start(self):
        """Start the profiler."""
        self._sampler.start()

    def stop(self):
        """Stop the profiler."""
        self._sampler.stop()

    def save(
        self,
        filename: str,
        truncate: bool = True,
        verbose: bool | None = None,
        full_path: bool | None = None,
    ):
        """
        Save the profiling data as an SVG flame graph.

        Args:
            filename: The output filename for the SVG file
            truncate: If True, only show the function as root node in the flame graph
            verbose: If True, print progress and completion messages.
                    If None, use the decorator's verbose setting
            full_path: If True, display absolute file paths in the flamegraph instead of
                      relative paths and hide site-packages details.
                      If None, use the decorator's full_path setting
        """
        import os
        import site
        import sys

        from .flamegraph import FlameGraph, process_stack_trace

        # Use decorator defaults if not specified
        if verbose is None:
            verbose = self._verbose
        if full_path is None:
            full_path = self._full_path

        if verbose:
            print(f"Saving profiling data to {filename}...")

        # Get the raw profiling data
        content = self._sampler.dumps()
        lines = content.splitlines()  # No more last empty line

        if truncate and self.function_name:
            # Filter lines to only include stacks that contain the target function
            filtered_lines = []
            for line in lines:
                if line.strip():
                    stack_part = line.rsplit(" ", 1)[0]  # Get stack without count
                    if self.function_name in stack_part:
                        # Truncate the stack to start from the target function
                        frames = stack_part.split(";")
                        # Find the first occurrence of our function
                        for i, frame in enumerate(frames):
                            if self.function_name in frame:
                                # Create new stack starting from this function
                                new_stack = ";".join(frames[i:])
                                count = line.rsplit(" ", 1)[1]
                                filtered_lines.append(f"{new_stack} {count}")
                                break
            lines = filtered_lines

        # Get site package path for flame graph configuration
        site_path = site.getsitepackages()[0] if site.getsitepackages() else ""
        work_dir = os.getcwd()

        # Process stack traces (remove site packages info etc.) only if full_path is False
        if not full_path:
            lines = process_stack_trace(lines, site_path, work_dir)

        # Generate flame graph
        fg = FlameGraph(
            lines,
            title=f"TelePy Profiler {self.function_name}",
            command=" ".join([sys.executable, *sys.argv]),
            package_path=os.path.dirname(site_path) if site.getsitepackages() else "",
            work_dir=work_dir,
        )

        fg.parse_input()
        svg_content = fg.generate_svg()

        # Save to file
        with open(filename, "w") as f:
            f.write(svg_content)

        if verbose:
            print(f"Profiling data saved to {filename}")

    @property
    def function_name(self):
        """Get the function name for truncation purposes."""
        return self._function_name

    @function_name.setter
    def function_name(self, name: str):
        """Set the function name for truncation purposes."""
        self._function_name = name
