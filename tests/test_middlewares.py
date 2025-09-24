import os
import tempfile
import threading

import telepy
from telepy.sampler import SamplerMiddleware

from .base import TestBase  # type: ignore


class TestMiddleware(SamplerMiddleware):
    """Test middleware that adds a prefix to dump output."""

    def __init__(self, prefix: str = "TEST_PREFIX"):
        self.prefix = prefix
        self.calls = {
            "before_start": 0,
            "after_start": 0,
            "before_stop": 0,
            "after_stop": 0,
            "process_dump": 0,
        }

    def on_before_start(self, sampler):
        self.calls["before_start"] += 1

    def on_after_start(self, sampler):
        self.calls["after_start"] += 1

    def on_before_stop(self, sampler):
        self.calls["before_stop"] += 1

    def on_after_stop(self, sampler):
        self.calls["after_stop"] += 1

    def process_dump(self, sampler, dump_str: str) -> str | None:
        self.calls["process_dump"] += 1
        if dump_str:
            lines = dump_str.split("\n")
            processed_lines = [
                f"{self.prefix}: {line}" if line.strip() else line for line in lines
            ]
            return "\n".join(processed_lines)
        return None


class NullMiddleware(SamplerMiddleware):
    """Middleware that returns None to use original output."""

    def __init__(self):
        self.process_dump_called = False

    def process_dump(self, sampler, dump_str: str) -> str | None:
        self.process_dump_called = True
        return None  # Use original output


class ExceptionMiddleware(SamplerMiddleware):
    """Middleware that raises exceptions to test error handling."""

    def __init__(self, fail_on: str = "process_dump"):
        self.fail_on = fail_on

    def on_before_start(self, sampler):
        if self.fail_on == "before_start":
            raise RuntimeError("Test exception in before_start")

    def on_after_start(self, sampler):
        if self.fail_on == "after_start":
            raise RuntimeError("Test exception in after_start")

    def on_before_stop(self, sampler):
        if self.fail_on == "before_stop":
            raise RuntimeError("Test exception in before_stop")

    def on_after_stop(self, sampler):
        if self.fail_on == "after_stop":
            raise RuntimeError("Test exception in after_stop")

    def process_dump(self, sampler, dump_str: str) -> str | None:
        if self.fail_on == "process_dump":
            raise RuntimeError("Test exception in process_dump")
        return None


