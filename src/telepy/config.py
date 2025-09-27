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


class TelePySamplerConfig:
    """Configuration class to replace argparse.Namespace dependency."""

    def __init__(
        self,
        *,
        # Sampler configuration
        interval: int = 8000,
        timeout: float = 10,
        debug: bool = False,
        full_path: bool = False,
        tree_mode: bool = False,
        inverted: bool = False,
        reverse: bool = False,
        # Filtering options
        ignore_frozen: bool = False,
        include_telepy: bool = False,
        focus_mode: bool = False,
        regex_patterns: list[str] | None = None,
        # Output configuration
        output: str = "result.svg",
        folded_file: str = "result.folded",
        folded_save: bool = False,
        width: int = 1200,
        # Process handling
        merge: bool = True,
        mp: bool = False,
        fork_server: bool = False,
        # Interface options
        verbose: bool = True,
        disable_traceback: bool = False,
        create_config: bool = False,
        # Input options
        input=None,
        parse: bool = False,
        cmd: str | None = None,
        module: str | None = None,
    ):
        """Initialize TelePySamplerConfig with keyword-only arguments.

        Args:
            interval: Sampling interval in microseconds. Controls how frequently
                the profiler samples the call stack. Smaller values provide more
                detailed profiling but increase overhead. Default: 8000 (8ms).
            timeout: Timeout in seconds for parent process to wait for child
                processes to merge flamegraph files in multiprocess scenarios.
                Default: 10.
            debug: Enable debug mode to print additional diagnostic information
                during profiling. Useful for troubleshooting. Default: False.
            full_path: Display absolute file paths in the flamegraph instead of
                relative paths. Makes the graph more verbose but can be helpful
                for debugging. Default: False.
            tree_mode: Use call site line numbers instead of the first line of
                function/method definitions. Provides more precise location
                information. Default: False.
            inverted: Render flamegraphs with the root frame at the top
                (inverted orientation). Default: False.
            reverse: Generate reversed flamegraphs (currently not fully implemented).
                Default: False.
            ignore_frozen: Ignore frozen modules (compiled modules) in the stack
                trace. Helps focus on user code by excluding standard library
                internals. Default: False.
            include_telepy: Whether to include telepy profiler code itself in
                the stack trace. Usually disabled to focus on user code.
                Default: False.
            focus_mode: When enabled, ignores standard library and third-party
                packages in stack traces, focusing only on user code.
                Default: False.
            regex_patterns: List of regex pattern strings for filtering stack
                traces. Only files or function/class names matching at least one pattern
                will be included. If None or empty, all files are included. Default: None.
            output: Output filename for the SVG flamegraph file.
                Default: "result.svg".
            folded_file: Output filename for the folded stack trace file, which
                contains the raw profiling data in a text format.
                Default: "result.folded".
            folded_save: Save the folded stack traces to a file. The folded
                format can be used for further analysis or re-generating
                flamegraphs. Default: False.
            width: Width in pixels for generated flamegraph SVGs.
                Default: 1200.
            merge: Merge multiple flamegraph files in multiprocess environments.
                When True, child process data is combined into a single output.
                When False, separate files are created for each process.
                Default: True.
            mp: Internal flag indicating this is a multiprocess child process.
                Used internally by the profiler. Default: False.
            fork_server: Internal flag indicating this is running in forkserver
                mode. Used internally by the profiler. Default: False.
            verbose: Enable verbose output messages during profiling.
                When True, suppresses most status and progress messages.
                Default: False.
            disable_traceback: Disable the rich (colorful) traceback display
                and use the default Python traceback format instead.
                Default: False.
            create_config: Create an example configuration file at
                ~/.telepy/.telepyrc and exit immediately. Used for initial
                setup. Default: False.
            input: Input file(s) to profile. Can be a list of file objects or
                None. Used when profiling specific files. Default: None.
            parse: Parse existing stack trace data to generate a flamegraph
                instead of running live profiling. Default: False.
            cmd: Command string to execute and profile. Used with -c option.
                Default: None.
            module: Module name to profile when using -m option.
                Default: None.
        """
        # Sampler configuration
        self.interval = interval
        self.timeout = timeout
        self.debug = debug
        self.full_path = full_path
        self.tree_mode = tree_mode
        self.inverted = inverted
        self.reverse = reverse

        # Filtering options
        self.ignore_frozen = ignore_frozen
        self.include_telepy = include_telepy
        self.focus_mode = focus_mode
        self.regex_patterns = regex_patterns

        # Output configuration
        self.output = output
        self.folded_file = folded_file
        self.folded_save = folded_save
        if width <= 0:
            raise ValueError("width must be a positive integer")
        self.width = width

        # Process handling
        self.merge = merge
        self.mp = mp
        self.fork_server = fork_server

        # Interface options
        self.verbose = verbose
        self.disable_traceback = disable_traceback
        self.create_config = create_config

        # Input options
        self.input = input
        self.parse = parse
        self.cmd = cmd
        self.module = module

    @classmethod
    def from_namespace(cls, args_namespace) -> "TelePySamplerConfig":
        """Create TelePySamplerConfig from argparse.Namespace.

        Args:
            args_namespace: An argparse.Namespace object containing the parsed
                command line arguments.

        Returns:
            A new TelePySamplerConfig instance with values extracted from the
            namespace, using appropriate defaults for missing attributes.
        """
        return cls(
            interval=getattr(args_namespace, "interval", 8000),
            timeout=getattr(args_namespace, "timeout", 10),
            debug=getattr(args_namespace, "debug", False),
            full_path=getattr(args_namespace, "full_path", False),
            tree_mode=getattr(args_namespace, "tree_mode", False),
            inverted=getattr(args_namespace, "inverted", False),
            reverse=getattr(args_namespace, "reverse", False),
            ignore_frozen=getattr(args_namespace, "ignore_frozen", False),
            include_telepy=getattr(args_namespace, "include_telepy", False),
            focus_mode=getattr(args_namespace, "focus_mode", False),
            regex_patterns=getattr(args_namespace, "regex_patterns", None),
            output=getattr(args_namespace, "output", "result.svg"),
            folded_file=getattr(args_namespace, "folded_file", "result.folded"),
            folded_save=getattr(args_namespace, "folded_save", False),
            width=getattr(args_namespace, "width", 1200),
            merge=getattr(args_namespace, "merge", True),
            mp=getattr(args_namespace, "mp", False),
            fork_server=getattr(args_namespace, "fork_server", False),
            verbose=getattr(args_namespace, "verbose", True),
            disable_traceback=getattr(args_namespace, "disable_traceback", False),
            create_config=getattr(args_namespace, "create_config", False),
            input=getattr(args_namespace, "input", None),
            parse=getattr(args_namespace, "parse", False),
            cmd=getattr(args_namespace, "cmd", None),
            module=getattr(args_namespace, "module", None),
        )

    def to_cli_args(self) -> list[str]:
        """Convert configuration to command line arguments.

        Returns:
            A list of command line arguments that represent the current
            configuration, suitable for passing to child processes.
        """
        res = []
        if self.debug:
            res.append("--debug")
        if self.full_path:
            res.append("--full-path")
        if not self.merge:
            res.append("--no-merge")
        if self.ignore_frozen:
            res.append("--ignore-frozen")
        if self.include_telepy:
            res.append("--include-telepy")
        if self.focus_mode:
            res.append("--focus-mode")
        if self.regex_patterns:
            for pattern in self.regex_patterns:
                res.append("--regex-patterns")
                res.append(pattern)
        if self.timeout:
            res.append("--timeout")
            res.append(str(self.timeout))
        if self.tree_mode:
            res.append("--tree-mode")
        if self.inverted:
            res.append("--inverted")
        if self.interval:
            res.append("--interval")
            res.append(str(self.interval))
        if self.folded_save:
            res.append("--folded-save")
        if self.folded_file:
            res.append("--folded-file")
            res.append(self.folded_file)
        if self.width:
            res.append("--width")
            res.append(str(self.width))
        if self.mp:
            res.append("--mp")
        if self.fork_server:  # pragma: no cover
            # nobody writes code to use it.
            res.append("--fork-server")
        return res


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
