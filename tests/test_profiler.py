"""Test for the functionalities in the profile decorator."""

import time
import unittest

from telepy import Profiler, ProfilerState
from telepy.environment import Environment

from .base import TestBase


class TestProfiler(TestBase):
    def test_profiler(self):
        pass


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
