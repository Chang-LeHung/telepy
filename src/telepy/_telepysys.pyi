# telepysys.pyi

"""
An utility module for telepysys
"""

from collections.abc import Callable
from threading import Thread
from types import FrameType

__version__: str

def current_frames() -> dict[int, FrameType]: ...
def unix_micro_time() -> int: ...
def register_main(callable: Callable, /, *args, **kwargs) -> None:
    """
    register a callable object to be called when the main thread is available
    Raises:
        RuntimeError: if the callable is not callable or failed to register
    """
    ...

def sched_yield() -> None:
    """
    Yield the current thread to other threads.
    Relax to call me, we handle the GIL properly.
    """

class Sampler:
    def __init__(self) -> None:
        # sampling interval in microseconds
        self.sampling_interval = 10_000  # 10ms
        self.sampling_thread: None | Thread
        self.sampler_life_time: int
        self.acc_sampling_time: int
        self.sampling_times: int
        self.debug: bool = False
        self.ignore_frozen: bool = False
        self.ignore_self: bool = False

    def start(self) -> None:
        """start the sampler"""
        ...

    def stop(self) -> None:
        """stop the sampler and join the sampling thread"""
        ...

    def clear(self) -> None:
        """clear the sampler"""
        ...

    def enabled(self) -> bool:
        """check if the sampler is enabled"""
        ...

    def join_sampling_thread(self) -> None:
        """join the sampling thread, you should not call
        this method unless you know what you are doing
        """
        ...

    def save(self, path: str) -> None:
        """save the sampled frames to a file"""
        ...

    def dumps(self) -> str:
        """dump the sampled frames to a string"""
        ...

class AsyncSampler:
    def __init__(self) -> None:
        # sampling interval in microseconds
        self.sampling_interval = 10_000  # 10ms
        self.sampler_life_time: int
        self.acc_sampling_time: int
        self.sampling_times: int
        self.debug: bool = False
        self.ignore_frozen: bool = False
        self.sampling_tid: int
        self.start_time: int
        self.end_time: int
        self.ignore_self: bool = False

    def start(self) -> None:
        """start the sampler"""
        ...

    def stop(self) -> None:
        """stop the sampler"""
        ...

    def clear(self) -> None:
        """clear the sampler, using a async thread to release the resources"""
        ...

    def enabled(self) -> bool:
        """check if the sampler is enabled"""
        ...

    def save(self, path: str) -> None:
        """save the sampled frames to a file"""
        ...

    def dumps(self) -> str:
        """
        dump the sampled frames to a string
        a stack trace per line, last line is empty.
        """
        ...

    def _async_routine(self, sig_num: int, frame: FrameType | None) -> None:
        """async routine"""
        ...
