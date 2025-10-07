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

import argparse
from typing import Final, cast

from .gc_analyzer import get_analyzer
from .server import TelePyApp, TelePyRequest, TelePyResponse
from .system import TelePySystem

TELEPY_SYSTEM: Final = "system"
ERROR_CODE: Final = -1
SUCCESS_CODE: Final = 0


def shutdown(req: TelePyRequest, resp: TelePyResponse) -> None:
    resp.return_json(
        {
            "data": "TelePy monitor is shutting down...",
            "code": SUCCESS_CODE,
        }
    )
    req.app.defered_shutdown()


def stack(req: TelePyRequest, resp: TelePyResponse):
    """
    Get the stack trace of all threads
    Example:
    {
        "data": [
            {
                "stack": ["telepy.py", "<module>],
                "name": "MainThread",
                "id": 1234567890,
                "daemon": true
            }
        ]
    }
    """
    system = cast(TelePySystem, req.app.lookup(TELEPY_SYSTEM))
    resp.return_json(
        {
            "data": system.thread(),
            "code": SUCCESS_CODE,
        }
    )  # type: ignore


def ping(req: TelePyRequest, resp: TelePyResponse):
    resp.return_json(
        {
            "data": "pong",
            "server": "TelePy Monitor",
            "code": SUCCESS_CODE,
        }
    )


def profile(req: TelePyRequest, resp: TelePyResponse):
    from argparse import ArgumentError

    def create_start_parser():
        parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
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
        parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
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
    system = cast(TelePySystem, req.app.lookup(TELEPY_SYSTEM))
    if len(args) == 0:
        resp.return_json(
            {"data": "No arguments provided, use 'start' or 'stop'", "code": ERROR_CODE}
        )
        return
    if args[0] == "start":
        parser = create_start_parser()
        try:
            parse_args = parser.parse_args(args[1:])
        except ArgumentError as e:
            resp.return_json({"data": e.message, "code": ERROR_CODE})
            return
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
        try:
            parse_args = parser.parse_args(args[1:])
        except ArgumentError as e:
            resp.return_json({"data": e.message, "code": ERROR_CODE})
            return
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


def gc_status(req: TelePyRequest, resp: TelePyResponse):
    """Get Python garbage collection status."""
    from argparse import ArgumentError

    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument(
        "--help",
        "-h",
        default=False,
        action="store_true",
        help="Show this help message and exit",
    )

    args = req.headers.get("args", "").strip().split()
    try:
        parse_args = parser.parse_args(args)
    except ArgumentError as e:
        resp.return_json({"data": e.message, "code": ERROR_CODE})
        return

    if parse_args.help:
        resp.return_json({"data": parser.format_help(), "code": SUCCESS_CODE})
        return

    analyzer = get_analyzer()
    status = analyzer.get_status()
    resp.return_json({"data": status, "code": SUCCESS_CODE})


def gc_stats(req: TelePyRequest, resp: TelePyResponse):
    """Get detailed garbage collection statistics."""
    from argparse import ArgumentError

    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument(
        "--help",
        "-h",
        default=False,
        action="store_true",
        help="Show this help message and exit",
    )

    args = req.headers.get("args", "").strip().split()
    try:
        parse_args = parser.parse_args(args)
    except ArgumentError as e:
        resp.return_json({"data": e.message, "code": ERROR_CODE})
        return

    if parse_args.help:
        resp.return_json({"data": parser.format_help(), "code": SUCCESS_CODE})
        return

    analyzer = get_analyzer()
    stats = analyzer.get_stats_summary()
    resp.return_json({"data": stats, "code": SUCCESS_CODE})


def gc_objects(req: TelePyRequest, resp: TelePyResponse):
    """Get statistics about tracked objects by type."""
    from argparse import ArgumentError

    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
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
    try:
        parse_args = parser.parse_args(args)
    except ArgumentError as e:
        resp.return_json({"data": e.message, "code": ERROR_CODE})
        return

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


def gc_garbage(req: TelePyRequest, resp: TelePyResponse):
    """Get information about uncollectable garbage objects."""
    from argparse import ArgumentError

    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument(
        "--help",
        "-h",
        default=False,
        action="store_true",
        help="Show this help message and exit",
    )

    args = req.headers.get("args", "").strip().split()
    try:
        parse_args = parser.parse_args(args)
    except ArgumentError as e:
        resp.return_json({"data": e.message, "code": ERROR_CODE})
        return

    if parse_args.help:
        resp.return_json({"data": parser.format_help(), "code": SUCCESS_CODE})
        return

    analyzer = get_analyzer()
    garbage_info = analyzer.get_garbage_info()
    resp.return_json({"data": garbage_info, "code": SUCCESS_CODE})


def gc_collect(req: TelePyRequest, resp: TelePyResponse):
    """Manually trigger garbage collection."""
    from argparse import ArgumentError

    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
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
    try:
        parse_args = parser.parse_args(args)
    except ArgumentError as e:
        resp.return_json({"data": e.message, "code": ERROR_CODE})
        return

    if parse_args.help:
        resp.return_json({"data": parser.format_help(), "code": SUCCESS_CODE})
        return

    analyzer = get_analyzer()
    result = analyzer.collect_garbage(generation=parse_args.generation)
    resp.return_json({"data": result, "code": SUCCESS_CODE})


def gc_monitor(req: TelePyRequest, resp: TelePyResponse):
    """Monitor garbage collection activity since last check."""
    from argparse import ArgumentError

    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument(
        "--help",
        "-h",
        default=False,
        action="store_true",
        help="Show this help message and exit",
    )

    args = req.headers.get("args", "").strip().split()
    try:
        parse_args = parser.parse_args(args)
    except ArgumentError as e:
        resp.return_json({"data": e.message, "code": ERROR_CODE})
        return

    if parse_args.help:
        resp.return_json({"data": parser.format_help(), "code": SUCCESS_CODE})
        return

    analyzer = get_analyzer()
    monitor_result = analyzer.monitor_collection_activity()
    resp.return_json({"data": monitor_result, "code": SUCCESS_CODE})


class TelePyMonitor:
    def __init__(self, port: int = 8026, host: str = "127.0.0.1", log=True):
        app = TelePyApp(port=port, host=host, log=log)
        app.register(TELEPY_SYSTEM, TelePySystem())
        app.route("/shutdown")(shutdown)
        app.route("/stack")(stack)
        app.route("/ping")(ping)
        app.route("/profile")(profile)
        app.route("/gc-status")(gc_status)
        app.route("/gc-stats")(gc_stats)
        app.route("/gc-objects")(gc_objects)
        app.route("/gc-garbage")(gc_garbage)
        app.route("/gc-collect")(gc_collect)
        app.route("/gc-monitor")(gc_monitor)
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
        TelePyApp.enable_address_reuse()

    @staticmethod
    def disable_address_reuse():
        TelePyApp.disable_address_reuse()
