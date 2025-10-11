import json
from typing import Any, Final
from urllib import request
from urllib.error import HTTPError, URLError

ERROR_CODE: Final = -1

SUCCESS_CODE: Final = 0

# Global registry for commands
COMMAND_REGISTRY: dict[str, type["CommandProcessor"]] = {}


def register_command(name: str, help_text: str):
    """
    Decorator to register a command with the global command registry.

    Args:
        name: The command name
        help_text: Help text for this command
    """

    def decorator(cls: type["CommandProcessor"]) -> type["CommandProcessor"]:
        cls._command_name = name  # type: ignore
        cls._help_text = help_text  # type: ignore
        COMMAND_REGISTRY[name] = cls
        return cls

    return decorator


class CommandProcessor:
    _command_name: str = ""
    _help_text: str = ""

    def __init__(self, host: str = "127.0.0.1", port: int = 8026, timeout=5) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    @classmethod
    def get_help(cls) -> str:
        """Return help text for this command."""
        return getattr(cls, "_help_text", "No help available")

    def process(self, *args: str) -> tuple[Any, bool]:  # type: ignore
        """
        Processes a command by making an HTTP request to the specified host and port.

        Args:
            *args: Command arguments, where the first argument is used as the endpoint path.

        Returns:
            tuple[str, bool]: A tuple containing:
                - str: Response data if successful, or error message if failed.
                - bool: True if request succeeded, False otherwise.

        Raises:
            AssertionError: If no arguments are provided.
        """  # noqa: E501
        assert len(args) > 0
        try:
            url = f"http://{self.host}:{self.port}/{args[0]}"
            headers = {
                "args": " ".join(args[1:]),
            }
            req = request.Request(url, headers=headers)
            resp = request.urlopen(req, timeout=self.timeout)
            data = json.loads(resp.read().decode("utf-8"))
            assert data["code"] in [ERROR_CODE, SUCCESS_CODE]
            return data["data"], data["code"] == SUCCESS_CODE
        except URLError as e:  # pragma: no cover
            return f"Url Error: {e.reason}", False
        except HTTPError as e:  # pragma: no cover
            return f"Http Error: {e.code}", False
        except Exception as e:  # pragma: no cover
            return f"Error: {e}", False


@register_command("shutdown", "shutdown the server")
class Shutdown(CommandProcessor):
    pass


@register_command("stack", "print stack trace of all threads")
class Stack(CommandProcessor):
    """
    Display stack traces for all threads.

    The server formats the stack traces, so the client simply
    displays the formatted output.
    """

    pass


@register_command("ping", "ping the server")
class Ping(CommandProcessor):
    pass


@register_command("profile", "profile the process")
class Profile(CommandProcessor):
    def process(self, *args):  # pragma: no cover
        assert args[0] == "profile"
        return super().process(*args)


@register_command("help", "show available commands")
class Help(CommandProcessor):
    def process(self, *args):  # pragma: no cover
        assert len(args) == 1 and args[0] == "help"
        return CommandManager.help_msg(), True


@register_command("gc-status", "show GC status and configuration")
class GCStatus(CommandProcessor):
    pass


@register_command("gc-stats", "show detailed GC statistics")
class GCStats(CommandProcessor):
    pass


@register_command("gc-objects", "show tracked objects by type")
class GCObjects(CommandProcessor):
    pass


@register_command("gc-garbage", "show uncollectable garbage objects")
class GCGarbage(CommandProcessor):
    pass


@register_command("gc-collect", "manually trigger garbage collection")
class GCCollect(CommandProcessor):
    pass


@register_command("gc-monitor", "monitor GC collection activity")
class GCMonitor(CommandProcessor):
    pass


class CommandManager(CommandProcessor):
    def __init__(self, host: str = "127.0.0.1", port: int = 8026) -> None:
        super().__init__(host, port)
        # Initialize commands from global registry
        self.commands: dict[str, CommandProcessor] = {}
        for name, cmd_class in COMMAND_REGISTRY.items():
            self.commands[name] = cmd_class(host, port)

    def process(self, *args: str) -> tuple[str, bool]:  # type: ignore
        assert len(args) > 0
        cmd = args[0]
        if cmd in self.commands:
            return self.commands[cmd].process(*args)
        else:
            return f'Unknown command "{args[0]}"', False

    @staticmethod
    def help_msg() -> str:
        """Generate help message from registered commands."""
        lines = ["", "Available commands:"]
        for name, cmd_class in COMMAND_REGISTRY.items():
            help_text = cmd_class.get_help()
            lines.append(f"  • {name:<12} - {help_text}")
        lines.append("")
        return "\n".join(lines)
