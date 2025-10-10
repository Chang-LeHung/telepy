"""
TelePy command entry point.
"""

import argparse
import heapq
import os
import sys
import weakref
from abc import ABC, abstractmethod
from typing import override

from rich import print
from rich.panel import Panel
from rich.table import Table
from rich.traceback import Traceback, install
from rich_argparse import RichHelpFormatter

from . import logger
from ._telepysys import __version__
from .config import TelePyConfig, TelePySamplerConfig, merge_config_with_args
from .environment import CodeMode, telepy_env, telepy_finalize
from .flamegraph import FlameGraph
from .shell import TelePyShell

console = logger.console
err_console = logger.err_console


in_coverage = "coverage" in sys.modules


class ArgsHandler(ABC):
    def __init__(self, name: str, priority: int = 0) -> None:
        """
        Initialize a new instance with the given name and optional priority.

        Args:
            name (str): The name of the instance.
            priority (int, optional): The priority level. Defaults to 0.
        """
        self.name = name
        self.priority = priority

    @property
    def weight(self) -> int:
        return self.priority

    def __str__(self):  # pragma: no cover
        return f"[bold blue] Handler[name = {self.name}, priority={self.priority}][/bold blue]"  # noqa: E501

    @abstractmethod
    def handle(self, args: argparse.Namespace) -> bool:
        """
        Handle the command.
        Args:
            args (argparse.Namespace): The arguments passed to the command.
        Returns:
            bool: Whether the command be handled.
        """
        pass  # pragma: no cover

    @classmethod
    @abstractmethod
    def build(cls) -> "ArgsHandler":
        pass  # pragma: no cover

    def __lt__(self, other: "ArgsHandler") -> bool:
        return self.weight > other.weight  # big heap


handlers: list[ArgsHandler] = []


def _positive_int(value: str) -> int:
    ivalue = int(value)
    if ivalue <= 0:
        raise argparse.ArgumentTypeError("width must be a positive integer")
    return ivalue


def register_handler(handler: type[ArgsHandler]) -> None:
    """Register a handler class to be used in the application.

    Args:
        handler (type[ArgsHandler]): A handler class that must implement the ArgsHandler interface.
    """  # noqa: E501
    global handlers
    heapq.heappush(handlers, handler.build())


@register_handler
class StackTraceHandler(ArgsHandler):
    """
    Generating a flame graph from a stack trace.
    """

    @classmethod
    def build(cls) -> ArgsHandler:
        return cls()

    def __init__(self, priority: int = 1024) -> None:
        super().__init__("StackTraceHandler", priority=priority)

    @override
    def handle(self, args: argparse.Namespace) -> bool:
        if args.parse:
            self.parse_stack_trace(args)
            return True
        return False

    def parse_stack_trace(self, args: argparse.Namespace) -> None:
        input_files = getattr(args, "input", []) or []
        folded_lines: list[str] = []
        input_names: list[str] = []

        for file_obj in input_files:
            input_names.append(getattr(file_obj, "name", "<unknown>"))
            folded_lines.extend(line for line in file_obj if line.strip() != "")

        flamegraph = FlameGraph(
            folded_lines,
            inverted=getattr(args, "inverted", False),
            width=getattr(args, "width", 1200),
        )
        flamegraph.parse_input()
        svg = flamegraph.generate_svg()

        for file_obj in input_files:
            file_obj.close()
        with open(args.output, "w") as f:
            f.write(svg)

        input_display = ", ".join(input_names) if input_names else "<unknown>"
        logger.log_success_panel(
            f"Generated a flamegraph svg file `{args.output}` from the stack "
            f"trace file(s) `{input_display}`, "
            f"please check it out via `open {args.output}`"
        )


