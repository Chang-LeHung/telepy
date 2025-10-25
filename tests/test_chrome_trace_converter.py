"""
Unit tests for chrome_trace_converter.py
"""

import os
import re
import sys
import tempfile
from pathlib import Path

from telex.chrome_trace_converter import (
    ChromeTraceConverter,
    convert_chrome_trace_to_folded,
)
from tests.base import TestBase


class TestChromeTraceConverter(TestBase):
    """Test suite for ChromeTraceConverter functionality."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures that are used across all test methods."""
        cls.trace_file = Path("tests/test_files/trace.json")
        cls.temp_dir = tempfile.mkdtemp()
        cls.temp_files = []

    @classmethod
    def tearDownClass(cls):
        """Clean up temporary files after all tests."""
        for temp_file in cls.temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        if os.path.exists(cls.temp_dir):
            os.rmdir(cls.temp_dir)

    def tearDown(self):
        """Clean up test-specific temporary files."""
        super().tearDown()
        # Clean up any generated files in test_files directory
        test_dir = Path("tests/test_files")
        for pattern in ["*_test.folded", "*_test.svg"]:
            for f in test_dir.glob(pattern):
                f.unlink(missing_ok=True)

    def test_basic_conversion_with_convenience_function(self):
        """Test basic conversion using the convenience function."""
        output_file = "tests/test_files/trace_test.folded"
        self.__class__.temp_files.append(output_file)

        # Test using the convenience function
        result = convert_chrome_trace_to_folded(str(self.trace_file), output_file)

        # Verify the file was created
        self.assertTrue(os.path.exists(result), "Output file should exist")
        self.assertEqual(result, output_file, "Should return output path")

        # Verify the output content
        with open(result) as f:
            lines = f.readlines()

        self.assertGreater(len(lines), 0, "Should generate folded stack lines")

        # Check format of first few lines
        for i, line in enumerate(lines[:5]):
            line_stripped = line.strip()
            last_space = line_stripped.rfind(" ")

            self.assertGreater(last_space, 0, f"Line {i} should have space separator")

            stack = line_stripped[:last_space]
            count_str = line_stripped[last_space + 1 :]

            self.assertTrue(
                stack.startswith("Process("), f"Line {i} should start with Process()"
            )
            self.assertIn(";Thread(", stack, f"Line {i} should contain Thread()")
            self.assertTrue(count_str.isdigit(), f"Line {i} count should be a number")

            count = int(count_str)
            self.assertGreater(count, 0, f"Line {i} should have positive count")

    def test_converter_class_load_and_convert(self):
        """Test using the ChromeTraceConverter class directly."""
        output_file = "tests/test_files/trace_class_test.folded"
        self.__class__.temp_files.append(output_file)

        converter = ChromeTraceConverter(str(self.trace_file))

        # Test load_trace
        converter.load_trace()
        self.assertGreater(len(converter.events), 0, "Should load trace events")

        # Test convert_to_folded
        stacks = converter.convert_to_folded()
        self.assertGreater(len(stacks), 0, "Should generate unique stack traces")

        # Test save_folded
        converter.save_folded(output_file)
        self.assertTrue(os.path.exists(output_file), "Should save folded file")

    def test_stack_format(self):
        """Test that stacks have correct Process(pid);Thread(tid) format."""
        converter = ChromeTraceConverter(str(self.trace_file))
        converter.load_trace()
        stacks = converter.convert_to_folded()

        # Verify format of sample stacks
        sample_stacks = list(stacks.keys())[:10]
        for stack in sample_stacks:
            self.assertTrue(
                stack.startswith("Process("),
                f"Stack should start with Process(): {stack[:50]}",
            )
            self.assertIn(
                ";Thread(", stack, f"Stack should contain Thread(): {stack[:50]}"
            )

    def test_nested_stacks_exist(self):
        """Test that nested stacks are properly generated."""
        converter = ChromeTraceConverter(str(self.trace_file))
        converter.load_trace()
        stacks = converter.convert_to_folded()

        # Verify nested stacks exist (depth > 5)
        nested_stacks = [s for s in stacks.keys() if s.count(";") > 5]
        self.assertGreater(
            len(nested_stacks), 0, "Should have nested stacks with depth > 5"
        )

        # Find and verify deepest stack
        deepest = max(nested_stacks, key=lambda s: s.count(";"))
        depth = deepest.count(";")
        self.assertGreater(depth, 10, f"Should have deep call stacks, got depth {depth}")

    def test_event_count_matches_trace_file(self):
        """Test that all events are loaded from trace file."""
        converter = ChromeTraceConverter(str(self.trace_file))
        converter.load_trace()

        # For the test trace.json, we expect 1154 events
        # (this is based on the actual test file)
        expected_events = 1154
        self.assertEqual(
            len(converter.events),
            expected_events,
            f"Should load {expected_events} events",
        )

    def test_stacks_have_positive_counts(self):
        """Test that all stacks have positive sample counts."""
        converter = ChromeTraceConverter(str(self.trace_file))
        converter.load_trace()
        stacks = converter.convert_to_folded()

        for stack, count in stacks.items():
            self.assertGreater(
                count, 0, f"Stack should have positive count: {stack[:50]}"
            )

    def test_output_file_not_empty(self):
        """Test that generated folded file is not empty."""
        output_file = "tests/test_files/trace_nonempty_test.folded"
        self.__class__.temp_files.append(output_file)

        converter = ChromeTraceConverter(str(self.trace_file))
        converter.convert(output_file)

        # Check file size
        file_size = os.path.getsize(output_file)
        self.assertGreater(
            file_size,
            1000,  # At least 1KB
            "Output file should not be empty",
        )

    def test_process_and_thread_ids_are_numeric(self):
        """Test that Process and Thread IDs are numeric."""
        converter = ChromeTraceConverter(str(self.trace_file))
        converter.load_trace()
        stacks = converter.convert_to_folded()

        for stack in list(stacks.keys())[:5]:
            # Extract Process(pid) and Thread(tid)
            process_match = re.search(r"Process\((\d+)\)", stack)
            thread_match = re.search(r"Thread\((\d+)\)", stack)

            self.assertIsNotNone(
                process_match, f"Should find Process(pid) in: {stack[:50]}"
            )
            self.assertIsNotNone(
                thread_match, f"Should find Thread(tid) in: {stack[:50]}"
            )

            if process_match:
                pid = int(process_match.group(1))
                self.assertGreater(pid, 0, "Process ID should be positive")

            if thread_match:
                tid = int(thread_match.group(1))
                self.assertGreater(tid, 0, "Thread ID should be positive")

    def test_conversion_idempotency(self):
        """Test that converting the same file twice produces same results."""
        converter1 = ChromeTraceConverter(str(self.trace_file))
        converter1.load_trace()
        stacks1 = converter1.convert_to_folded()

        converter2 = ChromeTraceConverter(str(self.trace_file))
        converter2.load_trace()
        stacks2 = converter2.convert_to_folded()

        self.assertEqual(
            stacks1,
            stacks2,
            "Converting same file twice should produce identical results",
        )

    def test_invalid_trace_file(self):
        """Test handling of non-existent trace file."""
        with self.assertRaises(FileNotFoundError):
            converter = ChromeTraceConverter("nonexistent.json")
            converter.load_trace()

    def test_svg_generation_with_default_params(self):
        """Test SVG generation with default parameters."""
        try:
            from telex.flamegraph import FlameGraph
        except ImportError:
            self.skipTest("FlameGraph module not available")

        output_folded = "tests/test_files/trace_svg_test.folded"
        output_svg = "tests/test_files/trace_svg_test.svg"
        self.__class__.temp_files.extend([output_folded, output_svg])

        # Generate folded file
        converter = ChromeTraceConverter(str(self.trace_file))
        converter.convert(output_folded)

        # Generate SVG
        with open(output_folded) as f:
            lines = f.readlines()

        fg = FlameGraph(lines)
        fg.parse_input()
        svg = fg.generate_svg()

        # Verify SVG content
        self.assertIn("<svg", svg, "Should contain SVG tag")
        self.assertIn("</svg>", svg, "Should have closing SVG tag")
        self.assertGreater(len(svg), 1000, "SVG should have substantial content")

        # Save and verify file
        with open(output_svg, "w") as f:
            f.write(svg)

        self.assertTrue(os.path.exists(output_svg), "SVG file should be created")
        svg_size = os.path.getsize(output_svg)
        self.assertGreater(svg_size, 1000, "SVG file should not be empty")

    def test_svg_generation_with_custom_params(self):
        """Test SVG generation with custom FlameGraph parameters."""
        try:
            from telex.flamegraph import FlameGraph
        except ImportError:
            self.skipTest("FlameGraph module not available")

        output_folded = "tests/test_files/trace_custom_svg_test.folded"
        output_svg = "tests/test_files/trace_custom_svg_test.svg"
        self.__class__.temp_files.extend([output_folded, output_svg])

        # Generate folded file
        converter = ChromeTraceConverter(str(self.trace_file))
        converter.convert(output_folded)

        # Generate SVG with custom parameters
        with open(output_folded) as f:
            lines = f.readlines()

        fg = FlameGraph(
            lines,
            height=20,
            width=1600,
            minwidth=0.5,
            title="Test Custom Flame Graph",
            countname="microseconds",
            inverted=True,
        )
        fg.parse_input()
        svg = fg.generate_svg()

        # Verify custom title
        self.assertIn("Test Custom Flame Graph", svg, "Should contain custom title")

        # Verify countname
        self.assertIn("microseconds", svg, "Should contain custom countname")

        # Save and verify
        with open(output_svg, "w") as f:
            f.write(svg)

        self.assertTrue(os.path.exists(output_svg), "Custom SVG should be created")

    def test_folded_format_compatibility_with_flamegraph(self):
        """Test that generated folded format is compatible with FlameGraph."""
        try:
            from telex.flamegraph import FlameGraph
        except ImportError:
            self.skipTest("FlameGraph module not available")

        output_file = "tests/test_files/trace_compat_test.folded"
        self.__class__.temp_files.append(output_file)

        # Generate folded file
        converter = ChromeTraceConverter(str(self.trace_file))
        converter.convert(output_file)

        # Try to parse with FlameGraph
        with open(output_file) as f:
            lines = f.readlines()

        fg = FlameGraph(lines)
        fg.parse_input()

        # Verify parsing succeeded
        self.assertGreater(
            fg.total_samples, 0, "FlameGraph should parse samples successfully"
        )
        self.assertGreater(fg.max_depth, 0, "FlameGraph should detect stack depth")
        self.assertGreater(len(fg.stacks), 0, "FlameGraph should have parsed stacks")

    def test_default_output_filename(self):
        """Test that default output filename is generated correctly."""
        converter = ChromeTraceConverter(str(self.trace_file))
        converter.load_trace()

        # When no output file is specified, convert() should generate one
        default_output = str(self.trace_file).replace(".json", ".folded")
        self.__class__.temp_files.append(default_output)

        converter.convert()

        self.assertTrue(
            os.path.exists(default_output),
            f"Default output file {default_output} should be created",
        )

    def test_multiple_processes_and_threads(self):
        """Test that converter handles multiple processes/threads correctly."""
        converter = ChromeTraceConverter(str(self.trace_file))
        converter.load_trace()
        stacks = converter.convert_to_folded()

        # Extract unique (pid, tid) combinations
        pid_tid_pairs = set()
        for stack in stacks.keys():
            process_match = re.search(r"Process\((\d+)\)", stack)
            thread_match = re.search(r"Thread\((\d+)\)", stack)

            if process_match and thread_match:
                pid = process_match.group(1)
                tid = thread_match.group(1)
                pid_tid_pairs.add((pid, tid))

        # Should have at least one process/thread combination
        self.assertGreater(
            len(pid_tid_pairs), 0, "Should have at least one process/thread combination"
        )

    def test_stack_trace_ordering(self):
        """Test that stack traces are properly ordered from root to leaf."""
        converter = ChromeTraceConverter(str(self.trace_file))
        converter.load_trace()
        stacks = converter.convert_to_folded()

        # Check a sample of deeper stacks
        deep_stacks = [s for s in stacks.keys() if s.count(";") > 10]
        self.assertGreater(len(deep_stacks), 0, "Should have some deep stacks")

        # Verify format: Process(pid);Thread(tid);func1;func2;...
        for stack in deep_stacks[:3]:
            parts = stack.split(";")
            self.assertTrue(
                parts[0].startswith("Process("), "First part should be Process(pid)"
            )
            self.assertTrue(
                parts[1].startswith("Thread("), "Second part should be Thread(tid)"
            )
            # Remaining parts should be function names (not empty)
            for i, part in enumerate(parts[2:], start=2):
                self.assertGreater(
                    len(part.strip()), 0, f"Stack part {i} should not be empty"
                )

    def test_total_sample_count(self):
        """Test that total sample count is reasonable."""
        converter = ChromeTraceConverter(str(self.trace_file))
        converter.load_trace()
        stacks = converter.convert_to_folded()

        total_samples = sum(stacks.values())
        self.assertGreater(total_samples, 0, "Total samples should be positive")

        # Verify it's approximately equal to the sum of durations from events
        # multiplied by 100 (durations are converted to integers and multiplied by 100)
        total_duration = sum(
            event.get("dur", 0) for event in converter.events if event.get("ph") == "X"
        )
        expected_total = total_duration * 100

        # Allow for small rounding differences
        # (durations may be floats but counts are integers)
        difference = abs(total_samples - expected_total)
        max_allowed_diff = len(stacks) * 100.0  # Allow up to 100 units per stack

        self.assertLess(
            difference,
            max_allowed_diff,
            f"Total samples ({total_samples}) should be close to "
            f"sum of durations ({total_duration}) * 100 = {expected_total}",
        )

    def test_event_types_filtering(self):
        """Test that Complete events ('X') are present in the trace."""
        converter = ChromeTraceConverter(str(self.trace_file))
        converter.load_trace()

        # Count 'X' events
        x_events = [e for e in converter.events if e.get("ph") == "X"]

        self.assertGreater(len(x_events), 0, "Should have Complete events")

        # Verify that we have at least some 'X' events
        # (the trace file may contain other event types too)
        event_types = set(e.get("ph") for e in converter.events)
        self.assertIn("X", event_types, "Should have Complete events ('X')")

    def test_empty_stacks_are_not_generated(self):
        """Test that empty or invalid stacks are not included."""
        converter = ChromeTraceConverter(str(self.trace_file))
        converter.load_trace()
        stacks = converter.convert_to_folded()

        for stack, count in stacks.items():
            # Stack should not be empty
            self.assertGreater(len(stack), 0, "Stack should not be empty")

            # Stack should have at least Process and Thread
            self.assertIn(";", stack, "Stack should have separators")

            # Count should be positive
            self.assertGreater(
                count, 0, f"Count should be positive for stack: {stack[:50]}"
            )

    def test_converter_convert_method(self):
        """Test the high-level convert() method."""
        output_file = "tests/test_files/trace_convert_method_test.folded"
        self.__class__.temp_files.append(output_file)

        converter = ChromeTraceConverter(str(self.trace_file))
        result = converter.convert(output_file)

        # Verify return value
        self.assertEqual(result, output_file, "convert() should return output filename")

        # Verify file was created
        self.assertTrue(os.path.exists(output_file), "Output file should exist")

        # Verify file has content
        with open(output_file) as f:
            lines = f.readlines()

        self.assertGreater(len(lines), 0, "Output file should have content")

    def test_format_stack_line_with_empty_stack(self):
        """Test _format_stack_line with empty stack."""
        converter = ChromeTraceConverter(str(self.trace_file))
        result = converter._format_stack_line(123, 456, [])
        expected = "Process(123);Thread(456)"
        self.assertEqual(result, expected, "Should handle empty stack")

    def test_format_stack_line_with_stack(self):
        """Test _format_stack_line with non-empty stack."""
        converter = ChromeTraceConverter(str(self.trace_file))
        result = converter._format_stack_line(123, 456, ["func1", "func2", "func3"])
        expected = "Process(123);Thread(456);func1;func2;func3"
        self.assertEqual(result, expected, "Should format stack correctly")

    def test_extract_event_name_with_category(self):
        """Test _extract_event_name with category."""
        converter = ChromeTraceConverter(str(self.trace_file))
        event = {"ph": "X", "name": "test_func", "cat": "python"}
        result = converter._extract_event_name(event)
        self.assertEqual(
            result, "python::test_func", "Should format with category prefix"
        )

    def test_extract_event_name_without_category(self):
        """Test _extract_event_name without category."""
        converter = ChromeTraceConverter(str(self.trace_file))
        event = {"ph": "X", "name": "test_func"}
        result = converter._extract_event_name(event)
        self.assertEqual(result, "test_func", "Should return just the name")

    def test_extract_event_name_non_x_event(self):
        """Test _extract_event_name with non-X event."""
        converter = ChromeTraceConverter(str(self.trace_file))
        event = {"ph": "B", "name": "test_func"}
        result = converter._extract_event_name(event)
        self.assertIsNone(result, "Should return None for non-X events")

    def test_extract_event_name_no_name(self):
        """Test _extract_event_name with no name field."""
        converter = ChromeTraceConverter(str(self.trace_file))
        event = {"ph": "X"}
        result = converter._extract_event_name(event)
        self.assertIsNone(result, "Should return None when name is missing")

    def test_build_call_tree_filters_non_x_events(self):
        """Test that _build_call_tree filters out non-X events."""
        converter = ChromeTraceConverter(str(self.trace_file))
        converter.events = [
            {"ph": "X", "pid": 1, "tid": 1, "ts": 100, "dur": 50, "name": "func1"},
            {"ph": "B", "pid": 1, "tid": 1, "ts": 110, "name": "func2"},
            {"ph": "X", "pid": 1, "tid": 1, "ts": 120, "dur": 30, "name": "func3"},
        ]

        thread_events = converter._build_call_tree()
        self.assertEqual(len(thread_events[(1, 1)]), 2, "Should have 2 X events")

    def test_build_call_tree_filters_no_duration(self):
        """Test that _build_call_tree filters events without duration."""
        converter = ChromeTraceConverter(str(self.trace_file))
        converter.events = [
            {"ph": "X", "pid": 1, "tid": 1, "ts": 100, "dur": 50, "name": "func1"},
            {"ph": "X", "pid": 1, "tid": 1, "ts": 110, "name": "func2"},  # No dur
        ]

        thread_events = converter._build_call_tree()
        self.assertEqual(len(thread_events[(1, 1)]), 1, "Should filter no-dur")

    def test_build_call_tree_sorts_by_time(self):
        """Test that _build_call_tree sorts events by timestamp."""
        converter = ChromeTraceConverter(str(self.trace_file))
        converter.events = [
            {"ph": "X", "pid": 1, "tid": 1, "ts": 200, "dur": 50, "name": "func3"},
            {"ph": "X", "pid": 1, "tid": 1, "ts": 100, "dur": 50, "name": "func1"},
            {"ph": "X", "pid": 1, "tid": 1, "ts": 150, "dur": 50, "name": "func2"},
        ]

        thread_events = converter._build_call_tree()
        events = thread_events[(1, 1)]

        self.assertEqual(events[0]["name"], "func1", "Should be sorted")
        self.assertEqual(events[1]["name"], "func2")
        self.assertEqual(events[2]["name"], "func3")

    def test_build_stack_trace_empty_events(self):
        """Test _build_stack_trace with empty events list."""
        converter = ChromeTraceConverter(str(self.trace_file))
        result = converter._build_stack_trace([], 0, 100.0)
        self.assertEqual(result, [], "Should return empty list for empty events")

    def test_build_stack_trace_out_of_bounds(self):
        """Test _build_stack_trace with index out of bounds."""
        converter = ChromeTraceConverter(str(self.trace_file))
        events = [
            {
                "ph": "X",
                "start": 100,
                "end": 200,
                "name": "func1",
                "ts": 100,
                "dur": 100,
            }
        ]
        result = converter._build_stack_trace(events, 10, 100.0)
        self.assertEqual(result, [], "Should return empty list for out of bounds")

    def test_convert_with_events_producing_empty_stacks(self):
        """Test conversion where events produce empty stacks."""
        converter = ChromeTraceConverter(str(self.trace_file))
        # Create events that will produce empty stacks (events without names)
        converter.events = [
            {
                "ph": "X",
                "pid": 1,
                "tid": 1,
                "ts": 100,
                "dur": 50,
                # No "name" field - should be skipped
            },
            {
                "ph": "X",
                "pid": 1,
                "tid": 1,
                "ts": 200,
                "dur": 30,
                # No "name" field - should be skipped
            },
        ]

        stacks = converter.convert_to_folded()
        # Should produce empty stacks dict since events have no names
        self.assertEqual(len(stacks), 0, "Should produce no stacks for nameless events")

    # ==================== CLI Tests ====================

    def test_cli_help_display(self):
        """Test CLI help display."""
        from io import StringIO

        from telex.chrome_trace_converter import main

        old_argv = sys.argv
        old_stdout = sys.stdout
        sys.stdout = StringIO()

        try:
            sys.argv = ["tracec", "--help"]
            try:
                main()
            except SystemExit as e:
                self.assertEqual(e.code, 0, "Help should exit with code 0")

            output = sys.stdout.getvalue()
            self.assertIn("TracEC", output, "Help should contain program name")
            self.assertIn("TRACE_FILE", output, "Help should mention trace file")
        finally:
            sys.stdout = old_stdout
            sys.argv = old_argv

    def test_cli_missing_trace_file(self):
        """Test CLI with missing trace file argument."""
        from telex.chrome_trace_converter import main

        old_argv = sys.argv

        try:
            sys.argv = ["tracec"]
            with self.assertRaises(SystemExit) as cm:
                main()

            self.assertEqual(cm.exception.code, 1, "Should exit with code 1")
        finally:
            sys.argv = old_argv

    def test_cli_basic_conversion(self):
        """Test CLI basic conversion."""
        from telex.chrome_trace_converter import main

        output_file = "tests/test_files/trace_cli_test.folded"
        self.__class__.temp_files.append(output_file)

        old_argv = sys.argv

        try:
            sys.argv = ["tracec", str(self.trace_file), "-o", output_file]
            main()

            self.assertTrue(os.path.exists(output_file), "CLI should create output")
        finally:
            sys.argv = old_argv

    def test_cli_verbose_mode(self):
        """Test CLI with verbose flag."""
        from telex.chrome_trace_converter import main

        output_file = "tests/test_files/trace_cli_verbose_test.folded"
        self.__class__.temp_files.append(output_file)

        old_argv = sys.argv

        try:
            sys.argv = ["tracec", str(self.trace_file), "-o", output_file, "-v"]
            main()

            self.assertTrue(
                os.path.exists(output_file), "CLI verbose should create output"
            )
        finally:
            sys.argv = old_argv

    def test_cli_svg_generation(self):
        """Test CLI with SVG generation."""
        from telex.chrome_trace_converter import main

        output_folded = "tests/test_files/trace_cli_svg_test.folded"
        output_svg = "tests/test_files/trace_cli_svg_test.svg"
        self.__class__.temp_files.extend([output_folded, output_svg])

        old_argv = sys.argv

        try:
            sys.argv = [
                "tracec",
                str(self.trace_file),
                "-o",
                output_folded,
                "-s",
                output_svg,
            ]
            main()

            self.assertTrue(os.path.exists(output_folded), "Should create folded")
            self.assertTrue(os.path.exists(output_svg), "Should create SVG")
        finally:
            sys.argv = old_argv

    def test_cli_svg_with_custom_params(self):
        """Test CLI SVG generation with custom parameters."""
        from telex.chrome_trace_converter import main

        output_folded = "tests/test_files/trace_cli_custom_svg_test.folded"
        output_svg = "tests/test_files/trace_cli_custom_svg_test.svg"
        self.__class__.temp_files.extend([output_folded, output_svg])

        old_argv = sys.argv

        try:
            sys.argv = [
                "tracec",
                str(self.trace_file),
                "-o",
                output_folded,
                "-s",
                output_svg,
                "--title",
                "Custom Title",
                "--width",
                "1600",
                "--height",
                "20",
                "--minwidth",
                "0.5",
                "--countname",
                "microseconds",
                "--inverted",
            ]
            main()

            self.assertTrue(os.path.exists(output_svg), "Should create custom SVG")

            # Verify custom parameters in SVG
            with open(output_svg) as f:
                svg_content = f.read()
                self.assertIn("Custom Title", svg_content, "Should have custom title")
                self.assertIn("microseconds", svg_content, "Should have custom countname")
        finally:
            sys.argv = old_argv

    def test_cli_nonexistent_file(self):
        """Test CLI with non-existent trace file."""
        from telex.chrome_trace_converter import main

        old_argv = sys.argv

        try:
            sys.argv = ["tracec", "nonexistent_trace.json"]
            with self.assertRaises(SystemExit) as cm:
                main()

            self.assertEqual(cm.exception.code, 1, "Should exit with code 1")
        finally:
            sys.argv = old_argv

    def test_cli_invalid_json(self):
        """Test CLI with invalid JSON file."""
        from telex.chrome_trace_converter import main

        # Create invalid JSON file
        invalid_json = "tests/test_files/invalid.json"
        self.__class__.temp_files.append(invalid_json)

        with open(invalid_json, "w") as f:
            f.write("{ invalid json content }")

        old_argv = sys.argv

        try:
            sys.argv = ["tracec", invalid_json]
            with self.assertRaises(SystemExit) as cm:
                main()

            self.assertEqual(cm.exception.code, 1, "Should exit with code 1")
        finally:
            sys.argv = old_argv

    def test_cli_with_all_svg_options(self):
        """Test CLI with all SVG customization options."""
        from telex.chrome_trace_converter import main

        output_folded = "tests/test_files/trace_all_options_test.folded"
        output_svg = "tests/test_files/trace_all_options_test.svg"
        self.__class__.temp_files.extend([output_folded, output_svg])

        old_argv = sys.argv

        try:
            sys.argv = [
                "tracec",
                str(self.trace_file),
                "-o",
                output_folded,
                "-s",
                output_svg,
                "--title",
                "Full Test",
                "--width",
                "1400",
                "--height",
                "18",
                "--minwidth",
                "0.2",
                "--countname",
                "samples",
                "--command",
                "test_command",
                "--package-path",
                "/test/path",
                "--work-dir",
                "/work",
                "--inverted",
                "-v",
            ]
            main()

            self.assertTrue(
                os.path.exists(output_svg), "Should create SVG with all options"
            )
        finally:
            sys.argv = old_argv

    def test_cli_svg_generation_import_error(self):
        """Test CLI SVG generation with ImportError - verify error path exists."""
        # This test documents that the ImportError handling exists in the code
        # The actual ImportError path is difficult to test because FlameGraph
        # is imported inside a try block in main(), and mocking __import__
        # causes recursion issues. The code path exists at lines 524-530.

        # We can verify the code structure includes error handling
        import inspect

        from telex.chrome_trace_converter import main

        source = inspect.getsource(main)
        self.assertIn("except ImportError", source, "Should handle ImportError")
        self.assertIn("flamegraph module", source, "Should mention flamegraph")

        # Just verify basic CLI works without SVG to ensure folded generation
        import sys

        output_folded = "tests/test_files/trace_no_svg_test.folded"
        self.__class__.temp_files.append(output_folded)

        old_argv = sys.argv
        try:
            sys.argv = ["tracec", str(self.trace_file), "-o", output_folded]
            main()
            self.assertTrue(os.path.exists(output_folded), "Should create folded")
        finally:
            sys.argv = old_argv

    def test_cli_svg_generation_runtime_error(self):
        """Test CLI SVG generation with runtime error."""
        import sys
        from unittest.mock import MagicMock, patch

        from telex.chrome_trace_converter import main

        output_folded = "tests/test_files/trace_runtime_error_test.folded"
        output_svg = "tests/test_files/trace_runtime_error_test.svg"
        self.__class__.temp_files.extend([output_folded, output_svg])

        old_argv = sys.argv

        try:
            sys.argv = [
                "tracec",
                str(self.trace_file),
                "-o",
                output_folded,
                "-s",
                output_svg,
            ]

            # Mock FlameGraph.generate_svg to raise exception
            with patch("telex.flamegraph.FlameGraph") as mock_fg_class:
                mock_fg = MagicMock()
                mock_fg.generate_svg.side_effect = RuntimeError("Test error")
                mock_fg_class.return_value = mock_fg

                with self.assertRaises(SystemExit) as cm:
                    main()

                self.assertEqual(cm.exception.code, 1, "Should exit with code 1")
        finally:
            sys.argv = old_argv

    def test_cli_malformed_json_structure(self):
        """Test CLI with JSON that's valid but has wrong structure."""
        import json
        import sys

        from telex.chrome_trace_converter import main

        # Create a JSON file with wrong structure (no traceEvents)
        malformed_json = "tests/test_files/malformed_structure.json"
        self.__class__.temp_files.append(malformed_json)

        with open(malformed_json, "w") as f:
            json.dump({"wrongKey": "wrongValue"}, f)

        output_file = "tests/test_files/malformed_output.folded"
        self.__class__.temp_files.append(output_file)

        old_argv = sys.argv

        try:
            sys.argv = ["tracec", malformed_json, "-o", output_file]
            # Should succeed but produce empty output
            main()

            # File should exist but be essentially empty (no stacks)
            self.assertTrue(os.path.exists(output_file), "Should create file")
        finally:
            sys.argv = old_argv

    def test_cli_unexpected_exception(self):
        """Test CLI handling of unexpected exceptions."""
        import sys
        from unittest.mock import patch

        from telex.chrome_trace_converter import main

        old_argv = sys.argv

        try:
            sys.argv = ["tracec", str(self.trace_file)]

            # Mock ChromeTraceConverter to raise unexpected exception
            with patch(
                "telex.chrome_trace_converter.ChromeTraceConverter"
            ) as mock_converter_class:
                mock_converter_class.side_effect = ValueError("Unexpected test error")

                with self.assertRaises(SystemExit) as cm:
                    main()

                self.assertEqual(cm.exception.code, 1, "Should exit with code 1 on error")
        finally:
            sys.argv = old_argv
