import argparse
import contextlib
import os
import site
import sys
import threading
import types
from multiprocessing import util
from typing import Any

from . import logging
from .flamegraph import FlameGraph, process_stack_trace
from .sampler import TelepySysAsyncWorkerSampler

_lock = threading.RLock()

# read only for other modules
sampler: None | TelepySysAsyncWorkerSampler = None
# read only for other modules
args: None | argparse.Namespace = None

main_mod = types.ModuleType("__main__")


def patch_os_fork():
    global sampler, args
    assert sampler is not None
    assert args is not None
    args.fork = True
    sampler.clear()


def patch_mp(sampler: TelepySysAsyncWorkerSampler):
    global args
    assert sampler is not None
    assert args is not None
    sampler.clear()
    sampler.start()
    args.mp = True


class Environment:
    initialized = False

    sampler_created = False

    @classmethod
    def init_telepy_environment(cls, args_: argparse.Namespace) -> dict[str, Any]:
        """
        Prepare the environment for a new process. If the process is a child process,
        `prepare_process_environment` will return directly (we have initialized the
        environment in the parent process).

        Args:
            args_ (argparse.Namespace): The arguments for the process.
        """
        global sampler, args, _lock, main_mod, filename
        args = args_
        with _lock:
            if Environment.initialized:
                return main_mod.__dict__

            sampler = TelepySysAsyncWorkerSampler(
                args.interval,
                debug=args.debug,
                ignore_frozen=args.ignore_frozen,
                ignore_self=not args.include_telepy,
            )
            sampler.adjust()
            Environment.sampler_created = True
            cls.initialized = True
            setattr(main_mod, "__file__", os.path.abspath(args.input[0].name))
            setattr(main_mod, "__builtins__", globals()["__builtins__"])
            sys.modules["__telepy_main__"] = sys.modules["__main__"]
            sys.modules["__main__"] = sys.modules["__mp_main__"] = main_mod
            old_arg = sys.argv
            setattr(sys, "telepy_argv", old_arg)
            if "--" in old_arg:
                idx = old_arg.index("--")
                sys.argv = old_arg[idx + 1 :]
            else:
                sys.argv = [args.input[0].name]

            os.register_at_fork(after_in_child=patch_os_fork)
            util.register_after_fork(sampler, patch_mp)
            sys.path.append(os.getcwd())
            return main_mod.__dict__

    @classmethod
    def destory_telepy_enviroment(cls):
        sys.modules["__main__"] = sys.modules["__telepy_main__"]
        del sys.modules["__telepy_main__"]
        sys.argv = getattr(sys, "telepy_argv")
        delattr(sys, "telepy_argv")
        sys.path.remove(os.getcwd())
        Environment.initialized = False


@contextlib.contextmanager
def telepy_env(args: argparse.Namespace):
    global sampler
    global_dict = Environment.init_telepy_environment(args)
    try:
        yield global_dict, sampler
    finally:
        Environment.destory_telepy_enviroment()


def telepy_finalize() -> None:
    """Stop and clean up the global sampler resource.

    This function should be called to properly finalize the telepy environment
    by stopping the global sampler instance and save profiling data.
    """
    global sampler
    if not Environment.sampler_created:
        raise RuntimeError("telepy environment is not initialized")
    assert sampler is not None
    assert args is not None
    sampler.stop()
    lines = sampler.dumps().splitlines()[:-1]

    site_path = site.getsitepackages()[0]
    work_dir = os.getcwd()
    if not args.full_path:
        lines = process_stack_trace(lines, site_path, work_dir)
    fg = FlameGraph(
        lines,
        title="TelePy Flame Graph",
        reverse=args.reverse,
        command=" ".join([sys.executable, *sys.argv]),
        package_path=os.path.dirname(site_path),
        work_dir=work_dir,
    )
    fg.parse_input()
    if args.folded_save:
        with open(args.folded_file, "w+") as fp:
            for idx, line in enumerate(lines):
                if idx == len(lines) - 1:
                    print(line, file=fp, end="")
                else:
                    print(line, file=fp)
        logging.log_success_panel(
            f"Saved folded stack trace to {args.folded_file}, "
            f"please check it out via `open {args.folded_file}`"
        )

    svg_content = fg.generate_svg()

    with open(args.output, "w+") as fp:
        fp.write(svg_content)
    logging.log_success_panel(
        f"Saved profiling data to flamegraph svg file {args.output}, "
        f"please check it out via `open {args.output}`"
    )
