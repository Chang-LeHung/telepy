"""."""

from __future__ import annotations

import threading
from enum import Enum
from types import FrameType

from . import _telexsys  # type: ignore
from ._telexsys import sched_yield, unix_micro_time
from .monitor import TeleXMonitor
from .sampler import TelexSysAsyncSampler, TelexSysAsyncWorkerSampler, TelexSysSampler
from .shell import TeleXShell
from .thread import in_main_thread

__all__: list[str] = [
    "Profiler",
    "ProfilerState",
    "TeleXMonitor",
    "TeleXShell",
    "TelexSysAsyncSampler",
    "TelexSysAsyncWorkerSampler",
    "TelexSysSampler",
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

__version__: str = _telexsys.__version__
version: str = __version__


def current_frames() -> dict[int, FrameType]:
    """
    Returns:
        A dictionary of thread IDs to frame objects, representing
        the current stack trace for each frame.
    """
    return _telexsys.current_frames()  # pragma: no cover


def current_stacks() -> dict[int, list[str]]:
    """
    Returns:
        A dictionary of thread IDs to lists of strings, representing
        the current stack trace for each frame.
    """
    frames = _telexsys.current_frames()
    res: dict[int, list[str]] = dict()

    for tid, frame in frames.items():
        stack: list[str] = []
        while True:
            co = frame.f_code
            filename = co.co_filename
            lineno = frame.f_lineno
            # co_qualname was added in Python 3.11
            qualname = getattr(co, "co_qualname", co.co_name)

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
) -> TeleXMonitor:
    """
    Install a TeleX monitor to the current process. If you want to shutdown
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
        TeleXMonitor: the monitor instance
        Call monitor.close() to stop the monitor.
    """
    monitor = TeleXMonitor(port, host, log=log)
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
    sampling_interval: int = 2_000,
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
    file: str = "result.svg",
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
        file: Output filename for the flame graph. Default is "result.svg".

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
    """

    def decorator(f):
        import functools

        # Create the sampler instance
        # Use default "result.svg" if file is not specified
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


class ProfilerState(Enum):
    """Enumeration of profiler states for state machine management.

    State transitions:
        UNINITIALIZED -> INITIALIZED (via __init__)
        INITIALIZED -> STARTED (via start())
        STARTED -> PAUSED (via pause())
        PAUSED -> STARTED (via resume())
        STARTED -> STOPPED (via stop())
        STOPPED -> STARTED (via start() - restart)
        STARTED -> FINISHED (via finish() or __exit__)
        PAUSED -> FINISHED (via finish())
    """

    UNINITIALIZED = "uninitialized"  # Before __init__ completes
    INITIALIZED = "initialized"  # After __init__, ready to start
    STARTED = "started"  # Profiler is actively sampling
    PAUSED = "paused"  # Profiler is paused, can resume
    STOPPED = "stopped"  # Profiler stopped, can restart
    FINISHED = "finished"  # Terminal state, profiler completed


class Profiler:
    """
    A sampler wrapper specifically designed for the profile decorator.

    This class wraps TelexSysAsyncWorkerSampler and provides additional
    functionality for saving flame graphs with optional truncation.

    The profiler uses a state machine with the following states:
        - UNINITIALIZED: Before initialization
        - INITIALIZED: Ready to start profiling
        - STARTED: Actively profiling
        - PAUSED: Profiling paused, can be resumed
        - STOPPED: Profiling stopped, can be restarted

    Example:
        >>> profiler = Profiler()  # INITIALIZED
        >>> profiler.start()       # STARTED
        >>> profiler.pause()       # PAUSED
        >>> profiler.resume()      # STARTED
        >>> profiler.stop()        # STOPPED
        >>> profiler.start()       # STARTED (restart)
    """

    def __init__(
        self,
        *,
        verbose: bool = True,
        full_path: bool = False,
        inverted: bool = False,
        width: int = 1200,
        sampling_interval: int = 8_000,
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
        """Initialize the FunctionProfiler with TelexSysAsyncWorkerSampler.

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
            ignore_self (bool): Whether to ignore telex stack trace data.
            regex_patterns (list | None): List of regex patterns for filtering stack traces.
        """  # noqa: E501
        if width <= 0:
            raise ValueError("width must be a positive integer")
        from .config import TeleXSamplerConfig

        # State machine initialization
        self._state = ProfilerState.UNINITIALIZED
        self._state_lock = threading.Lock()

        config = TeleXSamplerConfig(
            interval=sampling_interval,
            timeout=timeout,
            debug=debug,
            full_path=full_path,
            tree_mode=tree_mode,
            inverted=inverted,
            time=time,
            ignore_frozen=ignore_frozen,
            include_telex=not ignore_self,
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
        self._config = config

        # Don't create context yet - defer until first use
        # This prevents Environment singleton conflicts in tests
        self._ctx = None
        self._sampler: TelexSysAsyncWorkerSampler | None = None

        # Mark as initialized
        self._state = ProfilerState.INITIALIZED

    @property
    def state(self) -> ProfilerState:
        """Get the current state of the profiler."""
        with self._state_lock:
            return self._state

    def _transition_to(self, new_state: ProfilerState) -> None:
        """Transition to a new state with validation.

        Valid state transitions:
            INITIALIZED -> STARTED
            STARTED -> PAUSED
            STARTED -> STOPPED
            PAUSED -> STARTED
            PAUSED -> STOPPED
            STOPPED -> STARTED

        Args:
            new_state: The target state to transition to.

        Raises:
            RuntimeError: If the current state doesn't allow this transition.
        """
        # Define valid state transitions
        valid_transitions = {
            ProfilerState.INITIALIZED: [ProfilerState.STARTED],
            ProfilerState.STARTED: [
                ProfilerState.PAUSED,
                ProfilerState.FINISHED,
            ],
            ProfilerState.PAUSED: [
                ProfilerState.STARTED,
                ProfilerState.FINISHED,
            ],
            ProfilerState.STOPPED: [],  # Deprecated, use FINISHED
            ProfilerState.FINISHED: [],  # Terminal state
        }

        with self._state_lock:
            allowed_states = valid_transitions.get(self._state, [])
            if new_state not in allowed_states:
                raise RuntimeError(
                    f"Cannot transition to {new_state.value} from "
                    f"{self._state.value}. "
                    f"Allowed transitions: {[s.value for s in allowed_states]}"
                )
            self._state = new_state

    def __enter__(self):
        """Context manager entry."""
        self._context_depth += 1
        if self._context_depth == 1:
            # Create context on first use if not already created
            if self._ctx is None:
                from .environment import CodeMode, telex_env

                self._ctx = telex_env(self._config, CodeMode.PyString)

            # Initialize sampler from context if not already done
            if self._sampler is None:
                _, self._sampler = self._ctx.__enter__()

            # Only start the sampler on the first entry
            if self.state in (ProfilerState.INITIALIZED, ProfilerState.STOPPED):
                if self._sampler is not None:
                    self._transition_to(ProfilerState.STARTED)
                    self._sampler.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self._context_depth -= 1
        if self._context_depth == 0:
            # Stop the profiler when all contexts have exited
            if self.state in (ProfilerState.STARTED, ProfilerState.PAUSED):
                self.stop()
        return False

    def start(self):
        """Start the profiler.

        Valid transitions:
            INITIALIZED -> STARTED (first start)
            STOPPED -> STARTED (restart)

        Raises:
            RuntimeError: If called from an invalid state.
        """
        from .environment import CodeMode, telex_env

        self._transition_to(ProfilerState.STARTED)

        # Initialize sampler if needed
        if self._sampler is None:
            # Use existing context if available, otherwise create new one
            if self._ctx is None:
                self._ctx = telex_env(self._config, CodeMode.PyString)
            _, self._sampler = self._ctx.__enter__()

        self._sampler.start()

    def stop(self):
        """Stop the profiler completely (terminal state).

        This method stops profiling and transitions to FINISHED state.
        The profiler cannot be restarted after calling stop().

        Valid transitions:
            STARTED -> FINISHED
            PAUSED -> FINISHED

        Raises:
            RuntimeError: If called from an invalid state.
        """
        self._transition_to(ProfilerState.FINISHED)

        if self._sampler is not None:
            # Don't stop sampler here - let telex_finalize handle it
            # This ensures sampler.started is still True when _do_save() runs
            self._finalize()
            if self._ctx is not None:
                self._ctx.__exit__(None, None, None)
                self._ctx = None

    def pause(self):
        """Pause the profiler.

        Valid transitions:
            STARTED -> PAUSED

        Raises:
            RuntimeError: If called from an invalid state.
        """
        self._transition_to(ProfilerState.PAUSED)

        if self._sampler is not None:
            self._sampler.stop()

    def resume(self):
        """Resume the profiler from paused state.

        Valid transitions:
            PAUSED -> STARTED

        Raises:
            RuntimeError: If called from an invalid state.
        """
        self._transition_to(ProfilerState.STARTED)

        if self._sampler is not None:
            self._sampler.start()

    def _finalize(self):
        """Finalize the profiler, stopping the sampler and cleaning up."""
        from .environment import telex_finalize

        # Call telex_finalize to clean up environment
        telex_finalize()

        # Clean up internal state
        if self._sampler is not None:
            self._sampler = None
        if self._ctx is not None:
            self._ctx = None
