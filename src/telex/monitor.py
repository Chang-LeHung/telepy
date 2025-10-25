"""
All http response should be in json format and should have following structure:
```
{
    "data": "response data",
    "code": 0
}
If code is not 0, it means there is an error.
If code is 0, the data represents the successful msg, otherwise it represent error msg.
```
"""

from __future__ import annotations

import argparse
import io
import sys
from collections.abc import Callable
from typing import Final, cast

from .gc_analyzer import get_analyzer
from .server import TeleXApp, TeleXRequest, TeleXResponse
from .system import TelePySystem

TELEX_SYSTEM: Final = "system"
ERROR_CODE: Final = -1
SUCCESS_CODE: Final = 0

# Global registry for endpoints
ENDPOINT_REGISTRY: dict[str, Callable[[TeleXRequest, TeleXResponse], None]] = {}


def safe_parse_args(parser: argparse.ArgumentParser, args: list[str]):
    """
    Safely parse arguments handling both ArgumentError and SystemExit exceptions.

    Args:
        parser: The ArgumentParser instance
        args: List of arguments to parse

    Returns:
        tuple: (success: bool, result: Namespace or error_message: str)
    """
    # Capture stderr to get error messages
    old_stderr = sys.stderr
    sys.stderr = io.StringIO()

    try:
        parsed_args = parser.parse_args(args)
        return True, parsed_args
    except (argparse.ArgumentError, SystemExit) as e:
        error_output = sys.stderr.getvalue()

        # Extract the error message from stderr or exception
        if error_output:
            # Remove 'usage:' line and keep only the error
            lines = error_output.strip().split("\n")
            error_msg = "\n".join(
                line for line in lines if line and not line.startswith("usage:")
            )
            # Remove the program name prefix from error line
            if ":" in error_msg:
                error_msg = error_msg.split(":", 1)[1].strip()
                if error_msg.startswith("error:"):
                    error_msg = error_msg[6:].strip()
        elif isinstance(e, argparse.ArgumentError):
            error_msg = e.message
        else:
            error_msg = str(e)

        return False, error_msg
    finally:
        sys.stderr = old_stderr


def register_endpoint(path: str):
    """
    Decorator to register an endpoint with the global endpoint registry.

    Args:
        path: The endpoint path (e.g., "/shutdown", "/stack")

    Raises:
        ValueError: If the path is already registered

    Example:
        @register_endpoint("/my-endpoint")
        def my_handler(req: TeleXRequest, resp: TeleXResponse):
            resp.return_json({"data": "success", "code": 0})
    """

    def decorator(
        func: Callable[[TeleXRequest, TeleXResponse], None],
    ) -> Callable[[TeleXRequest, TeleXResponse], None]:
        if path in ENDPOINT_REGISTRY:
            raise ValueError(
                f"Endpoint path '{path}' is already registered. "
                f"Cannot overwrite existing endpoint."
            )
        ENDPOINT_REGISTRY[path] = func
        return func

    return decorator


@register_endpoint("/shutdown")
def shutdown(req: TeleXRequest, resp: TeleXResponse) -> None:
    resp.return_json(
        {
            "data": "TeleX monitor is shutting down...",
            "code": SUCCESS_CODE,
        }
    )
    req.app.defered_shutdown()


