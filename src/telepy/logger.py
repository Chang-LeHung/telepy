from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

# On Windows, disable legacy Windows rendering to avoid Unicode encoding issues
# legacy_windows=False uses modern ANSI escape sequences which handle UTF-8 better
console = Console(legacy_windows=False)
err_console = Console(stderr=True, legacy_windows=False)


def log_success_panel(content: str) -> None:
    console.print(Panel(content, style="green", title="Info"))


def log_error_panel(content: str) -> None:  # pragma: no cover
    err_console.print(Panel(content, style="red", title="Error"))


def log_warning_panel(content: str) -> None:
    console.print(Panel(content, style="yellow", title="Warning"))
