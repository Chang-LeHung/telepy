import re
import signal
import sys
import threading
from abc import ABC, abstractmethod
from typing import override

from . import _telepysys
from .thread import in_main_thread


class MultiProcessEnv:
    """
    We do not use the __slots__ to avoid a TypeError raise by CPython
    internals (Objects/typeobject.c:best_base).
    """

    def __init__(self) -> None:
        self.is_root: bool = True
        self.child_cnt: int = 0
        self.from_fork: bool = False
        self.from_mp: bool = False
        self.forkserver: bool = False


class SamplerMixin(ABC):
    @abstractmethod
    def adjust(self) -> bool:
        """Adjust the sampler's parameters and return whether updates occurred.

        Returns:
            bool: True if updates occurred, False otherwise.
        """
        pass  # pragma: no cover

    @abstractmethod
    def start(self) -> None:
        """
        Start the sampler. This is an abstract method that
        must be implemented by subclasses.
        """
        pass  # pragma: no cover

    @abstractmethod
    def stop(self) -> None:
        """Stop the sampler and release any resources."""
        pass  # pragma: no cover

    @staticmethod
    def setswitchinterval(val: float) -> None:
        """
        Sets the interval between switching between threads.
        Args:
            val (float): The interval(in seconds) between switching between threads.
        """
        sys.setswitchinterval(val)

    @staticmethod
    def getswitchinterval() -> float:
        """
        Returns:
            float: The interval(in seconds) between switching between threads.
        """
        return sys.getswitchinterval()