@register_handler
class PythonFileProfilingHandler(ArgsHandler):
    @classmethod
    def build(cls):
        return cls()

    def __init__(self, priority: int = 512):
        super().__init__("PythonFileProfilingHandler", priority=priority)

    @override
    def handle(self, args: argparse.Namespace) -> bool:
        if args.input is None or len(args.input) == 0:  # pragma: no cover
            return False
        filename: str = args.input[0].name

        if not filename.endswith(".py"):
            return False

        config = TelePySamplerConfig.from_namespace(args)
        with telepy_env(config, CodeMode.PyFile) as (global_dict, sampler):
            assert sampler is not None
            assert global_dict is not None
            code = args.input[0].read()
            pyc = compile(code, os.path.abspath(filename), "exec")
            sampler.start()
            if not in_coverage:
                weakref.finalize(sampler, telepy_finalize)  # pragma: no cover
            exec(pyc, global_dict)
        if in_coverage:
            telepy_finalize()
        return True


@register_handler
class PyCommandStringProfilingHandler(ArgsHandler):
    @classmethod
    def build(cls):
        return cls()

    def __init__(self, priority: int = 2048):
        super().__init__("PyCommandStringProfilingHandler", priority=priority)

    @override
    def handle(self, args: argparse.Namespace) -> bool:
        if args.cmd is None:
            return False
        str_code = args.cmd
        config = TelePySamplerConfig.from_namespace(args)
        with telepy_env(config, CodeMode.PyString) as (global_dict, sampler):
            assert sampler is not None
            assert global_dict is not None
            pyc = compile(str_code, "<string>", "exec")
            # see the enviroment.py:patch_multiprocesssing and patch_os_fork_in_child
            if not config.fork_server:
                sampler.start()
            if not in_coverage:
                weakref.finalize(sampler, telepy_finalize)  # pragma: no cover
            exec(pyc, global_dict)
        if in_coverage:
            telepy_finalize()
        return True


@register_handler
class PyCommandModuleProfilingHandler(ArgsHandler):
    @classmethod
    def build(cls):
        return cls()

    def __init__(self, priority: int = 2049):
        super().__init__("PyCommandModuleProfilingHandler", priority=priority)

    @override
    def handle(self, args: argparse.Namespace) -> bool:
        if args.module is None:
            return False
        module_name = args.module
        config = TelePySamplerConfig.from_namespace(args)
        with telepy_env(config, CodeMode.PyModule) as (global_dict, sampler):
            assert sampler is not None
            assert global_dict is not None
            import runpy

            code = "run_module(modname, run_name='__main__', alter_sys=False)"
            global_dict = {
                "run_module": runpy.run_module,
                "modname": module_name,
            }
            pyc = compile(code, "<string>", "exec")
            if not config.fork_server:
                sampler.start()
            if not in_coverage:  # pragma: no cover
                weakref.finalize(sampler, telepy_finalize)
            exec(pyc, global_dict)
        # coverage do not cover this line, god knows why
        if in_coverage:  # pragma: no cover
            telepy_finalize()
        return True  # pragma: no cover


@register_handler
class ShellHandler(ArgsHandler):
    @classmethod
    def build(cls):
        return cls()

    def __init__(self, priority: int = -1) -> None:
        super().__init__(name="shell", priority=priority)

    @override
    def handle(self, args: argparse.Namespace) -> bool:  # pragma: no cover
        if len(sys.argv) > 1:
            return False
        shell = TelePyShell()
        shell.run()
        return True


def dispatch(args: argparse.Namespace) -> None:
    for handler in handlers:
        if handler.handle(args):
            return

    raise RuntimeError(
        f"not found a proper handler to handle the arguments {args}, please check your arguments."  # noqa: E501
    )


def telepy_help(parser: argparse.ArgumentParser):
    parser.print_help()
    table = Table(title="Recommended Interval", show_lines=True)

    table.add_column("Task Duration", style="cyan", justify="right")
    table.add_column("Unit", style="green")
    table.add_column("Recommended Interval (μs)", style="magenta")

    table.add_row("< 1ms", "ms", "Uninstall TelePy, you do not need it at all.")
    table.add_row("< 100ms", "ms", "10")
    table.add_row("x seconds", "s", "1000")
    table.add_row("x minutes", "m", "10000")
    table.add_row("x hours", "h", "Up to you.")
    print()  # print a new line
    console.print(table)


