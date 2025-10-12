from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .test_command import CommandTemplate


class TestConfigCommand(CommandTemplate):
    """Test configuration file functionality through command line."""

    def run_command_with_output(
        self,
        options: list[str],
        stdout_check_list: list[str] = [],
        stderr_check_list: list[str] = [],
        timeout: int = 10,
        exit_code: int = 0,
    ):
        """Run command without TELEPY_SUPPRESS_OUTPUT to see output messages."""
        # Create environment without TELEPY_SUPPRESS_OUTPUT
        env = os.environ.copy()
        env.pop("TELEPY_SUPPRESS_OUTPUT", None)

        if "coverage" in sys.modules:
            cmd_line = [
                "coverage",
                "run",
                "--parallel-mode",
                "--source",
                "telepy",
                "-m",
                "telepy",
                *options,
            ]
        else:
            cmd_line = ["telepy", *options]

        output = subprocess.run(cmd_line, capture_output=True, timeout=timeout, env=env)
        self.assertEqual(output.returncode, exit_code)
        stdout = output.stdout.decode("utf-8")
        for check in stdout_check_list:
            self.assertRegex(stdout, check)
        stderr = output.stderr.decode("utf-8")
        for check in stderr_check_list:
            self.assertRegex(stderr, check)
        return output

    def test_create_config_command(self):
        """Test --create-config command line option."""
        # Use real home directory
        config_dir = Path.home() / ".telepy"
        config_file = config_dir / ".telepyrc"

        # Remove existing config file if it exists
        if config_file.exists():
            config_file.unlink()

        # Run telepy with --create-config (without TELEPY_SUPPRESS_OUTPUT)
        self.run_command_with_output(
            ["--create-config"],
            stdout_check_list=["Created example configuration file", ".telepy/.telepyrc"],
            exit_code=0,
        )

        # Verify config file was created
        self.assertTrue(config_file.exists())

        # Verify it contains valid JSON
        with open(config_file, encoding="utf-8") as f:
            config = json.load(f)

        # Check the new format - should have "args" key with a list
        self.assertIn("args", config)
        self.assertIsInstance(config["args"], list)
        # Check that args list contains expected parameters
        args_str = " ".join(config["args"])
        self.assertIn("--interval", args_str)
        self.assertIn("--timeout", args_str)

    def test_config_file_loading_with_debug(self):
        """Test that config file is loaded and applied."""
        # Use real home directory
        config_dir = Path.home() / ".telepy"
        config_file = config_dir / ".telepyrc"

        # Create config file with debug enabled
        config_dir.mkdir(exist_ok=True)
        test_config = {"args": ["--debug", "--interval", "5000"]}
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(test_config, f)

        try:
            # Run a simple command that should pick up debug config
            self.run_command(
                ["-c", "print('hello')"],
                stdout_check_list=[
                    "hello",
                    "TelePySampler Metrics",  # This appears when debug is True
                ],
                exit_code=0,
            )
        finally:
            # Clean up
            if config_file.exists():
                config_file.unlink()

    def test_command_line_overrides_config(self):
        """Test that command line arguments override config file."""
        # Use real home directory
        config_dir = Path.home() / ".telepy"
        config_file = config_dir / ".telepyrc"

        # Create config file without debug (empty args or args without --debug)
        config_dir.mkdir(exist_ok=True)
        test_config = {"args": ["--interval", "5000"]}
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(test_config, f)

        try:
            # Run with --debug on command line (should override config)
            self.run_command(
                ["--debug", "-c", "print('hello')"],
                stdout_check_list=[
                    "hello",
                    "TelePySampler Metrics",  # This appears when debug is True
                ],
                exit_code=0,
            )
        finally:
            # Clean up
            if config_file.exists():
                config_file.unlink()

    def test_config_with_invalid_json(self):
        """Test behavior with invalid JSON in config file."""
        # Use real home directory
        config_dir = Path.home() / ".telepy"
        config_file = config_dir / ".telepyrc"

        # Create invalid JSON config file
        config_dir.mkdir(exist_ok=True)
        with open(config_file, "w", encoding="utf-8") as f:
            f.write("{ invalid json }")

        try:
            # Should still work, just ignore the config file
            # Error message appears in stdout, not stderr
            self.run_command_with_output(
                ["-c", "print('hello')"],
                stdout_check_list=["hello", "Error: Invalid JSON"],
                exit_code=0,
            )
        finally:
            # Clean up
            if config_file.exists():
                config_file.unlink()

    def test_help_includes_create_config(self):
        """Test that help includes the --create-config option."""
        self.run_command(
            ["--help"],
            stdout_check_list=["--create-config", "Create an example configuration file"],
            exit_code=0,
        )
