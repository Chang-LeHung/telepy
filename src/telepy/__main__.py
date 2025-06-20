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
from .environment import CodeMode, telepy_env, telepy_finalize
from .flamegraph import FlameGraph

install()

console = logger.console


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

    def __str__(self):
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
        pass

    @classmethod
    @abstractmethod
    def build(cls) -> "ArgsHandler":
        pass

    def __lt__(self, other: "ArgsHandler") -> bool:
        return self.weight > other.weight  # big heap


handlers: list[ArgsHandler] = []


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
        flamegraph = FlameGraph(
            [line for line in args.input[0] if line.strip() != ""], reverse=args.reverse
        )
        flamegraph.parse_input()
        svg = flamegraph.generate_svg()

        if args.output is None:
            print(
                "[red]output file is not specified, using result.svg as default[/red]",
                file=sys.stderr,
            )
            args.output = "result.svg"
        args.input[0].close()
        with open(args.output, "w") as f:
            f.write(svg)
        logger.log_success_panel(
            f"Generated a flamegraph svg file `{args.output}` from the stack "
            f"trace file `{args.input[0].name}`, "
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
        if args.input is None:
            return False
        filename: str = args.input[0].name

        if not filename.endswith(".py"):
            return False

        with telepy_env(args, CodeMode.PyFile) as (global_dict, sampler):
            assert sampler is not None
            assert global_dict is not None
            code = args.input[0].read()
            pyc = compile(code, os.path.abspath(filename), "exec")
            sampler.start()
            exec(pyc, global_dict)
            weakref.finalize(sampler, telepy_finalize)
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
        with telepy_env(args, CodeMode.PyString) as (global_dict, sampler):
            assert sampler is not None
            assert global_dict is not None
            pyc = compile(str_code, "<string>", "exec")
            # see the enviroment.py:patch_multiprocesssing and patch_os_fork_in_child
            if not args.fork_server:
                sampler.start()
            exec(pyc, global_dict)
            weakref.finalize(sampler, telepy_finalize)
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
        with telepy_env(args, CodeMode.PyModule) as (global_dict, sampler):
            assert sampler is not None
            assert global_dict is not None
            import runpy

            code = "run_module(modname, run_name='__main__', alter_sys=False)"
            global_dict = {
                "run_module": runpy.run_module,
                "modname": module_name,
            }
            pyc = compile(code, "<string>", "exec")
            if not sampler.forkserver:
                sampler.start()
            exec(pyc, global_dict)
            weakref.finalize(sampler, telepy_finalize)
        return True


@register_handler
class ShellHandler(ArgsHandler):
    @classmethod
    def build(cls):
        return cls()

    def __init__(self, priority: int = -1) -> None:
        super().__init__(name="shell", priority=priority)

    @override
    def handle(self, args: argparse.Namespace) -> bool:
        return False


def dispatch(args: argparse.Namespace) -> None:
    for handler in handlers:
        if handler.handle(args):
            return

    raise RuntimeError(
        f"not found a proper handler to handle the arguments {args}, [green]please check your arguments.[/green]"  # noqa: E501
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


def _pre_chceck(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.help:
        telepy_help(parser)
        sys.exit(0)


def main():
    arguments = sys.argv[1:]
    if "--" in arguments:
        arguments = arguments[: arguments.index("--")]
    parser = argparse.ArgumentParser(
        description="TelePy is a very powerful python profiler and dignostic tool."
        " If it helps, you can star it here https://github.com/Chang-LeHung/telepy",
        add_help=False,
        formatter_class=RichHelpFormatter,
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
        "such as `telepy -p result.folded`.",
    )
    parser.add_argument(
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
        "--folded-save",
        action="store_true",
        help="Save folded stack traces to a file (default: False).",
    )
    parser.add_argument(
        "--folded-file",
        type=str,
        default="result.folded",
        help="Save folded stack traces into a file (default: result.folded). "
        "You should enable --folded-file if using this option.",
    )
    parser.add_argument(
        "-o", "--output", default="result.svg", help="Output file (default: result.svg)."
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        default=True,
        help="Merge multiple flamegraph files in multiprocess environment (default: "
        "True). If not merge them, the child flamegraphs and foldeds will be named in "
        "the format `pid-ppid.svg` and `pid-ppid.folded` respectively. ",
    )
    parser.add_argument(
        "--no-merge",
        dest="merge",
        action="store_false",
        help="Disable --merge",
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
        default=10.0,
        help="Timeout (in seconds) for parent process to wait for child processes"
        " to merge flamegraph files (default: 10.0).",
    )
    parser.add_argument(
        "-r",
        "--reverse",
        action="store_true",
        help=argparse.SUPPRESS,  # TODO: implement it!
    )
    parser.add_argument(
        "--tree-mode",
        action="store_true",
        help="Using call site line number instead of the first line of function(method).",
    )
    parser.add_argument(
        "--disbale-traceback",
        action="store_true",
        help="Disable the rich(colorfule) traceback and use the default traceback.",
    )
    parser.add_argument(
        "-c",
        "--cmd",
        type=str,
        help="Command to run (default: None).",
    )
    parser.add_argument(
        "--module",
        "-m",
        type=str,
        help="Module to run (default: None).",
    )
    parser.add_argument(
        "-h", "--help", action="store_true", help="Show this help message and exit."
    )

    args = parser.parse_args(arguments)
    _pre_chceck(args, parser)
    if not args.disbale_traceback:
        install()
    try:
        dispatch(args)
    except Exception as _:
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
        if not args.disbale_traceback:
            tb = Traceback()
            console.print(tb)
        else:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
