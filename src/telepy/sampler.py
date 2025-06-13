import signal
import sys
import threading
from collections.abc import Callable
from types import FrameType
from typing import Any, override

from . import _telepysys


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
    def started(self):
        """
        Return True if the sampler is started.
        """
        return self.enabled()


class TelepySysAsyncSampler(_telepysys.AsyncSampler):
    """
    AsyncSampler class.
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

    @override
    def save(self, filename: str) -> None:
        """
        Save the sampler data to a file.
        """
        content = self.dumps()
        with open(filename, "w") as f:
            f.write(content[:-1])  #   remove the last new line

    @property
    def started(self):
        """
        Return True if the sampler is started.
        """
        return self.enabled()

    @override
    def start(self) -> None:
        """
        Start the sampler.
        """
        if self.started:
            raise RuntimeError("Sampler is already started")

        if threading.current_thread() != threading.main_thread():
            raise RuntimeError(
                "TelepySysAsyncSampler must be started from the main thread"
            )

        current = signal.getsignal(signal.SIGPROF)
        if current not in (signal.SIG_DFL, signal.SIG_IGN):
            raise RuntimeError("signal.SIGPROF is already in use by another handler")

        signal.signal(signal.SIGPROF, self._async_routine)
        interval_sec = self.sampling_interval * 1e-6

        signal.setitimer(signal.ITIMER_PROF, interval_sec, interval_sec)
        self.sampling_tid = threading.get_ident()  # required for base class
        super().start()

    @override
    def stop(self) -> None:
        """
        Stop the sampler.
        """
        signal.setitimer(signal.ITIMER_PROF, 0, 0)
        signal.signal(signal.SIGPROF, signal.SIG_IGN)
        super().stop()
