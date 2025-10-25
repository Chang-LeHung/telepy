"""
Convert Chrome Trace Event Format trace.json to folded stack format.

This module reads Chrome Trace Event Format trace.json files and converts them
to the folded stack format used by TeleX for flame graph generation.
Each trace line starts with Process(pid);Thread(tid); followed by the stack trace.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from rich_argparse import RichHelpFormatter

from . import logger

console = logger.console
err_console = logger.err_console


class ChromeTraceConverter:
    """Convert Chrome Trace Event Format trace events to folded stack format."""

    def __init__(self, trace_file: str):
        """
        Initialize the converter with a trace file.

        Args:
            trace_file: Path to the Chrome Trace Event Format trace.json file
        """
        self.trace_file = Path(trace_file)
        self.events: list[dict[str, Any]] = []
        self.stacks: dict[str, int] = defaultdict(int)

    def load_trace(self) -> None:
        """Load trace events from the JSON file."""
        with open(self.trace_file) as f:
            data = json.load(f)
            self.events = data.get("traceEvents", [])

    def _format_stack_line(self, pid: int, tid: int, stack: list[str]) -> str:
        """
        Format a single stack trace line in folded format.

        Args:
            pid: Process ID
            tid: Thread ID
            stack: List of function names in the stack (bottom to top)

        Returns:
            Formatted folded stack line
        """
        prefix = f"Process({pid});Thread({tid})"
        if stack:
            stack_str = ";".join(stack)
            return f"{prefix};{stack_str}"
        return prefix

    def _extract_event_name(self, event: dict[str, Any]) -> str | None:
        """
        Extract the event name from a trace event.

        Args:
            event: Trace event dictionary

        Returns:
            Event name or None if not applicable
        """
        # Only process X (Complete) phase events with a name
        if event.get("ph") == "X" and "name" in event:
            name = event["name"]
            category = event.get("cat", "")
            # Format: category::name or just name
            if category:
                return f"{category}::{name}"
            return name
        return None

    def _build_call_tree(self) -> dict[tuple[int, int], list[dict[str, Any]]]:
        """
        Build a call tree by organizing events into nested structures.

        Groups events by (pid, tid) and sorts them by timestamp.

        Returns:
            Dictionary mapping (pid, tid) to list of events for that thread
        """
        # Group events by (pid, tid)
        thread_events: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)

        for event in self.events:
            # Only process X (Complete) events with duration
            if event.get("ph") != "X" or "dur" not in event:
                continue

            pid = event.get("pid", 0)
            tid = event.get("tid", 0)
            ts = event.get("ts", 0)
            dur = event.get("dur", 0)

            # Add start and end times
            event_copy = event.copy()
            event_copy["start"] = ts
            event_copy["end"] = ts + dur

            thread_events[(pid, tid)].append(event_copy)

        # Sort events by start time within each thread
        for key in thread_events:
            thread_events[key].sort(key=lambda e: (e["start"], -e["end"]))

        return thread_events

    def _build_stack_trace(
        self, events: list[dict[str, Any]], index: int, current_time: float
    ) -> list[str]:
        """
        Build a stack trace by finding parent events.

        An event A is a parent of event B if:
        - A.start <= B.start
        - A.end >= B.end
        - A is the closest such event to B

        Args:
            events: Sorted list of events for a thread
            index: Index of the current event
            current_time: Current timestamp

        Returns:
            Stack trace from root to current event
        """
        if index >= len(events):
            return []

        current_event = events[index]
        current_start = current_event["start"]
        current_end = current_event["end"]

        # Build stack by finding all enclosing events
        stack = []

        # Find all events that contain the current event
        for i in range(len(events)):
            if i == index:
                continue

            parent = events[i]
            parent_start = parent["start"]
            parent_end = parent["end"]

            # Check if parent contains current event
            if parent_start <= current_start and parent_end >= current_end:
                # Get parent name
                name = self._extract_event_name(parent)
                if name:
                    # Store with depth info for sorting
                    duration = parent_end - parent_start
                    stack.append((parent_start, parent_end, duration, name))

        # Sort by start time and duration (larger durations first = outer frames)
        stack.sort(key=lambda x: (x[0], -x[2]))

        # Extract just the names
        result = [item[3] for item in stack]

        # Add current event at the end (top of stack)
        current_name = self._extract_event_name(current_event)
        if current_name:
            result.append(current_name)

        return result

    def convert_to_folded(self) -> dict[str, int]:
        """
        Convert trace events to folded stack format.

        This method builds proper call stacks by analyzing event nesting.
        Events are grouped by thread, sorted by time, and nested based on
        their time ranges.

        Returns:
            Dictionary mapping folded stack lines to sample counts
        """
        # Build call tree organized by thread
        thread_events = self._build_call_tree()

        # Process each thread's events
        for (pid, tid), events in thread_events.items():
            # Process each event
            for i, event in enumerate(events):
                duration = event.get("dur", 0)
                if duration <= 0:
                    continue

                # Build stack trace for this event
                stack = self._build_stack_trace(events, i, event["start"])

                if not stack:
                    continue

                # Format the folded line
                folded_line = self._format_stack_line(pid, tid, stack)

                # Use duration as the sample count (rounded to nearest int)
                # Duration is in microseconds, multiply by 100 for better visibility
                count = max(1, round(duration * 100))
                self.stacks[folded_line] += count

        return self.stacks

    def save_folded(self, output_file: str) -> None:
        """
        Save the folded stacks to a file.

        Args:
            output_file: Path to the output folded file
        """
        output_path = Path(output_file)
        with open(output_path, "w") as f:
            for stack_line, count in sorted(self.stacks.items()):
                f.write(f"{stack_line} {count}\n")

    def convert(self, output_file: str | None = None) -> str:
        """
        Complete conversion pipeline: load, convert, and save.

        Args:
            output_file: Path to save the folded output.
                        If None, defaults to trace_file with .folded extension

        Returns:
            Path to the output file
        """
        if output_file is None:
            output_file = str(self.trace_file.with_suffix(".folded"))

        self.load_trace()
        self.convert_to_folded()
        self.save_folded(output_file)

        return output_file


def convert_chrome_trace_to_folded(
    trace_file: str, output_file: str | None = None
) -> str:
    """
    Convenience function to convert a Chrome Trace trace to folded format.

    Args:
        trace_file: Path to the Chrome Trace Event Format trace.json file
        output_file: Path to save the folded output.
                    If None, defaults to trace_file with .folded extension

    Returns:
        Path to the output file

    Example:
        >>> convert_chrome_trace_to_folded('trace.json', 'trace.folded')
        'trace.folded'
    """
    converter = ChromeTraceConverter(trace_file)
    return converter.convert(output_file)


def tracec_help(parser):
    """Display help information with rich formatting."""
    parser.print_help()


def main():
    """Main entry point for command-line usage."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="tracec",
        description=(
            "[bold cyan]TracEC[/bold cyan] - Convert Chrome Trace Event "
            "Format to folded stack format for flame graph generation.\n\n"
            "Report issues: [underline blue]"
            "https://github.com/Chang-LeHung/telex/issues[/underline blue]"
        ),
        formatter_class=RichHelpFormatter,
        add_help=False,
    )

    parser.add_argument(
        "-h", "--help", action="store_true", help="Show this help message and exit."
    )

    parser.add_argument(
        "trace_file",
        metavar="TRACE_FILE",
        nargs="?",
        help="Path to the Chrome Trace Event Format trace.json file",
    )

    parser.add_argument(
        "-o",
        "--output",
        metavar="OUTPUT_FILE",
        dest="output_file",
        help=(
            "Path to save the folded output file "
            "(default: trace_file with .folded extension)"
        ),
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output showing conversion statistics",
    )

    parser.add_argument(
        "-s",
        "--svg",
        metavar="SVG_FILE",
        dest="svg_file",
        help="Generate SVG flame graph and save to specified file",
    )

    parser.add_argument(
        "--title",
        metavar="TITLE",
        default="TeleX Torch Trace Flame Graph",
        help=('Title for the flame graph (default: "TeleX Torch Trace Flame Graph")'),
    )

    parser.add_argument(
        "--width",
        metavar="WIDTH",
        type=int,
        default=1200,
        help="Width of the flame graph in pixels (default: 1200)",
    )

    parser.add_argument(
        "--height",
        metavar="HEIGHT",
        type=int,
        default=15,
        help="Height of each frame in pixels (default: 15)",
    )

    parser.add_argument(
        "--minwidth",
        metavar="MINWIDTH",
        type=float,
        default=0.1,
        help="Minimum width percentage for a frame to be shown (default: 0.1)",
    )

    parser.add_argument(
        "--countname",
        metavar="COUNTNAME",
        default="samples",
        help='Label for the count/samples (default: "samples")',
    )

    parser.add_argument(
        "--command",
        metavar="COMMAND",
        default="",
        help='Command that generated the profile data (default: "")',
    )

    parser.add_argument(
        "--package-path",
        metavar="PATH",
        dest="package_path",
        default="",
        help='Path to the package being analyzed (default: "")',
    )

    parser.add_argument(
        "--work-dir",
        metavar="DIR",
        dest="work_dir",
        default="",
        help='Working directory for the analysis (default: "")',
    )

    parser.add_argument(
        "--inverted",
        action="store_true",
        help="Render inverted flame graph with root frame at the top",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0",
    )

    args = parser.parse_args()

    # Handle help
    if args.help:
        tracec_help(parser)
        sys.exit(0)

    # Validate required argument
    if not args.trace_file:
        err_console.print("[bold red]Error:[/bold red] TRACE_FILE is required")
        console.print("\nUse [bold cyan]tracec --help[/bold cyan] for more information.")
        sys.exit(1)

    # Perform conversion
    try:
        converter = ChromeTraceConverter(args.trace_file)

        if args.verbose:
            console.print(
                f"[cyan]Loading trace events from:[/cyan] "
                f"[yellow]{args.trace_file}[/yellow]"
            )

        converter.load_trace()

        if args.verbose:
            console.print(
                f"[green]✓[/green] Loaded [bold cyan]{len(converter.events)}"
                f"[/bold cyan] trace events"
            )

        stacks = converter.convert_to_folded()

        if args.verbose:
            console.print(
                f"[green]✓[/green] Generated [bold cyan]{len(stacks)}"
                f"[/bold cyan] unique stack traces"
            )
            console.print(
                f"[green]✓[/green] Total samples: "
                f"[bold magenta]{sum(stacks.values()):,}[/bold magenta]"
            )

        output_file = args.output_file or str(
            Path(args.trace_file).with_suffix(".folded")
        )
        converter.save_folded(output_file)

        console.print(
            f"[green]✓[/green] Converted trace saved to: "
            f"[bold yellow]{output_file}[/bold yellow]"
        )

        if args.verbose:
            # Show some statistics
            max_depth = max(len(stack.split(";")) for stack in stacks.keys())
            console.print(
                f"[green]✓[/green] Maximum stack depth: "
                f"[bold cyan]{max_depth}[/bold cyan]"
            )
            file_size = Path(output_file).stat().st_size
            console.print(
                f"[green]✓[/green] Output file size: "
                f"[bold cyan]{file_size:,}[/bold cyan] bytes"
            )

        # Generate SVG flame graph if requested
        if args.svg_file:
            if args.verbose:
                console.print("\n[cyan]Generating flame graph...[/cyan]")

            try:
                from telex.flamegraph import FlameGraph

                # Read the folded file
                with open(output_file) as f:
                    lines = f.readlines()

                if args.verbose:
                    console.print(
                        f"[green]✓[/green] Read [bold cyan]{len(lines)}"
                        f"[/bold cyan] folded stack lines"
                    )

                # Create flame graph
                fg = FlameGraph(
                    lines,
                    height=args.height,
                    width=args.width,
                    minwidth=args.minwidth,
                    title=args.title,
                    countname=args.countname,
                    command=args.command,
                    package_path=args.package_path,
                    work_dir=args.work_dir,
                    inverted=args.inverted,
                )
                fg.parse_input()

                if args.verbose:
                    console.print(
                        f"[green]✓[/green] Parsed "
                        f"[bold magenta]{fg.total_samples:,}[/bold magenta] samples"
                    )

                # Generate SVG
                svg = fg.generate_svg()

                # Save to file
                with open(args.svg_file, "w") as f:
                    f.write(svg)

                console.print(
                    f"[green]✓[/green] Flame graph saved to: "
                    f"[bold yellow]{args.svg_file}[/bold yellow]"
                )

                if args.verbose:
                    svg_size = Path(args.svg_file).stat().st_size
                    console.print(
                        f"[green]✓[/green] SVG file size: "
                        f"[bold cyan]{svg_size:,}[/bold cyan] bytes"
                    )

            except ImportError as e:  # pragma: no cover
                err_console.print(
                    f"[bold red]Warning:[/bold red] Could not import "
                    f"flamegraph module - {e}"
                )
                err_console.print(
                    "SVG generation skipped. Make sure telex is properly installed."
                )
            except Exception as e:
                err_console.print(
                    f"[bold red]Error generating flame graph:[/bold red] {e}"
                )
                sys.exit(1)

    except FileNotFoundError as e:
        logger.log_error_panel(f"File not found: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.log_error_panel(
            f"Invalid JSON format: {e}\n\n"
            f"Please ensure the file is a valid Chrome Trace Event Format "
            f"JSON file."
        )
        sys.exit(1)
    except Exception as e:
        logger.log_error_panel(
            f"Unexpected error: {e}\n\n"
            f"Please report this issue at: "
            f"https://github.com/Chang-LeHung/telex/issues"
        )
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
