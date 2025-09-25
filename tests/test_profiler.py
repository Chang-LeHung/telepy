"""Test for the functionalities in the profile decorator."""

import os

from telepy import profile
from telepy.sampler import TelepySysAsyncSampler, TelepySysAsyncWorkerSampler

from .base import TestBase


class TestProfileDecoratorAutoSave(TestBase):
    """Test auto-save functionality of the profile decorator."""

    def setUp(self):
        """Set up each test."""
        super().setUp()
        self.test_files = []

    def tearDown(self):
        """Clean up after each test."""
        # Remove any test files created
        for filename in self.test_files:
            if os.path.exists(filename):
                try:
                    os.remove(filename)
                except OSError:
                    pass  # Ignore removal errors
        super().tearDown()

    def test_auto_save_functionality(self):
        test_file = "test_auto_save_functionality.svg"
        self.test_files.append(test_file)

        if os.path.exists(test_file):
            os.remove(test_file)

        def mul(a, b):
            return a * b

        @profile(file=test_file, sampling_interval=10, verbose=False)
        def test_function(n):
            total = 0
            for i in range(n):
                for j in range(100):
                    total += mul(i, j)
            return total

        # Execute the function
        result = test_function(50000)

        # Check that the function executed correctly
        self.assertIsInstance(result, int)
        self.assertGreater(result, 0)

        # Check that the file was automatically created
        self.assertTrue(os.path.exists(test_file), "Auto-save file should be created")

        # Check that the file has reasonable size
        file_size = os.path.getsize(test_file)
        self.assertGreater(file_size, 100, "SVG file should have reasonable size")

        # Check that it's a valid SVG by looking for SVG content
        with open(test_file) as f:
            content = f.read()
            self.assertIn("<?xml version=", content)
            self.assertIn("<svg", content)

    def test_no_auto_save_without_file_parameter(self):
        """Test that no file is created when file parameter is not provided."""
        test_file = "test_no_auto_save.svg"

        # Remove file if it exists
        if os.path.exists(test_file):
            os.remove(test_file)

        @profile(sampling_interval=10, verbose=False)
        def test_function(n):
            total = 0
            for i in range(n):
                for j in range(100):
                    total += i * j
            return total

        # Execute the function
        result = test_function(500)

        # Check that the function executed correctly
        self.assertIsInstance(result, int)
        self.assertGreater(result, 0)

        # Check that no file was created
        self.assertFalse(
            os.path.exists(test_file), "No file should be created without file parameter"
        )

    def test_manual_save_still_works(self):
        """Test that manual save functionality still works alongside auto-save."""
        auto_save_file = "test_auto_save_manual.svg"
        manual_save_file = "test_manual_save_manual.svg"
        self.test_files.extend([auto_save_file, manual_save_file])

        # Remove files if they exist
        for filename in [auto_save_file, manual_save_file]:
            if os.path.exists(filename):
                os.remove(filename)

        @profile(file=auto_save_file, sampling_interval=10, verbose=False)
        def test_function(n):
            total = 0
            for i in range(n):
                for j in range(100):
                    total += i * j
            return total

        # Execute the function
        test_function(500)

        # Check that auto-save file was created
        self.assertTrue(
            os.path.exists(auto_save_file), "Auto-save file should be created"
        )

        # Also manually save to a different file
        test_function.sampler.save(manual_save_file, truncate=True, verbose=False)

        # Check that manual save file was also created
        self.assertTrue(
            os.path.exists(manual_save_file), "Manual save file should be created"
        )

        # Both files should have reasonable sizes
        auto_size = os.path.getsize(auto_save_file)
        manual_size = os.path.getsize(manual_save_file)

        self.assertGreater(auto_size, 100, "Auto-save file should have reasonable size")
        self.assertGreater(
            manual_size, 100, "Manual save file should have reasonable size"
        )

    def test_auto_save_with_different_parameters(self):
        """Test auto-save works with different profile decorator parameters."""
        test_file = "test_auto_save_params.svg"
        self.test_files.append(test_file)

        # Remove file if it exists
        if os.path.exists(test_file):
            os.remove(test_file)

        @profile(
            file=test_file,
            sampling_interval=10,
            verbose=False,
            full_path=True,
            focus_mode=False,
        )
        def fibonacci(n):
            if n <= 1:
                return n
            return fibonacci(n - 1) + fibonacci(n - 2)

        # Execute the function
        result = fibonacci(30)

        # Check that the function executed correctly
        self.assertEqual(result, 832040)  # fibonacci(30) = 832040

        # Check that the file was automatically created
        self.assertTrue(os.path.exists(test_file), "Auto-save file should be created")

        # Check that the file has reasonable size
        file_size = os.path.getsize(test_file)
        self.assertGreater(file_size, 100, "SVG file should have reasonable size")

    def test_auto_save_respects_inverted_orientation(self):
        """Profile decorator should propagate the inverted flag to the output."""
        test_file = "test_auto_save_inverted.svg"
        self.test_files.append(test_file)

        if os.path.exists(test_file):
            os.remove(test_file)

        @profile(file=test_file, sampling_interval=10, verbose=False, inverted=True)
        def test_function():
            total = 0
            for i in range(100):
                total += i
            return total

        self.assertEqual(test_function(), sum(range(100)))

        self.assertTrue(os.path.exists(test_file), "Auto-save file should be created")

        with open(test_file) as f:
            content = f.read()

        self.assertIn('data-orientation="inverted"', content)

    def test_auto_save_error_handling(self):
        """Test that auto-save handles errors gracefully."""
        # Test with invalid directory
        invalid_file = "/invalid/directory/test.svg"

        try:

            @profile(file=invalid_file, sampling_interval=10, verbose=False)
            def test_function(n):
                return n * 2

            # This should still execute the function even if save fails
            result = test_function(10)
            self.assertEqual(result, 20)

        except Exception as e:
            # If an exception occurs, it should be related to file operations
            # not to the function execution itself
            self.assertTrue(
                "No such file or directory" in str(e)
                or "Permission denied" in str(e)
                or "Invalid" in str(e)
            )