class TestSamplerMiddleware(TestBase):
    """Test cases for SamplerMiddleware functionality."""

    def setUp(self):
        super().setUp()
        self.temp_files = []

    def tearDown(self):
        """Clean up test files after each test."""
        super().tearDown()
        for file in self.temp_files:
            if os.path.exists(file):
                os.remove(file)

    def _create_temp_file(self, suffix: str = ".folded") -> str:
        """Create a temporary file and track it for cleanup."""
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            temp_file = f.name
        self.temp_files.append(temp_file)
        return temp_file

    def _do_work(self):
        """Perform some work to generate stack traces."""
        result = 0
        for i in range(1000):
            result += i * i
        return result

    def test_middleware_registration(self):
        """Test middleware registration and unregistration."""
        sampler = telepy.TelepySysSampler(sampling_interval=1000)

        # Initially no middleware
        self.assertEqual(len(sampler._middleware), 0)

        # Register middleware
        middleware1 = TestMiddleware("TEST1")
        middleware2 = TestMiddleware("TEST2")

        sampler.register_middleware(middleware1)
        self.assertEqual(len(sampler._middleware), 1)
        self.assertIn(middleware1, sampler._middleware)

        sampler.register_middleware(middleware2)
        self.assertEqual(len(sampler._middleware), 2)
        self.assertIn(middleware2, sampler._middleware)

        # Test duplicate registration (should not add twice)
        sampler.register_middleware(middleware1)
        self.assertEqual(len(sampler._middleware), 2)

        # Unregister middleware
        sampler.unregister_middleware(middleware1)
        self.assertEqual(len(sampler._middleware), 1)
        self.assertNotIn(middleware1, sampler._middleware)
        self.assertIn(middleware2, sampler._middleware)

        # Clear all middleware
        sampler.clear_middleware()
        self.assertEqual(len(sampler._middleware), 0)

    def test_middleware_lifecycle_calls(self):
        """Test that middleware lifecycle methods are called correctly."""
        sampler = telepy.TelepySysSampler(sampling_interval=1000)
        middleware = TestMiddleware()
        sampler.register_middleware(middleware)

        # Before start/stop, no calls should be made
        self.assertEqual(middleware.calls["before_start"], 0)
        self.assertEqual(middleware.calls["after_start"], 0)
        self.assertEqual(middleware.calls["before_stop"], 0)
        self.assertEqual(middleware.calls["after_stop"], 0)

        # Start sampler
        sampler.start()
        self._do_work()

        # Check start calls
        self.assertEqual(middleware.calls["before_start"], 1)
        self.assertEqual(middleware.calls["after_start"], 1)
        self.assertEqual(middleware.calls["before_stop"], 0)
        self.assertEqual(middleware.calls["after_stop"], 0)

        # Stop sampler
        sampler.stop()

        # Check stop calls
        self.assertEqual(middleware.calls["before_start"], 1)
        self.assertEqual(middleware.calls["after_start"], 1)
        self.assertEqual(middleware.calls["before_stop"], 1)
        self.assertEqual(middleware.calls["after_stop"], 1)

    def test_process_dump_middleware(self):
        """Test process_dump middleware functionality."""
        sampler = telepy.TelepySysSampler(sampling_interval=1000)

        # Start sampling to get some data
        sampler.start()
        self._do_work()
        sampler.stop()

        # Get original dump
        original_dump = sampler.dumps()
        self.assertIsInstance(original_dump, str)

        # Add middleware and test processing
        middleware = TestMiddleware("PROCESSED")
        sampler.register_middleware(middleware)

        processed_dump = sampler.dumps()
        self.assertIsInstance(processed_dump, str)
        self.assertEqual(middleware.calls["process_dump"], 1)

        # Verify processing occurred
        if original_dump:  # Only test if we have data
            self.assertIn("PROCESSED:", processed_dump)
            self.assertNotEqual(original_dump, processed_dump)

    def test_null_middleware(self):
        """Test middleware that returns None (uses original output)."""
        sampler = telepy.TelepySysSampler(sampling_interval=1000)

        # Start sampling to get some data
        sampler.start()
        self._do_work()
        sampler.stop()

        # Get original dump
        original_dump = sampler.dumps()

        # Add null middleware
        null_middleware = NullMiddleware()
        sampler.register_middleware(null_middleware)

        processed_dump = sampler.dumps()

        # Should be identical to original
        self.assertEqual(original_dump, processed_dump)
        self.assertTrue(null_middleware.process_dump_called)

    def test_middleware_chain(self):
        """Test multiple middleware processing in sequence."""
        sampler = telepy.TelepySysSampler(sampling_interval=1000)

        # Start sampling to get some data
        sampler.start()
        self._do_work()
        sampler.stop()

        # Add multiple middleware
        middleware1 = TestMiddleware("FIRST")
        middleware2 = TestMiddleware("SECOND")

        sampler.register_middleware(middleware1)
        sampler.register_middleware(middleware2)

        processed_dump = sampler.dumps()

        # Both middleware should have been called
        self.assertEqual(middleware1.calls["process_dump"], 1)
        self.assertEqual(middleware2.calls["process_dump"], 1)

        # Both prefixes should be present if we have data
        if processed_dump:
            self.assertIn("FIRST:", processed_dump)
            self.assertIn("SECOND:", processed_dump)

    def test_middleware_exception_handling(self):
        """Test that middleware exceptions don't break the sampler."""
        sampler = telepy.TelepySysSampler(sampling_interval=1000)

        # Start sampling to get some data
        sampler.start()
        self._do_work()
        sampler.stop()

        # Add exception middleware
        exception_middleware = ExceptionMiddleware("process_dump")
        working_middleware = TestMiddleware("WORKING")

        sampler.register_middleware(exception_middleware)
        sampler.register_middleware(working_middleware)

        # Should not raise exception, and working middleware should still process
        processed_dump = sampler.dumps()

        # Working middleware should have processed the dump
        self.assertEqual(working_middleware.calls["process_dump"], 1)
        if processed_dump:
            self.assertIn("WORKING:", processed_dump)

    def test_save_with_middleware(self):
        """Test that save() method uses middleware-processed dumps."""
        sampler = telepy.TelepySysSampler(sampling_interval=1000)

        # Start sampling to get some data
        sampler.start()
        self._do_work()
        sampler.stop()

        # Add middleware
        middleware = TestMiddleware("SAVED")
        sampler.register_middleware(middleware)

        # Save to file
        temp_file = self._create_temp_file()
        sampler.save(temp_file)

        # Read file content
        with open(temp_file) as f:
            file_content = f.read()

        # Verify middleware was applied
        self.assertEqual(middleware.calls["process_dump"], 1)
        if file_content:
            self.assertIn("SAVED:", file_content)


