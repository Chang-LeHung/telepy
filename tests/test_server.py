import threading
from unittest import TestCase

from telepy.server import TelepyApp, TelePyRequest, TelePyResponse


class TestApp(TestCase):
    def test_app(self):
        app = TelepyApp()

        @app.route("/")
        def hello(req: TelePyRequest, resp: TelePyResponse) -> None:
            resp.return_json({"hello": "world"})

        @app.route("/shutdown")
        def shutdown(req: TelePyRequest, resp: TelePyResponse) -> None:
            req.app.defered_shutdown()
            resp.return_json({"code": 200, "message": "server is shutting down"})

        @app.route("/test")
        def test(req: TelePyRequest, resp: TelePyResponse) -> None:
            resp.return_json({"test": "test"})

        def client() -> None:
            import time
            from urllib import request

            time.sleep(1)

            base = "http://127.0.0.1:8026/"
            test = base + "test"
            with request.urlopen(test) as response:
                self.assertEqual(response.status, 200)
                data = response.read().decode("utf-8")
                self.assertEqual(data, '{"test": "test"}')

            with request.urlopen(base + "shutdown") as response:
                self.assertEqual(response.status, 200)
                data = response.read().decode("utf-8")
                self.assertEqual(
                    data, '{"code": 200, "message": "server is shutting down"}'
                )

        t = threading.Thread(target=client)
        t.daemon = True
        t.start()
        app.run()
