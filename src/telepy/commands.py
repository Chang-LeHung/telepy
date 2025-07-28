import io
import json
from typing import Any, Final, cast
from urllib import request
from urllib.error import HTTPError, URLError

ERROR_CODE: Final = -1

SUCCESS_CODE: Final = 0


class CommandProcessor:
    def __init__(self, host: str = "127.0.0.1", port: int = 8026, timeout=5) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

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
        except URLError as e:
            return f"Url Error: {e.reason}", False
        except HTTPError as e:
            return f"Http Error: {e.code}", False
        except Exception as e:
            return f"Error: {e}", False


class Shutdown(CommandProcessor):
    pass


class Stack(CommandProcessor):
    def process(self, *args):
        """
        {
            "data": [
                {
                    "stack": "\n".join(["telepy.py", "<module>]),
                    "name": "MainThread",
                    "id": 1234567890,
                    "daemon": true
                }
            ]
        }
        """
        assert len(args) > 0 and args[0] == "stack"
        if len(args) > 1:
            return "Too many arguments", False
        result = super().process(*args)
        msg, ok = cast(tuple[list[dict[str, Any]], bool], result)
        if ok:
            s = io.StringIO()
            for item in msg:
                s.write(
                    f"Thread ({item['id']}, {item['name']}, daemon={item['daemon']})\n"
                )
                s.write(item["stack"])
                s.write("\n")
            return s.getvalue()[:-1], ok

        return msg, ok


class Ping(CommandProcessor):
    pass


class Profile(CommandProcessor):
    def process(self, *args):
        assert args[0] == "profile"
        return super().process(*args)


class CommandManager(CommandProcessor):
    def __init__(self, host: str = "127.0.0.1", port: int = 8026) -> None:
        # attach is a special command that doesn't need to be processed
        self.commands: dict[str, CommandProcessor] = {
            "shutdown": Shutdown(host, port),
            "stack": Stack(host, port),
            "ping": Ping(host, port),
            "profile": Profile(host, port),
        }

    def process(self, *args: str) -> tuple[str, bool]:  # type: ignore
        assert len(args) > 0
        cmd = args[0]
        if cmd in self.commands:
            return self.commands[cmd].process(*args)
        else:
            return f'Unknown command "{args[0]}"', False
