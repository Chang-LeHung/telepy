import signal
import sys
import threading
from collections.abc import Callable
from types import FrameType
from typing import Any, override

from . import _telepysys


class TelepySysSampler(_telepysys.Sampler):
    """
    A sampler that uses the TelepySys library to sample the current stack.
    """

    def __init__(
        self,
        sampling_interval: int = 10000,
        debug: bool = False,
        ignore_frozen: bool = False,
    ):
        """
        Parameters:
            sampling_interval: int = 10000
                The interval between samples in microseconds.
                Defaults to 10ms.
            debug: bool = False
                Whether to enable debug mode.
            ignore_frozen: bool = False
                Whether to ignore frozen frames.
        """
        super().__init__()
        self.sampling_interval = sampling_interval
        self.debug = debug
        self.ignore_frozen = ignore_frozen

    @property
    def started(self):
        return self.enabled()

    @override
    def save(self, path: str) -> None:
        with open(path, "w") as f:
            f.write(self.dumps())

    @override
    def dumps(self) -> str:
        return super().dumps()[:-1]  # remove the last newline

    def adjust_interval(self):
        """
        Adjust the sampling interval to the system's switch interval.
        Returns:
            bool: True if the interval is adjusted, False otherwise.
        """
        sys_interval = sys.getswitchinterval()
        interval = self.sampling_interval * 1e-6
        if sys_interval * 4 > interval:
            sys.setswitchinterval(interval / 4)
            return True
        return False

    @property
    def sampling_time_rate(self):
        if not self.started:
            return self.acc_sampling_time / self.sampler_life_time
        raise RuntimeError("Sampler is not is running")


class TelepySysAsyncSampler(_telepysys.AsyncSampler):
    """
    TelepySysAsyncSampler is used to profile the system asynchronously.
    """

    def __init__(
        self,
        sampling_interval: int = 10000,
        debug: bool = False,
        ignore_frozen: bool = False,
    ):
        """
        Initialize the TelepySysAsyncSampler.
        Parameters:
            sampling_interval: int = 10000
                The interval between each sampling in microseconds.
            debug: bool = False
                Whether to enable debug mode.
            ignore_frozen: bool = False
                Whether to ignore frozen threads.
        """
        super().__init__()
        self.sampling_interval = sampling_interval
        self.debug = debug
        self.ignore_frozen = ignore_frozen
        self.old: Callable[[int, FrameType | None], Any]

    @property
    def started(self) -> bool:
        """
        Returns whether the sampler is started.
        Returns:
        bool
            Whether the sampler is started.
        """
        return self.enabled()

    def start(self):
        """
        Starts the sampler. You only can start the sampler in the
        main thread. SIGPROF signal will be sent to the main thread
        every `sampling_interval` microseconds.
        """
        self.old = signal.getsignal(signal.SIGPROF)
        if self.old not in (None, signal.SIG_DFL, signal.SIG_IGN):
            raise RuntimeError("signal.SIGPROF already used")
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("AsyncSampler can only be started in main thread")
        self.sampling_tid = threading.get_ident()
        signal.signal(signal.SIGPROF, self._async_routine)
        interval = self.sampling_interval * 1e-6
        signal.setitimer(signal.ITIMER_PROF, interval, interval)
        super().start()

    def stop(self):
        signal.setitimer(signal.ITIMER_PROF, 0, 0)
        signal.signal(signal.SIGPROF, self.old)