class TestAsyncSamplerMiddleware(TestBase):
    """Test cases for middleware with async samplers."""

    def setUp(self):
        super().setUp()
        self.temp_files = []

    def tearDown(self):
        """Clean up test files after each test."""
        super().tearDown()
        for file in self.temp_files:
            if os.path.exists(file):
                os.remove(file)

    def _create_temp_file(self, suffix: str = ".folded") -> str:
        """Create a temporary file and track it for cleanup."""
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            temp_file = f.name
        self.temp_files.append(temp_file)
        return temp_file

    def _do_work(self):
        """Perform some work to generate stack traces."""
        result = 0
        for i in range(1000):
            result += i * i
        return result

    def test_async_sampler_middleware(self):
        """Test middleware with TelepySysAsyncSampler."""
        # Skip if not in main thread (async sampler requirement)
        if threading.current_thread() != threading.main_thread():
            self.skipTest("AsyncSampler requires main thread")

        sampler = telepy.TelepySysAsyncSampler(sampling_interval=1000)
        middleware = TestMiddleware("ASYNC")
        sampler.register_middleware(middleware)

        # Test lifecycle
        sampler.start()
        self._do_work()
        sampler.stop()

        # Check middleware calls
        self.assertEqual(middleware.calls["before_start"], 1)
        self.assertEqual(middleware.calls["after_start"], 1)
        self.assertEqual(middleware.calls["before_stop"], 1)
        self.assertEqual(middleware.calls["after_stop"], 1)

        # Test dump processing
        sampler.dumps()  # This should trigger middleware
        self.assertEqual(middleware.calls["process_dump"], 1)

    def test_worker_sampler_middleware(self):
        """Test middleware with TelepySysAsyncWorkerSampler."""

        def worker_function():
            sampler = telepy.TelepySysAsyncWorkerSampler(sampling_interval=1000)
            middleware = TestMiddleware("WORKER")
            sampler.register_middleware(middleware)

            sampler.start()
            self._do_work()
            sampler.stop()

            # Test dump processing
            processed_dump = sampler.dumps()

            # Store results for main thread to check
            self.worker_results = {
                "middleware_calls": middleware.calls,
                "dump_processed": "WORKER:" in processed_dump
                if processed_dump
                else False,
            }

        # Run worker in thread
        thread = threading.Thread(target=worker_function)
        thread.start()
        thread.join(timeout=5.0)  # 5 second timeout

        # Check results
        if hasattr(self, "worker_results"):
            calls = self.worker_results["middleware_calls"]
            self.assertEqual(calls["before_start"], 1)
            self.assertEqual(calls["after_start"], 1)
            self.assertEqual(calls["before_stop"], 1)
            self.assertEqual(calls["after_stop"], 1)
            self.assertEqual(calls["process_dump"], 1)
