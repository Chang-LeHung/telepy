import os
import site
import sys
import threading
from typing import Any, Final

import telepy

from .flamegraph import FlameGraph
from .sampler import TelepySysAsyncWorkerSampler

TITLE: Final = "TelePy System Monitor Flame Graph"


class TelePySystem:
    def __init__(self) -> None:
        self.profiling = False
        self.profiler: None | TelepySysAsyncWorkerSampler = None

    @staticmethod
    def thread() -> list[dict[str, Any]]:
        stacks = telepy.join_current_stacks(telepy.current_stacks())
        threads = {t.ident: (t.name, t.daemon) for t in threading.enumerate()}
        t_infos = [
            {
                "id": str(t_id),
                "name": threads[t_id][0],
                "daemon": threads[t_id][1],
                "stack": stacks[t_id],
            }
            for t_id in stacks.keys()
        ]
        return t_infos

    def start_profiling(
        self,
        interval: int = 10_000,
        ignore_frozen: bool = False,
        ignore_self: bool = True,
        tree_mode: bool = False,
    ) -> bool:
        """
        Start profiling the system.
        Args:
            interval (int): The interval between samples in microseconds.
            ignore_frozen (bool): Whether to ignore frozen objects.
            ignore_self (bool): Whether to ignore the telepy.
            tree_mode (bool): Whether to use tree mode.
        """
        if self.profiling:  # pragma: no cover
            return False
        self.profiling = True
        self.profiler = TelepySysAsyncWorkerSampler(
            sampling_interval=interval,
            debug=False,
            ignore_frozen=ignore_frozen,
            ignore_self=ignore_self,
            tree_mode=tree_mode,
            is_root=True,
        )
        self.profiler.adjust()
        self.profiler.start()
        return True

    def finish_profiling(
        self,
        filename: str | None = None,
        save_folded: bool = False,
        folded_filename: str | None = None,
        *,
        inverted: bool = False,
    ) -> tuple[str, str]:
        """
        Finish profiling and save the flame graph to a file.
        If filename is None, the file name will be generated automatically.
        Returns:
            The absolute path of the generated file.
        Raises:
            RuntimeError: If profiler is not started or profiler is None.
        """
        if not self.profiling or self.profiler is None:
            raise RuntimeError("profiler not started or profiler is None")
        self.profiler.stop()
        if filename is None:
            filename = f"telepy-monitor-{os.getpid()}.svg"
        abs_path, folded_filename = self.save(
            filename,
            save_folded=save_folded,
            folded_filename=folded_filename,
            inverted=inverted,
        )
        self.profiler = None
        self.profiling = False
        return (abs_path, folded_filename)

    def save(
        self,
        filename: str,
        title: str = TITLE,
        save_folded: bool = False,
        folded_filename: str | None = None,
        *,
        inverted: bool = False,
    ) -> tuple[str, str]:
        """
        Save the flame graph to a file.
        Args:
            filename (str): The file name to save the flame graph.
        Returns:
            The absolute path of the generated file.
        Raises:
            RuntimeError: If profiling is not started or profiler is None.
        """
        if not self.profiling or self.profiler is None:  # pragma: no cover
            raise RuntimeError("Profiling not started or profiler is None")

        lines = self.profiler.dumps().splitlines()

        site_path = site.getsitepackages()[0]
        fg = FlameGraph(
            lines,
            title=title,
            command=" ".join([sys.executable, *sys.argv]),
            package_path=os.path.dirname(site_path),
            work_dir=os.getcwd(),
            inverted=inverted,
        )
        fg.parse_input()
        svg = fg.generate_svg()
        with open(filename, "w") as f:
            f.write(svg)
        folded_filename = folded_filename or f"{filename}.folded"
        if save_folded:
            with open(folded_filename, "w") as f:
                f.write("\n".join(lines))
        return os.path.abspath(filename), os.path.abspath(folded_filename)
