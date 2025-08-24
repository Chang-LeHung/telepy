import argparse
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from telepy.config import (
    TelePyConfig,
    TelePySamplerConfig,
    load_config_if_exists,
    merge_config_with_args,
)


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


class TestTelePySamplerConfig(unittest.TestCase):
    """Test cases for TelePySamplerConfig functionality."""

    def test_init_with_keyword_arguments(self):
        """Test creating TelePySamplerConfig with keyword arguments."""
        config = TelePySamplerConfig(
            interval=5000,
            debug=True,
            full_path=False,
            output="test.svg",
            ignore_frozen=True,
            merge=False,
        )

        self.assertEqual(config.interval, 5000)
        self.assertTrue(config.debug)
        self.assertFalse(config.full_path)
        self.assertEqual(config.output, "test.svg")
        self.assertTrue(config.ignore_frozen)
        self.assertFalse(config.merge)

        # Check defaults for unspecified parameters
        self.assertEqual(config.timeout, 10)  # default
        self.assertFalse(config.tree_mode)  # default
        self.assertEqual(config.folded_file, "result.folded")  # default

    def test_init_with_defaults(self):
        """Test creating TelePySamplerConfig with all default values."""
        config = TelePySamplerConfig()

        # Check all default values
        self.assertEqual(config.interval, 8000)
        self.assertEqual(config.timeout, 10)
        self.assertFalse(config.debug)
        self.assertFalse(config.full_path)
        self.assertFalse(config.tree_mode)
        self.assertFalse(config.reverse)
        self.assertFalse(config.ignore_frozen)
        self.assertFalse(config.include_telepy)
        self.assertEqual(config.output, "result.svg")
        self.assertEqual(config.folded_file, "result.folded")
        self.assertFalse(config.folded_save)
        self.assertTrue(config.merge)
        self.assertFalse(config.mp)
        self.assertFalse(config.fork_server)
        self.assertFalse(config.no_verbose)
        self.assertIsNone(config.input)
        self.assertFalse(config.parse)
        self.assertIsNone(config.cmd)
        self.assertIsNone(config.module)

    def test_init_prohibits_positional_arguments(self):
        """Test that positional arguments are prohibited."""
        with self.assertRaises(TypeError) as context:
            TelePySamplerConfig(5000, True, "test.svg")

        error_message = str(context.exception)
        self.assertIn("takes 1 positional argument", error_message)

    def test_from_namespace_with_full_args(self):
        """Test creating config from argparse.Namespace with all attributes."""
        args = argparse.Namespace()
        args.interval = 6000
        args.timeout = 15.0
        args.debug = True
        args.full_path = True
        args.tree_mode = False
        args.reverse = True
        args.ignore_frozen = True
        args.include_telepy = False
        args.output = "namespace.svg"
        args.folded_file = "namespace.folded"
        args.folded_save = True
        args.merge = False
        args.mp = False
        args.fork_server = False
        args.no_verbose = True
        args.input = None
        args.parse = False
        args.cmd = "print('test')"
        args.module = "test_module"

        config = TelePySamplerConfig.from_namespace(args)

        # Verify all attributes are correctly transferred
        self.assertEqual(config.interval, 6000)
        self.assertEqual(config.timeout, 15.0)
        self.assertTrue(config.debug)
        self.assertTrue(config.full_path)
        self.assertFalse(config.tree_mode)
        self.assertTrue(config.reverse)
        self.assertTrue(config.ignore_frozen)
        self.assertFalse(config.include_telepy)
        self.assertEqual(config.output, "namespace.svg")
        self.assertEqual(config.folded_file, "namespace.folded")
        self.assertTrue(config.folded_save)
        self.assertFalse(config.merge)
        self.assertFalse(config.mp)
        self.assertFalse(config.fork_server)
        self.assertTrue(config.no_verbose)
        self.assertIsNone(config.input)
        self.assertFalse(config.parse)
        self.assertEqual(config.cmd, "print('test')")
        self.assertEqual(config.module, "test_module")

    def test_from_namespace_with_missing_attributes(self):
        """Test from_namespace with missing attributes uses defaults."""
        args = argparse.Namespace()
        # Only set a few attributes
        args.interval = 7000
        args.debug = True
        args.output = "minimal.svg"

        config = TelePySamplerConfig.from_namespace(args)

        # Check set values
        self.assertEqual(config.interval, 7000)
        self.assertTrue(config.debug)
        self.assertEqual(config.output, "minimal.svg")

        # Check defaults for missing attributes
        self.assertEqual(config.timeout, 10)  # default
        self.assertFalse(config.full_path)  # default
        self.assertFalse(config.tree_mode)  # default
        self.assertEqual(config.folded_file, "result.folded")  # default
        self.assertTrue(config.merge)  # default
        self.assertFalse(config.mp)  # default

    def test_from_namespace_empty_namespace(self):
        """Test from_namespace with completely empty namespace."""
        args = argparse.Namespace()

        config = TelePySamplerConfig.from_namespace(args)

        # Should get all defaults
        self.assertEqual(config.interval, 8000)
        self.assertEqual(config.timeout, 10)
        self.assertFalse(config.debug)
        self.assertEqual(config.output, "result.svg")
        self.assertTrue(config.merge)

    def test_parameter_types(self):
        """Test that parameters accept correct types."""
        config = TelePySamplerConfig(
            interval=5000,  # int
            timeout=15.5,  # float
            debug=True,  # bool
            output="test.svg",  # str
            cmd=None,  # Optional[str]
            module="test",  # Optional[str] with value
        )

        self.assertIsInstance(config.interval, int)
        self.assertIsInstance(config.timeout, float)
        self.assertIsInstance(config.debug, bool)
        self.assertIsInstance(config.output, str)
        self.assertIsNone(config.cmd)
        self.assertIsInstance(config.module, str)

    def test_comprehensive_configuration(self):
        """Test a comprehensive configuration covering all parameters."""
        config = TelePySamplerConfig(
            # Sampler configuration
            interval=4000,
            timeout=20.0,
            debug=True,
            full_path=True,
            tree_mode=True,
            reverse=False,
            # Filtering options
            ignore_frozen=True,
            include_telepy=True,
            # Output configuration
            output="comprehensive.svg",
            folded_file="comprehensive.folded",
            folded_save=True,
            # Process handling
            merge=True,
            mp=True,
            fork_server=False,
            # Interface options
            no_verbose=False,
            disable_traceback=True,
            create_config=False,
            # Input options
            parse=True,
            cmd="import sys; print(sys.version)",
            module="json.tool",
        )

        # Verify the comprehensive configuration
        self.assertEqual(config.interval, 4000)
        self.assertEqual(config.timeout, 20.0)
        self.assertTrue(config.debug)
        self.assertTrue(config.full_path)
        self.assertTrue(config.tree_mode)
        self.assertFalse(config.reverse)
        self.assertTrue(config.ignore_frozen)
        self.assertTrue(config.include_telepy)
        self.assertEqual(config.output, "comprehensive.svg")
        self.assertEqual(config.folded_file, "comprehensive.folded")
        self.assertTrue(config.folded_save)
        self.assertTrue(config.merge)
        self.assertTrue(config.mp)
        self.assertFalse(config.fork_server)
        self.assertFalse(config.no_verbose)
        self.assertTrue(config.disable_traceback)
        self.assertFalse(config.create_config)
        self.assertTrue(config.parse)
        self.assertEqual(config.cmd, "import sys; print(sys.version)")
        self.assertEqual(config.module, "json.tool")

    def test_new_interface_parameters(self):
        """Test the newly added interface parameters."""
        # Test default values
        config = TelePySamplerConfig()
        self.assertFalse(config.disable_traceback)
        self.assertFalse(config.create_config)

        # Test explicit values
        config = TelePySamplerConfig(disable_traceback=True, create_config=True)
        self.assertTrue(config.disable_traceback)
        self.assertTrue(config.create_config)

    def test_from_namespace_new_parameters(self):
        """Test from_namespace method with new parameters."""

        # Mock namespace object with new parameters
        class MockNamespace:
            def __init__(self):
                # Set all defaults
                self.interval = 8000
                self.timeout = 10
                self.debug = False
                self.full_path = False
                self.tree_mode = False
                self.reverse = False
                self.ignore_frozen = False
                self.include_telepy = False
                self.output = "result.svg"
                self.folded_file = "result.folded"
                self.folded_save = False
                self.merge = True
                self.mp = False
                self.fork_server = False
                self.no_verbose = False
                self.disable_traceback = True  # Test new parameter
                self.create_config = True  # Test new parameter
                self.input = None
                self.parse = False
                self.cmd = None
                self.module = None

        mock_args = MockNamespace()
        config = TelePySamplerConfig.from_namespace(mock_args)

        # Verify new parameters are correctly set
        self.assertTrue(config.disable_traceback)
        self.assertTrue(config.create_config)


if __name__ == "__main__":
    unittest.main()
