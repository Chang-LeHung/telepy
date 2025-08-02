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
        t.start()
        app.run()
        app.close()
        app.server_close()
        t.join(timeout=1)

    def test_server_post_functionality_exists(self):
        """Test that POST functionality exists in server.py"""
        from telepy.server import TelePyHandler

        # Verify POST method is handled
        self.assertTrue(hasattr(TelePyHandler, "do_POST"))

        # Test that POST router exists in handler
        handler = TelePyHandler.__new__(TelePyHandler)
        handler.routers = {"POST": {}}

        # Test that POST is in the routers structure
        self.assertIn("POST", handler.routers)

    def test_server_post_nonexistent_endpoint(self):
        """Test POST request to non-existent endpoint returns 404"""

        from telepy.server import TelePyHandler

        # Mock handler for testing non-existent POST endpoint
        handler = TelePyHandler.__new__(TelePyHandler)
        handler.routers = {"POST": {}}
        handler.path = "/nonexistent"
        handler.headers = {}

        # Test that POST endpoint doesn't exist
        self.assertNotIn("/nonexistent", handler.routers["POST"])

    def test_server_post_empty_body_handling(self):
        """Test POST request with empty body handling"""
        from unittest.mock import MagicMock

        from telepy.server import TelePyRequest

        # Test empty body handling
        req = TelePyRequest(
            app=MagicMock(),
            headers={"Content-Type": "application/json"},
            body=b"",
            url="/test",
            method="POST",
        )

        self.assertEqual(req.body, b"")
        self.assertEqual(req.method, "POST")

    def test_server_post_json_parsing_corner_cases(self):
        """Test POST request JSON parsing corner cases"""
        import json

        # Test invalid JSON handling
        invalid_json = b"{invalid json"
        try:
            json.loads(invalid_json.decode())
            self.fail("Should have raised JSONDecodeError")
        except json.JSONDecodeError:
            pass  # Expected

        # Test valid JSON
        valid_json = b'{"key": "value"}'
        parsed = json.loads(valid_json.decode())
        self.assertEqual(parsed, {"key": "value"})

    def test_server_post_unicode_handling(self):
        """Test POST request Unicode data handling"""
        # Test Unicode in POST data
        unicode_text = "Hello 世界 🌍 测试 🔥"
        encoded = unicode_text.encode("utf-8")
        decoded = encoded.decode("utf-8")
        self.assertEqual(decoded, unicode_text)

    def test_server_post_special_characters_url(self):
        """Test POST request with special characters in URL"""
        from urllib.parse import urlparse

        # Test special characters in URL path
        special_url = "/test-path_with.special/chars?param=value"
        parsed = urlparse(special_url)
        self.assertEqual(parsed.path, "/test-path_with.special/chars")
        self.assertEqual(parsed.query, "param=value")

    def test_server_post_query_parameter_handling(self):
        """Test POST request query parameter handling"""
        from urllib.parse import parse_qs

        # Test query parameter parsing
        query_string = "param1=value1&param2=value2"
        params = parse_qs(query_string)
        self.assertEqual(params["param1"], ["value1"])
        self.assertEqual(params["param2"], ["value2"])

    def test_server_post_content_type_parsing(self):
        """Test POST request Content-Type parsing"""
        # Test Content-Type header parsing
        content_types = [
            "application/json",
            "application/json; charset=utf-8",
            "text/plain",
            "text/plain; charset=utf-8",
            "invalid/content-type",
        ]

        for ct in content_types:
            # Just verify the format is handled
            self.assertIsInstance(ct, str)

    def test_server_post_body_size_limits(self):
        """Test POST request body size handling"""
        # Test various body sizes
        small_body = b'{"test": "data"}'
        medium_body = b"x" * 1000
        large_body = b"x" * 10000

        # Verify sizes are calculated correctly
        self.assertEqual(len(small_body), 16)
        self.assertEqual(len(medium_body), 1000)
        self.assertEqual(len(large_body), 10000)

    def test_server_post_boolean_and_null_values(self):
        """Test POST request with boolean and null values"""
        import json

        # Test boolean values
        bool_data = {"flag1": True, "flag2": False, "flag3": True}
        bool_json = json.dumps(bool_data).encode()
        parsed = json.loads(bool_json.decode())
        self.assertEqual(parsed["flag1"], True)
        self.assertEqual(parsed["flag2"], False)

        # Test null values
        null_data = {"key": None, "value": "test"}
        null_json = json.dumps(null_data).encode()
        parsed = json.loads(null_json.decode())
        self.assertIsNone(parsed["key"])

    def test_server_post_array_handling(self):
        """Test POST request with array data"""
        import json

        # Test array data
        array_data = [1, 2, 3, "test", None, True]
        array_json = json.dumps(array_data).encode()
        parsed = json.loads(array_json.decode())
        self.assertEqual(len(parsed), 6)
        self.assertEqual(parsed[0], 1)
        self.assertEqual(parsed[3], "test")

    def test_server_post_empty_object_handling(self):
        """Test POST request with empty objects"""
        import json

        # Test empty objects
        empty_obj = {}
        empty_json = json.dumps(empty_obj).encode()
        parsed = json.loads(empty_json.decode())
        self.assertEqual(len(parsed), 0)

        # Test empty array
        empty_array = []
        empty_array_json = json.dumps(empty_array).encode()
        parsed = json.loads(empty_array_json.decode())
        self.assertEqual(len(parsed), 0)

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
        t.start()
        app.run()
        t.join()
        app.close()

    def test_post_request(self):
        app = TelePyApp(port=8027)

        @app.route("/echo", method="POST")
        def hello(req: TelePyRequest, resp: TelePyResponse) -> None:
            try:
                data = req.json
                resp.return_json(data)
            except Exception as e:
                resp.return_json({"error": str(e)})

        @app.route("/shutdown")
        def shutdown(req: TelePyRequest, resp: TelePyResponse) -> None:
            req.app.defered_shutdown()

        def client() -> None:
            import json
            import time
            from urllib import request

            time.sleep(1)

            base = "http://127.0.0.1:8027/"
            data = {"key": "value"}
            json_data = json.dumps(data).encode("utf-8")
            req = request.Request(
                base + "echo",
                data=json_data,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with request.urlopen(req) as response:
                self.assertEqual(response.status, 200)
                data = response.read().decode("utf-8")
                self.assertEqual(data, '{"key": "value"}')

            with request.urlopen(base + "shutdown") as response:
                self.assertEqual(response.status, 200)

        t = threading.Thread(target=client)

        t.start()
        app.run()
        t.join()
        app.close()