@register_endpoint("/stack")
def stack(req: TeleXRequest, resp: TeleXResponse):
    """
    Get the stack trace of all threads and format it on the server side.

    The response will be a formatted string showing each thread's information
    and its complete stack trace with indentation for better readability.

    Args:
        --strip-site-packages, -s: Remove sys.base_prefix from paths
        --strip-cwd, -c: Remove current working directory prefix
        --help, -h: Show help message
    """
    import os
    import sys

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--strip-site-packages",
        "-s",
        action="store_true",
        default=False,
        help="Remove sys.base_prefix from paths",
    )
    parser.add_argument(
        "--strip-cwd",
        "-c",
        action="store_true",
        default=False,
        help="Remove current working directory prefix from stack traces",
    )
    parser.add_argument(
        "--help",
        "-h",
        action="store_true",
        default=False,
        help="Show this help message and exit",
    )

    args_str = req.headers.get("args", "").strip()
    args_list = args_str.split() if args_str else []

    success, result = safe_parse_args(parser, args_list)
    if not success:
        resp.return_json({"data": result, "code": ERROR_CODE})
        return

    parse_args = result
    if parse_args.help:
        resp.return_json({"data": parser.format_help(), "code": SUCCESS_CODE})
        return

    system = cast(TelePySystem, req.app.lookup(TELEX_SYSTEM))
    thread_data = system.thread()

    # Get sys.base_prefix for stripping
    base_prefix = sys.base_prefix if parse_args.strip_site_packages else None

    # Get current working directory for stripping
    cwd = os.getcwd() if parse_args.strip_cwd else None

    def strip_path(path: str) -> str:
        """Strip common path prefixes from a file path.

        Applies path stripping based on command-line flags:
        - strip_site_packages: Remove sys.base_prefix from paths
        - strip_cwd: Remove current working directory prefix
        """
        # Strip sys.base_prefix (if requested)
        if base_prefix and path.startswith(base_prefix):
            return path[len(base_prefix) :].lstrip("/")

        # Strip current working directory (if requested)
        if cwd and path.startswith(cwd):
            return path[len(cwd) :].lstrip("/")

        return path

    # Format the stack traces with simple indentation
    lines = []
    for idx, item in enumerate(thread_data):
        if idx > 0:
            lines.append("")  # Add blank line between threads

        # Thread header
        lines.append(f"Thread ({item['id']}, {item['name']}, daemon={item['daemon']})")

        # Add indented stack frames with path stripping
        stack_lines = item["stack"].strip().split("\n")
        for frame_line in stack_lines:
            # Always strip standard lib paths, conditionally strip cwd
            # Frame format: "path:line function_name"
            if ":" in frame_line:
                path_part, rest = frame_line.split(":", 1)
                stripped_path = strip_path(path_part)
                frame_line = f"{stripped_path}:{rest}"

            lines.append(f"  {frame_line}")

    formatted_output = "\n".join(lines)

    resp.return_json(
        {
            "data": formatted_output,
            "code": SUCCESS_CODE,
        }
    )


@register_endpoint("/ping")
def ping(req: TeleXRequest, resp: TeleXResponse):
    resp.return_json(
        {
            "data": "pong",
            "server": "TeleX Monitor",
            "code": SUCCESS_CODE,
        }
    )


@register_endpoint("/profile")
def profile(req: TeleXRequest, resp: TeleXResponse):
    def create_start_parser():
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument(
            "--interval",
            type=int,
            default=1000,
            help="Interval in milliseconds",
        )
        parser.add_argument(
            "--ignore-frozen",
            action="store_true",
            default=False,
            help="Ignore frozen objects",
        )
        parser.add_argument(
            "--ignore-self",
            action="store_true",
            default=False,
            help="Ignore the telepy",
        )
        parser.add_argument(
            "--help",
            "-h",
            default=False,
            action="store_true",
            help="Show this help message and exit",
        )

        return parser

    def create_stop_parser():
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument(
            "-f",
            "--filename",
            type=str,
            default=None,
            help="Filename to save the flame graph",
        )
        parser.add_argument(
            "--help",
            "-h",
            default=False,
            action="store_true",
            help="Show this help message and exit",
        )
        parser.add_argument(
            "--save-folded",
            action="store_true",
            default=False,
            help="Save the flame graph in folded format",
        )
        parser.add_argument(
            "--folded-filename",
            type=str,
            default=None,
            help="Filename to save the flame graph",
        )
        parser.add_argument(
            "--inverted",
            action="store_true",
            default=False,
            help="Render flame graphs with the root frame at the top "
            "(inverted orientation)",
        )
        return parser

    args = req.headers["args"].split()
    system = cast(TelePySystem, req.app.lookup(TELEX_SYSTEM))
    if len(args) == 0:
        resp.return_json(
            {"data": "No arguments provided, use 'start' or 'stop'", "code": ERROR_CODE}
        )
        return
    if args[0] == "start":
        parser = create_start_parser()
        success, result = safe_parse_args(parser, args[1:])
        if not success:
            resp.return_json({"data": result, "code": ERROR_CODE})
            return
        parse_args = result
        if parse_args.help:
            resp.return_json({"data": parser.format_help(), "code": SUCCESS_CODE})
            return
        ret = system.start_profiling(
            interval=parse_args.interval,
            ignore_frozen=parse_args.ignore_frozen,
            ignore_self=parse_args.ignore_self,
        )
        if ret:
            resp.return_json({"data": "Profiler started", "code": SUCCESS_CODE})
        else:  # pragma: no cover
            # the command profile will lead to dead lock so we do not test it.
            resp.return_json({"data": "Profiler already started", "code": SUCCESS_CODE})
    elif args[0] == "stop":
        parser = create_stop_parser()
        success, result = safe_parse_args(parser, args[1:])
        if not success:
            resp.return_json({"data": result, "code": ERROR_CODE})
            return
        parse_args = result
        if parse_args.help:
            resp.return_json({"data": parser.format_help(), "code": SUCCESS_CODE})
            return
        try:
            filename, folded_name = system.finish_profiling(
                filename=parse_args.filename,
                save_folded=parse_args.save_folded,
                folded_filename=parse_args.folded_filename,
                inverted=parse_args.inverted,
            )
            msg = f"Profiler stopped, flame graph was saved to {filename}"
            if parse_args.save_folded:
                msg += f" and the folded file was saved to {folded_name}"
            resp.return_json(
                {
                    "data": msg,
                    "code": SUCCESS_CODE,
                }
            )
        except RuntimeError as e:
            resp.return_json({"data": str(e), "code": ERROR_CODE})
    else:
        resp.return_json(
            {"data": "Invalid argument, use 'start' or 'stop'", "code": ERROR_CODE}
        )


