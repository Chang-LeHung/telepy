"""
Jupyter/IPython integration for TelePy.

Usage:
  1) In a notebook, load the extension once:
       %load_ext telepy.jupyter

  2) Profile a cell with options and render SVG inline:
       %%telepy --interval 8000 --ignore-frozen --focus-mode \
                --title "My Cell Profile" --width 1200 --height 15
       # your python code here

  3) Optionally store SVG text into a variable (without printing text):
       %%telepy --var svg_text
       # your code
     Then access the SVG content via that variable in the notebook without printing raw text.

Supported options (subset of TelePy CLI):
  --interval INT         Sampling interval in microseconds (default: 8000)
  --debug                Enable debug mode
  --ignore-frozen        Ignore frozen modules
  --include-telepy       Include TelePy frames in results
  --tree-mode            Use call site line numbers
  --focus-mode           Focus on user code only
  --regex-patterns P     Regex pattern to filter stacks (repeatable)
  --full-path            Do not trim site-packages/workdir prefixes

FlameGraph layout options:
  --title TEXT           SVG title (default: "TelePy Flame Graph")
  --width INT            SVG width (default: 1200)
  --height INT           Frame height (default: 15)
  --minwidth FLOAT       Minimum frame width in px percent (default: 0.1)
  --countname TEXT       Count label (default: "samples")

Notes:
  - The sampler runs with SIGPROF and must start from the main thread (Jupyter
    kernels typically execute code on the main thread).
  - If the cell raises, the sampler is stopped and the exception propagates.
"""  # noqa: E501

from __future__ import annotations

import argparse
import os
import site
from typing import Any

from IPython.core.magic import Magics, cell_magic, magics_class
from IPython.display import HTML, display

from .flamegraph import FlameGraph, process_stack_trace
from .sampler import TelepySysAsyncWorkerSampler


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    # Sampler options
    parser.add_argument("--interval", type=int, default=8000)
    parser.add_argument("--debug", action="store_true", default=False)
    parser.add_argument("--ignore-frozen", action="store_true", default=False)
    parser.add_argument("--include-telepy", action="store_true", default=False)
    parser.add_argument("--tree-mode", action="store_true", default=False)
    parser.add_argument("--focus-mode", action="store_true", default=False)
    parser.add_argument(
        "--regex-patterns", action="append", default=None, help="Repeatable regex pattern"
    )
    parser.add_argument(
        "--full-path",
        action="store_true",
        default=False,
        help="Do not trim site-packages/workdir prefixes",
    )

    # FlameGraph layout options
    parser.add_argument("--title", type=str, default="TelePy Flame Graph")
    parser.add_argument("--width", type=int, default=1200)
    parser.add_argument("--height", type=int, default=15)
    parser.add_argument("--minwidth", type=float, default=0.1)
    parser.add_argument("--countname", type=str, default="samples")
    parser.add_argument(
        "--var",
        type=str,
        default=None,
        help="Store generated SVG text into a variable in user namespace",
    )

    return parser


@magics_class
class TelePyMagics(Magics):
    def __init__(self, shell):  # type: ignore[no-untyped-def]
        super().__init__(shell)
        self._parser = _build_parser()

    @cell_magic
    def telepy(self, line: str, cell: str) -> None:
        """Profile the cell with TelePy and render SVG inline.

        Displays SVG inline only. If --var is given, also stores the SVG string
        into the specified user variable. Does not print or return text.
        """
        try:
            args = (
                self._parser.parse_args(line.split())
                if line
                else self._parser.parse_args([])
            )
        except SystemExit:
            # Show help-like guidance when parsing fails
            raise ValueError(
                "Invalid arguments for %%telepy. Check options or run with no args for defaults."  # noqa: E501
            )

        sampler = TelepySysAsyncWorkerSampler(
            sampling_interval=args.interval,
            debug=args.debug,
            ignore_frozen=args.ignore_frozen,
            ignore_self=not args.include_telepy,
            tree_mode=args.tree_mode,
            focus_mode=args.focus_mode,
            regex_patterns=args.regex_patterns,
            is_root=True,
        )

        # Ensure switch interval is adjusted conservatively
        sampler.adjust()

        started = False
        try:
            sampler.start()
            started = True

            # Execute the cell in the user namespace
            exec(
                compile(cell, "<telepy-cell>", "exec"),
                self.shell.user_ns,  # type: ignore[attr-defined]
                self.shell.user_ns,  # type: ignore[attr-defined]
            )  # type: ignore[attr-defined]
        finally:
            if started and sampler.started:
                sampler.stop()

        # Build flamegraph from raw lines
        content = sampler.dumps()
        lines = [ln for ln in content.splitlines() if ln.strip()]

        # Optionally trim site/workdir prefixes
        if not args.full_path:
            site_paths = site.getsitepackages()
            site_path = site_paths[0] if site_paths else ""
            lines = process_stack_trace(lines, site_path, os.getcwd())

        fg = FlameGraph(
            lines,
            reverse=False,
            height=args.height,
            width=args.width,
            minwidth=args.minwidth,
            title=args.title,
            countname=args.countname,
            command="IPython %%telepy cell",
            package_path=(
                site.getsitepackages() and os.path.dirname(site.getsitepackages()[0])
            )
            or "",
            work_dir=os.getcwd(),
        )
        fg.parse_input()
        svg = fg.generate_svg()

        # Render inline only (no text output)
        try:
            display(HTML(svg))
        except Exception:
            # Fallback to raw HTML if SVG wrapper fails
            display(HTML(svg))
        if getattr(args, "var", None):
            # Save SVG string to a notebook variable, without printing
            self.shell.user_ns[args.var] = svg  # type: ignore[attr-defined]
        return None


def load_ipython_extension(ipython: Any) -> None:
    """IPython entrypoint: %load_ext telepy.jupyter"""
    ipython.register_magics(TelePyMagics)


def unload_ipython_extension(ipython: Any) -> None:  # pragma: no cover
    # Nothing persistent to clean up
    pass
