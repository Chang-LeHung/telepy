import threading
from unittest import TestCase

from telepy.server import TelePyApp, TelePyInterceptor, TelePyRequest, TelePyResponse


class TestApp(TestCase):
    def test_app(self):
        app = TelePyApp()

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
        app.close()

    def test_before_request(self):
        app = TelePyApp(port=8027)

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

        @app.register_interceptor
        def intercept(req: TelePyRequest, interceptor: TelePyInterceptor) -> None:
            interceptor.headers["Pass"] = "Interceptor"
            interceptor.flow = False

        @app.register_response_handler
        def tail_handler(req: TelePyRequest, resp: TelePyResponse) -> None:
            print("Tail Handler")
            resp.headers["Tail"] = "Handler"

        def client() -> None:
            import time
            from urllib import request

            time.sleep(1)

            base = "http://127.0.0.1:8027/"
            test = base + "test"
            with request.urlopen(test) as response:
                self.assertEqual(response.status, 200)
                data = response.read().decode("utf-8")
                self.assertEqual(data, '{"test": "test"}')
                print(response.headers)
                self.assertEqual(response.headers["Pass"], "Interceptor")
                self.assertEqual(response.headers["Tail"], "Handler")

            with request.urlopen(base + "shutdown") as response:
                self.assertEqual(response.status, 200)
                data = response.read().decode("utf-8")
                self.assertEqual(
                    data, '{"code": 200, "message": "server is shutting down"}'
                )
                self.assertEqual(response.headers["Pass"], "Interceptor")
                self.assertEqual(response.headers["Tail"], "Handler")

        t = threading.Thread(target=client)
        t.daemon = True
        t.start()
        app.run()
        app.close()
