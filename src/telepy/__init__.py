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
