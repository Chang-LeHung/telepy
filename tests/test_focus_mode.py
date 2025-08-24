import threading
import time

import telepy

from .base import TestBase  # type: ignore


class TestFocusMode(TestBase):
    """Test cases for focus_mode and regex_patterns functionality."""

    def test_focus_mode_basic(self):
        """Test basic focus_mode functionality."""
        # Test creating sampler with focus_mode enabled
        sampler = telepy.TelepySysSampler(
            sampling_interval=1000,
            focus_mode=True,
            debug=False,
        )

        # Verify the focus_mode attribute is set correctly
        self.assertTrue(sampler.focus_mode)

        # Test that we can change focus_mode
        sampler.focus_mode = False
        self.assertFalse(sampler.focus_mode)

    def test_regex_patterns_basic(self):
        """Test basic regex_patterns functionality."""
        patterns = [r".*test.*\.py$", r".*main.*\.py$"]

        sampler = telepy.TelepySysSampler(
            sampling_interval=1000,
            regex_patterns=patterns,
            debug=False,
        )

        # Verify regex_patterns is set and compiled
        self.assertIsNotNone(sampler.regex_patterns)
        self.assertEqual(len(sampler.regex_patterns), 2)

        # Test that each pattern is a compiled regex
        for pattern in sampler.regex_patterns:
            self.assertTrue(hasattr(pattern, "search"))
            self.assertTrue(hasattr(pattern, "match"))

    def test_invalid_regex_patterns(self):
        """Test handling of invalid regex patterns."""
        invalid_patterns = [r"[invalid(regex"]

        with self.assertRaises(ValueError) as context:
            telepy.TelepySysSampler(
                sampling_interval=1000,
                regex_patterns=invalid_patterns,
                debug=False,
            )

        self.assertIn("Invalid regex pattern", str(context.exception))

    def test_none_regex_patterns(self):
        """Test that None regex_patterns works correctly."""
        sampler = telepy.TelepySysSampler(
            sampling_interval=1000,
            regex_patterns=None,
            debug=False,
        )

        self.assertIsNone(sampler.regex_patterns)

    def test_empty_regex_patterns(self):
        """Test that empty regex_patterns list works correctly."""
        sampler = telepy.TelepySysSampler(
            sampling_interval=1000,
            regex_patterns=[],
            debug=False,
        )

        self.assertIsNone(sampler.regex_patterns)

    def test_async_sampler_focus_mode(self):
        """Test focus_mode with AsyncSampler."""
        async_sampler = telepy.TelepySysAsyncSampler(
            sampling_interval=100,
            focus_mode=True,
            debug=False,
        )

        self.assertTrue(async_sampler.focus_mode)

        # Test setting regex patterns
        patterns = [r".*\.py$"]
        async_sampler.regex_patterns = async_sampler._compile_regex_patterns(patterns)
        self.assertIsNotNone(async_sampler.regex_patterns)
        self.assertEqual(len(async_sampler.regex_patterns), 1)

    def test_focus_mode_with_actual_sampling(self):
        """Test focus_mode with actual sampling to verify filtering works."""

        def simple_function():
            """A simple function to sample."""
            time.sleep(0.01)  # Small delay to ensure sampling
            return sum(range(100))

        # Test with focus_mode disabled (should capture everything)
        sampler_normal = telepy.TelepySysSampler(
            sampling_interval=1000,
            focus_mode=False,
            debug=False,
        )

        sampler_normal.start()
        simple_function()
        sampler_normal.stop()

        normal_output = sampler_normal.dumps()
        sampler_normal.clear()

        # Test with focus_mode enabled (should filter out stdlib)
        sampler_focus = telepy.TelepySysSampler(
            sampling_interval=1000,
            focus_mode=True,
            debug=False,
        )

        sampler_focus.start()
        simple_function()
        sampler_focus.stop()

        focus_output = sampler_focus.dumps()

        # The focus mode output should generally be shorter or different
        # since it filters out standard library calls
        self.assertIsInstance(normal_output, str)
        self.assertIsInstance(focus_output, str)

        # Both should contain our test function
        self.assertIn("simple_function", normal_output)
        self.assertIn("simple_function", focus_output)

        # Normal mode should contain standard library calls
        # Focus mode should filter them out
        stdlib_indicators = ["time.py", "/lib/python", "site-packages"]

        # Check that normal mode might contain stdlib calls
        # (Note: may not always be present depending on sampling timing)

        # Focus mode should definitely not contain stdlib patterns
        for indicator in stdlib_indicators:
            self.assertNotIn(
                indicator, focus_output, f"Focus mode should filter out: {indicator}"
            )

        # Both outputs should contain user code
        self.assertIn("test_focus_mode", normal_output)
        self.assertIn("test_focus_mode", focus_output)

    def test_regex_patterns_with_actual_sampling(self):
        """Test regex_patterns with actual sampling."""

        def test_function():
            """A test function to sample."""
            time.sleep(0.01)
            return 42

        # Only include files with 'test' in the path
        patterns = [r".*test.*"]

        sampler = telepy.TelepySysSampler(
            sampling_interval=1000,
            regex_patterns=patterns,
            debug=False,
        )

        sampler.start()
        test_function()
        sampler.stop()

        output = sampler.dumps()

        # Should contain our test function since this file has 'test' in the name
        self.assertIsInstance(output, str)

    def test_config_integration(self):
        """Test that config properly passes focus_mode and regex_patterns."""
        from telepy.config import TelePySamplerConfig

        config = TelePySamplerConfig(
            focus_mode=True,
            regex_patterns=[r".*\.py$", r".*test.*"],
            interval=1000,
            debug=False,
        )

        self.assertTrue(config.focus_mode)
        self.assertIsNotNone(config.regex_patterns)
        self.assertEqual(len(config.regex_patterns), 2)

    def test_sampler_attribute_setting(self):
        """Test setting attributes directly on sampler."""
        sampler = telepy.TelepySysSampler(sampling_interval=1000)

        # Test setting focus_mode
        sampler.focus_mode = True
        self.assertTrue(sampler.focus_mode)

        # Test setting regex_patterns
        compiled_patterns = sampler._compile_regex_patterns([r".*\.py$"])
        sampler.regex_patterns = compiled_patterns
        self.assertIsNotNone(sampler.regex_patterns)
        self.assertEqual(len(sampler.regex_patterns), 1)

        # Test setting to None
        sampler.regex_patterns = None
        self.assertIsNone(sampler.regex_patterns)