@register_endpoint("/gc-status")
def gc_status(req: TeleXRequest, resp: TeleXResponse):
    """Get Python garbage collection status."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--help",
        "-h",
        default=False,
        action="store_true",
        help="Show this help message and exit",
    )

    args = req.headers.get("args", "").strip().split()
    success, result = safe_parse_args(parser, args)
    if not success:
        resp.return_json({"data": result, "code": ERROR_CODE})
        return

    parse_args = result
    if parse_args.help:
        resp.return_json({"data": parser.format_help(), "code": SUCCESS_CODE})
        return

    analyzer = get_analyzer()
    status = analyzer.get_status()
    resp.return_json({"data": status, "code": SUCCESS_CODE})


@register_endpoint("/gc-stats")
def gc_stats(req: TeleXRequest, resp: TeleXResponse):
    """Get detailed garbage collection statistics."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--help",
        "-h",
        default=False,
        action="store_true",
        help="Show this help message and exit",
    )

    args = req.headers.get("args", "").strip().split()
    success, result = safe_parse_args(parser, args)
    if not success:
        resp.return_json({"data": result, "code": ERROR_CODE})
        return

    parse_args = result
    if parse_args.help:
        resp.return_json({"data": parser.format_help(), "code": SUCCESS_CODE})
        return

    analyzer = get_analyzer()
    stats = analyzer.get_stats_summary()
    resp.return_json({"data": stats, "code": SUCCESS_CODE})