class TelepySysSampler(_telepysys.Sampler, SamplerMixin, MultiProcessEnv):
    """
    Inherited sampler for TelepySys.
    """

    def __init__(
        self,
        sampling_interval: int = 10_000,
        debug: bool = False,
        ignore_frozen: bool = False,
        ignore_self: bool = True,
        tree_mode: bool = False,
        focus_mode: bool = False,
        regex_patterns: list | None = None,
        is_root: bool = True,
        from_fork: bool = False,
        from_mp: bool = False,
        forkserver: bool = False,
    ) -> None:
        """
        Args:
            sampling_interval (int):
                The interval at which the sampler will sample the current stack trace.
            debug (bool):
                Whether to print debug messages.
            ignore_frozen (bool):
                Whether to ignore frozen threads.
            ignore_self (bool):
                Whether to ignore the current thread stack trace data.
            tree_mode (bool):
                Whether to use the tree mode.
            focus_mode (bool):
                Whether to focus on user code by ignoring standard library and third-party packages.
            regex_patterns (list | None):
                List of regex pattern strings for filtering stack traces. Only files matching
                at least one pattern will be included. If None or empty, all files are included.
            is_root (bool):
                Whether the sampler is running in the root process.
            from_fork (bool):
                Whether the sampler is running in the child process with the fork syscall.
            from_mp (bool):
                Whether the sampler is running in the child process with the multiprocessing.
            forkserver (bool):
                Whether the current process is the forkserver.
        """  # noqa: E501
        super().__init__()
        MultiProcessEnv.__init__(self)
        if not debug and sampling_interval < 5:
            sampling_interval = 5  # pragma: no cover
        self.sampling_interval = sampling_interval
        self.debug = debug
        self.ignore_frozen = ignore_frozen
        self.ignore_self = ignore_self
        self.tree_mode = tree_mode
        self.focus_mode = focus_mode
        self.regex_patterns = self._compile_regex_patterns(regex_patterns)
        self.is_root = is_root
        self.from_fork = from_fork
        self.from_mp = from_mp
        self.forkserver = forkserver

    def _compile_regex_patterns(self, patterns: list[str] | None) -> list | None:
        """Compile regex patterns for stack trace filtering."""
        if patterns is None or len(patterns) == 0:
            return None

        compiled_patterns = []
        for pattern in patterns:
            try:
                compiled_patterns.append(re.compile(pattern))
            except re.error as e:
                # If regex compilation fails, raise an error with context
                raise ValueError(f"Invalid regex pattern '{pattern}': {e}") from e

        return compiled_patterns

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

    @override
    def adjust(self):
        return self.adjust_interval()

    @property
    def sampling_time_rate(self):
        """Get the ratio of accumulated sampling time to total program lifetime.

        Returns:
            float: The ratio of time spent sampling versus total program runtime.
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


class TelepySysAsyncSampler(_telepysys.AsyncSampler, SamplerMixin, MultiProcessEnv):
    """
    AsyncSampler class.
    """

    def __init__(
        self,
        sampling_interval: int = 10_000,
        debug: bool = False,
        ignore_frozen: bool = False,
        ignore_self: bool = True,
        tree_mode: bool = False,
        focus_mode: bool = False,
        regex_patterns: list | None = None,
        is_root: bool = True,
        from_fork: bool = False,
        from_mp: bool = False,
        forkserver: bool = False,
    ) -> None:
        """
        Args:
            sampling_interval (int):
                The interval at which the sampler will sample the current stack trace.
            debug (bool):
                Whether to print debug messages.
            ignore_frozen (bool):
                Whether to ignore frozen threads.
            ignore_self (bool):
                Whether to ignore the current thread stack trace data.
            tree_mode (bool):
                Whether to use the tree mode.
            focus_mode (bool):
                Whether to focus on user code by ignoring standard library and third-party packages.
            regex_patterns (list | None):
                List of regex pattern strings for filtering stack traces. Only files matching
                at least one pattern will be included. If None or empty, all files are included.
            is_root (bool):
                Whether the sampler is running in the root process.
            from_fork (bool):
                Whether the sampler is running in the child process with the fork syscall.
            from_mp (bool):
                Whether the sampler is running in the child process with the multiprocessing.
            forkserver (bool):
                Whether the current process is the forkserver.
        """  # noqa: E501
        super().__init__()
        MultiProcessEnv.__init__(self)
        if not debug and sampling_interval < 5:
            # this line is hard to be coveraged
            sampling_interval = 5  # pragma: no cover
        self.sampling_interval = sampling_interval
        self.debug = debug
        self.ignore_frozen = ignore_frozen
        self.ignore_self = ignore_self
        self.tree_mode = tree_mode
        self.focus_mode = focus_mode
        self.regex_patterns = self._compile_regex_patterns(regex_patterns)
        self.is_root = is_root
        self.from_fork = from_fork
        self.from_mp = from_mp
        self.forkserver = forkserver

    def _compile_regex_patterns(self, patterns: list[str] | None) -> list | None:
        """Compile regex patterns for stack trace filtering."""
        if patterns is None or len(patterns) == 0:
            return None

        compiled_patterns = []
        for pattern in patterns:
            try:
                compiled_patterns.append(re.compile(pattern))
            except re.error as e:
                # If regex compilation fails, raise an error with context
                raise ValueError(f"Invalid regex pattern '{pattern}': {e}") from e

        return compiled_patterns

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
            # coverage do not cover this line, god knows why
            raise RuntimeError(
                "TelepySysAsyncSampler must be started from the main thread"
            )  # pragma: no cover

        current = signal.getsignal(signal.SIGPROF)
        if current not in (signal.SIG_DFL, signal.SIG_IGN):
            raise RuntimeError(
                "signal.SIGPROF is already in use by another handler"
            )  # pragma: no cover

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

    @override
    def adjust(self) -> bool:
        interval = self.sampling_interval / 1000_000
        if interval < sys.getswitchinterval():
            sys.setswitchinterval(interval)  # be careful of bus error
            return True
        return False

    @property
    def sampling_time_rate(self):
        """Get the ratio of accumulated sampling time to total program lifetime.

        Returns:
            float: The ratio of time spent sampling versus total program runtime.
        """
        return self.acc_sampling_time / self.sampler_life_time


class TelepySysAsyncWorkerSampler(TelepySysAsyncSampler):
    """
    TelepyAsyncWorkerSampler is a TelepySysAsyncSampler that runs in the non-main threads.
    """

    @override
    @in_main_thread
    def start(self):
        """
        Raises:
            RuntimeError: If the sampler is not started or failed
                            to execute in the main thread.
        """
        return super().start()

    @override
    @in_main_thread
    def stop(self):
        """
        Raises:
            RuntimeError: If the sampler is not started or failed
                            to execute in the main thread.
        """
        return super().stop()