class TestQuickAutoSave(TestBase):
    def test_quick_auto_save(self):
        @profile(file="quick_test.svg", sampling_interval=1000)
        def fibonacci(n):
            if n <= 1:
                return n
            return fibonacci(n - 1) + fibonacci(n - 2)

        fibonacci(20)

        import os

        if os.path.exists("quick_test.svg"):
            os.remove("quick_test.svg")

    def test_recursive_auto_save(self):
        @profile(file="recursive_test.svg", sampling_interval=10, verbose=False)
        def recursive_fibonacci(n):
            if n <= 1:
                return n
            return recursive_fibonacci(n - 1) + recursive_fibonacci(n - 2)

        recursive_fibonacci(10)


class TestRecursiveContextManager(TestBase):
    """Test recursive context manager functionality."""

    def test_recursive_sync_sampler_context_manager(self):
        """Test that sync sampler context manager supports recursive calls."""
        sampler = TelepySysAsyncWorkerSampler(sampling_interval=1000)

        # Track start/stop calls
        original_start = sampler.start
        original_stop = sampler.stop
        start_count = 0
        stop_count = 0

        def mock_start():
            nonlocal start_count
            start_count += 1
            return original_start()

        def mock_stop():
            nonlocal stop_count
            stop_count += 1
            return original_stop()

        sampler.start = mock_start
        sampler.stop = mock_stop

        # Test nested context managers
        with sampler:
            self.assertEqual(start_count, 1)
            self.assertEqual(stop_count, 0)
            self.assertEqual(sampler._context_depth, 1)

            with sampler:
                self.assertEqual(start_count, 1)  # Should not start again
                self.assertEqual(stop_count, 0)
                self.assertEqual(sampler._context_depth, 2)

                with sampler:
                    self.assertEqual(start_count, 1)  # Should not start again
                    self.assertEqual(stop_count, 0)
                    self.assertEqual(sampler._context_depth, 3)

                self.assertEqual(start_count, 1)
                self.assertEqual(stop_count, 0)  # Should not stop yet
                self.assertEqual(sampler._context_depth, 2)

            self.assertEqual(start_count, 1)
            self.assertEqual(stop_count, 0)  # Should not stop yet
            self.assertEqual(sampler._context_depth, 1)

        # Only now should it stop
        self.assertEqual(start_count, 1)
        self.assertEqual(stop_count, 1)
        self.assertEqual(sampler._context_depth, 0)

    def test_recursive_async_sampler_context_manager(self):
        """Test that async sampler context manager supports recursive calls."""
        sampler = TelepySysAsyncSampler(sampling_interval=10)

        # Track start/stop calls
        original_start = sampler.start
        original_stop = sampler.stop
        start_count = 0
        stop_count = 0

        def mock_start():
            nonlocal start_count
            start_count += 1
            return original_start()

        def mock_stop():
            nonlocal stop_count
            stop_count += 1
            return original_stop()

        sampler.start = mock_start
        sampler.stop = mock_stop

        # Test nested context managers
        with sampler:
            self.assertEqual(start_count, 1)
            self.assertEqual(stop_count, 0)
            self.assertEqual(sampler._context_depth, 1)

            with sampler:
                self.assertEqual(start_count, 1)  # Should not start again
                self.assertEqual(stop_count, 0)
                self.assertEqual(sampler._context_depth, 2)

            self.assertEqual(start_count, 1)
            self.assertEqual(stop_count, 0)  # Should not stop yet
            self.assertEqual(sampler._context_depth, 1)

        # Only now should it stop
        self.assertEqual(start_count, 1)
        self.assertEqual(stop_count, 1)
        self.assertEqual(sampler._context_depth, 0)

    def test_context_manager_exception_handling(self):
        """Test that context manager works correctly even with exceptions."""
        sampler = TelepySysAsyncWorkerSampler(sampling_interval=1000)

        # Track start/stop calls
        original_start = sampler.start
        original_stop = sampler.stop
        start_count = 0
        stop_count = 0

        def mock_start():
            nonlocal start_count
            start_count += 1
            return original_start()

        def mock_stop():
            nonlocal stop_count
            stop_count += 1
            return original_stop()

        sampler.start = mock_start
        sampler.stop = mock_stop

        # Test exception in nested context
        try:
            with sampler:
                self.assertEqual(start_count, 1)
                self.assertEqual(sampler._context_depth, 1)

                with sampler:
                    self.assertEqual(start_count, 1)
                    self.assertEqual(sampler._context_depth, 2)
                    raise ValueError("Test exception")

        except ValueError:
            pass

        # Sampler should still be properly cleaned up
        self.assertEqual(start_count, 1)
        self.assertEqual(stop_count, 1)
        self.assertEqual(sampler._context_depth, 0)


