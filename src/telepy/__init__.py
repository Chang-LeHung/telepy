"""."""

import sys
from types import FrameType
from typing import override

from . import _telepysys  # type: ignore

__all__: list[str] = [
    "TelepySysSampler",
    "__version__",
    "current_frames",
    "current_stacks",
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


class TelepySysSampler(_telepysys.Sampler):
    """
    Inherited sampler for TelepySys.
    """

    def __init__(
        self,
        sampling_interval: int = 10_000,
        debug: bool = False,
        ignore_frozen: bool = False,
    ) -> None:
        """
        Args:
            sampling_interval:
                The interval at which the sampler will sample the current stack trace.
            debug:
                Whether to print debug messages.
            ignore_frozen:
                Whether to ignore frozen threads.
        """
        super().__init__()
        self.sampling_interval = sampling_interval
        self.debug = debug
        self.ignore_frozen = ignore_frozen

    def adjust_interval(self) -> bool:
        """
        Adjusts sys's interval to match TelepySys's interval.
        Returns:
            bool: True if sys's interval adjusted, False otherwise
        """
        interval = self.sampling_interval / 1000_000
        sys_interval = sys.getswitchinterval()
        if interval < sys_interval * 4:
            sys.setswitchinterval(interval / 4)
            return True
        return False

    @property
    def sampling_time_rate(self):
        """
        sampling time rate
        """
        return self.acc_sampling_time / self.sampler_life_time

    @override
    def save(self, filename: str) -> None:
        """
        Save the sampler data to a file.
        """
        content = self.dumps()
        with open(filename, "w") as f:
            f.write(content[:-1])  #   remove the last new line

    @property
    def stared(self):
        """
        Return True if the sampler is started.
        """
        return self.enabled
