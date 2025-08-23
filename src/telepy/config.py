"""
Configuration file handling for TelePy.
"""

import json
import os
from pathlib import Path
from typing import Any

from . import logger

CONFIG_DIR = ".telepy"
CONFIG_FILE = ".telepyrc"


def _is_testing() -> bool:
    """Check if we're running in a testing environment."""
    # Check if explicitly set to suppress output during testing
    return os.environ.get("TELEPY_SUPPRESS_OUTPUT", "").lower() in ("1", "true", "yes")


def _safe_print(message: str) -> None:
    """Print message only if not in testing environment."""
    if not _is_testing():
        logger.console.print(message)


def _safe_input(prompt: str, default: str = "n") -> str:
    """Get user input only if not in testing environment."""
    # In testing, always use input() to allow mocking
    return input(prompt)


class TelePyConfig:
    """Configuration manager for TelePy."""

    def __init__(self) -> None:
        self.config_path = self._get_config_path()

    def _get_config_path(self) -> Path:
        """Get the path to the configuration file."""
        home_dir = Path.home()
        config_dir = home_dir / CONFIG_DIR
        return config_dir / CONFIG_FILE

    def load_config(self) -> dict[str, Any]:
        """
        Load configuration from ~/.telepy/.telepyrc file.

        Returns:
            dict[str, Any]: Configuration dictionary. Empty dict if file doesn't exist.
        """
        if not self.config_path.exists():
            return {}

        try:
            with open(self.config_path, encoding="utf-8") as f:
                config = json.load(f)
                if not isinstance(config, dict):
                    _safe_print(
                        f"[yellow]Warning: Configuration file {self.config_path} "
                        "is not a valid JSON object. Ignoring.[/yellow]"
                    )
                    return {}
                return config
        except json.JSONDecodeError as e:
            _safe_print(
                f"[red]Error: Invalid JSON in configuration file "
                f"{self.config_path}: {e}[/red]"
            )
            return {}
        except Exception as e:  # pragma: no cover
            _safe_print(
                f"[red]Error loading configuration file {self.config_path}: {e}[/red]"
            )
            return {}

    def merge_with_args(self, config: dict[str, Any], cmd_args: list[str]) -> list[str]:
        """
        Merge configuration with command line arguments.
        Command line arguments take precedence over configuration file.

        Args:
            config (dict[str, Any]): Configuration dictionary from file
            cmd_args (list[str]): Command line arguments

        Returns:
            list[str]: Merged arguments with config applied first, then command line args
        """
        if not config:
            return cmd_args

        # Get args from config file
        config_args = config.get("args", [])

        # Validate that args is a list
        if not isinstance(config_args, list):
            _safe_print(
                f"[yellow]Warning: 'args' in configuration file should be a list, "
                f"got {type(config_args).__name__}. Ignoring config args.[/yellow]"
            )
            config_args = []

        # Merge: config args first, then command line args (command line takes precedence)
        merged_args = config_args + cmd_args

        return merged_args

    def create_example_config(self) -> None:
        """Create an example configuration file."""
        # Check if config file already exists
        if self.config_path.exists():
            _safe_print(
                f"[yellow]Configuration file already exists at "
                f"{self.config_path}[/yellow]"
            )
            response = (
                _safe_input("Do you want to overwrite it? (y/N): ", "n").strip().lower()
            )
            if response not in ("y", "yes"):
                _safe_print("[blue]Configuration file creation cancelled.[/blue]")
                return

        config_dir = self.config_path.parent
        config_dir.mkdir(exist_ok=True)

        example_config = {
            "args": [
                # Sampling configuration
                "--interval",
                "8000",
                "--timeout",
                "30",
                # Output configuration
                "--output",
                "result.svg",
                "--folded-file",
                "result.folded",
                "--folded-save",
                # Display options (boolean flags)
                # "--debug",         # Enable debug mode
                # "--full-path",     # Show full paths
                # "--tree-mode",     # Enable tree mode
                # Filtering options
                "--ignore-frozen",  # Ignore frozen modules (recommended)
                # "--include-telepy", # Include telepy in profiling
                # Process handling
                "--merge",  # Merge multiprocess results
                # "--no-merge",      # Disable merging (alternative to --merge)
            ]
        }

        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(example_config, f, indent=2)

        _safe_print(
            f"[green]Created example configuration file at {self.config_path}[/green]"
        )


def load_config_if_exists() -> dict[str, Any]:
    """
    Convenience function to load configuration if it exists.

    Returns:
        dict[str, Any]: Configuration dictionary
    """
    config_manager = TelePyConfig()
    return config_manager.load_config()


def merge_config_with_args(cmd_args: list[str]) -> list[str]:
    """
    Convenience function to merge configuration with command line arguments.

    Args:
        cmd_args (list[str]): Command line arguments

    Returns:
        list[str]: Merged arguments
    """
    config_manager = TelePyConfig()
    config = config_manager.load_config()
    return config_manager.merge_with_args(config, cmd_args)