def _pre_checks(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.help:
        telepy_help(parser)
        sys.exit(0)

    if args.version:
        print(f"TelePy version {__version__}")
        sys.exit(0)

    if args.create_config:
        config_manager = TelePyConfig()
        config_manager.create_example_config()
        sys.exit(0)


def main():
    arguments = sys.argv[1:]
    if "--" in arguments:
        arguments = arguments[: arguments.index("--")]

    # Merge configuration file with command line arguments
    arguments = merge_config_with_args(arguments)

    parser = argparse.ArgumentParser(
        description="TelePy is a very powerful python profiler and dignostic tool."
        " Report bugs here https://github.com/Chang-LeHung/telepy",
        add_help=False,
        formatter_class=RichHelpFormatter,
    )
    parser.add_argument(
        "-h", "--help", action="store_true", help="Show this help message and exit."
    )
    parser.add_argument(
        "-v", "--version", action="store_true", help="Show version information and exit."
    )
    parser.add_argument(
        "--verbose",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable verbose mode (default: True).",
    )
    parser.add_argument(
        "input",
        nargs="*",
        help="Input file(s), if run a python file, it must be ended with .py.",
        type=argparse.FileType("r"),
    )
    parser.add_argument(
        "-p",
        "--parse",
        action="store_true",
        help="Parse stack trace data to generate a flamegraph svg file, "
        "such as `telepy -p result.folded`. Multiple input files are supported, "
        "TelePy will merge them into a single SVG file.",
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=int,
        default=8000,
        help="Sampling interval in microseconds (default: 8000, i.e., 8 ms). "
        "The minimum value is 5; if a smaller value is specified, it will be"
        " set to 5. The larger the value, the higher the overhead. Howerever, if you "
        "enable debug mode, telepy will not check the value.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode (default: False). Print some debug information.",
    )
    parser.add_argument(
        "--time",
        choices=("cpu", "wall"),
        default="cpu",
        help="Select the timer source for sampling: 'cpu' uses SIGPROF/ITIMER_PROF,"
        " while 'wall' uses SIGALRM/ITIMER_REAL (default: cpu).",
    )
    parser.add_argument(
        "--full-path",
        action="store_true",
        help="Display absolute file path in the flamegraph (default: False).",
    )
    parser.add_argument(
        "--ignore-frozen",
        action="store_true",
        help="Ignore frozen modules (default: False).",
    )
    parser.add_argument(
        "--include-telepy",
        action="store_true",
        help="Whether to include telepy in the stack trace (default: False).",
    )
    parser.add_argument(
        "--focus-mode",
        action="store_true",
        help="Focus on user code by ignoring standard library and "
        "third-party packages (default: False).",
    )
    parser.add_argument(
        "--regex-patterns",
        action="append",
        help="Regex patterns for filtering stack traces. Only files or function/class "
        "names matching at least one pattern will be included. Can be specified multiple"
        " times.",
    )
    parser.add_argument(
        "--folded-save",
        action="store_true",
        help="Save folded stack traces to a file (default: False).",
    )
    parser.add_argument(
        "--folded-file",
        type=str,
        default="result.folded",
        help="Save folded stack traces into a file (default: result.folded). "
        "You should enable --folded-save if using this option.",
    )
    parser.add_argument(
        "-o", "--output", default="result.svg", help="Output file (default: result.svg)."
    )
    parser.add_argument(
        "--width",
        type=_positive_int,
        default=1200,
        help="SVG width in pixels for generated flamegraphs (default: 1200).",
    )
    parser.add_argument(
        "--merge",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Merge multiple flamegraph files in multiprocess environment (default: "
        "True). If not merge them, the child flamegraphs and foldeds will be named in "
        "the format `pid-ppid.svg` and `pid-ppid.folded` respectively. ",
    )
    parser.add_argument(
        "--mp", action="store_true", help=argparse.SUPPRESS
    )  # internal flag
    parser.add_argument(
        "--fork-server", action="store_true", help=argparse.SUPPRESS
    )  # internal flag
    parser.add_argument(
        "--timeout",
        type=float,
        default=10,
        help="Timeout (in seconds) for parent process to wait for child processes"
        " to merge flamegraph files (default: 10).",
    )
    parser.add_argument(
        "--tree-mode",
        action="store_true",
        help="Using call site line number instead of the first line of function(method).",
    )
    parser.add_argument(
        "--inverted",
        action="store_true",
        help="Render flame graphs with the root frame at the top (inverted orientation).",
    )
    parser.add_argument(
        "--disable-traceback",
        action="store_true",
        help="Disable the rich(colorful) traceback and use the default traceback.",
    )
    parser.add_argument(
        "-c",
        "--cmd",
        type=str,
        help="program passed in as string.",
    )
    parser.add_argument(
        "--module",
        "-m",
        type=str,
        help="run library module as a script.",
    )
    parser.add_argument(
        "--create-config",
        action="store_true",
        help="Create an example configuration file at ~/.telepy/.telepyrc and exit.",
    )
    # PyTorch profiler arguments
    parser.add_argument(
        "--torch-profile",
        action="store_true",
        help="Enable PyTorch profiler integration (default: False).",
    )
    parser.add_argument(
        "--torch-output-dir",
        type=str,
        default="./pytorch_profiles",
        help="Directory to save PyTorch profiler outputs (default: ./pytorch_profiles).",
    )
    parser.add_argument(
        "--torch-activities",
        action="append",
        choices=["cpu", "cuda", "xpu"],
        help="PyTorch profiler activities to profile. Can be specified multiple times. "
        "Options: cpu, cuda, xpu. Default: ['cpu'].",
    )
    parser.add_argument(
        "--torch-record-shapes",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether to record tensor shapes in PyTorch profiler (default: True).",
    )
    parser.add_argument(
        "--torch-profile-memory",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether to profile memory usage in PyTorch profiler (default: True).",
    )
    parser.add_argument(
        "--torch-with-stack",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Whether to record call stack in PyTorch profiler (default: False).",
    )
    parser.add_argument(
        "--torch-export-chrome-trace",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Whether to export Chrome trace format from PyTorch profiler "
        "(default: False).",
    )
    parser.add_argument(
        "--torch-sort-by",
        type=str,
        default="cpu_time_total",
        help="Sort key for PyTorch profiler statistics (default: cpu_time_total). "
        "Options: cpu_time, cuda_time, cpu_time_total, cuda_time_total, "
        "cpu_memory_usage, cuda_memory_usage, self_cpu_memory_usage, "
        "self_cuda_memory_usage, count.",
    )
    parser.add_argument(
        "--torch-row-limit",
        type=int,
        default=10,
        help="Maximum number of rows in PyTorch profiler statistics table "
        "(default: 10). Set to -1 for unlimited rows (may cause OOM for large profiles).",
    )

    args = parser.parse_args(arguments)
    _pre_checks(args, parser)
    if not args.disable_traceback:
        install()
    try:
        dispatch(args)
    except Exception as e:
        if not args.disable_traceback:
            console.print(
                Panel(
                    "[bold red]The following traceback may be useful for debugging.[/bold red]"  # noqa: E501
                    " If [bold cyan]telepy[/bold cyan] leads to this error, please report it at:"  # noqa: E501
                    " [underline blue]https://github.com/Chang-LeHung/telepy/issues[/underline blue]",  # noqa: E501
                    title="[bold yellow]⚠ Error Traceback[/bold yellow]",
                    style="red",
                    border_style="bright_red",
                )
            )
            tb = Traceback()
            err_console.print(tb)
            err_console.print(
                "[bold cyan]You can also try running with --disable-traceback for a simpler output.[/bold cyan]"  # noqa: E501
            )
        else:
            print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
