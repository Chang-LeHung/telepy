from telepy import TelePyMonitor

from .base import TestBase


class MonitorSession:
    def __init__(self, port: int = 9000):
        self.port = port
        self.monitor: None | TelePyMonitor = None

    def __enter__(self):
        import time

        from telepy import install_monitor

        self.monitor = install_monitor(port=self.port, in_thread=False)
        time.sleep(0.5)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        from urllib import request

        req = request.Request(f"http://127.0.0.1:{self.port}/shutdown")
        with request.urlopen(req) as response:
            assert response.status == 200

        self.monitor.close()

    def run_command(
        self, command: str, args: list[str] = [], expected_data: list[str] = []
    ) -> None:
        import json
        from urllib import request

        url = f"http://127.0.0.1:{self.port}/{command}"
        headers = {
            "args": " ".join(args),
        }

        req = request.Request(url, headers=headers)
        with request.urlopen(req) as response:
            assert response.status == 200
            data = json.loads(response.read().decode())
            out = data["data"]
            for expected in expected_data:
                assert str(out).find(expected) != -1


class TestMonitor(TestBase):
    def setUp(self):
        TelePyMonitor.enable_address_reuse()
        return super().setUp()

    def tearDown(self):
        TelePyMonitor.disable_address_reuse()

        return super().tearDown()

    def client_template_command(
        self, command: str, args: list[str] = [], expected_data: list[str] = [], port=7777
    ) -> None:
        import json
        import threading
        from urllib import request

        from telepy import install_monitor

        def server():
            monitor = install_monitor(port=port, in_thread=True)
            while monitor.is_alive:
                pass
            monitor.close()

        t = threading.Thread(target=server)
        t.start()

        url = f"http://127.0.0.1:{port}/{command}"
        headers = {
            "args": " ".join(args),
        }
        req = request.Request(url, headers=headers)
        with request.urlopen(req) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode())
        out = data["data"]
        for expected in expected_data:
            self.assertRegex(str(out), expected)

        url = f"http://127.0.0.1:{port}/shutdown"
        req = request.Request(url)
        with request.urlopen(req) as response:
            self.assertEqual(response.status, 200)

        t.join()

    def compound_template_command(
        self, command: str, args: list[str] = [], expected_data: list[str] = []
    ) -> None:
        self.client_template_command(command, args, expected_data)
        self.server_template_command(command, args, expected_data)

    def server_template_command(
        self, command: str, args: list[str] = [], expected_data: list[str] = [], port=8899
    ) -> None:
        import json
        import threading
        import time
        from urllib import request

        from telepy import install_monitor

        def client():
            time.sleep(0.5)
            url = f"http://127.0.0.1:{port}/{command}"
            headers = {
                "args": " ".join(args),
            }
            req = request.Request(url, headers=headers)
            with request.urlopen(req) as response:
                self.assertEqual(response.status, 200)
                data = json.loads(response.read().decode())
                out = data["data"]
                for expected in expected_data:
                    self.assertRegex(str(out), expected)

            url = f"http://127.0.0.1:{port}/shutdown"
            req = request.Request(url, headers=headers)
            with request.urlopen(req) as response:
                self.assertEqual(response.status, 200)

        t = threading.Thread(target=client)
        t.start()

        monitor = install_monitor(port=port, in_thread=True)
        while monitor.is_alive:
            pass

        t.join()
        monitor.close()

    def test_ping(self):
        self.compound_template_command("ping", expected_data=["pong"])

    def test_stack(self):
        """Test stack command basic functionality."""
        self.compound_template_command(
            "stack", expected_data=["MainThread", "daemon", "telepy"]
        )

    def test_stack_help(self):
        """Test stack command help output."""
        self.compound_template_command(
            "stack",
            args=["-h"],
            expected_data=[
                "usage",
                "--strip-site-packages",
                "--strip-cwd",
                "--help",
            ],
        )

    def test_stack_strip_site_packages(self):
        """Test stack command with --strip-site-packages flag."""
        self.compound_template_command(
            "stack",
            args=["--strip-site-packages"],
            expected_data=["MainThread", "daemon", "telepy"],
        )

    def test_stack_strip_site_packages_short(self):
        """Test stack command with -s short flag."""
        self.compound_template_command(
            "stack",
            args=["-s"],
            expected_data=["MainThread", "daemon", "telepy"],
        )

    def test_stack_strip_cwd(self):
        """Test stack command with --strip-cwd flag."""
        self.compound_template_command(
            "stack",
            args=["--strip-cwd"],
            expected_data=["MainThread", "daemon", "telepy"],
        )

    def test_stack_strip_cwd_short(self):
        """Test stack command with -c short flag."""
        self.compound_template_command(
            "stack",
            args=["-c"],
            expected_data=["MainThread", "daemon", "telepy"],
        )

    def test_stack_combined_flags(self):
        """Test stack command with combined flags."""
        self.compound_template_command(
            "stack",
            args=["-s", "-c"],
            expected_data=["MainThread", "daemon", "telepy"],
        )

    def launch_server(self, port: int = 6666, in_thread: bool = False) -> None:
        from telepy import install_monitor

        monitor = install_monitor(port=port, in_thread=in_thread)
        while monitor.is_alive:
            pass
        monitor.close()

    def test_profile(self):
        """
        We can not use multiple threads in the same process, because if we test the
        command profile, the register function must be called in the main thread and it
        is blocked at the receive function at the same time.
        """
        import json
        import os
        import time
        from urllib import request

        port = 4678
        pid = os.fork()
        if pid == 0:
            self.launch_server(port, True)
            os._exit(0)

        time.sleep(1)
        args = ["start", "--interval", "500000"]
        headers = {
            "args": " ".join(args),
        }
        req = request.Request(f"http://127.0.0.1:{port}/profile", headers=headers)
        with request.urlopen(req) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode())
            self.assertIn("started", data["data"])

        req = request.Request(
            f"http://127.0.0.1:{port}/profile",
            headers={
                "args": "start -h",
            },
        )
        with request.urlopen(req) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode())
            self.assertIn("usage", data["data"])
            self.assertIn("--interval INTERVAL", data["data"])
            self.assertIn("--ignore-frozen", data["data"])
            self.assertIn("--ignore-self", data["data"])
            self.assertIn("--help, -h", data["data"])

        stop_headers = {
            "args": "stop --save-folded",
        }
        req = request.Request(f"http://127.0.0.1:{port}/profile", headers=stop_headers)
        with request.urlopen(req) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode())
            self.assertIn("stopped", data["data"])
            filename = f"telepy-monitor-{pid}.svg"
            self.assertIn(filename, data["data"])
            self.assertIn(filename + ".folded", data["data"])
            os.unlink(filename)

        req = request.Request(
            f"http://127.0.0.1:{port}/profile", headers={"args": "stop -h"}
        )
        with request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            # Check for options presence (format may vary across argparse versions)
            self.assertIn("--help", data["data"])
            self.assertIn("-h", data["data"])
            self.assertIn("-f", data["data"])
            self.assertIn("--filename", data["data"])
            self.assertIn("--save-folded", data["data"])
            self.assertIn("--folded-filename", data["data"])
            self.assertIn("--inverted", data["data"])

        req = request.Request(f"http://127.0.0.1:{port}/shutdown")
        with request.urlopen(req) as response:
            self.assertEqual(response.status, 200)

    def test_profile_switch_process(self):
        """
        This method is to cover the code ran in the main thread.
        """
        import json
        import os
        import time
        from urllib import request

        port = 4444
        pid = os.fork()
        if pid != 0:
            self.launch_server(port, True)
        else:
            time.sleep(1)
            args = ["start", "--interval", "500000"]
            headers = {
                "args": " ".join(args),
            }
            req = request.Request(f"http://127.0.0.1:{port}/profile", headers=headers)
            with request.urlopen(req) as response:
                self.assertEqual(response.status, 200)
                data = json.loads(response.read().decode())
                self.assertIn("started", data["data"])

            req = request.Request(
                f"http://127.0.0.1:{port}/profile",
                headers={
                    "args": "start -h",
                },
            )
            with request.urlopen(req) as response:
                self.assertEqual(response.status, 200)
                data = json.loads(response.read().decode())
                self.assertIn("usage", data["data"])
                self.assertIn("--interval INTERVAL", data["data"])
                self.assertIn("--ignore-frozen", data["data"])
                self.assertIn("--ignore-self", data["data"])
                self.assertIn("--help, -h", data["data"])

            stop_headers = {
                "args": "stop --save-folded",
            }
            req = request.Request(
                f"http://127.0.0.1:{port}/profile", headers=stop_headers
            )
            with request.urlopen(req) as response:
                self.assertEqual(response.status, 200)
                data = json.loads(response.read().decode())
                self.assertIn("stopped", data["data"])
                filename = f"telepy-monitor-{os.getppid()}.svg"
                self.assertIn(filename, data["data"])
                self.assertIn(filename + ".folded", data["data"])
                os.unlink(filename)

            req = request.Request(
                f"http://127.0.0.1:{port}/profile", headers={"args": "stop -h"}
            )
            with request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                # Check for options presence (format may vary across argparse versions)
                self.assertIn("--help", data["data"])
                self.assertIn("-h", data["data"])
                self.assertIn("-f", data["data"])
                self.assertIn("--filename", data["data"])
                self.assertIn("--save-folded", data["data"])
                self.assertIn("--folded-filename", data["data"])

            req = request.Request(f"http://127.0.0.1:{port}/shutdown")
            with request.urlopen(req) as response:
                self.assertEqual(response.status, 200)
            os._exit(0)

    def test_errors(self):
        self.compound_template_command("profile", expected_data=["No arguments provided"])
        self.compound_template_command(
            "profile", ["start", "-x"], expected_data=["unrecognized arguments: -x"]
        )
        self.compound_template_command(
            "profile", ["stop", "-x"], expected_data=["unrecognized arguments: -x"]
        )
        self.compound_template_command(
            "profile",
            ["stop", "-x", "-y"],
            expected_data=["unrecognized arguments: -x -y"],
        )
        self.compound_template_command(
            "profile", ["x"], expected_data=["Invalid argument, use 'start' or 'stop'"]
        )
        self.compound_template_command(
            "profile",
            ["stop"],
            expected_data=["profiler not started or profiler is None"],
        )

    def test_shutdown(self):
        from urllib import request

        from telepy import install_monitor

        port = 4533
        monitor = install_monitor(port=port)

        req = request.Request(f"http://127.0.0.1:{port}/shutdown")

        with request.urlopen(req) as response:
            self.assertEqual(response.status, 200)

        monitor.close()

    def test_profile_inverted_flamegraph(self):
        """Test that the monitor correctly generates inverted flamegraphs."""
        import json
        import os
        import time
        from urllib import request

        port = 4555
        pid = os.fork()
        if pid == 0:
            self.launch_server(port, True)
            os._exit(0)

        time.sleep(1)
        # Start profiling
        args = ["start", "--interval", "500000"]
        headers = {"args": " ".join(args)}
        req = request.Request(f"http://127.0.0.1:{port}/profile", headers=headers)
        with request.urlopen(req) as response:
            self.assertEqual(response.status, 200)

        # Stop profiling with inverted flag
        stop_headers = {"args": "stop --inverted"}
        req = request.Request(f"http://127.0.0.1:{port}/profile", headers=stop_headers)
        with request.urlopen(req) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode())
            self.assertIn("stopped", data["data"])
            filename = f"telepy-monitor-{pid}.svg"
            self.assertIn(filename, data["data"])

            # Verify the SVG contains inverted orientation metadata
            with open(filename) as f:
                content = f.read()
                self.assertIn('data-orientation="inverted"', content)
            os.unlink(filename)

        # Shutdown server
        req = request.Request(f"http://127.0.0.1:{port}/shutdown")
        with request.urlopen(req) as response:
            self.assertEqual(response.status, 200)

    def test_gc_status(self):
        """Test gc-status command."""
        self.compound_template_command(
            "gc-status", expected_data=["enabled", "count", "threshold"]
        )

    def test_gc_status_help(self):
        """Test gc-status help message."""
        self.compound_template_command(
            "gc-status", ["--help"], expected_data=["usage", "--help"]
        )

    def test_gc_stats(self):
        """Test gc-stats command."""
        self.compound_template_command(
            "gc-stats",
            expected_data=["GC Status", "Collections", "Collected", "Uncollectable"],
        )

    def test_gc_stats_help(self):
        """Test gc-stats help message."""
        self.compound_template_command(
            "gc-stats", ["--help"], expected_data=["usage", "--help"]
        )

    def test_gc_objects(self):
        """Test gc-objects command with default parameters."""
        self.compound_template_command(
            "gc-objects", expected_data=["Object Statistics", "Type", "Count"]
        )

    def test_gc_objects_with_limit(self):
        """Test gc-objects command with custom limit."""
        self.compound_template_command(
            "gc-objects",
            ["--limit", "10"],
            expected_data=["Object Statistics", "Type", "Count"],
        )

    def test_gc_objects_with_generation(self):
        """Test gc-objects command with specific generation."""
        self.compound_template_command(
            "gc-objects",
            ["--generation", "0"],
            expected_data=["Object Statistics", "Type", "Count"],
        )

    def test_gc_objects_with_memory(self):
        """Test gc-objects command with memory calculation."""
        self.compound_template_command(
            "gc-objects",
            ["--calculate-memory"],
            expected_data=["Object Statistics", "Type", "Count", "Memory"],
        )

    def test_gc_objects_sort_by_memory(self):
        """Test gc-objects command sorted by memory."""
        self.compound_template_command(
            "gc-objects",
            ["--calculate-memory", "--sort-by", "memory"],
            expected_data=["Object Statistics", "Type", "Count", "Memory"],
        )

    def test_gc_objects_sort_by_avg_memory(self):
        """Test gc-objects command sorted by average memory."""
        self.compound_template_command(
            "gc-objects",
            ["--calculate-memory", "--sort-by", "avg_memory"],
            expected_data=["Object Statistics", "Type", "Count", "Memory"],
        )

    def test_gc_objects_help(self):
        """Test gc-objects help message."""
        self.compound_template_command(
            "gc-objects",
            ["--help"],
            expected_data=[
                "usage",
                "--limit",
                "--generation",
                "--calculate-memory",
                "--sort-by",
            ],
        )

    def test_gc_objects_error_sort_without_memory(self):
        """Test gc-objects error when sorting by memory without --calculate-memory."""
        self.compound_template_command(
            "gc-objects",
            ["--sort-by", "memory"],
            expected_data=["Error", "--sort-by memory requires --calculate-memory"],
        )

    def test_gc_garbage(self):
        """Test gc-garbage command."""
        self.compound_template_command(
            "gc-garbage", expected_data=["count", "types", "objects"]
        )

    def test_gc_garbage_help(self):
        """Test gc-garbage help message."""
        self.compound_template_command(
            "gc-garbage", ["--help"], expected_data=["usage", "--help"]
        )

    def test_gc_collect(self):
        """Test gc-collect command with default generation."""
        self.compound_template_command(
            "gc-collect", expected_data=["generation", "unreachable", "collected"]
        )

    def test_gc_collect_generation_0(self):
        """Test gc-collect command for generation 0."""
        self.compound_template_command(
            "gc-collect",
            ["--generation", "0"],
            expected_data=["generation.*0", "unreachable", "collected"],
        )

    def test_gc_collect_generation_1(self):
        """Test gc-collect command for generation 1."""
        self.compound_template_command(
            "gc-collect",
            ["--generation", "1"],
            expected_data=["generation.*1", "unreachable", "collected"],
        )

    def test_gc_collect_generation_2(self):
        """Test gc-collect command for generation 2."""
        self.compound_template_command(
            "gc-collect",
            ["--generation", "2"],
            expected_data=["generation.*2", "unreachable", "collected"],
        )

    def test_gc_collect_help(self):
        """Test gc-collect help message."""
        self.compound_template_command(
            "gc-collect", ["--help"], expected_data=["usage", "--generation", "--help"]
        )

    def test_gc_monitor(self):
        """Test gc-monitor command."""
        self.compound_template_command(
            "gc-monitor", expected_data=["current_counts", "current_collections", "delta"]
        )

    def test_gc_monitor_help(self):
        """Test gc-monitor help message."""
        self.compound_template_command(
            "gc-monitor", ["--help"], expected_data=["usage", "--help"]
        )

    # ========== GC Commands Error/Exception Tests ==========

    def test_gc_status_error_invalid_arg(self):
        """Test gc-status with invalid argument."""
        self.compound_template_command(
            "gc-status", ["--invalid"], expected_data=["unrecognized arguments"]
        )

    def test_gc_status_error_unknown_flag(self):
        """Test gc-status with unknown flag."""
        self.compound_template_command(
            "gc-status", ["-x"], expected_data=["unrecognized arguments"]
        )

    def test_gc_stats_error_invalid_arg(self):
        """Test gc-stats with invalid argument."""
        self.compound_template_command(
            "gc-stats", ["--invalid"], expected_data=["unrecognized arguments"]
        )

    def test_gc_stats_error_unknown_flag(self):
        """Test gc-stats with unknown flag."""
        self.compound_template_command(
            "gc-stats", ["-x"], expected_data=["unrecognized arguments"]
        )

    def test_gc_objects_error_invalid_limit(self):
        """Test gc-objects with invalid limit value."""
        self.compound_template_command(
            "gc-objects", ["--limit", "invalid"], expected_data=["invalid int value"]
        )

    def test_gc_objects_error_invalid_generation(self):
        """Test gc-objects with invalid generation value."""
        self.compound_template_command(
            "gc-objects",
            ["--generation", "5"],
            expected_data=["invalid choice.*5"],
        )

    def test_gc_objects_error_negative_limit(self):
        """Test gc-objects with negative limit."""
        self.compound_template_command("gc-objects", ["--limit", "-10"], expected_data=[])

    def test_gc_objects_error_invalid_sort_by(self):
        """Test gc-objects with invalid sort-by value."""
        self.compound_template_command(
            "gc-objects",
            ["--sort-by", "invalid"],
            expected_data=["invalid choice"],
        )

    def test_gc_objects_error_sort_memory_without_flag(self):
        """Test gc-objects sorting by memory without --calculate-memory flag."""
        self.compound_template_command(
            "gc-objects",
            ["--sort-by", "memory"],
            expected_data=["Error", "--sort-by memory requires --calculate-memory"],
        )

    def test_gc_objects_error_sort_avg_memory_without_flag(self):
        """Test gc-objects sorting by avg_memory without --calculate-memory."""
        self.compound_template_command(
            "gc-objects",
            ["--sort-by", "avg_memory"],
            expected_data=["Error", "--sort-by avg_memory requires --calculate-memory"],
        )

    def test_gc_objects_error_multiple_invalid_args(self):
        """Test gc-objects with multiple invalid arguments."""
        self.compound_template_command(
            "gc-objects",
            ["--invalid1", "--invalid2"],
            expected_data=["unrecognized arguments"],
        )

    def test_gc_garbage_error_invalid_arg(self):
        """Test gc-garbage with invalid argument."""
        self.compound_template_command(
            "gc-garbage", ["--invalid"], expected_data=["unrecognized arguments"]
        )

    def test_gc_garbage_error_unknown_flag(self):
        """Test gc-garbage with unknown flag."""
        self.compound_template_command(
            "gc-garbage", ["-x"], expected_data=["unrecognized arguments"]
        )

    def test_gc_collect_error_invalid_generation(self):
        """Test gc-collect with invalid generation value."""
        self.compound_template_command(
            "gc-collect",
            ["--generation", "3"],
            expected_data=["invalid choice.*3"],
        )

    def test_gc_collect_error_invalid_generation_negative(self):
        """Test gc-collect with negative generation value."""
        self.compound_template_command(
            "gc-collect",
            ["--generation", "-1"],
            expected_data=["invalid choice"],
        )

    def test_gc_collect_error_invalid_generation_type(self):
        """Test gc-collect with non-integer generation value."""
        self.compound_template_command(
            "gc-collect",
            ["--generation", "invalid"],
            expected_data=["invalid int value"],
        )

    def test_gc_collect_error_unknown_flag(self):
        """Test gc-collect with unknown flag."""
        self.compound_template_command(
            "gc-collect", ["-x"], expected_data=["unrecognized arguments"]
        )

    def test_gc_collect_error_multiple_invalid_args(self):
        """Test gc-collect with multiple invalid arguments."""
        self.compound_template_command(
            "gc-collect",
            ["--invalid1", "--invalid2"],
            expected_data=["unrecognized arguments"],
        )

    def test_gc_monitor_error_invalid_arg(self):
        """Test gc-monitor with invalid argument."""
        self.compound_template_command(
            "gc-monitor", ["--invalid"], expected_data=["unrecognized arguments"]
        )

    def test_gc_monitor_error_unknown_flag(self):
        """Test gc-monitor with unknown flag."""
        self.compound_template_command(
            "gc-monitor", ["-x"], expected_data=["unrecognized arguments"]
        )

    def test_gc_objects_value_error_exception(self):
        """Test gc-objects ValueError exception handling from analyzer."""
        from unittest.mock import MagicMock, patch

        from telepy.monitor import gc_objects

        # Create mock request and response objects
        req = MagicMock()
        req.headers = {"args": ""}
        resp = MagicMock()

        # Mock the analyzer to raise ValueError
        with patch("telepy.monitor.get_analyzer") as mock_get_analyzer:
            mock_analyzer = mock_get_analyzer.return_value
            mock_analyzer.get_object_stats_formatted.side_effect = ValueError(
                "Test ValueError from analyzer"
            )

            # Call the function directly
            gc_objects(req, resp)

            # Verify error response was returned
            resp.return_json.assert_called_once()
            call_args = resp.return_json.call_args[0][0]
            self.assertEqual(call_args["code"], -1)  # ERROR_CODE
            self.assertIn("Test ValueError from analyzer", call_args["data"])


