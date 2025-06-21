from rich.console import Console
from rich.panel import Panel

console = Console()


def log_success_panel(content: str) -> None:
    console.print(Panel(content, style="green", title="Info"))


def log_error_panel(content: str) -> None:  # pragma: no cover
    console.print(Panel(content, style="red", title="Error"))


def log_warning_panel(content: str) -> None:
    console.print(Panel(content, style="yellow", title="Warning"))
