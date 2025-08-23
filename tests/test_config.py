import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from telepy.config import TelePyConfig, load_config_if_exists, merge_config_with_args


class TestTelePyConfig(unittest.TestCase):
    """Test cases for TelePy configuration functionality."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_dir = Path(self.temp_dir) / ".telepy"
        self.config_file = self.config_dir / ".telepyrc"

    def tearDown(self):
        """Clean up test environment."""
        if self.config_file.exists():
            self.config_file.unlink()
        if self.config_dir.exists():
            self.config_dir.rmdir()
        os.rmdir(self.temp_dir)

    @patch("telepy.config.Path.home")
    def test_get_config_path(self, mock_home):
        """Test that config path is constructed correctly."""
        mock_home.return_value = Path(self.temp_dir)
        config = TelePyConfig()
        expected_path = Path(self.temp_dir) / ".telepy" / ".telepyrc"
        self.assertEqual(config.config_path, expected_path)

    @patch("telepy.config.Path.home")
    def test_load_config_file_not_exists(self, mock_home):
        """Test loading config when file doesn't exist."""
        mock_home.return_value = Path(self.temp_dir)
        config = TelePyConfig()
        result = config.load_config()
        self.assertEqual(result, {})

    @patch("telepy.config.Path.home")
    def test_load_config_valid_json(self, mock_home):
        """Test loading valid JSON config file."""
        mock_home.return_value = Path(self.temp_dir)
        self.config_dir.mkdir(exist_ok=True)

        test_config = {"args": ["--interval", "5000", "--debug", "--output", "test.svg"]}

        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(test_config, f)

        config = TelePyConfig()
        result = config.load_config()
        self.assertEqual(result, test_config)

    @patch("telepy.config.Path.home")
    def test_load_config_invalid_json(self, mock_home):
        """Test loading invalid JSON config file."""
        mock_home.return_value = Path(self.temp_dir)
        self.config_dir.mkdir(exist_ok=True)

        # Write invalid JSON
        with open(self.config_file, "w", encoding="utf-8") as f:
            f.write("{ invalid json }")

        config = TelePyConfig()
        result = config.load_config()
        self.assertEqual(result, {})

    @patch("telepy.config.Path.home")
    def test_load_config_not_dict(self, mock_home):
        """Test loading config file that doesn't contain a dictionary."""
        mock_home.return_value = Path(self.temp_dir)
        self.config_dir.mkdir(exist_ok=True)

        # Write JSON array instead of object
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump([1, 2, 3], f)

        config = TelePyConfig()
        result = config.load_config()
        self.assertEqual(result, {})

    def test_merge_with_args_empty_config(self):
        """Test merging with empty config."""
        config = TelePyConfig()
        cmd_args = ["--debug", "--interval", "1000"]
        result = config.merge_with_args({}, cmd_args)
        self.assertEqual(result, cmd_args)

    def test_merge_with_args_with_config_args(self):
        """Test merging config args with command line args."""
        config = TelePyConfig()
        test_config = {"args": ["--debug", "--interval", "5000"]}
        cmd_args = ["--output", "test.svg"]
        result = config.merge_with_args(test_config, cmd_args)

        # Should include config args first, then command line args
        expected = ["--debug", "--interval", "5000", "--output", "test.svg"]
        self.assertEqual(result, expected)

    def test_merge_with_args_command_line_precedence(self):
        """Test that command line args take precedence over config."""
        config = TelePyConfig()
        test_config = {"args": ["--interval", "5000"]}
        cmd_args = ["--interval", "1000"]  # Should override config
        result = config.merge_with_args(test_config, cmd_args)

        # Both should be present, but argparse will use the last one (command line)
        expected = ["--interval", "5000", "--interval", "1000"]
        self.assertEqual(result, expected)

    def test_merge_with_args_invalid_args_type(self):
        """Test handling of invalid args type in config."""
        config = TelePyConfig()
        test_config = {"args": "not a list"}  # Invalid type
        cmd_args = ["--debug"]
        result = config.merge_with_args(test_config, cmd_args)

        # Should ignore invalid config and return only command line args
        self.assertEqual(result, cmd_args)

    def test_merge_with_args_no_args_key(self):
        """Test config without args key."""
        config = TelePyConfig()
        test_config = {"other": "value"}  # No "args" key
        cmd_args = ["--debug"]
        result = config.merge_with_args(test_config, cmd_args)

        # Should return only command line args
        self.assertEqual(result, cmd_args)

    def test_merge_with_args_boolean_flags(self):
        """Test merging with boolean flags."""
        config = TelePyConfig()
        test_config = {"args": ["--debug", "--ignore-frozen", "--no-merge"]}
        cmd_args = ["--interval", "1000"]
        result = config.merge_with_args(test_config, cmd_args)

        expected = ["--debug", "--ignore-frozen", "--no-merge", "--interval", "1000"]
        self.assertEqual(result, expected)

    def test_merge_with_args_mixed_args(self):
        """Test merging with mixed argument types."""
        config = TelePyConfig()
        test_config = {
            "args": [
                "--debug",
                "--interval",
                "5000",
                "--output",
                "profile.svg",
                "--no-merge",
            ]
        }
        cmd_args = ["script.py", "--timeout", "30"]
        result = config.merge_with_args(test_config, cmd_args)

        expected = [
            "--debug",
            "--interval",
            "5000",
            "--output",
            "profile.svg",
            "--no-merge",
            "script.py",
            "--timeout",
            "30",
        ]
        self.assertEqual(result, expected)

    @patch("telepy.config.Path.home")
    def test_create_example_config(self, mock_home):
        """Test creating example config file."""
        mock_home.return_value = Path(self.temp_dir)
        config = TelePyConfig()
        config.create_example_config()

        # Check that file was created
        self.assertTrue(self.config_file.exists())

        # Check that it contains valid JSON
        with open(self.config_file, encoding="utf-8") as f:
            data = json.load(f)

        # Check that it has "args" key with a list
        self.assertIn("args", data)
        self.assertIsInstance(data["args"], list)

    @patch("telepy.config.Path.home")
    @patch("telepy.config.input")
    def test_create_example_config_overwrite_yes(self, mock_input, mock_home):
        """Test creating example config file when file exists and user
        chooses to overwrite."""
        mock_home.return_value = Path(self.temp_dir)
        mock_input.return_value = "y"

        config = TelePyConfig()

        # Create existing config file
        self.config_dir.mkdir(exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump({"args": ["--existing"]}, f)

        config.create_example_config()

        # Check that file was overwritten
        self.assertTrue(self.config_file.exists())
        with open(self.config_file, encoding="utf-8") as f:
            data = json.load(f)

        # Should contain new example config, not the old one
        self.assertIn("args", data)
        self.assertNotEqual(data["args"], ["--existing"])

    @patch("telepy.config.Path.home")
    @patch("telepy.config.input")
    def test_create_example_config_overwrite_no(self, mock_input, mock_home):
        """Test creating example config file when file exists and user
        chooses not to overwrite."""
        mock_home.return_value = Path(self.temp_dir)
        mock_input.return_value = "n"

        config = TelePyConfig()

        # Create existing config file
        self.config_dir.mkdir(exist_ok=True)
        original_config = {"args": ["--existing"]}
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(original_config, f)

        config.create_example_config()

        # Check that file was NOT overwritten
        self.assertTrue(self.config_file.exists())
        with open(self.config_file, encoding="utf-8") as f:
            data = json.load(f)

        # Should still contain the original config
        self.assertEqual(data, original_config)

    @patch("telepy.config.TelePyConfig.load_config")
    def test_load_config_if_exists(self, mock_load):
        """Test convenience function load_config_if_exists."""
        test_config = {"args": ["--debug"]}
        mock_load.return_value = test_config

        result = load_config_if_exists()
        self.assertEqual(result, test_config)
        mock_load.assert_called_once()

    @patch("telepy.config.TelePyConfig.load_config")
    @patch("telepy.config.TelePyConfig.merge_with_args")
    def test_merge_config_with_args(self, mock_merge, mock_load):
        """Test convenience function merge_config_with_args."""
        test_config = {"args": ["--debug"]}
        test_args = ["--interval", "1000"]
        expected_result = ["--debug", "--interval", "1000"]

        mock_load.return_value = test_config
        mock_merge.return_value = expected_result

        result = merge_config_with_args(test_args)

        self.assertEqual(result, expected_result)
        mock_load.assert_called_once()
        mock_merge.assert_called_once_with(test_config, test_args)


if __name__ == "__main__":
    unittest.main()