class TestAsyncSamplerFocusMode(TestBase):
    """Test cases specifically for AsyncSampler focus mode functionality."""

    def test_async_sampler_focus_mode_basic(self):
        """Test basic focus_mode functionality with AsyncSampler."""
        sampler = telepy.TelepySysAsyncSampler(
            sampling_interval=100,
            focus_mode=True,
            regex_patterns=[r".*test.*"],
            debug=False,
        )

        self.assertTrue(sampler.focus_mode)
        self.assertIsNotNone(sampler.regex_patterns)
        self.assertEqual(len(sampler.regex_patterns), 1)

    def test_async_sampler_thread_safety(self):
        """Test that focus mode works correctly in threaded environment."""

        def worker_function():
            time.sleep(0.01)
            return threading.current_thread().name

        sampler = telepy.TelepySysAsyncWorkerSampler(
            sampling_interval=100,
            focus_mode=True,
            debug=False,
        )

        sampler.start()

        # This test mainly ensures no crashes occur with threading
        threads = []
        for i in range(3):
            t = threading.Thread(target=worker_function, name=f"Worker-{i}")
            threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        sampler.stop()

        # Verify the sampler is still functional
        self.assertTrue(sampler.focus_mode)
        output = sampler.dumps()
        self.assertIsInstance(output, str)

        # Test focus_mode filtering: should contain user code but not standard library
        # Should contain our test function
        self.assertIn("worker_function", output)

        # Should contain our test file name (since it's user code)
        self.assertIn("test_focus_mode", output)

        # With focus_mode=True, should NOT contain standard library functions
        # These are common stdlib functions that might appear in stack traces
        stdlib_patterns = [
            "threading.py",  # threading module
            "time.py",  # time module
            "/lib/python",  # standard library path
            "site-packages",  # third-party packages
        ]

        for pattern in stdlib_patterns:
            self.assertNotIn(
                pattern, output, f"Focus mode should filter out stdlib pattern: {pattern}"
            )

        # Should contain user code patterns
        user_patterns = [
            "test_focus_mode.py",  # our test file
            "worker_function",  # our test function
        ]

        for pattern in user_patterns:
            self.assertIn(
                pattern, output, f"Focus mode should include user code pattern: {pattern}"
            )
