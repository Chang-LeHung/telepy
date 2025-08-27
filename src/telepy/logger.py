from rich.console import Console
from rich.panel import Panel

console = Console()
err_console = Console(stderr=True)


def log_success_panel(content: str) -> None:
    console.print(Panel(content, style="green", title="Info"))


def log_error_panel(content: str) -> None:  # pragma: no cover
    err_console.print(Panel(content, style="red", title="Error"))


def log_warning_panel(content: str) -> None:
    console.print(Panel(content, style="yellow", title="Warning"))
