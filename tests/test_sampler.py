import threading

import telepy

from .base import TestBase  # type: ignore


class TestAsyncSampler(TestBase):
    def test_sampler(self):
        self.assertEqual(threading.current_thread(), threading.main_thread())

        def fib(n: int) -> int:
            if n < 2:
                return n
            return fib(n - 1) + fib(n - 2)

        async_sampler = telepy.TelepySysAsyncSampler(
            sampling_interval=10,
            ignore_frozen=True,
        )
        async_sampler.start()
        t = threading.Thread(target=fib, args=(38,))
        t.start()
        t.join()
        async_sampler.stop()
        async_sampler.save("test_async_sampler.stack")
        print(f"{async_sampler.sampling_times = }")

    def test_worker_sampler(self):
        import threading

        from telepy import TelepySysAsyncWorkerSampler

        def fib(n: int) -> int:
            if n < 2:
                return n
            return fib(n - 1) + fib(n - 2)

        finished = False

        def profiling_in_non_main_thread():
            nonlocal finished

            sampler = TelepySysAsyncWorkerSampler(sampling_interval=100)

            adjusted = sampler.adjust()
            self.assertTrue(adjusted)
            sampler.start()
            t = threading.Thread(target=fib, args=(20,))
            t.start()
            t.join()
            sampler.stop()
            content = sampler.dumps()
            self.assertGreater(len(content), 0)
            self.assertIn("MainThread", content)
            self.assertIn("fib", content)
            sampler.save("test_worker_sampler.stack")
            self.assertLessEqual(sampler.sampling_time_rate, 1)
            finished = True

        t = threading.Thread(target=profiling_in_non_main_thread)
        t.start()
        # using busy wait to avoid deadlock
        while not finished:
            pass
        # do not join the thread before, which will cause the deadlock
        t.join()

    def test_switch_interval(self):
        import sys

        async_sampler = telepy.TelepySysAsyncSampler()
        async_sampler.setswitchinterval(0.001)
        self.assertEqual(sys.getswitchinterval(), async_sampler.getswitchinterval())

        async_sampler = telepy.TelepySysAsyncSampler(sampling_interval=1000000)
        async_sampler.adjust()
        self.assertEqual(async_sampler.getswitchinterval(), 0.001)

    def test_sampler_runtime_error(self):
        async_sampler = telepy.TelepySysAsyncSampler()
        async_sampler.start()
        try:
            async_sampler.start()
        except RuntimeError:
            pass
        else:
            self.fail("RuntimeError not raised")
        async_sampler.stop()

        def spawn_sampler():
            async_sampler = telepy.TelepySysAsyncSampler()

            try:
                async_sampler.start()
            except RuntimeError:
                pass
            else:
                self.fail("RuntimeError not raised")

        t = threading.Thread(target=spawn_sampler)
        t.start()
        t.join()
        print(async_sampler.sampling_time_rate)

    def test_async_sampler_not_in_main(self):
        import threading

        def bar():
            async_sampler = telepy.TelepySysAsyncSampler()
            try:
                async_sampler.start()
            except RuntimeError:
                pass
            else:
                self.fail("RuntimeError not raised")

        t = threading.Thread(target=bar)
        t.start()
        t.join()


class TestSamplerContextManager(TestBase):
    """Test cases for context manager functionality of samplers."""

    def sample_workload(self):
        """A simple workload function for testing."""
        total = 0
        for i in range(1000):
            total += i * 2
        return total

    def test_telepysys_sampler_context_manager(self):
        """Test TelepySysSampler as context manager."""
        sampler = telepy.TelepySysSampler(sampling_interval=1000)

        # Initially not started
        self.assertFalse(sampler.started)

        # Use as context manager
        with sampler:
            self.assertTrue(sampler.started)
            result = self.sample_workload()
            self.assertGreater(result, 0)

        # Should be stopped after context
        self.assertFalse(sampler.started)

    def test_telepysys_async_sampler_context_manager(self):
        """Test TelepySysAsyncSampler as context manager."""
        sampler = telepy.TelepySysAsyncSampler(sampling_interval=1000)

        # Initially not started
        self.assertFalse(sampler.started)

        # Use as context manager
        with sampler:
            self.assertTrue(sampler.started)
            result = self.sample_workload()
            self.assertGreater(result, 0)

        # Should be stopped after context
        self.assertFalse(sampler.started)

    def test_context_manager_exception_handling(self):
        """Test that sampler is properly stopped even when exception occurs."""
        sampler = telepy.TelepySysSampler(sampling_interval=1000)

        self.assertFalse(sampler.started)

        # Exception should not prevent proper cleanup
        with self.assertRaises(ValueError):
            with sampler:
                self.assertTrue(sampler.started)
                raise ValueError("Test exception")

        # Should be stopped after exception
        self.assertFalse(sampler.started)

    def test_context_manager_returns_self(self):
        """Test that context manager returns self for chaining."""
        sampler = telepy.TelepySysSampler(sampling_interval=1000)

        with sampler as s:
            self.assertIs(s, sampler)
            self.assertTrue(s.started)

    def test_nested_context_managers(self):
        """Test behavior with nested context managers."""
        sampler1 = telepy.TelepySysSampler(sampling_interval=1000)
        sampler2 = telepy.TelepySysSampler(sampling_interval=1000)

        with sampler1:
            self.assertTrue(sampler1.started)
            with sampler2:
                self.assertTrue(sampler2.started)
                self.assertTrue(sampler1.started)
                result = self.sample_workload()
                self.assertGreater(result, 0)
            self.assertFalse(sampler2.started)
            self.assertTrue(sampler1.started)
        self.assertFalse(sampler1.started)

    def test_context_manager_with_focus_mode(self):
        """Test context manager with focus mode enabled."""
        sampler = telepy.TelepySysSampler(sampling_interval=1000, focus_mode=True)

        with sampler:
            self.assertTrue(sampler.started)
            self.assertTrue(sampler.focus_mode)
            result = self.sample_workload()
            self.assertGreater(result, 0)

        self.assertFalse(sampler.started)

    def test_context_manager_with_regex_patterns(self):
        """Test context manager with regex patterns."""
        sampler = telepy.TelepySysSampler(
            sampling_interval=1000, regex_patterns=[r"test_.*", r"sample_.*"]
        )

        with sampler:
            self.assertTrue(sampler.started)
            self.assertIsNotNone(sampler.regex_patterns)
            result = self.sample_workload()
            self.assertGreater(result, 0)

        self.assertFalse(sampler.started)

    def test_multiple_sequential_context_uses(self):
        """Test using the same sampler in multiple sequential contexts."""
        sampler = telepy.TelepySysSampler(sampling_interval=1000)

        # First use
        with sampler:
            self.assertTrue(sampler.started)
            result1 = self.sample_workload()
        self.assertFalse(sampler.started)

        # Second use
        with sampler:
            self.assertTrue(sampler.started)
            result2 = self.sample_workload()
        self.assertFalse(sampler.started)

        self.assertGreater(result1, 0)
        self.assertGreater(result2, 0)

    def test_async_sampler_exception_handling(self):
        """Test async sampler exception handling in context manager."""
        sampler = telepy.TelepySysAsyncSampler(sampling_interval=1000)

        self.assertFalse(sampler.started)

        with self.assertRaises(RuntimeError):
            with sampler:
                self.assertTrue(sampler.started)
                raise RuntimeError("Async test exception")

        self.assertFalse(sampler.started)
