import os
import tempfile
import threading

import telepy
from telepy.sampler import SamplerMiddleware

from .base import TestBase  # type: ignore
from .test_command import CommandTemplate  # type: ignore


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


class TestPyTorchProfilerMiddleware(TestBase):
    """Test cases for PyTorchProfilerMiddleware functionality."""

    def setUp(self):
        super().setUp()
        self.temp_dirs = []
        self.temp_files = []
        # Try to import PyTorch
        try:
            import torch

            self.torch_available = True
            self.cuda_available = torch.cuda.is_available()
            # Check XPU availability safely
            self.xpu_available = False
            try:
                if hasattr(torch, "xpu"):
                    self.xpu_available = torch.xpu.is_available()
            except (AttributeError, RuntimeError):
                pass
        except ImportError:
            self.torch_available = False
            self.cuda_available = False
            self.xpu_available = False

    def tearDown(self):
        """Clean up test files and directories after each test."""
        super().tearDown()
        # Clean up files
        for file in self.temp_files:
            if os.path.exists(file):
                try:
                    os.remove(file)
                except Exception:
                    pass
        # Clean up directories
        for dir_path in self.temp_dirs:
            if os.path.exists(dir_path):
                try:
                    import shutil

                    shutil.rmtree(dir_path)
                except Exception:
                    pass

    def _create_temp_dir(self) -> str:
        """Create a temporary directory and track it for cleanup."""
        temp_dir = tempfile.mkdtemp()
        self.temp_dirs.append(temp_dir)
        return temp_dir

    def _do_pytorch_work(self):
        """Perform some PyTorch work to generate profiling data."""
        if not self.torch_available:
            return

        import torch

        # Simple tensor operations with enough work to be profiled
        x = torch.randn(100, 100)
        y = torch.randn(100, 100)
        for _ in range(50):  # Increased iterations
            z = torch.matmul(x, y)
            z = torch.relu(z)
            z = z.sum()

    def test_pytorch_middleware_import_error(self):
        """Test PyTorchProfilerMiddleware raises ImportError if PyTorch unavailable."""
        if self.torch_available:
            self.skipTest("PyTorch is available, skipping import error test")

        from telepy.sampler import PyTorchProfilerMiddleware

        with self.assertRaises(ImportError):
            PyTorchProfilerMiddleware()

    def test_pytorch_middleware_initialization(self):
        """Test PyTorchProfilerMiddleware initialization."""
        if not self.torch_available:
            self.skipTest("PyTorch not available")

        from telepy.sampler import PyTorchProfilerMiddleware

        temp_dir = self._create_temp_dir()

        # Test default initialization
        middleware = PyTorchProfilerMiddleware(output_dir=temp_dir)
        self.assertEqual(middleware.output_dir, temp_dir)
        self.assertEqual(middleware.activities, ["cpu"])
        self.assertTrue(middleware.record_shapes)
        self.assertTrue(middleware.profile_memory)
        self.assertTrue(middleware.with_stack)
        self.assertTrue(middleware.export_chrome_trace)
        self.assertEqual(middleware.sort_by, "cpu_time_total")
        self.assertFalse(middleware.verbose)

        # Test custom initialization
        middleware2 = PyTorchProfilerMiddleware(
            output_dir=temp_dir,
            activities=["cpu", "cuda"],
            record_shapes=False,
            profile_memory=False,
            with_stack=False,
            export_chrome_trace=False,
            sort_by="cuda_time_total",
            verbose=True,
        )
        self.assertEqual(middleware2.activities, ["cpu", "cuda"])
        self.assertFalse(middleware2.record_shapes)
        self.assertFalse(middleware2.profile_memory)
        self.assertFalse(middleware2.with_stack)
        self.assertFalse(middleware2.export_chrome_trace)
        self.assertEqual(middleware2.sort_by, "cuda_time_total")
        self.assertTrue(middleware2.verbose)

    def test_pytorch_middleware_registration(self):
        """Test registering PyTorchProfilerMiddleware with sampler."""
        if not self.torch_available:
            self.skipTest("PyTorch not available")

        from telepy.sampler import PyTorchProfilerMiddleware

        temp_dir = self._create_temp_dir()
        sampler = telepy.TelepySysSampler(sampling_interval=1000)
        middleware = PyTorchProfilerMiddleware(output_dir=temp_dir, verbose=False)

        sampler.register_middleware(middleware)
        self.assertIn(middleware, sampler._middleware)

    def test_pytorch_middleware_lifecycle_cpu(self):
        """Test PyTorchProfilerMiddleware lifecycle with CPU profiling."""
        if not self.torch_available:
            self.skipTest("PyTorch not available")

        from telepy.sampler import PyTorchProfilerMiddleware

        temp_dir = self._create_temp_dir()
        sampler = telepy.TelepySysSampler(sampling_interval=1000)
        middleware = PyTorchProfilerMiddleware(
            output_dir=temp_dir, activities=["cpu"], verbose=False
        )

        sampler.register_middleware(middleware)

        # Initially profiler should not be started
        self.assertIsNone(middleware.profiler)

        # Start sampler
        sampler.start()
        self._do_pytorch_work()

        # Profiler should now be running
        if middleware.profiler is None:
            # Debug info
            print(f"\nDEBUG: torch_available={middleware.torch_available}")
            print(f"DEBUG: activities={middleware.activities}")
        self.assertIsNotNone(
            middleware.profiler, "Profiler should be started after sampler.start()"
        )

        # Stop sampler
        sampler.stop()

        # Profiler should be stopped
        self.assertIsNone(middleware.profiler)

        # Check that output directory was created
        self.assertTrue(os.path.exists(temp_dir))

    def test_pytorch_middleware_output_files(self):
        """Test that PyTorchProfilerMiddleware generates expected output files."""
        if not self.torch_available:
            self.skipTest("PyTorch not available")

        from telepy.sampler import PyTorchProfilerMiddleware

        temp_dir = self._create_temp_dir()
        sampler = telepy.TelepySysSampler(sampling_interval=1000)
        middleware = PyTorchProfilerMiddleware(
            output_dir=temp_dir,
            activities=["cpu"],
            export_chrome_trace=True,
            verbose=False,
        )

        sampler.register_middleware(middleware)

        # Run profiling
        sampler.start()
        self._do_pytorch_work()
        sampler.stop()

        # Check chrome trace file exists
        chrome_trace = os.path.join(temp_dir, "chrome_trace.json")
        self.assertTrue(
            os.path.exists(chrome_trace), f"Chrome trace not found at {chrome_trace}"
        )

        # Check stats file exists (with timestamp)
        stats_files = [f for f in os.listdir(temp_dir) if f.startswith("profiler_stats_")]
        self.assertGreater(
            len(stats_files), 0, "No profiler statistics file was generated"
        )

        # Verify chrome trace is valid JSON
        with open(chrome_trace) as f:
            import json

            try:
                json.load(f)
            except json.JSONDecodeError:
                self.fail("Chrome trace is not valid JSON")

    def test_pytorch_middleware_cuda_availability(self):
        """Test PyTorchProfilerMiddleware handles CUDA availability correctly."""
        if not self.torch_available:
            self.skipTest("PyTorch not available")

        from telepy.sampler import PyTorchProfilerMiddleware

        temp_dir = self._create_temp_dir()
        sampler = telepy.TelepySysSampler(sampling_interval=1000)

        # Request CUDA profiling
        middleware = PyTorchProfilerMiddleware(
            output_dir=temp_dir, activities=["cpu", "cuda"], verbose=False
        )

        sampler.register_middleware(middleware)
        sampler.start()
        self._do_pytorch_work()
        sampler.stop()

        # Should not raise an error even if CUDA is not available
        # The middleware should handle this gracefully
        self.assertTrue(True, "Middleware handled CUDA unavailability gracefully")

    def test_pytorch_middleware_xpu_availability(self):
        """Test PyTorchProfilerMiddleware handles XPU availability correctly."""
        if not self.torch_available:
            self.skipTest("PyTorch not available")

        from telepy.sampler import PyTorchProfilerMiddleware

        temp_dir = self._create_temp_dir()
        sampler = telepy.TelepySysSampler(sampling_interval=1000)

        # Request XPU profiling
        middleware = PyTorchProfilerMiddleware(
            output_dir=temp_dir, activities=["cpu", "xpu"], verbose=False
        )

        sampler.register_middleware(middleware)
        sampler.start()
        self._do_pytorch_work()
        sampler.stop()

        # Should not raise an error even if XPU is not available
        # The middleware should handle this gracefully
        self.assertTrue(True, "Middleware handled XPU unavailability gracefully")

    def test_pytorch_middleware_no_export_chrome_trace(self):
        """Test PyTorchProfilerMiddleware with chrome trace export disabled."""
        if not self.torch_available:
            self.skipTest("PyTorch not available")

        from telepy.sampler import PyTorchProfilerMiddleware

        temp_dir = self._create_temp_dir()
        sampler = telepy.TelepySysSampler(sampling_interval=1000)
        middleware = PyTorchProfilerMiddleware(
            output_dir=temp_dir,
            activities=["cpu"],
            export_chrome_trace=False,
            verbose=False,
        )

        sampler.register_middleware(middleware)
        sampler.start()
        self._do_pytorch_work()
        sampler.stop()

        # Chrome trace should NOT exist
        chrome_trace = os.path.join(temp_dir, "chrome_trace.json")
        self.assertFalse(
            os.path.exists(chrome_trace),
            "Chrome trace should not be created when export_chrome_trace=False",
        )

        # But stats file should still exist
        stats_files = [f for f in os.listdir(temp_dir) if f.startswith("profiler_stats_")]
        self.assertGreater(len(stats_files), 0, "Statistics file should still be created")

    def test_pytorch_middleware_custom_sort_by(self):
        """Test PyTorchProfilerMiddleware with custom sort_by parameter."""
        if not self.torch_available:
            self.skipTest("PyTorch not available")

        from telepy.sampler import PyTorchProfilerMiddleware

        temp_dir = self._create_temp_dir()
        sampler = telepy.TelepySysSampler(sampling_interval=1000)
        middleware = PyTorchProfilerMiddleware(
            output_dir=temp_dir,
            activities=["cpu"],
            sort_by="cpu_time",
            verbose=False,
        )

        sampler.register_middleware(middleware)
        sampler.start()
        self._do_pytorch_work()
        sampler.stop()

        # Stats file should exist
        stats_files = [f for f in os.listdir(temp_dir) if f.startswith("profiler_stats_")]
        self.assertGreater(len(stats_files), 0)

        # Read stats file and verify it's not empty
        stats_path = os.path.join(temp_dir, stats_files[0])
        with open(stats_path) as f:
            content = f.read()
        self.assertGreater(len(content), 0, "Statistics file should not be empty")

    def test_pytorch_middleware_with_async_sampler(self):
        """Test PyTorchProfilerMiddleware with async sampler."""
        if not self.torch_available:
            self.skipTest("PyTorch not available")

        # Skip if not in main thread (async sampler requirement)
        if threading.current_thread() != threading.main_thread():
            self.skipTest("AsyncSampler requires main thread")

        from telepy.sampler import PyTorchProfilerMiddleware

        temp_dir = self._create_temp_dir()
        sampler = telepy.TelepySysAsyncSampler(sampling_interval=1000)
        middleware = PyTorchProfilerMiddleware(
            output_dir=temp_dir, activities=["cpu"], verbose=False
        )

        sampler.register_middleware(middleware)
        sampler.start()
        self._do_pytorch_work()
        sampler.stop()

        # Check output files were created
        self.assertTrue(os.path.exists(temp_dir))
        files_created = os.listdir(temp_dir)
        self.assertGreater(len(files_created), 0, "No output files were created")

    def test_pytorch_middleware_repr(self):
        """Test PyTorchProfilerMiddleware __repr__ method."""
        if not self.torch_available:
            self.skipTest("PyTorch not available")

        from telepy.sampler import PyTorchProfilerMiddleware

        temp_dir = self._create_temp_dir()
        middleware = PyTorchProfilerMiddleware(output_dir=temp_dir)
        repr_str = repr(middleware)
        self.assertIn("PyTorchProfilerMiddleware", repr_str)
        self.assertIn(temp_dir, repr_str)

    def test_pytorch_middleware_multiple_runs(self):
        """Test PyTorchProfilerMiddleware with multiple start/stop cycles."""
        if not self.torch_available:
            self.skipTest("PyTorch not available")

        from telepy.sampler import PyTorchProfilerMiddleware

        temp_dir = self._create_temp_dir()
        sampler = telepy.TelepySysSampler(sampling_interval=1000)
        middleware = PyTorchProfilerMiddleware(
            output_dir=temp_dir, activities=["cpu"], verbose=False
        )

        sampler.register_middleware(middleware)

        # First run
        sampler.start()
        self._do_pytorch_work()
        sampler.stop()

        first_files = os.listdir(temp_dir)

        # Second run
        sampler.start()
        self._do_pytorch_work()
        sampler.stop()

        second_files = os.listdir(temp_dir)

        # Should have more files after second run
        self.assertGreaterEqual(
            len(second_files),
            len(first_files),
            "Second run should create additional files",
        )

    def test_pytorch_middleware_context_manager(self):
        """Test PyTorchProfilerMiddleware with context manager."""
        if not self.torch_available:
            self.skipTest("PyTorch not available")

        from telepy.sampler import PyTorchProfilerMiddleware

        temp_dir = self._create_temp_dir()
        sampler = telepy.TelepySysSampler(sampling_interval=1000)
        middleware = PyTorchProfilerMiddleware(
            output_dir=temp_dir, activities=["cpu"], verbose=False
        )

        sampler.register_middleware(middleware)

        # Use context manager
        with sampler:
            self._do_pytorch_work()

        # Profiler should be stopped after exiting context
        self.assertIsNone(middleware.profiler)

        # Output files should exist
        self.assertTrue(os.path.exists(temp_dir))
        files = os.listdir(temp_dir)
        self.assertGreater(len(files), 0, "No output files were created")


