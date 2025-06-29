import io
import json
import logging
import sys
import threading
from collections import defaultdict
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, override
from urllib.parse import parse_qs, urlparse

from ._telepysys import __version__

logger = logging.getLogger("http.server")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(message)s")
handler.setFormatter(formatter)
logger.handlers = [handler]


class TelePyHandler(BaseHTTPRequestHandler):
    """
    All the following fileds are auto-generated by telepy.
    """

    routers: dict[str, dict[str, Callable[..., Any]]]
    app: "TelepyApp"
    server: HTTPServer

    def __init__(self, request, client_address, server) -> None:
        super().__init__(request, client_address, server)
        self.telepy_headers: dict[str, str] = {}

    def before_request(self):
        """
        This method is called before the request is handled.
        """
        pass

    def after_request(self):
        """
        This method is called after the request is handled.
        """
        pass

    @override
    def handle_one_request(self):
        """Handle a single HTTP request.

        You normally don't need to override this method; see the class
        __doc__ string for information on how to handle specific HTTP
        commands such as GET and POST.

        """
        try:
            self.raw_requestline = self.rfile.readline(65537)
            if len(self.raw_requestline) > 65536:  # pragma: no cover
                self.requestline = ""
                self.request_version = ""
                self.command = ""
                self.send_error(HTTPStatus.REQUEST_URI_TOO_LONG)
                return
            if not self.raw_requestline:  # pragma: no cover
                self.close_connection = True
                return
            if not self.parse_request():  # pragma: no cover
                # An error code has been sent, just exit
                return
            mname = "do_" + self.command
            if not hasattr(self, mname):  # pragma: no cover
                self.send_error(
                    HTTPStatus.NOT_IMPLEMENTED,
                    f"Unsupported method ({self.command!r})",
                )
                return
            method = getattr(self, mname)
            self.before_request()
            method()
            self.after_request()
            self.wfile.flush()  # actually send the response if not already done.
        except TimeoutError as e:  # pragma: no cover
            # a read or a write timed out.  Discard this connection
            self.log_error("Request timed out: %r", e)
            self.close_connection = True
            return

    def do_GET(self):
        parsed_url = urlparse(self.path)
        query = parse_qs(parsed_url.query)

        path = parsed_url.path
        if path in self.routers["GET"]:
            req = TelePyRequest(
                app=self.app,
                headers=self.headers,
                query=query,
                url=parsed_url.path,
                method="GET",
            )
            self._check_request(req)
            resp = TelePyResponse(status_code=HTTPStatus.OK.value, headers={})

            self.routers["GET"][path](req, resp)
            resp.start()
            self.send_response(resp.status_code)
            resp.finish()
            for key, val in resp.headers.items():
                self.send_header(key, val)
            self.end_headers()
            self.wfile.write(resp.buf.getvalue())
            self._check_response(resp)
            return

        self.send_error_response(HTTPStatus.NOT_FOUND.value, HTTPStatus.NOT_FOUND.phrase)

    def do_POST(self):
        parsed_url = urlparse(self.path)
        query = parse_qs(parsed_url.query)

        path = parsed_url.path
        if path in self.routers["POST"]:
            req = TelePyRequest(
                app=self.app,
                headers=self.headers,
                query=query,
                url=parsed_url.path,
                method="POST",
                body=self.rfile.read(int(self.headers["Content-Length"])),
            )
            self._check_request(req)
            resp = TelePyResponse(status_code=HTTPStatus.OK.value, headers={})
            resp.start()
            self.routers["POST"][path](req, resp)
            resp.finish()
            for key, val in resp.headers.items():
                self.send_header(key, val)
            self.end_headers()
            self.wfile.write(resp.buf.getvalue())
            self._check_response(resp)
            return
        self.send_error_response(HTTPStatus.NOT_FOUND.value, HTTPStatus.NOT_FOUND.phrase)

    def _check_response(self, resp: "TelePyResponse"):
        pass

    def _check_request(self, req: "TelePyRequest"):
        pass

    def send_error_response(self, status_code: int, message: str):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        body = {
            "error": {
                "code": status_code,
                "message": message,
            }
        }
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, format, *args):
        logger.info(
            f"{self.client_address[0]} - - [{self.log_date_time_string()}] {format % args}"  # noqa: E501
        )

    @override
    def send_response(self, code, message=None):
        """Add the response header to the headers buffer and log the
        response code.

        Also send two standard headers with the server software
        version and the current date.

        """
        self.log_request(code)
        self.send_response_only(code, message)
        self.send_header("Server", f"TelePy Monitoring Server/{__version__}")
        self.send_header("Date", self.date_time_string())


class TelePyException(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class TelePyRequest:
    def __init__(
        self,
        app: "TelepyApp",
        headers: dict[str, str],
        body: bytes | None = None,
        url: str = "/",
        query: dict[str, list[str]] | None = None,
        method: str = "GET",
    ):
        self.app = app
        self.headers = headers
        self.body = body
        self.url = url
        if query is None:
            query = {}
        self.query = query
        self.method = method


class TelePyResponseMixin:
    """
    Add lifecycle methods to TelePyResponse.
    """

    def start(self) -> None:
        """Call it before call the user's router."""
        pass

    def finish(self) -> None:
        """Call it after call the user's router."""
        pass


class TelePyResponse(TelePyResponseMixin):
    def __init__(self, status_code: int, headers: dict[str, str]) -> None:
        self.status_code = status_code
        self.headers = headers
        self.buf = io.BytesIO()
        self.close: bool = False

    def return_raw(self, data: bytes) -> None:
        self.buf.write(data)

    def return_str(self, data: str) -> None:
        self.headers["Content-Type"] = "text/plain; charset=utf-8"
        self.return_raw(data.encode())

    def return_json(self, data: Any) -> None:
        self.headers["Content-Type"] = "application/json; charset=utf-8"
        self.return_raw(json.dumps(data).encode())

    def finish(self):
        super().finish()
        if "Content-Length" not in self.headers:
            self.headers["Content-Length"] = str(len(self.buf.getvalue()))
        if "Content-Type" not in self.headers:
            self.headers["Content-Type"] = "text/plain; charset=utf-8"


class TelepyApp:
    supported_methods = ("GET",)

    def __init__(
        self,
        port: int = 8026,
        host: str = "127.0.0.1",
    ) -> None:
        self.port = port
        self.host = host

        self.routers: dict[str, dict[str, Callable[..., Any]]] = defaultdict(dict)

    def route(
        self, path: str, method: str = "GET"
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        if method not in self.supported_methods:
            raise TelePyException(f"Method {method} is not supported")

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.routers[method.upper()][path] = func
            return func

        return decorator

    def run(self) -> None:
        clazz = type(
            "TelePyAppHandler", (TelePyHandler,), {"app": self, "routers": self.routers}
        )
        self.server = HTTPServer((self.host, self.port), clazz)

        self.server.serve_forever()

    def defered_shutdown(self):
        """Gracefully shuts down the server asynchronously."""

        t = threading.Thread(target=self.server.shutdown)
        t.daemon = True
        t.start()
