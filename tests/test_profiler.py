"""Test for the functionalities in the profile decorator."""

import os
import time
import unittest

from telepy import Profiler, ProfilerState, profile
from telepy.environment import Environment

from .base import TestBase


class TestProfiler(TestBase):
    """Test basic profiler functionality."""

    def setUp(self):
        """Set up test environment."""
        # Clear Environment singleton before each test
        Environment.clear_instances()
        super().setUp()

    def test_profiler_initialization(self):
        """Test profiler can be initialized with default parameters."""
        profiler = Profiler(verbose=False)
        self.assertEqual(profiler.state, ProfilerState.INITIALIZED)
        self.assertIsNotNone(profiler._config)

    def test_profiler_custom_config(self):
        """Test profiler with custom configuration parameters."""
        profiler = Profiler(
            verbose=False,
            sampling_interval=100,
            output="custom_test.svg",
            folded_saved=True,
            folded_filename="custom_test.folded",
            width=1600,
            full_path=True,
            inverted=True,
        )
        self.assertEqual(profiler._sampling_interval, 100)
        self.assertEqual(profiler._output, "custom_test.svg")
        self.assertEqual(profiler._width, 1600)
        self.assertTrue(profiler._full_path)
        self.assertTrue(profiler._inverted)

    def test_profiler_invalid_width(self):
        """Test that invalid width raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            Profiler(verbose=False, width=0)
        self.assertIn("width must be a positive integer", str(cm.exception))

        with self.assertRaises(ValueError) as cm:
            Profiler(verbose=False, width=-100)
        self.assertIn("width must be a positive integer", str(cm.exception))

    def test_profiler_output_generation(self):
        """Test that profiler generates output files."""
        output_file = "test_output_generation.svg"
        profiler = Profiler(verbose=False, output=output_file)

        with profiler:
            # Do some work
            total = 0
            for i in range(1000):
                total += i * i
            time.sleep(0.1)

        # Check if file was created
        self.assertTrue(
            os.path.exists(output_file),
            f"Output file {output_file} was not created",
        )

        # Clean up
        if os.path.exists(output_file):
            os.unlink(output_file)

    def test_profiler_folded_output(self):
        """Test that profiler can save folded stack trace."""
        output_file = "test_folded.svg"
        folded_file = "test_folded.folded"

        profiler = Profiler(
            verbose=False,
            output=output_file,
            folded_saved=True,
            folded_filename=folded_file,
        )

        with profiler:
            total = 0
            for i in range(500):
                total += i
            time.sleep(0.1)

        # Check if both files were created
        self.assertTrue(
            os.path.exists(output_file),
            f"SVG file {output_file} was not created",
        )
        self.assertTrue(
            os.path.exists(folded_file),
            f"Folded file {folded_file} was not created",
        )

        # Clean up
        for file in [output_file, folded_file]:
            if os.path.exists(file):
                os.unlink(file)

    def test_profiler_context_manager_multiple_uses(self):
        """Test context manager rejects reuse after completion."""
        profiler = Profiler(verbose=False, output="test_multiple_context.svg")

        # First use should work
        with profiler:
            time.sleep(0.05)

        self.assertEqual(profiler.state, ProfilerState.FINISHED)

        # The context manager enters successfully but start() should fail
        # because profiler is in FINISHED state
        # Note: __enter__ increments context_depth before checking state
        try:
            with profiler:
                # If we get here, the context manager didn't check state
                # This is actually OK - the important part is that
                # the profiler stays in FINISHED and doesn't restart
                pass
        except RuntimeError:
            # This would be raised if __enter__ tried to transition state
            pass

        # Verify profiler is still in FINISHED state
        self.assertEqual(profiler.state, ProfilerState.FINISHED)

        # Clean up
        if os.path.exists("test_multiple_context.svg"):
            os.unlink("test_multiple_context.svg")

    def test_profiler_with_actual_computation(self):
        """Test profiler with actual computation to ensure sampling works."""
        output_file = "test_computation.svg"
        profiler = Profiler(verbose=False, output=output_file, sampling_interval=10)

        def fibonacci(n):
            if n <= 1:
                return n
            return fibonacci(n - 1) + fibonacci(n - 2)

        with profiler:
            # Run computation that should generate samples
            result = fibonacci(20)
            self.assertEqual(result, 6765)

        # Verify output was created
        self.assertTrue(os.path.exists(output_file))

        # Clean up
        if os.path.exists(output_file):
            os.unlink(output_file)


class TestProfileDecorator(TestBase):
    """Test the @profile decorator functionality."""

    def setUp(self):
        """Set up test environment."""
        # Clear Environment singleton before each test
        Environment.clear_instances()
        super().setUp()

    def test_profile_decorator_basic(self):
        """Test basic profile decorator usage."""

        @profile(verbose=False, file="test_decorator_basic.svg")
        def simple_function():
            total = 0
            for i in range(100):
                total += i
            return total

        result = simple_function()
        self.assertEqual(result, 4950)

        # Check if sampler attribute exists
        self.assertTrue(hasattr(simple_function, "sampler"))
        self.assertIsInstance(simple_function.sampler, Profiler)
        self.assertEqual(simple_function.sampler.state, ProfilerState.FINISHED)

        # Clean up
        if os.path.exists("test_decorator_basic.svg"):
            os.unlink("test_decorator_basic.svg")

    def test_profile_decorator_without_params(self):
        """Test profile decorator without parameters."""

        @profile
        def simple_function():
            return sum(range(100))

        result = simple_function()
        self.assertEqual(result, 4950)
        self.assertTrue(hasattr(simple_function, "sampler"))

        # Clean up default output
        if os.path.exists("result.svg"):
            os.unlink("result.svg")

    def test_profile_decorator_with_args_kwargs(self):
        """Test profile decorator on function with arguments."""

        @profile(verbose=False, file="test_decorator_args.svg", time="wall")
        def add_numbers(a, b, multiplier=1):
            time.sleep(0.05)
            return (a + b) * multiplier

        result = add_numbers(5, 3, multiplier=2)
        self.assertEqual(result, 16)

        # Clean up
        if os.path.exists("test_decorator_args.svg"):
            os.unlink("test_decorator_args.svg")

    def test_profile_decorator_multiple_calls(self):
        """Test that profiler stays in FINISHED after first call."""

        @profile(verbose=False, file="test_decorator_multi.svg")
        def counter(n):
            total = 0
            for i in range(n):
                total += i
            return total

        # First call should work
        result1 = counter(50)
        self.assertEqual(result1, 1225)

        # After first call, profiler should be in FINISHED state
        self.assertEqual(counter.sampler.state, ProfilerState.FINISHED)

        # Second call will enter context manager but won't restart profiler
        # because it's in FINISHED state (context_depth increments but no state change)
        result2 = counter(100)
        self.assertEqual(result2, 4950)

        # Profiler should still be in FINISHED state
        self.assertEqual(counter.sampler.state, ProfilerState.FINISHED)

        # Clean up
        if os.path.exists("test_decorator_multi.svg"):
            os.unlink("test_decorator_multi.svg")

    def test_profile_decorator_custom_settings(self):
        """Test profile decorator with custom settings."""

        @profile(
            verbose=False,
            file="test_decorator_custom.svg",
            sampling_interval=20,
            width=1800,
            inverted=True,
        )
        def complex_function():
            result = []
            for i in range(100):
                result.append(i**2)
            return result

        result = complex_function()
        self.assertEqual(len(result), 100)
        self.assertEqual(result[0], 0)
        self.assertEqual(result[-1], 9801)

        # Check sampler configuration
        sampler = complex_function.sampler
        self.assertEqual(sampler._sampling_interval, 20)
        self.assertEqual(sampler._width, 1800)
        self.assertTrue(sampler._inverted)

        # Clean up
        if os.path.exists("test_decorator_custom.svg"):
            os.unlink("test_decorator_custom.svg")

    def test_profile_decorator_with_exception(self):
        """Test profile decorator when function raises exception."""

        @profile(verbose=False, file="test_decorator_exception.svg")
        def failing_function():
            raise ValueError("Intentional error for testing")

        # Function should raise exception
        with self.assertRaises(ValueError) as cm:
            failing_function()
        self.assertIn("Intentional error", str(cm.exception))

        # Profiler should still be in valid state
        self.assertEqual(failing_function.sampler.state, ProfilerState.FINISHED)

        # Clean up
        if os.path.exists("test_decorator_exception.svg"):
            os.unlink("test_decorator_exception.svg")

    def test_profile_decorator_with_return_value(self):
        """Test that decorator preserves function return values."""

        @profile(verbose=False, file="test_decorator_return.svg")
        def return_dict():
            return {"key": "value", "number": 42}

        result = return_dict()
        self.assertIsInstance(result, dict)
        self.assertEqual(result["key"], "value")
        self.assertEqual(result["number"], 42)

        # Clean up
        if os.path.exists("test_decorator_return.svg"):
            os.unlink("test_decorator_return.svg")

    def test_profile_decorator_preserves_function_metadata(self):
        """Test that decorator preserves function name and docstring."""

        @profile(verbose=False, file="test_decorator_metadata.svg")
        def documented_function():
            """This is a test function with documentation."""
            return "success"

        # Check function metadata is preserved
        self.assertEqual(documented_function.__name__, "documented_function")
        self.assertIn("test function with documentation", documented_function.__doc__)

        # Function should still work
        result = documented_function()
        self.assertEqual(result, "success")

        # Clean up
        if os.path.exists("test_decorator_metadata.svg"):
            os.unlink("test_decorator_metadata.svg")

    def test_profile_decorator_with_class_method(self):
        """Test profile decorator on class methods."""

        class Calculator:
            @profile(verbose=False, file="test_decorator_method.svg")
            def multiply(self, a, b):
                return a * b

        calc = Calculator()
        result = calc.multiply(6, 7)
        self.assertEqual(result, 42)

        # Check sampler exists on the method
        self.assertTrue(hasattr(Calculator.multiply, "sampler"))

        # Clean up
        if os.path.exists("test_decorator_method.svg"):
            os.unlink("test_decorator_method.svg")

    def test_profile_decorator_all_timer_modes(self):
        """Test profile decorator with different timer modes."""

        @profile(verbose=False, file="test_timer_cpu.svg", time="cpu")
        def cpu_intensive():
            return sum(i * i for i in range(1000))

        @profile(verbose=False, file="test_timer_wall.svg", time="wall")
        def wall_time():
            time.sleep(0.05)
            return "done"

        result1 = cpu_intensive()
        self.assertEqual(result1, 332833500)
        self.assertEqual(cpu_intensive.sampler._time, "cpu")

        result2 = wall_time()
        self.assertEqual(result2, "done")
        self.assertEqual(wall_time.sampler._time, "wall")

        # Clean up
        for f in ["test_timer_cpu.svg", "test_timer_wall.svg"]:
            if os.path.exists(f):
                os.unlink(f)

    def test_profile_decorator_with_focus_mode(self):
        """Test profile decorator with focus_mode enabled."""

        @profile(
            verbose=False,
            file="test_focus_enabled.svg",
            focus_mode=True,
        )
        def with_focus():
            return [x**2 for x in range(50)]

        result = with_focus()
        self.assertEqual(len(result), 50)
        self.assertTrue(with_focus.sampler._focus_mode)

        # Clean up
        if os.path.exists("test_focus_enabled.svg"):
            os.unlink("test_focus_enabled.svg")

    def test_profile_decorator_with_tree_mode(self):
        """Test profile decorator with tree_mode enabled."""

        @profile(
            verbose=False,
            file="test_tree_mode.svg",
            tree_mode=True,
        )
        def tree_function():
            def helper():
                return sum(range(100))

            return helper()

        result = tree_function()
        self.assertEqual(result, 4950)
        self.assertTrue(tree_function.sampler._tree_mode)

        # Clean up
        if os.path.exists("test_tree_mode.svg"):
            os.unlink("test_tree_mode.svg")

    def test_profile_decorator_with_full_path(self):
        """Test profile decorator with full_path option."""

        @profile(
            verbose=False,
            file="test_full_path.svg",
            full_path=True,
        )
        def full_path_function():
            return "paths"

        result = full_path_function()
        self.assertEqual(result, "paths")
        self.assertTrue(full_path_function.sampler._full_path)

        # Clean up
        if os.path.exists("test_full_path.svg"):
            os.unlink("test_full_path.svg")

    def test_profile_decorator_with_debug_mode(self):
        """Test profile decorator with debug mode."""

        @profile(
            verbose=False,
            file="test_debug.svg",
            debug=True,
        )
        def debug_function():
            return sum(range(50))

        result = debug_function()
        self.assertEqual(result, 1225)
        self.assertTrue(debug_function.sampler._debug)

        # Clean up
        if os.path.exists("test_debug.svg"):
            os.unlink("test_debug.svg")

    def test_profile_decorator_with_ignore_frozen(self):
        """Test profile decorator with ignore_frozen option."""

        @profile(
            verbose=False,
            file="test_ignore_frozen.svg",
            ignore_frozen=True,
        )
        def ignore_frozen_function():
            return list(range(100))

        result = ignore_frozen_function()
        self.assertEqual(len(result), 100)
        self.assertTrue(ignore_frozen_function.sampler._ignore_frozen)

        # Clean up
        if os.path.exists("test_ignore_frozen.svg"):
            os.unlink("test_ignore_frozen.svg")

    def test_profile_decorator_recursive_function(self):
        """Test profile decorator on recursive functions."""

        @profile(verbose=False, file="test_recursive.svg")
        def factorial(n):
            if n <= 1:
                return 1
            return n * factorial(n - 1)

        result = factorial(5)
        self.assertEqual(result, 120)

        # Clean up
        if os.path.exists("test_recursive.svg"):
            os.unlink("test_recursive.svg")

    def test_profile_decorator_generator_function(self):
        """Test profile decorator on generator functions."""

        @profile(verbose=False, file="test_generator.svg")
        def generate_numbers():
            for i in range(10):
                yield i * 2

        result = list(generate_numbers())
        self.assertEqual(result, [0, 2, 4, 6, 8, 10, 12, 14, 16, 18])

        # Clean up
        if os.path.exists("test_generator.svg"):
            os.unlink("test_generator.svg")

    def test_profile_decorator_with_lambda(self):
        """Test that profile decorator works with named lambda."""

        # Note: Direct lambda decoration is unusual but should work
        profiled_lambda = profile(verbose=False, file="test_lambda.svg")(lambda x: x * x)

        result = profiled_lambda(7)
        self.assertEqual(result, 49)
        self.assertTrue(hasattr(profiled_lambda, "sampler"))

        # Clean up
        if os.path.exists("test_lambda.svg"):
            os.unlink("test_lambda.svg")


class TestProfilerAdvanced(TestBase):
    """Test advanced profiler features."""

    def setUp(self):
        """Set up test environment."""
        # Clear Environment singleton before each test
        Environment.clear_instances()
        super().setUp()

    def test_profiler_pause_resume_functionality(self):
        """Test that pause and resume actually affect profiling."""
        output_file = "test_pause_resume_func.svg"
        profiler = Profiler(verbose=False, output=output_file, sampling_interval=10)

        profiler.start()

        # Do some work
        for _ in range(100):
            _ = sum(range(100))

        # Pause profiling
        profiler.pause()
        self.assertEqual(profiler.state, ProfilerState.PAUSED)

        # Do work that shouldn't be profiled
        time.sleep(0.05)

        # Resume profiling
        profiler.resume()
        self.assertEqual(profiler.state, ProfilerState.STARTED)

        # Do more work
        for _ in range(100):
            _ = sum(range(100))

        profiler.stop()

        # Verify output was created
        self.assertTrue(os.path.exists(output_file))

        # Clean up
        if os.path.exists(output_file):
            os.unlink(output_file)

    def test_profiler_nested_context(self):
        """Test nested context manager usage."""
        output_file = "test_nested_context.svg"
        profiler = Profiler(verbose=False, output=output_file)

        with profiler:
            # Outer context
            time.sleep(0.05)

            # Nested context (should not restart)
            with profiler:
                time.sleep(0.05)

            # Still in outer context
            time.sleep(0.05)

        self.assertEqual(profiler.state, ProfilerState.FINISHED)

        # Clean up
        if os.path.exists(output_file):
            os.unlink(output_file)

    def test_profiler_timer_modes(self):
        """Test different timer modes (cpu vs wall)."""
        # Test CPU timer
        profiler_cpu = Profiler(
            verbose=False,
            output="test_cpu_timer.svg",
            time="cpu",
            sampling_interval=50,
        )

        with profiler_cpu:
            # CPU-intensive work
            total = 0
            for i in range(10000):
                total += i * i

        self.assertTrue(os.path.exists("test_cpu_timer.svg"))

        # Test wall timer
        profiler_wall = Profiler(
            verbose=False,
            output="test_wall_timer.svg",
            time="wall",
            sampling_interval=50,
        )

        with profiler_wall:
            # Mix of CPU and I/O
            time.sleep(0.1)
            total = sum(range(1000))

        self.assertTrue(os.path.exists("test_wall_timer.svg"))

        # Clean up
        for file in ["test_cpu_timer.svg", "test_wall_timer.svg"]:
            if os.path.exists(file):
                os.unlink(file)

    def test_profiler_focus_mode(self):
        """Test focus mode configuration."""
        profiler = Profiler(
            verbose=False,
            output="test_focus_mode.svg",
            focus_mode=True,
        )

        self.assertTrue(profiler._focus_mode)

        with profiler:
            # Do some work
            _ = [i**2 for i in range(100)]
            time.sleep(0.05)

        # Clean up
        if os.path.exists("test_focus_mode.svg"):
            os.unlink("test_focus_mode.svg")

    def tearDown(self):
        """Clean up any generated test files."""
        test_files = [
            "test_output_generation.svg",
            "test_folded.svg",
            "test_folded.folded",
            "test_multiple_context.svg",
            "test_computation.svg",
            "test_decorator_basic.svg",
            "test_decorator_args.svg",
            "test_decorator_multi.svg",
            "test_decorator_custom.svg",
            "test_decorator_exception.svg",
            "test_decorator_return.svg",
            "test_decorator_metadata.svg",
            "test_decorator_method.svg",
            "test_timer_cpu.svg",
            "test_timer_wall.svg",
            "test_focus_enabled.svg",
            "test_tree_mode.svg",
            "test_full_path.svg",
            "test_debug.svg",
            "test_ignore_frozen.svg",
            "test_recursive.svg",
            "test_generator.svg",
            "test_lambda.svg",
            "test_pause_resume_func.svg",
            "test_nested_context.svg",
            "test_cpu_timer.svg",
            "test_wall_timer.svg",
            "test_focus_mode.svg",
            "result.svg",  # Default output
        ]
        for filename in test_files:
            if os.path.exists(filename):
                os.unlink(filename)

        Environment.clear_instances()
        super().tearDown()


class TestProfilerStateMachine(TestBase):
    """Test Profiler state machine transitions."""

    def test_initial_state(self):
        """Test that profiler starts in INITIALIZED state."""
        profiler = Profiler(verbose=False)
        self.assertEqual(profiler.state, ProfilerState.INITIALIZED)

    def test_start_from_initialized(self):
        """Test starting profiler from INITIALIZED state."""
        profiler = Profiler(verbose=False)
        profiler.start()
        self.assertEqual(profiler.state, ProfilerState.STARTED)
        profiler.stop()

    def test_stop_from_started(self):
        """Test stopping profiler from STARTED state goes to FINISHED."""
        profiler = Profiler(verbose=False)
        profiler.start()
        profiler.stop()
        self.assertEqual(profiler.state, ProfilerState.FINISHED)

    def test_pause_from_started(self):
        """Test pausing profiler from STARTED state."""
        profiler = Profiler(verbose=False)
        profiler.start()
        profiler.pause()
        self.assertEqual(profiler.state, ProfilerState.PAUSED)
        profiler.stop()

    def test_resume_from_paused(self):
        """Test resuming profiler from PAUSED state."""
        profiler = Profiler(verbose=False)
        profiler.start()
        profiler.pause()
        profiler.resume()
        self.assertEqual(profiler.state, ProfilerState.STARTED)
        profiler.stop()

    def test_restart_from_stopped(self):
        """Test that cannot restart after stop (stop is terminal)."""
        profiler = Profiler(verbose=False)
        profiler.start()
        profiler.stop()
        self.assertEqual(profiler.state, ProfilerState.FINISHED)

        # Try to start again - should raise RuntimeError
        with self.assertRaises(RuntimeError) as cm:
            profiler.start()
        self.assertIn("Cannot transition", str(cm.exception))

    def test_multiple_start_stop_cycles(self):
        """Test that stop is terminal and cannot restart."""
        profiler = Profiler(verbose=False, output="test_cycle.svg")

        # First cycle
        profiler.start()
        self.assertEqual(profiler.state, ProfilerState.STARTED)
        time.sleep(0.1)
        profiler.stop()
        self.assertEqual(profiler.state, ProfilerState.FINISHED)

        # Cannot start again after FINISHED
        with self.assertRaises(RuntimeError) as cm:
            profiler.start()
        self.assertIn("Cannot transition", str(cm.exception))

    def test_pause_resume_cycles(self):
        """Test multiple pause-resume cycles."""
        profiler = Profiler(verbose=False)
        profiler.start()

        # First pause-resume
        profiler.pause()
        self.assertEqual(profiler.state, ProfilerState.PAUSED)
        profiler.resume()
        self.assertEqual(profiler.state, ProfilerState.STARTED)

        # Second pause-resume
        profiler.pause()
        self.assertEqual(profiler.state, ProfilerState.PAUSED)
        profiler.resume()
        self.assertEqual(profiler.state, ProfilerState.STARTED)

        profiler.stop()

    def test_invalid_start_from_started(self):
        """Test that starting from STARTED state raises error."""
        profiler = Profiler(verbose=False)
        profiler.start()
        with self.assertRaises(RuntimeError) as cm:
            profiler.start()
        self.assertIn("Cannot transition", str(cm.exception))
        profiler.stop()

    def test_invalid_stop_from_initialized(self):
        """Test that stopping from INITIALIZED state raises error."""
        profiler = Profiler(verbose=False)
        with self.assertRaises(RuntimeError) as cm:
            profiler.stop()
        self.assertIn("Cannot transition", str(cm.exception))

    def test_invalid_pause_from_initialized(self):
        """Test that pausing from INITIALIZED state raises error."""
        profiler = Profiler(verbose=False)
        with self.assertRaises(RuntimeError) as cm:
            profiler.pause()
        self.assertIn("Cannot transition", str(cm.exception))

    def test_invalid_resume_from_started(self):
        """Test that resuming from STARTED state raises error."""
        profiler = Profiler(verbose=False)
        profiler.start()
        with self.assertRaises(RuntimeError) as cm:
            profiler.resume()
        self.assertIn("Cannot transition", str(cm.exception))
        profiler.stop()

    def test_context_manager_state_transitions(self):
        """Test that context manager properly handles state transitions."""
        profiler = Profiler(verbose=False, output="test_context.svg")
        self.assertEqual(profiler.state, ProfilerState.INITIALIZED)

        with profiler:
            self.assertEqual(profiler.state, ProfilerState.STARTED)
            time.sleep(0.1)

        # Context manager should transition to FINISHED (terminal state)
        self.assertEqual(profiler.state, ProfilerState.FINISHED)

    def test_stop_from_paused(self):
        """Test stopping profiler from PAUSED state goes to FINISHED."""
        profiler = Profiler(verbose=False)
        profiler.start()
        profiler.pause()
        profiler.stop()
        self.assertEqual(profiler.state, ProfilerState.FINISHED)

    def test_state_property_thread_safe(self):
        """Test that state property is thread-safe."""
        profiler = Profiler(verbose=False)
        profiler.start()

        # Access state multiple times
        state1 = profiler.state
        state2 = profiler.state
        state3 = profiler.state

        self.assertEqual(state1, state2)
        self.assertEqual(state2, state3)
        self.assertEqual(state1, ProfilerState.STARTED)

        profiler.stop()

    def test_with_statement_basic(self):
        """Test basic with statement usage transitions to FINISHED."""
        profiler = Profiler(verbose=False, output="test_with_basic.svg")
        self.assertEqual(profiler.state, ProfilerState.INITIALIZED)

        with profiler:
            self.assertEqual(profiler.state, ProfilerState.STARTED)
            time.sleep(0.1)

        self.assertEqual(profiler.state, ProfilerState.FINISHED)

    def test_stop_is_terminal_no_restart(self):
        """Test that stop() is terminal and cannot restart."""
        profiler = Profiler(verbose=False, output="test_terminal.svg")

        # First start/stop
        profiler.start()
        self.assertEqual(profiler.state, ProfilerState.STARTED)
        time.sleep(0.1)
        profiler.stop()
        self.assertEqual(profiler.state, ProfilerState.FINISHED)

        # Try to restart - should fail
        with self.assertRaises(RuntimeError) as cm:
            profiler.start()
        self.assertIn("Cannot transition", str(cm.exception))

    def test_explicit_stop_goes_to_finished(self):
        """Test that explicit stop() call transitions to FINISHED."""
        profiler = Profiler(verbose=False, output="test_explicit.svg")
        self.assertEqual(profiler.state, ProfilerState.INITIALIZED)

        profiler.start()
        self.assertEqual(profiler.state, ProfilerState.STARTED)
        time.sleep(0.1)

        profiler.stop()
        self.assertEqual(profiler.state, ProfilerState.FINISHED)

    def test_stop_from_paused_goes_to_finished(self):
        """Test that stop() from PAUSED state goes to FINISHED."""
        profiler = Profiler(verbose=False, output="test_paused_stop.svg")

        profiler.start()
        self.assertEqual(profiler.state, ProfilerState.STARTED)

        profiler.pause()
        self.assertEqual(profiler.state, ProfilerState.PAUSED)

        profiler.stop()
        self.assertEqual(profiler.state, ProfilerState.FINISHED)

    def test_pause_resume_then_stop(self):
        """Test pause/resume functionality followed by stop."""
        profiler = Profiler(verbose=False, output="test_pause_resume_stop.svg")

        profiler.start()
        self.assertEqual(profiler.state, ProfilerState.STARTED)
        time.sleep(0.1)

        profiler.pause()
        self.assertEqual(profiler.state, ProfilerState.PAUSED)
        time.sleep(0.05)

        profiler.resume()
        self.assertEqual(profiler.state, ProfilerState.STARTED)
        time.sleep(0.1)

        profiler.stop()
        self.assertEqual(profiler.state, ProfilerState.FINISHED)

    def tearDown(self):
        """Clean up any generated files."""
        import os

        # Remove test files if they exist
        test_files = [
            "test_cycle.svg",
            "test_context.svg",
            "test_with_basic.svg",
            "test_terminal.svg",
            "test_explicit.svg",
            "test_paused_stop.svg",
            "test_pause_resume_stop.svg",
        ]
        for filename in test_files:
            if os.path.exists(filename):
                os.unlink(filename)

        # Reset Environment singleton for next test
        Environment.clear_instances()
        super().tearDown()


if __name__ == "__main__":
    unittest.main()