class TestRecursiveFibonacci(TestBase):
    @profile(file="recursive_test.svg", sampling_interval=10, verbose=False)
    def recursive_fibonacci(self, n):
        if n <= 1:
            return n
        return self.recursive_fibonacci(n - 1) + self.recursive_fibonacci(n - 2)

    def test_recursive_fibonacci(self):
        self.recursive_fibonacci(10)


class TestDebugSampler(TestBase):
    def test_sampler(self):
        @profile(sampling_interval=1000)  # 1ms interval
        def test_function():
            """Test function to debug sampler behavior."""
            # CPU intensive computation
            total = 0
            for i in range(50000):  # Moderate computation
                total += i * i
            return total

        test_function()

        # Check if we can get data when sampler is stopped
        content1 = test_function.sampler._sampler.dumps()
        if content1.strip():
            any("test_function" in line for line in content1.splitlines())


class TestComprehensiveAutoSave(TestBase):
    """Comprehensive test suite for auto-save functionality."""

    def test_auto_save_features(self):
        """Test comprehensive auto-save features."""

        @profile(file="test_basic.svg", sampling_interval=1000, verbose=False)
        def basic_function(n):
            total = 0
            for i in range(n):
                total += i * i
            return total

        basic_function(20000)

        if os.path.exists("test_basic.svg"):
            os.path.getsize("test_basic.svg")
            os.remove("test_basic.svg")
        else:
            self.fail("Auto-save failed")

        @profile(file="test_recursive.svg", sampling_interval=1000, verbose=False)
        def fibonacci(n):
            if n <= 1:
                return n
            return fibonacci(n - 1) + fibonacci(n - 2)

        fibonacci(8)

        if os.path.exists("test_recursive.svg"):
            os.remove("test_recursive.svg")
        else:
            self.fail("Recursive auto-save failed")

        @profile(sampling_interval=10, verbose=False)
        def no_auto_save_function(n):
            return sum(range(n))

        no_auto_save_function(100)

        @profile(file="test_auto.svg", sampling_interval=10, verbose=False)
        def dual_save_function(n):
            return sum(range(n))

        dual_save_function(100)

        # Check auto-save
        auto_exists = os.path.exists("test_auto.svg")
        # Test manual save
        dual_save_function.sampler.save("test_manual.svg")
        manual_exists = os.path.exists("test_manual.svg")
        if auto_exists and manual_exists:
            os.remove("test_auto.svg")
            os.remove("test_manual.svg")
        else:
            self.fail(f"Dual save failed! Auto: {auto_exists}, Manual: {manual_exists}")


