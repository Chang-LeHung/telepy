from __future__ import annotations

import os
import sys
import textwrap
from collections import Counter
from collections.abc import Iterable
from enum import Enum
from typing import Final

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.input import Input
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.output import Output
from pygments.lexers.python import PythonLexer  # type: ignore
from rich import print

from ._telexsys import __version__
from .commands import COMMAND_REGISTRY, CommandManager

MAX_HISTORY_SIZE: Final = 10000

MAX_UNIQUE_COMMANDS: Final = 1000

EXIT_COMMANDS: Final = ["exit", "quit", "q"]

PROMPT: Final = rf"""Welcome to TeleX Shell {__version__}
  ______     __    _  __  _____ __         ____
 /_  __/__  / /__ | |/ / / ___// /_  ___  / / /
  / / / _ \/ / _ \|   /  \__ \/ __ \/ _ \/ / /
 / / /  __/ /  __/   |  ___/ / / / /  __/ / /
/_/  \___/_/\___/_/|_| /____/_/ /_/\___/_/_/
"""


class CaseInsensitiveFrequencyCompleter(Completer):
    def __init__(self, history: str | None = None):
        # Get commands from the global registry and add shell-specific commands
        registry_commands = list(COMMAND_REGISTRY.keys())
        shell_commands = ["exit", "attach"]  # Commands specific to shell
        self.commands = registry_commands + shell_commands
        # ensure ~/.telex exists
        if not os.path.exists(os.path.join(os.path.expanduser("~"), ".telex")):
            os.makedirs(os.path.join(os.path.expanduser("~"), ".telex"))
        self.history = history
        if not self.history:
            self.history = os.path.join(os.path.expanduser("~"), ".telex", "history")
        if not os.path.exists(self.history):
            open(self.history, "w", encoding="utf-8").close()

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        assert self.history is not None
        if complete_event.completion_requested:
            with open(self.history, "r+", encoding="utf-8") as fp:
                lines = [
                    line.strip()
                    for line in fp.readlines()
                    if line.strip() not in self.commands
                ]
            self.most_common = Counter(lines).most_common()
            before_cursor = document.text_before_cursor
            text = document.text
            if text == before_cursor:
                if " " not in text:
                    for word in self.commands:
                        if word.startswith(text):
                            yield Completion(word, -len(text))
                    for w in self.most_common:
                        if w[0].startswith(before_cursor.lower()):
                            yield Completion(w[0], -len(text))

    def add_command(self, cmd: str):
        assert self.history is not None
        with open(self.history, "a+", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines()]
            lines.append(cmd)
            if len(lines) >= MAX_HISTORY_SIZE:
                cnter = Counter(lines)
                lines = [line for line, _ in cnter.most_common(MAX_UNIQUE_COMMANDS)]
                f.seek(0)
                f.truncate()
                f.write("\n".join(lines))
            else:
                f.write(f"{cmd}\n")


class ShellState(Enum):
    """Shell state."""

    ATTACHED = 0
    DETACHED = 1


class TeleXShell:
    def __init__(
        self,
        input: Input | None = None,
        output: Output | None = None,
    ) -> None:
        """Initialize the shell with connection settings and command history.

        Args:
            host (str): IP address to connect to (default: "127.0.0.1").
            port (int): Port number for the connection (default: 8026).
            his_file (str): Path to file storing command history (default: cmd_file).
            input (Input | None): Input source for the prompt session (default: None).
            output (Output | None): Output destination for the prompt session (default: None).

        Initializes:
            - Command history from specified file
            - Prompt session with Python lexer and completer
            - Connection state as DETACHED
            - Command manager with given host/port
        """  # noqa: E501
        self.completer = CaseInsensitiveFrequencyCompleter()
        self.session: PromptSession[str] = PromptSession(
            lexer=PygmentsLexer(PythonLexer),
            completer=self.completer,
            multiline=False,
            input=input,
            output=output,
        )
        self.state = ShellState.DETACHED
        self.host: str | None = None
        self.port: int | None = None
        self.cmd_manager: CommandManager | None

        self.out = sys.stdout
        if output is not None:
            self.out = output

    def dispatch(self, cmd: str) -> tuple[str, bool]:
        """Dispatch the command to the appropriate handler."""
        args = cmd.split()
        if self.state == ShellState.DETACHED:
            if args[0] != "attach" and args[0] != "help":
                return (
                    "Please attach a process first. For example: attach 127.0.0.1:8026",
                    False,
                )
            elif args[0] == "help":
                return textwrap.dedent(CommandManager.help_msg()[1:])[:-1], True
            else:
                try:
                    host, port = args[1].split(":")
                    self.host = host
                    self.port = int(port)
                    self.cmd_manager = CommandManager(self.host, self.port)
                    res, ok = self.cmd_manager.process("ping")
                    if not ok or res != "pong":
                        return (
                            res,
                            False,
                        )
                    self.state = ShellState.ATTACHED
                    return (f"Attached to {self.host}:{self.port}", True)
                except Exception:
                    return (
                        f"Invalid Host/Port format {cmd}. For example: attach 127.0.0.1:8026",  # noqa: E501
                        False,
                    )
        elif self.state == ShellState.ATTACHED:
            assert self.cmd_manager is not None
            return self.cmd_manager.process(*args)

        raise RuntimeError("Invalid state")

    def run(self) -> None:
        """
        Run the shell.
        """
        print(PROMPT)
        while True:
            try:
                ipt = self.session.prompt(">>> ")
                ipt = ipt.strip()
                if len(ipt) == 0:  # pragma: no cover
                    continue
                if ipt in EXIT_COMMANDS:
                    break
                msg, ok = self.dispatch(ipt)
                if ok:
                    print(msg, file=self.out)
                    self.completer.add_command(ipt)
                else:  # pragma: no cover
                    print(f"[red]{msg}[/red]", file=self.out)

            except (KeyboardInterrupt, EOFError):
                break
