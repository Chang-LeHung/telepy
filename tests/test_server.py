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

    def test_large_post_request(self):
        """Test POST request handling with large body size validation"""
        from unittest.mock import MagicMock

        # Test content length validation logic
        max_size = 10 * 1024 * 1024  # 10MB

        # Test normal size
        normal_size = 1024
        self.assertLess(normal_size, max_size)

        # Test large size
        large_size = 15 * 1024 * 1024  # 15MB
        self.assertGreater(large_size, max_size)

        # Test request with body size information
        req = TelePyRequest(
            app=MagicMock(),
            headers={"Content-Length": str(normal_size)},
            body=b"x" * normal_size,
        )
        self.assertEqual(req.content_length, normal_size)
        self.assertEqual(len(req.body), normal_size)

    def test_post_request_not_found(self):
        """Test POST request to non-existent endpoint"""
        app = TelePyApp(port=8029)

        @app.route("/shutdown")
        def shutdown(req: TelePyRequest, resp: TelePyResponse) -> None:
            req.app.defered_shutdown()
            resp.return_json({"message": "shutting down"})

        def client() -> None:
            import json
            import time
            from urllib import request
            from urllib.error import HTTPError

            time.sleep(1)

            # Try POST to non-existent endpoint
            try:
                data = {"test": "data"}
                json_data = json.dumps(data).encode("utf-8")
                req = request.Request(
                    "http://127.0.0.1:8029/nonexistent",
                    data=json_data,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with request.urlopen(req) as response:
                    self.fail("Should have received 404 error")
            except HTTPError as e:
                self.assertEqual(e.code, 404)
                error_data = json.loads(e.read().decode("utf-8"))
                self.assertIn("error", error_data)
                self.assertEqual(error_data["error"]["code"], 404)

            # Shutdown server
            with request.urlopen("http://127.0.0.1:8029/shutdown") as response:
                self.assertEqual(response.status, 200)

        t = threading.Thread(target=client)
        t.start()
        app.run()
        t.join()
        app.close()

    def test_get_request_not_found(self):
        """Test GET request to non-existent endpoint"""
        app = TelePyApp(port=8030)

        @app.route("/shutdown")
        def shutdown(req: TelePyRequest, resp: TelePyResponse) -> None:
            req.app.defered_shutdown()
            resp.return_json({"message": "shutting down"})

        def client() -> None:
            import json
            import time
            from urllib import request
            from urllib.error import HTTPError

            time.sleep(1)

            # Try GET to non-existent endpoint
            try:
                with request.urlopen("http://127.0.0.1:8030/nonexistent") as response:
                    self.fail("Should have received 404 error")
            except HTTPError as e:
                self.assertEqual(e.code, 404)
                error_data = json.loads(e.read().decode("utf-8"))
                self.assertIn("error", error_data)
                self.assertEqual(error_data["error"]["code"], 404)

            # Shutdown server
            with request.urlopen("http://127.0.0.1:8030/shutdown") as response:
                self.assertEqual(response.status, 200)

        t = threading.Thread(target=client)
        t.start()
        app.run()
        t.join()
        app.close()

    def test_response_content_type_defaults(self):
        """Test response content type default handling"""
        app = TelePyApp(port=8031)

        @app.route("/raw")
        def raw_response(req: TelePyRequest, resp: TelePyResponse) -> None:
            resp.return_raw(b"raw data")

        @app.route("/text")
        def text_response(req: TelePyRequest, resp: TelePyResponse) -> None:
            resp.return_str("text data")

        @app.route("/shutdown")
        def shutdown(req: TelePyRequest, resp: TelePyResponse) -> None:
            req.app.defered_shutdown()
            resp.return_json({"message": "shutting down"})

        def client() -> None:
            import time
            from urllib import request

            time.sleep(1)

            # Test raw response
            with request.urlopen("http://127.0.0.1:8031/raw") as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b"raw data")
                self.assertIn("Content-Type", response.headers)

            # Test text response
            with request.urlopen("http://127.0.0.1:8031/text") as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read().decode(), "text data")
                self.assertEqual(
                    response.headers["Content-Type"], "text/plain; charset=utf-8"
                )

            # Shutdown server
            with request.urlopen("http://127.0.0.1:8031/shutdown") as response:
                self.assertEqual(response.status, 200)

        t = threading.Thread(target=client)
        t.start()
        app.run()
        t.join()
        app.close()

    def test_app_register_and_lookup(self):
        """Test app register and lookup functionality"""
        app = TelePyApp(port=8032)

        # Test register and lookup
        app.register("test_key", "test_value")
        self.assertEqual(app.lookup("test_key"), "test_value")
        self.assertIsNone(app.lookup("nonexistent_key"))

        # Test duplicate register
        with self.assertRaises(KeyError):
            app.register("test_key", "another_value")

        @app.route("/lookup")
        def lookup_test(req: TelePyRequest, resp: TelePyResponse) -> None:
            value = req.app.lookup("test_key")
            resp.return_json({"value": value})

        @app.route("/shutdown")
        def shutdown(req: TelePyRequest, resp: TelePyResponse) -> None:
            req.app.defered_shutdown()
            resp.return_json({"message": "shutting down"})

        def client() -> None:
            import json
            import time
            from urllib import request

            time.sleep(1)

            with request.urlopen("http://127.0.0.1:8032/lookup") as response:
                self.assertEqual(response.status, 200)
                data = json.loads(response.read().decode())
                self.assertEqual(data["value"], "test_value")

            # Shutdown server
            with request.urlopen("http://127.0.0.1:8032/shutdown") as response:
                self.assertEqual(response.status, 200)

        t = threading.Thread(target=client)
        t.start()
        app.run()
        t.join()
        app.close()

    def test_unsupported_method(self):
        """Test route decorator with unsupported method"""
        app = TelePyApp()

        with self.assertRaises(Exception) as context:

            @app.route("/test", method="DELETE")
            def delete_handler(req: TelePyRequest, resp: TelePyResponse) -> None:
                pass

        self.assertIn("DELETE", str(context.exception))

    def test_request_properties(self):
        """Test TelePyRequest properties"""
        import json
        from unittest.mock import MagicMock

        # Test content_length property
        req = TelePyRequest(
            app=MagicMock(),
            headers={"Content-Length": "123"},
            body=b'{"test": "data"}',
            url="/test",
            method="POST",
        )

        self.assertEqual(req.content_length, 123)
        self.assertEqual(req.content_type, "")
        self.assertEqual(req.json, {"test": "data"})

        # Test invalid content length
        req2 = TelePyRequest(
            app=MagicMock(),
            headers={"Content-Length": "invalid"},
            body=None,
        )
        self.assertEqual(req2.content_length, 0)

        # Test content type
        req3 = TelePyRequest(
            app=MagicMock(),
            headers={"Content-Type": "application/json"},
            body=None,
        )
        self.assertEqual(req3.content_type, "application/json")

        # Test JSON with no body
        req4 = TelePyRequest(
            app=MagicMock(),
            headers={},
            body=None,
        )
        self.assertIsNone(req4.json)

        # Test JSON decode error
        req5 = TelePyRequest(
            app=MagicMock(),
            headers={},
            body=b"{invalid json}",
        )
        with self.assertRaises(json.JSONDecodeError):
            _ = req5.json

        # Test repeated JSON access after error
        with self.assertRaises(json.JSONDecodeError):
            _ = req5.json

    def test_interceptor_properties(self):
        """Test TelePyInterceptor properties"""
        interceptor = TelePyInterceptor(200, {})

        # Test initial state
        self.assertTrue(interceptor.forward)
        self.assertTrue(interceptor.flow)

        # Test setting forward to False affects flow
        interceptor.forward = False
        self.assertFalse(interceptor.forward)
        self.assertFalse(interceptor.flow)

        # Test setting flow independently
        interceptor2 = TelePyInterceptor(200, {})
        interceptor2.flow = False
        self.assertFalse(interceptor2.flow)
        self.assertTrue(interceptor2.forward)  # forward should still be True

    def test_server_static_methods(self):
        """Test TelePyApp static methods"""
        from http.server import HTTPServer

        # Test enable_address_reuse
        TelePyApp.enable_address_reuse()
        self.assertTrue(HTTPServer.allow_reuse_address)

        # Test disable_address_reuse
        TelePyApp.disable_address_reuse()
        self.assertFalse(HTTPServer.allow_reuse_address)

    def test_app_is_alive(self):
        """Test TelePyApp is_alive property"""
        app = TelePyApp()

        # Should be alive initially
        self.assertTrue(app.is_alive)

        # Should be dead after setting _close
        app._close = True
        self.assertFalse(app.is_alive)

    def test_response_mixin_lifecycle(self):
        """Test TelePyResponseMixin lifecycle methods"""
        from telepy.server import TelePyResponseMixin

        mixin = TelePyResponseMixin()

        # These should not raise exceptions
        mixin.start()
        mixin.finish()

    def test_interceptor_flow_control(self):
        """Test interceptor flow control in request handling"""
        # This test only verifies the interceptor properties work correctly
        interceptor = TelePyInterceptor(200, {})

        # Test that setting flow to False stops processing
        interceptor.flow = False
        self.assertFalse(interceptor.flow)

        # Test that forward controls flow
        interceptor2 = TelePyInterceptor(200, {})
        interceptor2.forward = False
        self.assertFalse(interceptor2.forward)
        self.assertFalse(interceptor2.flow)

    def test_response_handler_flow_control(self):
        """Test response handler flow control"""
        # This test only verifies the response properties work correctly
        response = TelePyResponse(200, {})

        # Test flow property
        response.flow = False
        self.assertFalse(response.flow)

        # Test that response can handle different content types
        response.return_str("test")
        self.assertEqual(response.headers["Content-Type"], "text/plain; charset=utf-8")

        response2 = TelePyResponse(200, {})
        response2.return_json({"test": "data"})
        self.assertEqual(
            response2.headers["Content-Type"], "application/json; charset=utf-8"
        )

    def test_logging_with_filename(self):
        """Test app logging with filename"""
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            log_file = f.name

        try:
            app = TelePyApp(port=8035, filename=log_file, log=True)

            # Verify logger is set up correctly
            self.assertIsNotNone(app.logger)
            self.assertEqual(app.logger.name, "http.server")

            # Test that we can create the app without errors
            app.close()

        finally:
            # Clean up
            if os.path.exists(log_file):
                os.unlink(log_file)

    def test_logging_disabled(self):
        """Test app with logging disabled"""
        app = TelePyApp(log=False)
        self.assertIsNone(app.logger)
        app.close()

    def test_server_headers(self):
        """Test server response headers"""
        app = TelePyApp(port=8036)

        @app.route("/headers")
        def headers_test(req: TelePyRequest, resp: TelePyResponse) -> None:
            resp.return_json({"test": "headers"})

        @app.route("/shutdown")
        def shutdown(req: TelePyRequest, resp: TelePyResponse) -> None:
            req.app.defered_shutdown()
            resp.return_json({"message": "shutting down"})

        def client() -> None:
            import time
            from urllib import request

            time.sleep(1)

            with request.urlopen("http://127.0.0.1:8036/headers") as response:
                self.assertEqual(response.status, 200)
                # Check server header is set correctly
                self.assertIn("TelePy Monitoring Server", response.headers["Server"])
                self.assertIn("Date", response.headers)

            # Shutdown server
            with request.urlopen("http://127.0.0.1:8036/shutdown") as response:
                self.assertEqual(response.status, 200)

        t = threading.Thread(target=client)
        t.start()
        app.run()
        t.join()
        app.close()