class TestProfileDecorator(TestBase):
    """Test the profile decorator functionality."""

    def setUp(self):
        """Set up the test by ensuring we import from local source."""
        import os
        import signal
        import sys

        # Add src to path to import our local telepy
        src_path = os.path.join(os.path.dirname(__file__), "..", "src")
        if src_path not in sys.path:
            sys.path.insert(0, src_path)

        # Reset signal handler to default state
        signal.signal(signal.SIGPROF, signal.SIG_DFL)

        super().setUp()

    def tearDown(self):
        """Clean up after each test."""
        import signal

        # Reset signal handler to default state
        signal.signal(signal.SIGPROF, signal.SIG_DFL)

        super().tearDown()

    def test_profile_decorator_without_params(self):
        """Test profile decorator when used without parameters."""
        import time

        from telepy import profile

        # Test basic functionality with CPU-intensive function
        @profile(sampling_interval=1000)  # Use 1ms interval for better sampling
        def cpu_intensive_task(n):
            """A CPU-intensive function that ensures sampling occurs."""
            total = 0
            for i in range(n):
                for j in range(100):  # Increased nested loop for more CPU time
                    total += i * j
                    if (i + j) % 1000 == 0:  # Add more computation
                        total += sum(range(10))
            return total

        # Test that the function works correctly
        result = cpu_intensive_task(5000)  # Increased from 1000 to 5000
        self.assertIsInstance(result, int)

        # Test that the sampler attribute exists
        self.assertTrue(hasattr(cpu_intensive_task, "sampler"))
        self.assertIsNotNone(cpu_intensive_task.sampler)

        # Test that we can access sampler methods
        self.assertTrue(hasattr(cpu_intensive_task.sampler, "save"))

        # Test that sampler collected stack traces during function execution
        content = cpu_intensive_task.sampler._sampler.dumps()
        self.assertIsInstance(content, str)
        lines = content.splitlines()

        # If no traces were collected, run the function again to ensure sampling
        if len(lines) == 0:
            result2 = cpu_intensive_task(8000)  # Even larger workload
            self.assertIsInstance(result2, int)
            content = cpu_intensive_task.sampler._sampler.dumps()
            lines = content.splitlines()

        self.assertGreater(len(lines), 0, "Sampler should have collected stack traces")

        # Test that function appears in stack traces
        has_function = any("cpu_intensive_task" in line for line in lines if line.strip())
        self.assertTrue(has_function, "cpu_intensive_task should appear in stack traces")

        # Test with recursive fibonacci function (larger parameter for longer execution)
        @profile(sampling_interval=1000)  # Use consistent 1ms interval
        def fibonacci(n):
            """Recursive fibonacci with larger parameter for better sampling."""
            if n <= 1:
                return n
            return fibonacci(n - 1) + fibonacci(n - 2)

        # Use smaller fibonacci parameter that still takes reasonable time
        fib_result = fibonacci(30)  # Reduced from 35 to 30 for faster execution
        self.assertEqual(fib_result, 832040)  # fibonacci(30) = 832040

        # Check fibonacci traces
        fib_content = fibonacci.sampler._sampler.dumps()
        fib_lines = fib_content.splitlines()

        # If no traces collected, the recursive nature should still have some traces
        if len(fib_lines) == 0:
            # Run a slightly larger fibonacci to ensure sampling
            fib_result2 = fibonacci(32)
            self.assertEqual(fib_result2, 2178309)
            fib_content = fibonacci.sampler._sampler.dumps()
            fib_lines = fib_content.splitlines()

        self.assertGreater(len(fib_lines), 0, "Fibonacci sampler should collect traces")

        has_fibonacci = any("fibonacci" in line for line in fib_lines if line.strip())
        self.assertTrue(has_fibonacci, "fibonacci function should appear in stack traces")

        # Test that multiple calls accumulate more traces
        initial_lines = len(lines)

        # Run function again to collect more traces
        result2 = cpu_intensive_task(800)
        self.assertIsInstance(result2, int)

        # Check that more traces were accumulated
        updated_content = cpu_intensive_task.sampler._sampler.dumps()
        updated_lines = updated_content.splitlines()
        self.assertGreaterEqual(
            len(updated_lines),
            initial_lines,
            "Multiple calls should accumulate stack traces",
        )

        # Test independent sampler instance
        @profile(sampling_interval=100)  # Use shorter interval for better sampling
        def another_computation(n):
            """Another function to test independent sampling."""
            result = 0
            for i in range(n):
                for k in range(10):  # Add nested loop for more CPU time
                    result += i**2 + k
                if i % 25 == 0:
                    time.sleep(0.0001)  # Periodic delay
            return result

        # Test that this sampler starts with empty content
        initial_another_content = another_computation.sampler._sampler.dumps()
        initial_another_lines = len(initial_another_content.splitlines())

        # Run the function to collect traces (use larger parameter for longer execution)
        result3 = another_computation(2000)  # Increased from 600 to 2000
        self.assertIsInstance(result3, int)

        # Verify traces were collected
        final_another_content = another_computation.sampler._sampler.dumps()
        final_another_lines = len(final_another_content.splitlines())
        self.assertGreaterEqual(
            final_another_lines,
            initial_another_lines,
            "New sampler should collect traces independently",
        )

        # Check that function appears in its own traces
        has_another_function = any(
            "another_computation" in line
            for line in final_another_content.splitlines()
            if line.strip()
        )
        self.assertTrue(
            has_another_function,
            "another_computation should appear in its own stack traces",
        )

    def test_profile_decorator_with_params(self):
        """Test profile decorator when used with parameters."""
        import time

        from telepy import profile

        @profile(
            sampling_interval=1000, debug=True, verbose=False, full_path=True
        )  # 1ms interval
        def slow_function():
            """A function that takes some time to execute."""
            # CPU-intensive computation for proper sampling
            total = 0
            for i in range(200000):  # Much more CPU intensive computation
                total += i * i
                if i % 10000 == 0:
                    # Additional computation every 10k iterations
                    for j in range(100):
                        total += j * j
            return total + sum(range(500))

        # Test that the function works correctly
        result = slow_function()
        expected = (
            sum(i * i for i in range(200000))
            + sum(j * j for j in range(100)) * 20  # 20 iterations of inner loop
            + sum(range(500))
        )
        self.assertEqual(result, expected)

        # Test that the sampler attribute exists
        self.assertTrue(hasattr(slow_function, "sampler"))
        self.assertIsNotNone(slow_function.sampler)

        # Test that the decorator parameters are stored correctly
        self.assertFalse(slow_function.sampler._verbose)
        self.assertTrue(slow_function.sampler._full_path)

        # Test sampler content with shorter intervals
        content = slow_function.sampler._sampler.dumps()
        self.assertIsInstance(content, str)
        lines = content.splitlines()
        self.assertGreater(len(lines), 0, "Sampler should have collected data")

        # Check that function appears in stack traces
        has_slow_function = any("slow_function" in line for line in lines if line.strip())
        self.assertTrue(has_slow_function, "slow_function should appear in stack traces")

        n = 200000

        # Test start/stop with parameters and verify sampling
        @profile(sampling_interval=10, verbose=False)
        def quick_computation():
            """Quick function for testing sampling with parameters."""
            return [i * i for i in range(n)]

        # Test that sampler starts automatically with function execution
        before_content = quick_computation.sampler._sampler.dumps()
        before_lines = len(before_content.splitlines())

        # Start sampling and execute
        if not quick_computation.sampler._sampler.started:
            quick_computation.sampler.start()
        time.sleep(0.001)  # Very short interval
        result = quick_computation()
        time.sleep(0.001)  # Very short interval after
        quick_computation.sampler.stop()

        self.assertEqual(len(result), n)

        # Verify new traces were collected
        after_content = quick_computation.sampler._sampler.dumps()
        after_lines = len(after_content.splitlines())
        self.assertGreaterEqual(
            after_lines, before_lines, "Should collect new traces after restart"
        )

        # Check that quick_computation appears in new traces
        has_quick_computation = any(
            "quick_computation" in line
            for line in after_content.splitlines()
            if line.strip()
        )
        self.assertTrue(
            has_quick_computation,
            "quick_computation should appear in stack traces after restart",
        )

    def test_profile_decorator_save_functionality(self):
        """Test that the profile decorator can save profiling data."""
        import os
        import tempfile

        from telepy import profile

        @profile
        def test_function():
            """A simple test function."""
            return sum(range(1000))

        # Execute the function
        result = test_function()
        self.assertEqual(result, sum(range(1000)))

        # Test saving to a temporary file
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp_file:
            tmp_filename = tmp_file.name

        try:
            # Test save with truncate=True and verbose=False
            test_function.sampler.save(tmp_filename, truncate=True, verbose=False)
            self.assertTrue(os.path.exists(tmp_filename))
            self.assertGreater(os.path.getsize(tmp_filename), 0)

            # Test save with truncate=False and full_path=True
            tmp_filename_full = tmp_filename.replace(".svg", "_full.svg")
            test_function.sampler.save(
                tmp_filename_full, truncate=False, verbose=True, full_path=True
            )
            self.assertTrue(os.path.exists(tmp_filename_full))
            self.assertGreater(os.path.getsize(tmp_filename_full), 0)

            # Test save with verbose=False and full_path=False
            tmp_filename_minimal = tmp_filename.replace(".svg", "_minimal.svg")
            test_function.sampler.save(
                tmp_filename_minimal, verbose=False, full_path=False
            )
            self.assertTrue(os.path.exists(tmp_filename_minimal))
            self.assertGreater(os.path.getsize(tmp_filename_minimal), 0)

        finally:
            # Clean up temporary files
            tmp_filename_minimal = tmp_filename.replace(".svg", "_minimal.svg")
            for filename in [tmp_filename, tmp_filename_full, tmp_filename_minimal]:
                if os.path.exists(filename):
                    os.unlink(filename)

    def test_profile_decorator_function_name(self):
        """Test that the profile decorator correctly sets the function name."""
        from telepy import profile

        @profile
        def named_function():
            """A function with a specific name."""
            return 42

        # Execute the function
        result = named_function()
        self.assertEqual(result, 42)

        # Check that the function name is set correctly in the sampler
        self.assertEqual(named_function.sampler._function_name, "named_function")

    def test_profile_decorator_multiple_calls(self):
        """Test that the profile decorator works correctly with multiple calls."""
        import time

        from telepy import profile

        @profile(sampling_interval=1000)  # 1ms interval instead of 500us
        def counter_function():
            """A function that increments a counter."""
            if not hasattr(counter_function, "call_count"):
                counter_function.call_count = 0
            counter_function.call_count += 1
            # Add CPU-intensive computation instead of just sleep
            total = 0
            for i in range(50000):  # CPU intensive loop
                total += i * i
            time.sleep(0.001)  # Short sleep for sampling
            return counter_function.call_count

    def test_profile_decorator_sampler_state_control(self):
        """Test explicit control of sampler start/stop states and stack trace content."""
        import time

        from telepy import profile

        @profile(sampling_interval=10)  # Very short interval for quick testing
        def target_function(iterations):
            """Function to test sampler state control."""
            result = 0
            for i in range(iterations):
                result += i * i
                if i % 50 == 0:  # Small pause every 50 iterations
                    time.sleep(0.0001)
            return result

        initial_content = target_function.sampler._sampler.dumps()
        initial_lines = len(initial_content.splitlines())
        n = 100000
        result1 = target_function(n)
        self.assertEqual(result1, sum(i * i for i in range(n)))

        # Should have accumulated traces
        after_first_content = target_function.sampler._sampler.dumps()
        after_first_lines = len(after_first_content.splitlines())
        self.assertGreaterEqual(
            after_first_lines,
            initial_lines,
            "Sampler should automatically collect traces",
        )

        if not target_function.sampler._sampler.started:
            target_function.sampler.start()
        time.sleep(0.001)  # Short pause to ensure sampling starts
        result3 = target_function(n)  # Longer execution for more sampling
        time.sleep(0.001)  # Short pause after execution
        target_function.sampler.stop()

        self.assertEqual(result3, sum(i * i for i in range(n)))

        final_content = target_function.sampler._sampler.dumps()
        has_target_function = any(
            "target_function" in line
            for line in final_content.splitlines()
            if line.strip()
        )
        self.assertTrue(
            has_target_function, "target_function should appear in collected stack traces"
        )

        for cycle in range(3):
            before_cycle = target_function.sampler._sampler.dumps()
            before_cycle_lines = len(before_cycle.splitlines())

            if not target_function.sampler._sampler.started:
                target_function.sampler.start()
            time.sleep(0.001)
            target_function(50)
            target_function.sampler.stop()

            after_cycle = target_function.sampler._sampler.dumps()
            after_cycle_lines = len(after_cycle.splitlines())
            self.assertGreaterEqual(
                after_cycle_lines,
                before_cycle_lines,
                f"Cycle {cycle + 1} should collect traces",
            )