class TestRegisterEndpoint(TestBase):
    """Test cases for register_endpoint decorator."""

    def setUp(self):
        """Save the current endpoint registry state."""
        super().setUp()
        from telepy.monitor import ENDPOINT_REGISTRY

        # Save current registry state
        self.original_registry = ENDPOINT_REGISTRY.copy()

    def tearDown(self):
        """Restore the original endpoint registry state."""
        from telepy.monitor import ENDPOINT_REGISTRY

        # Restore original registry
        ENDPOINT_REGISTRY.clear()
        ENDPOINT_REGISTRY.update(self.original_registry)
        super().tearDown()

    def test_register_endpoint_success(self):
        """Test successfully registering a new endpoint."""
        from telepy.monitor import ENDPOINT_REGISTRY, register_endpoint

        @register_endpoint("/test-endpoint")
        def test_handler(req, resp):
            resp.return_json({"data": "test"})

        # Verify endpoint was registered
        self.assertIn("/test-endpoint", ENDPOINT_REGISTRY)
        self.assertEqual(ENDPOINT_REGISTRY["/test-endpoint"], test_handler)

    def test_register_endpoint_duplicate_raises_error(self):
        """Test that registering duplicate endpoint raises ValueError."""
        from telepy.monitor import ENDPOINT_REGISTRY, register_endpoint

        # Clear the registry to avoid conflicts with module-level registrations
        ENDPOINT_REGISTRY.clear()

        @register_endpoint("/duplicate-endpoint")
        def handler1(req, resp):
            resp.return_json({"data": "handler1"})

        # Try to register the same path again
        with self.assertRaises(ValueError) as context:

            @register_endpoint("/duplicate-endpoint")
            def handler2(req, resp):
                resp.return_json({"data": "handler2"})

        # Verify error message
        self.assertIn("/duplicate-endpoint", str(context.exception))
        self.assertIn("already registered", str(context.exception))

    def test_register_endpoint_different_paths_success(self):
        """Test registering multiple endpoints with different paths."""
        from telepy.monitor import ENDPOINT_REGISTRY, register_endpoint

        @register_endpoint("/endpoint-1")
        def handler1(req, resp):
            resp.return_json({"data": "1"})

        @register_endpoint("/endpoint-2")
        def handler2(req, resp):
            resp.return_json({"data": "2"})

        # Verify both endpoints were registered
        self.assertIn("/endpoint-1", ENDPOINT_REGISTRY)
        self.assertIn("/endpoint-2", ENDPOINT_REGISTRY)
        self.assertEqual(ENDPOINT_REGISTRY["/endpoint-1"], handler1)
        self.assertEqual(ENDPOINT_REGISTRY["/endpoint-2"], handler2)

    def test_register_endpoint_prevents_overwrite_existing(self):
        """Test that existing endpoints cannot be overwritten."""
        from telepy.monitor import ENDPOINT_REGISTRY, register_endpoint

        # Clear the registry to avoid conflicts with module-level registrations
        ENDPOINT_REGISTRY.clear()

        # Register an endpoint
        @register_endpoint("/protected-endpoint")
        def original_handler(req, resp):
            resp.return_json({"data": "original"})

        original_handler_ref = ENDPOINT_REGISTRY["/protected-endpoint"]

        # Try to overwrite it
        with self.assertRaises(ValueError):

            @register_endpoint("/protected-endpoint")
            def new_handler(req, resp):
                resp.return_json({"data": "new"})

        # Verify original handler is still registered
        self.assertEqual(ENDPOINT_REGISTRY["/protected-endpoint"], original_handler_ref)
