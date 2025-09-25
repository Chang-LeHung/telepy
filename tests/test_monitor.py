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
        self.compound_template_command(
            "stack", expected_data=["MainThread", "daemon", "telepy"]
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
            self.assertIn("--help, -h", data["data"])
            self.assertIn("-f FILENAME, --filename FILENAME", data["data"])
            self.assertIn("--save-folded", data["data"])
            self.assertIn("--folded-filename FOLDED_FILENAME", data["data"])
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
                self.assertIn("--help, -h", data["data"])
                self.assertIn("-f FILENAME, --filename FILENAME", data["data"])
                self.assertIn("--save-folded", data["data"])
                self.assertIn("--folded-filename FOLDED_FILENAME", data["data"])

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