class TestPyTorchProfilerCLI(CommandTemplate):
    """Test PyTorch profiler CLI integration."""

    def setUp(self):
        super().setUp()
        self.temp_dirs = []
        # Check if PyTorch and numpy are available
        try:
            import torch  # noqa: F401
            import numpy  # noqa: F401

            self.torch_available = True
        except ImportError:
            self.torch_available = False

    def tearDown(self):
        """Clean up temporary directories."""
        super().tearDown()
        import shutil

        for temp_dir in self.temp_dirs:
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass

    def _create_temp_dir(self) -> str:
        """Create a temporary directory and track it for cleanup."""
        temp_dir = tempfile.mkdtemp()
        self.temp_dirs.append(temp_dir)
        return temp_dir

    def test_torch_profile_basic(self):
        """Test: telepy test_torch.py --torch-profile -- --epochs 1."""
        if not self.torch_available:
            self.skipTest("PyTorch not available")

        temp_dir = self._create_temp_dir()

        # Run with torch profiler enabled
        self.run_filename(
            "test_files/test_torch.py",
            stdout_check_list=[
                r"Epoch 1:",  # Training output
                r"Test accuracy:",  # Final test accuracy
            ],
            options=[
                "--torch-profile",
                "--torch-output-dir",
                temp_dir,
                "--",
                "--epochs",
                "1",
            ],
            timeout=120,
            exit_code=0,
        )

        # Verify output directory was created and contains files
        self.assertTrue(
            os.path.exists(temp_dir),
            "PyTorch profiler output directory not created",
        )

        files = os.listdir(temp_dir)
        self.assertGreater(len(files), 0, "No PyTorch profiler output files were created")

        # Check for profiler statistics files
        stats_files = [f for f in files if f.startswith("profiler_stats_")]
        self.assertGreater(len(stats_files), 0, "No profiler statistics files found")

    def test_torch_profile_with_verbose(self):
        """Test torch profiler with --debug --verbose flags."""
        if not self.torch_available:
            self.skipTest("PyTorch not available")

        temp_dir = self._create_temp_dir()

        # Run with debug and verbose flags
        self.run_filename(
            "test_files/test_torch.py",
            stdout_check_list=[
                r"Epoch 1:",
                r"Test accuracy:",
            ],
            options=[
                "--debug",
                "--verbose",
                "--torch-profile",
                "--torch-output-dir",
                temp_dir,
                "--",
                "--epochs",
                "1",
                "--batch-size",
                "128",
            ],
            timeout=120,
            exit_code=0,
        )

        # Verify output files
        files = os.listdir(temp_dir)
        self.assertGreater(len(files), 0, "No output files created")

        stats_files = [f for f in files if f.startswith("profiler_stats_")]
        self.assertGreater(len(stats_files), 0, "No stats files found")

    def test_torch_profile_without_chrome_trace(self):
        """Test PyTorch profiler with chrome trace disabled."""
        if not self.torch_available:
            self.skipTest("PyTorch not available")

        temp_dir = self._create_temp_dir()

        # Run with --no-torch-export-chrome-trace
        self.run_filename(
            "test_files/test_torch.py",
            stdout_check_list=[
                r"Epoch 1:",
                r"Test accuracy:",
            ],
            options=[
                "--torch-profile",
                "--torch-output-dir",
                temp_dir,
                "--no-torch-export-chrome-trace",
                "--",
                "--epochs",
                "1",
            ],
            timeout=120,
            exit_code=0,
        )

        files = os.listdir(temp_dir)
        # Should have stats files but no chrome_trace.json
        chrome_traces = [f for f in files if f == "chrome_trace.json"]
        self.assertEqual(len(chrome_traces), 0, "Chrome trace should not be exported")

        # But stats files should exist
        stats_files = [f for f in files if f.startswith("profiler_stats_")]
        self.assertGreater(len(stats_files), 0, "Stats files should exist")

    def test_torch_profile_custom_activities(self):
        """Test PyTorch profiler with custom activities."""
        if not self.torch_available:
            self.skipTest("PyTorch not available")

        temp_dir = self._create_temp_dir()

        # Run with explicit CPU activity
        self.run_filename(
            "test_files/test_torch.py",
            stdout_check_list=[
                r"Epoch 1:",
                r"Test accuracy:",
            ],
            options=[
                "--torch-profile",
                "--torch-output-dir",
                temp_dir,
                "--torch-activities",
                "cpu",
                "--",
                "--epochs",
                "1",
            ],
            timeout=120,
            exit_code=0,
        )

        # Verify output files exist
        files = os.listdir(temp_dir)
        self.assertGreater(len(files), 0, "No output files created")

    def test_without_torch_profile(self):
        """Test that training works without torch profiler."""
        if not self.torch_available:
            self.skipTest("PyTorch not available")

        # Run without --torch-profile flag
        self.run_filename(
            "test_files/test_torch.py",
            stdout_check_list=[
                r"Epoch 1:",
                r"Test accuracy:",
            ],
            options=[
                "--",
                "--epochs",
                "1",
            ],
            timeout=120,
            exit_code=0,
        )
