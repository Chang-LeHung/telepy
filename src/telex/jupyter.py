"""
Jupyter/IPython integration for TeleX using the same sampling pipeline as the CLI.

Usage:
    1) In a notebook, load the extension once:
             %load_ext telex.jupyter

    2) Profile a cell with CLI-like options and render SVG inline:
             %%telex --interval 8000 --ignore-frozen --focus-mode --width 1200
             # your python code here

    3) Optionally store SVG text into a variable (without printing text):
             %%telex --var svg_text
             # your code
         Then access the SVG content via that variable in the notebook.

Supported options (mirroring ``telex`` CLI flags that affect sampling):
    --interval INT         Sampling interval in microseconds (default: 8000)
    --timeout FLOAT        Wait time for child processes (default: 10)
    --verbose/--no-verbose Enable/suppress verbose panels
    --ignore-frozen        Ignore frozen modules
    --include-telex       Include TeleX frames in results
    --focus-mode           Focus on user code only
    --time {cpu,wall}      Select sampling timer: cpu (SIGPROF) or wall (SIGALRM)
    --regex-patterns P     Regex pattern to filter stacks (repeatable)
    --tree-mode            Use call site line numbers
    --inverted             Render inverted flame graphs
    --width INT            SVG width (default: 1200)

Jupyter-specific options:
    --var NAME             Store the generated SVG string into ``NAME``.

Notes:
    - The sampler runs with SIGPROF and must start from the main thread (Jupyter
        kernels typically execute code on the main thread).
    - If the cell raises, the sampler is finalised and the exception propagates.
    - Generated SVG and folded data are stored in temporary files, read back into
        the notebook, and then removed.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shlex
from pathlib import Path

from IPython.core.interactiveshell import InteractiveShell
from IPython.core.magic import Magics, cell_magic, magics_class
from IPython.display import SVG, display

from .config import TeleXSamplerConfig
from .environment import CodeMode, clear_resources, telex_env, telex_finalize

_RESERVED_GLOBAL_KEYS = {
    "__name__",
    "__file__",
    "__builtins__",
    "__package__",
    "__loader__",
    "__spec__",
    "__annotations__",
}

# Python 3.8 compatibility: BooleanOptionalAction was added in Python 3.9
_BOOLEAN_OPTIONAL_ACTION = getattr(argparse, "BooleanOptionalAction", None)


def _positive_int(value: str) -> int:
    ivalue = int(value)
    if ivalue <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return ivalue


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    # Sampler and environment options (aligned with CLI behaviour)
    parser.add_argument("-i", "--interval", type=_positive_int, default=8000)
    parser.add_argument("--timeout", type=float, default=10)
    # Python 3.8 compatibility: handle BooleanOptionalAction manually
    if _BOOLEAN_OPTIONAL_ACTION is not None:
        parser.add_argument("--verbose", action=_BOOLEAN_OPTIONAL_ACTION, default=None)
    else:
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--verbose", action="store_true", dest="verbose")
        group.add_argument("--no-verbose", action="store_false", dest="verbose")
        parser.set_defaults(verbose=None)
    parser.add_argument("--ignore-frozen", action="store_true", default=False)
    parser.add_argument("--include-telex", action="store_true", default=False)
    parser.add_argument("--focus-mode", action="store_true", default=False)
    parser.add_argument("--tree-mode", action="store_true", default=False)
    parser.add_argument("--inverted", action="store_true", default=False)
    parser.add_argument(
        "--time",
        choices=("cpu", "wall"),
        default="cpu",
        help="Select sampling timer: cpu (SIGPROF) or wall (SIGALRM).",
    )
    parser.add_argument(
        "--regex-patterns",
        action="append",
        default=None,
        help="Repeatable regex pattern (matches CLI --regex-patterns)",
    )
    parser.add_argument("--width", type=_positive_int, default=1200)
    # Jupyter-specific convenience
    parser.add_argument(
        "--var",
        type=str,
        default=None,
        help="Store generated SVG text into a variable in user namespace",
    )

    return parser


@magics_class
class TeleXMagics(Magics):
    def __init__(self, shell: InteractiveShell) -> None:
        super().__init__(shell)
        self._parser = _build_parser()

    @cell_magic
    def telex(self, line: str, cell: str) -> None:
        """Profile the cell with TeleX and render SVG inline.

        Displays SVG inline only. If --var is given, also stores the SVG string
        into the specified user variable. Does not print or return text.
        """
        root = os.getpid()
        try:
            args = (
                self._parser.parse_args(shlex.split(line))
                if line
                else self._parser.parse_args([])
            )
        except (SystemExit, ValueError) as e:
            # Show help-like guidance when parsing fails
            if isinstance(e, ValueError):
                # shlex parsing error (e.g., unmatched quotes)
                raise ValueError(f"Invalid quote syntax in arguments: {e}")
            raise ValueError(
                "Invalid arguments for %%telex. Check options or run with "
                "no args for defaults."
            )

        defaults = TeleXSamplerConfig()
        if getattr(args, "verbose", None) is None:
            args.verbose = defaults.verbose
        if getattr(args, "merge", None) is None:
            args.merge = defaults.merge

        config = TeleXSamplerConfig.from_namespace(args)
        config.verbose = getattr(args, "verbose", True)

        config.folded_save = False
        config.input = None
        config.cmd = None
        config.module = None
        config.verbose = False

        finalize_exc: Exception | None = None
        finalize_needed = False
        try:
            with telex_env(config, CodeMode.PyString) as (global_dict, sampler):
                finalize_needed = True
                assert sampler is not None
                assert global_dict is not None

                # Make existing notebook variables available during execution
                user_ns = self.shell.user_ns  # type: ignore[attr-defined]
                preserved = {key: global_dict.get(key) for key in _RESERVED_GLOBAL_KEYS}
                global_dict.update(user_ns)
                global_dict.update(
                    {key: value for key, value in preserved.items() if value is not None}
                )

                pyc = compile(cell, "<telepy-cell>", "exec")
                if not config.fork_server:
                    sampler.start()
                exec(pyc, global_dict, global_dict)

                # Propagate definitions back to the notebook namespace
                for name, value in global_dict.items():
                    if name in _RESERVED_GLOBAL_KEYS:
                        continue
                    user_ns[name] = value
        finally:
            try:
                if finalize_needed:
                    telex_finalize()
            except Exception as exc:  # pragma: no cover - defensive safeguard
                finalize_exc = exc
            finally:
                clear_resources()

        if finalize_exc:
            raise finalize_exc

        if os.getpid() == root:
            svg_path = Path("result.svg")
            svg_text = svg_path.read_text(encoding="utf-8")
            for path in (svg_path,):
                with contextlib.suppress(FileNotFoundError):
                    if path.exists():
                        path.unlink()
            display(SVG(svg_text))
            if getattr(args, "var", None):
                # Save SVG string to a notebook variable, without printing
                self.shell.user_ns[args.var] = svg_text  # type: ignore[attr-defined]


def load_ipython_extension(ipython: InteractiveShell) -> None:
    """IPython entrypoint: %load_ext telex.jupyter"""
    ipython.register_magics(TeleXMagics)


def unload_ipython_extension(ipython: InteractiveShell) -> None:  # pragma: no cover
    # Nothing persistent to clean up
    pass
