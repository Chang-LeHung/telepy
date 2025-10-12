"""
Additional unit tests for chrome_trace_converter.py CLI functionality
"""

import os
import sys
from io import StringIO
from pathlib import Path

from tests.base import TestBase


class TestChromeTraceCLI(TestBase):
    """Test suite for ChromeTraceConverter CLI functionality."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.trace_file = Path("tests/test_files/trace.json")
        cls.temp_files = []

    @classmethod
    def tearDownClass(cls):
        """Clean up temporary files."""
        for temp_file in cls.temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def test_cli_help_display(self):
        """Test CLI help display."""
        from telepy.chrome_trace_converter import main

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
        from telepy.chrome_trace_converter import main

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
        from telepy.chrome_trace_converter import main

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
        from telepy.chrome_trace_converter import main

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
        from telepy.chrome_trace_converter import main

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
        from telepy.chrome_trace_converter import main

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
        from telepy.chrome_trace_converter import main

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
        from telepy.chrome_trace_converter import main

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
        from telepy.chrome_trace_converter import main

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