@register_endpoint("/gc-objects")
def gc_objects(req: TeleXRequest, resp: TeleXResponse):
    """Get statistics about tracked objects by type."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=20,
        help="Limit the number of object types to display (default: 20)",
    )
    parser.add_argument(
        "--generation",
        "-g",
        type=int,
        default=None,
        choices=[0, 1, 2],
        help="Specify which generation to analyze (0, 1, or 2, default: all generations)",
    )
    parser.add_argument(
        "--calculate-memory",
        "-m",
        action="store_true",
        default=False,
        help="Calculate memory usage for each object type",
    )
    parser.add_argument(
        "--sort-by",
        "-s",
        type=str,
        default="count",
        choices=["count", "memory", "avg_memory"],
        help="Sort by 'count' (default), 'memory', or 'avg_memory' "
        "(requires -m/--calculate-memory)",
    )
    parser.add_argument(
        "--help",
        "-h",
        default=False,
        action="store_true",
        help="Show this help message and exit",
    )

    args = req.headers.get("args", "").strip().split()
    success, result = safe_parse_args(parser, args)
    if not success:
        resp.return_json({"data": result, "code": ERROR_CODE})
        return

    parse_args = result
    if parse_args.help:
        resp.return_json({"data": parser.format_help(), "code": SUCCESS_CODE})
        return

    # Validate sort_by parameter
    if parse_args.sort_by in ["memory", "avg_memory"] and not parse_args.calculate_memory:
        resp.return_json(
            {
                "data": f"Error: --sort-by {parse_args.sort_by} requires "
                "--calculate-memory/-m",
                "code": ERROR_CODE,
            }
        )
        return

    analyzer = get_analyzer()
    try:
        formatted = analyzer.get_object_stats_formatted(
            generation=parse_args.generation,
            limit=parse_args.limit,
            calculate_memory=parse_args.calculate_memory,
            sort_by=parse_args.sort_by,
        )
        resp.return_json({"data": formatted, "code": SUCCESS_CODE})
    except ValueError as e:
        resp.return_json({"data": str(e), "code": ERROR_CODE})


@register_endpoint("/gc-garbage")
def gc_garbage(req: TeleXRequest, resp: TeleXResponse):
    """Get information about uncollectable garbage objects."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--help",
        "-h",
        default=False,
        action="store_true",
        help="Show this help message and exit",
    )

    args = req.headers.get("args", "").strip().split()
    success, result = safe_parse_args(parser, args)
    if not success:
        resp.return_json({"data": result, "code": ERROR_CODE})
        return

    parse_args = result
    if parse_args.help:
        resp.return_json({"data": parser.format_help(), "code": SUCCESS_CODE})
        return

    analyzer = get_analyzer()
    garbage_info = analyzer.get_garbage_info()
    resp.return_json({"data": garbage_info, "code": SUCCESS_CODE})


@register_endpoint("/gc-collect")
def gc_collect(req: TeleXRequest, resp: TeleXResponse):
    """Manually trigger garbage collection."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--generation",
        "-g",
        type=int,
        default=2,
        choices=[0, 1, 2],
        help="Specify which generation to collect (0, 1, or 2, default: 2)",
    )
    parser.add_argument(
        "--help",
        "-h",
        default=False,
        action="store_true",
        help="Show this help message and exit",
    )

    args = req.headers.get("args", "").strip().split()
    success, result = safe_parse_args(parser, args)
    if not success:
        resp.return_json({"data": result, "code": ERROR_CODE})
        return

    parse_args = result
    if parse_args.help:
        resp.return_json({"data": parser.format_help(), "code": SUCCESS_CODE})
        return

    analyzer = get_analyzer()
    result = analyzer.collect_garbage(generation=parse_args.generation)
    resp.return_json({"data": result, "code": SUCCESS_CODE})


@register_endpoint("/gc-monitor")
def gc_monitor(req: TeleXRequest, resp: TeleXResponse):
    """Monitor garbage collection activity since last check."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--help",
        "-h",
        default=False,
        action="store_true",
        help="Show this help message and exit",
    )

    args = req.headers.get("args", "").strip().split()
    success, result = safe_parse_args(parser, args)
    if not success:
        resp.return_json({"data": result, "code": ERROR_CODE})
        return

    parse_args = result
    if parse_args.help:
        resp.return_json({"data": parser.format_help(), "code": SUCCESS_CODE})
        return

    analyzer = get_analyzer()
    monitor_result = analyzer.monitor_collection_activity()
    resp.return_json({"data": monitor_result, "code": SUCCESS_CODE})


class TeleXMonitor:
    def __init__(self, port: int = 8026, host: str = "127.0.0.1", log=True):
        app = TeleXApp(port=port, host=host, log=log)
        app.register(TELEX_SYSTEM, TelePySystem())

        # Automatically register all endpoints from the global registry
        for path, handler in ENDPOINT_REGISTRY.items():
            app.route(path)(handler)

        self.app = app

    def run(self):
        self.app.run()

    def close(self):
        self.app.close()

    def shutdown(self):  # pragma: no cover
        self.app.shutdown()

    @property
    def is_alive(self) -> bool:
        return self.app.is_alive

    @staticmethod
    def enable_address_reuse():
        TeleXApp.enable_address_reuse()

    @staticmethod
    def disable_address_reuse():
        TeleXApp.disable_address_reuse()
