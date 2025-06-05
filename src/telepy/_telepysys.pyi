# telepysys.pyi

"""
An utility module for telepysys
"""

from threading import Thread
from types import FrameType

__version__: str

def current_frames() -> dict[int, FrameType]: ...

class Sampler:
    def __init__(self) -> None:
        # sampling interval in microseconds
        self.sampling_interval = 10_000  # 10ms
        self.sampling_thread: None | Thread
        self.sampler_life_time: int
        self.acc_sampling_time: int

    def start(self) -> None:
        """start the sampler"""
        ...

    def stop(self) -> None:
        """stop the sampler"""
        ...

    def clear(self) -> None:
        """clear the sampler"""

    def enabled(self) -> bool:
        """check if the sampler is enabled"""
        ...

    def join_sampling_thread(self) -> None:
        """join the sampling thread"""
        ...

    def save(self, path: str) -> None:
        """save the sampled frames to a file"""
        ...

    def dumps(self) -> str:
        """dump the sampled frames to a string"""
        ...
