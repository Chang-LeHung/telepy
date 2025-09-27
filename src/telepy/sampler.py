import re
import signal
import sys
import threading
from abc import ABC, abstractmethod
from typing import override

from . import _telepysys
from .thread import in_main_thread


class SamplerMiddleware(ABC):
    """Abstract base class for sampler middleware."""

    def on_before_start(
        self, sampler: "TelepySysAsyncSampler | TelepySysSampler"
    ) -> None:
        """Called before the sampler starts.

        Args:
            sampler: The sampler instance that is about to start.
        """
        pass

    def on_after_start(self, sampler: "TelepySysAsyncSampler | TelepySysSampler") -> None:
        """Called after the sampler has started.

        Args:
            sampler: The sampler instance that has started.
        """
        pass

    def on_before_stop(self, sampler: "TelepySysAsyncSampler | TelepySysSampler") -> None:
        """Called before the sampler stops.

        Args:
            sampler: The sampler instance that is about to stop.
        """
        pass

    def on_after_stop(self, sampler: "TelepySysAsyncSampler | TelepySysSampler") -> None:
        """Called after the sampler has stopped.

        Args:
            sampler: The sampler instance that has stopped.
        """
        pass

    def process_dump(
        self, sampler: "TelepySysAsyncSampler | TelepySysSampler", dump_str: str
    ) -> str | None:
        """Process the dump string before it's returned.

        Args:
            sampler: The sampler instance that produced the dump.
            dump_str: The original dump string from the sampler.

        Returns:
            str: A processed dump string to use instead of the original.
            None: Use the original dump string unchanged.

        Example:
            A folded stack dump produced by the sampler might look like::

                "my_app/main.py;Worker.run;handle_task 42\n"
                "scheduler.py;poll 1"

            This represents two call stacks—``my_app/main.py -> Worker.run ->``
            ``handle_task`` sampled 42 times, and ``scheduler.py -> poll``
            sampled once. Note that the final line intentionally lacks a trailing
            newline. Middleware can return a modified string (for example, stripping
            paths or redacting frames) or ``None`` to keep the original text.
        """
        return None


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
    def __init__(self) -> None:
        self._context_depth = 0
        self._context_lock = threading.Lock()
        # Initialize middleware support
        self._middleware: list[SamplerMiddleware] = []
        self._middleware_lock = threading.Lock()
        super().__init__()

    def register_middleware(self, middleware: SamplerMiddleware) -> None:
        """Register a middleware to be called on start and stop.

        Args:
            middleware: The middleware instance to register.
        """
        with self._middleware_lock:
            if middleware not in self._middleware:
                self._middleware.append(middleware)

    def unregister_middleware(self, middleware: SamplerMiddleware) -> None:
        """Unregister a middleware.

        Args:
            middleware: The middleware instance to unregister.
        """
        with self._middleware_lock:
            if middleware in self._middleware:
                self._middleware.remove(middleware)

    def clear_middleware(self) -> None:
        """Clear all registered middleware."""
        with self._middleware_lock:
            self._middleware.clear()

    def _call_middleware_before_start(self) -> None:
        """Call on_before_start for all registered middleware."""
        with self._middleware_lock:
            # Create a copy to avoid issues if middleware list is modified
            # during iteration
            middleware_list = self._middleware.copy()

        for middleware in middleware_list:
            try:
                # Type ignore because we know self is a sampler instance
                middleware.on_before_start(self)  # type: ignore
            except Exception as e:
                # Log the error but continue with other middleware
                print(f"Warning: Middleware {middleware} failed in on_before_start: {e}")

    def _call_middleware_after_start(self) -> None:
        """Call on_after_start for all registered middleware."""
        with self._middleware_lock:
            # Create a copy to avoid issues if middleware list is modified
            # during iteration
            middleware_list = self._middleware.copy()

        for middleware in middleware_list:
            try:
                # Type ignore because we know self is a sampler instance
                middleware.on_after_start(self)  # type: ignore
            except Exception as e:
                # Log the error but continue with other middleware
                print(f"Warning: Middleware {middleware} failed in on_after_start: {e}")

    def _call_middleware_before_stop(self) -> None:
        """Call on_before_stop for all registered middleware."""
        with self._middleware_lock:
            # Create a copy to avoid issues if middleware list is modified
            # during iteration
            middleware_list = self._middleware.copy()

        # Call in reverse order for proper cleanup
        for middleware in reversed(middleware_list):
            try:
                # Type ignore because we know self is a sampler instance
                middleware.on_before_stop(self)  # type: ignore
            except Exception as e:
                # Log the error but continue with other middleware
                print(f"Warning: Middleware {middleware} failed in on_before_stop: {e}")

    def _call_middleware_after_stop(self) -> None:
        """Call on_after_stop for all registered middleware."""
        with self._middleware_lock:
            # Create a copy to avoid issues if middleware list is modified
            # during iteration
            middleware_list = self._middleware.copy()

        # Call in reverse order for proper cleanup
        for middleware in reversed(middleware_list):
            try:
                # Type ignore because we know self is a sampler instance
                middleware.on_after_stop(self)  # type: ignore
            except Exception as e:
                # Log the error but continue with other middleware
                print(f"Warning: Middleware {middleware} failed in on_after_stop: {e}")

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

    def __enter__(self):
        """Context manager entry point. Starts the sampler on first entry."""
        assert self._context_depth >= 0
        with self._context_lock:
            self._context_depth += 1
            if self._context_depth == 1:
                # Only start the sampler on the first nested call if not already started
                self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point. Stops the sampler on last exit."""
        assert self._context_depth > 0
        with self._context_lock:
            self._context_depth -= 1
            if self._context_depth == 0:
                # Only stop the sampler when all nested contexts are exited
                # and the context manager originally started it
                self.stop()
        return False

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


# Deprecated: Use TelepySysAsyncWorkerSampler instead.
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
                List of regex pattern strings for filtering stack traces. Only files or function/class names matching
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
        _telepysys.Sampler.__init__(self)
        SamplerMixin.__init__(self)
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

    def dumps(self) -> str:
        """Get the sampler data as a string, processed through middleware.

        Returns:
            str: The sampler data, potentially processed by middleware.
        """
        # Get the original dump from the parent class
        original_dump = super().dumps()

        # Process through middleware
        with self._middleware_lock:
            middleware_list = self._middleware.copy()

        result = original_dump
        for middleware in middleware_list:
            try:
                processed = middleware.process_dump(self, result)
                if processed is not None:
                    result = processed
            except Exception as e:
                print(f"Warning: Middleware {middleware} failed in process_dump: {e}")

        return result

    @override
    def save(self, filename: str) -> None:
        """
        Save the sampler data to a file.
        """
        content = self.dumps()
        with open(filename, "w") as f:
            f.write(content)  # no need to remove last newline anymore

    @override
    def start(self) -> None:
        """Start the sampler with middleware support."""
        # Call middleware before starting
        self._call_middleware_before_start()

        try:
            # Call the C extension's start method
            super().start()

            # Call middleware after successful star
            self._call_middleware_after_start()
        except Exception:
            # If start fails, clean up
            raise

    @override
    def stop(self) -> None:
        """Stop the sampler with middleware support."""
        # Call middleware before stopping
        self._call_middleware_before_stop()

        try:
            # Call the C extension's stop method
            super().stop()

            # Call middleware after successful stop
            self._call_middleware_after_stop()
        except Exception:
            # If stop fails, clean up
            raise

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
                List of regex pattern strings for filtering stack traces. Only files or function/class names matching
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
        _telepysys.AsyncSampler.__init__(self)
        SamplerMixin.__init__(self)
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

    @override
    def save(self, filename: str) -> None:
        """
        Save the sampler data to a file.
        """
        content = self.dumps()
        with open(filename, "w") as f:
            f.write(content)  # no need to remove last newline anymore

    @property
    def started(self):
        """
        Return True if the sampler is started.
        """
        return self.enabled()

    def dumps(self) -> str:
        """Get the sampler data as a string, processed through middleware.

        Returns:
            str: The sampler data, potentially processed by middleware.
        """
        # Get the original dump from the parent class
        original_dump = super().dumps()

        # Process through middleware
        with self._middleware_lock:
            middleware_list = self._middleware.copy()

        result = original_dump
        for middleware in middleware_list:
            try:
                processed = middleware.process_dump(self, result)
                if processed is not None:
                    result = processed
            except Exception as e:
                print(f"Warning: Middleware {middleware} failed in process_dump: {e}")

        return result

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
        if current not in (signal.SIG_DFL, signal.SIG_IGN):  # pragma: no cover
            print(
                "signal.SIGPROF is already in use by another handler, reset it now.",
                file=sys.stderr,
            )
            signal.setitimer(signal.ITIMER_PROF, 0, 0)
            signal.signal(signal.SIGPROF, signal.SIG_IGN)

        # Call middleware before starting
        self._call_middleware_before_start()

        try:
            self.sampling_tid = threading.get_ident()  # required for base class
            signal.signal(signal.SIGPROF, self._async_routine)
            interval_sec = self.sampling_interval * 1e-6
            signal.setitimer(signal.ITIMER_PROF, interval_sec, interval_sec)
            super().start()

            # Call middleware after successful star
            self._call_middleware_after_start()
        except Exception:
            # If start fails, clean up
            raise

    @override
    def stop(self) -> None:
        """
        Stop the sampler.
        """
        # Call middleware before stopping
        self._call_middleware_before_stop()

        try:
            signal.setitimer(signal.ITIMER_PROF, 0, 0)
            signal.signal(signal.SIGPROF, signal.SIG_IGN)
            super().stop()

            # Call middleware after successful stop
            self._call_middleware_after_stop()
        except Exception:
            # If stop fails, clean up
            raise

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


# PyTorch Profiler Middleware


class PyTorchProfilerMiddleware(SamplerMiddleware):
    """Middleware that integrates PyTorch profiler with TelePy sampler.

    This middleware starts PyTorch profiler when the sampler starts and
    exports the profiling results when the sampler stops.
    """

    def __init__(
        self,
        output_dir: str = "./pytorch_profiles",
        activities: list[str] | None = None,
        record_shapes: bool = True,
        profile_memory: bool = True,
        with_stack: bool = True,
        export_chrome_trace: bool = True,
        export_tensorboard: bool = False,
        group_by_stack_n: int = 5,
        schedule_wait: int = 1,
        schedule_warmup: int = 1,
        schedule_active: int = 3,
        schedule_repeat: int = 1,
    ):
        """Initialize PyTorch profiler middleware.

        Args:
            output_dir: Directory to save profiler outputs.
            activities: List of activities to profile ('cpu', 'cuda').
                       If None, defaults to ['cpu'].
            record_shapes: Whether to record tensor shapes.
            profile_memory: Whether to profile memory usage.
            with_stack: Whether to record call stack.
            export_chrome_trace: Whether to export Chrome trace format.
            export_tensorboard: Whether to export TensorBoard format.
            group_by_stack_n: Group operators by top N stack frames.
            schedule_wait: Number of steps to skip before profiling.
            schedule_warmup: Number of warmup steps.
            schedule_active: Number of active profiling steps.
            schedule_repeat: Number of cycles to repeat.
        """
        # Check if PyTorch is available
        try:
            import torch  # noqa: F401
            from torch.profiler import profile

            self.torch_available = True
            print("[PyTorchProfilerMiddleware] PyTorch detected")
        except ImportError:
            print("[PyTorchProfilerMiddleware] Warning: PyTorch not available")
        self.output_dir = output_dir
        self.activities = activities or ["cpu"]
        self.record_shapes = record_shapes
        self.profile_memory = profile_memory
        self.with_stack = with_stack
        self.export_chrome_trace = export_chrome_trace
        self.export_tensorboard = export_tensorboard
        self.group_by_stack_n = group_by_stack_n
        self.schedule_wait = schedule_wait
        self.schedule_warmup = schedule_warmup
        self.schedule_active = schedule_active
        self.schedule_repeat = schedule_repeat

        self.profiler: profile | None = None
        self.torch_available = False

    def on_before_start(
        self, sampler: "TelepySysAsyncSampler | TelepySysSampler"
    ) -> None:
        """Called before the sampler starts - prepare PyTorch profiler."""
        if not self.torch_available:
            print("[PyTorchProfilerMiddleware] Skipping: PyTorch not available")
            return

        print("[PyTorchProfilerMiddleware] Preparing to start PyTorch profiler...")
        print(f"  - Output directory: {self.output_dir}")
        print(f"  - Activities: {self.activities}")

    def on_after_start(self, sampler: "TelepySysAsyncSampler | TelepySysSampler") -> None:
        """Called after the sampler starts - start PyTorch profiler."""
        if not self.torch_available:
            return

        try:
            import os

            import torch

            # Create output directory
            os.makedirs(self.output_dir, exist_ok=True)

            # Configure activities
            activities = []
            if "cpu" in self.activities:
                activities.append(torch.profiler.ProfilerActivity.CPU)
            if "cuda" in self.activities and torch.cuda.is_available():
                activities.append(torch.profiler.ProfilerActivity.CUDA)

            # Create schedule
            schedule = torch.profiler.schedule(
                wait=self.schedule_wait,
                warmup=self.schedule_warmup,
                active=self.schedule_active,
                repeat=self.schedule_repeat,
            )

            # Initialize profiler
            self.profiler = torch.profiler.profile(
                activities=activities,
                schedule=schedule,
                record_shapes=self.record_shapes,
                profile_memory=self.profile_memory,
                with_stack=self.with_stack,
                on_trace_ready=self._trace_handler,
            )

            self.profiler.start()
            print("[PyTorchProfilerMiddleware] Started PyTorch profiler")
            print(f"  - Record shapes: {self.record_shapes}")
            print(f"  - Profile memory: {self.profile_memory}")

        except Exception as e:
            print(f"[PyTorchProfilerMiddleware] Error starting profiler: {e}")
            self.profiler = None

    def on_before_stop(self, sampler: "TelepySysAsyncSampler | TelepySysSampler") -> None:
        """Called before the sampler stops - prepare to stop profiler."""
        if not self.torch_available or self.profiler is None:
            return

        print("[PyTorchProfilerMiddleware] Preparing to stop PyTorch profiler...")

    def on_after_stop(self, sampler: "TelepySysAsyncSampler | TelepySysSampler") -> None:
        """Called after the sampler stops - stop profiler and export results."""
        if not self.torch_available or self.profiler is None:
            return

        try:
            import os

            self.profiler.stop()
            print("[PyTorchProfilerMiddleware] Stopped PyTorch profiler")

            # Export additional formats if requested
            if self.export_chrome_trace:
                trace_path = os.path.join(self.output_dir, "chrome_trace.json")
                self.profiler.export_chrome_trace(trace_path)
                print(f"[PyTorchProfilerMiddleware] Exported Chrome trace: {trace_path}")

            # Print profiler summary
            print("\n" + "=" * 60)
            print("PyTorch Profiler Summary")
            print("=" * 60)
            print(
                self.profiler.key_averages(group_by_stack_n=self.group_by_stack_n).table(
                    sort_by="cpu_time_total", row_limit=10
                )
            )
            print("=" * 60 + "\n")

        except Exception as e:
            print(f"[PyTorchProfilerMiddleware] Error stopping profiler: {e}")
        finally:
            self.profiler = None

    def _trace_handler(self, prof):
        """Handle trace export during profiling."""
        try:
            import os
            import time

            timestamp = int(time.time())
            trace_path = os.path.join(self.output_dir, f"pytorch_trace_{timestamp}.json")

            prof.export_chrome_trace(trace_path)

            if self.export_tensorboard:
                tb_path = os.path.join(self.output_dir, "tensorboard")
                prof.export_stacks(tb_path, "profiler_stacks.txt")

        except Exception as e:
            print(f"[PyTorchProfilerMiddleware] Error in trace handler: {e}")

    def __repr__(self) -> str:
        return f"PyTorchProfilerMiddleware(output_dir='{self.output_dir}')"
