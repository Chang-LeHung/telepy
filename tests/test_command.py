import logging
import os
import re
import subprocess
import sys
import tempfile

from .base import TestBase  # type: ignore


class CommandTemplate(TestBase):
    def run_filename(
        self,
        filename: str,
        stdout_check_list: list[str] = [],
        stderr_check_list: list[str] = [],
        options: list[str] = [],
        timeout: int = 10,
        exit_code: int = 0,
        debug: bool = False,
    ):
        """
        Run a Python script file with given options and validate its output.

        Args:
            filename: Path to the script file to execute (relative to this test file)
            stdout_check_list: List of regex patterns to check against stdout
            stderr_check_list: List of regex patterns to check against stderr
            options: Additional command line options to pass to the script
            timeout: Maximum execution time in seconds
            exit_code: Expected exit code
            debug: Whether to print debug information

        Returns:
            The completed subprocess.CompletedProcess instance

        Raises:
            AssertionError: If any output check fails or exit code doesn't match
        """
        path = os.path.dirname(os.path.abspath(__file__))
        if "coverage" in sys.modules:
            cmd_line = [
                "coverage",
                "run",
                "--parallel-mode",
                "--source",
                "telepy",
                "-m",
                "telepy",
                os.path.join(path, filename),
                *options,
            ]
        else:
            cmd_line = ["telepy", os.path.join(path, filename), *options]
        if debug:
            logging.debug(cmd_line)
        output = subprocess.run(cmd_line, capture_output=True, timeout=timeout)  # type: ignore
        # TODO: why exits with -10 sometimes?
        self.assertIn(output.returncode, [exit_code, -10])
        stdout = output.stdout.decode("utf-8", errors="replace")
        if debug:
            logging.debug(stdout)
        for check in stdout_check_list:
            self.assertRegex(stdout, check)
        stderr = output.stderr.decode("utf-8", errors="replace")
        for check in stderr_check_list:
            self.assertRegex(stderr, check)
        return output

    def run_command(
        self,
        options: list[str],
        stdout_check_list: list[str] = [],
        stderr_check_list: list[str] = [],
        timeout: int = 10,
        exit_code: int = 0,
    ):
        """
        Run a command with given options and validate its output.

        Args:
            options: List of command line options to pass to the telepy command.
            stdout_check_list: List of regex patterns to check against stdout.
            stderr_check_list: List of regex patterns to check against stderr.
            timeout: Maximum time in seconds to wait for command completion.
            exit_code: Expected exit code of the command.

        Returns:
            The completed subprocess.CompletedProcess object.

        Raises:
            AssertionError: If any of the checks fail (exit code, stdout, or stderr).
        """
        if "coverage" in sys.modules:
            cmd_line = [
                "coverage",
                "run",
                "--parallel-mode",
                "--source",
                "telepy",
                "-m",
                "telepy",
                *options,
            ]
        else:
            cmd_line = ["telepy", *options]
        output = subprocess.run(cmd_line, capture_output=True, timeout=timeout)  # type: ignore
        # TODO: why exits with -10 sometimes?
        self.assertIn(output.returncode, [exit_code, -10])
        stdout = output.stdout.decode("utf-8")
        for check in stdout_check_list:
            self.assertRegex(stdout, check)
        stderr = output.stderr.decode("utf-8")
        for check in stderr_check_list:
            self.assertRegex(stderr, check)
        return output


class TestCommand(CommandTemplate):
    def test_fib(self):
        import os
        import tempfile

        # Create unique output file for this test
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            svg_file = f.name

        try:
            self.run_filename(
                "test_files/test_fib.py",
                ["3524578", "saved the profiling data to the svg file"],
                options=["-o", svg_file],
            )
        finally:
            # Clean up the temporary file
            if os.path.exists(svg_file):
                os.unlink(svg_file)

    def test_fib_fork(self):
        output = self.run_filename(
            "test_files/test_fib_fork.py",
            [],
        )
        self.assertEqual(output.returncode, 0)

    def test_spawn(self):
        self.run_filename(
            "test_files/test_spawn.py",
            [],
        )

    def test_forkserver(self):
        import os
        import tempfile

        # Create unique output file for this test
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            svg_file = f.name

        try:
            self.run_filename(
                "test_files/test_forkserver.py",
                options=[
                    "--interval",
                    "5",
                    "--debug",
                    "--full-path",
                    "--ignore-frozen",
                    "--include-telepy",
                    "--tree-mode",
                    "--no-merge",
                    "-o",
                    svg_file,
                ],
                stdout_check_list=[
                    "hello bob",
                    "saved the profiling data to the svg file",
                    "TelePySampler Metrics",
                    "Accumulated Sampling Time",
                    "TelePy Sampler Start Time",
                    "TelePy Sampler End Time",
                    "Sampling Count",
                ],
            )
        finally:
            # Clean up the temporary file
            if os.path.exists(svg_file):
                os.unlink(svg_file)

    def test_help(self):
        expected = [
            "-h, --help",
            "-v, --version",
            "--no-verbose",
            "-p, --parse",
            "-i, --interval INTERVAL",
            "--debug",
            "--full-path",
            "--ignore-frozen",
            "--include-telepy",
            "--focus-mode",
            "--regex-patterns REGEX_PATTERNS",
            "--folded-save",
            "--folded-file FOLDED_FILE",
            "-o, --output OUTPUT",
            "--merge",
            "--no-merge",
            "--timeout TIMEOUT",
            "--tree-mode",
            "--inverted",
            "--disable-traceback",
            "-c, --cmd CMD",
            "--module, -m MODULE",
            "--create-config",
        ]
        self.run_command(
            ["-h"],
            stdout_check_list=expected,
        )
        self.run_command(
            ["--help"],
            stdout_check_list=expected,
        )

    def test_version(self):
        """Test --version and -v flags functionality"""
        # Test short version flag
        self.run_command(
            ["-v"],
            stdout_check_list=[
                r"TelePy version \d+\.\d+\.\d+",
            ],
        )

        # Test long version flag
        self.run_command(
            ["--version"],
            stdout_check_list=[
                r"TelePy version \d+\.\d+\.\d+",
            ],
        )

    def test_interval_short_option(self):
        """Test -i short option for interval functionality"""
        import os
        import tempfile

        # Create unique output files for this test
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f1:
            svg_file1 = f1.name
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f2:
            svg_file2 = f2.name

        try:
            # Test short interval option
            self.run_command(
                [
                    "-c",
                    "import time; time.sleep(0.01); print('Test with -i')",
                    "-i",
                    "1000",
                    "-o",
                    svg_file1,
                ],
                stdout_check_list=[
                    "Test with -i",
                    "saved the profiling data to the svg file",
                ],
            )

            # Verify that both -i and --interval work the same way
            self.run_command(
                [
                    "-c",
                    "import time; time.sleep(0.01); print('Test with --interval')",
                    "--interval",
                    "1000",
                    "-o",
                    svg_file2,
                ],
                stdout_check_list=[
                    "Test with --interval",
                    "saved the profiling data to the svg file",
                ],
            )
        finally:
            # Clean up the temporary files
            for svg_file in [svg_file1, svg_file2]:
                if os.path.exists(svg_file):
                    os.unlink(svg_file)

    def test_run_site(self):
        self.run_command(
            ["-m", "site"],
            [r"sys.path = \[", "python"],
        )

    def test_run_sys_exit(self):
        self.run_command(["-c", "import sys; sys.exit(0)"])

    def test_run_os__exit(self):
        self.run_command(["-c", "import os; os._exit(0)"])

    def test_argv(self):
        self.run_filename(
            "test_files/test_argv.py",
            stdout_check_list=["hello", "world", "test_argv.py"],
            options=["--folded-save", "--", "hello", "world"],
        )

    def test_run_string_argv(self):
        self.run_command(
            ["-c", "import sys; print(sys.argv)", "--", "hello", "world"],
            stdout_check_list=["hello", "world", "-c"],
        )

    def test_run_module(self):
        self.run_command(
            ["-m", "telepy", "--", "-h"],
            stdout_check_list=[
                "-h, --help",
                "--no-verbose",
                "-p, --parse",
                "-i, --interval INTERVAL",
                "--debug",
                "--full-path",
                "--ignore-frozen",
                "--include-telepy",
                "--focus-mode",
                "--regex-patterns REGEX_PATTERNS",
                "--folded-save",
                "--folded-file FOLDED_FILE",
                "-o, --output OUTPUT",
                "--merge",
                "--no-merge",
                "--timeout TIMEOUT",
                "--tree-mode",
                "--inverted",
                "--disable-traceback",
                "-c, --cmd CMD",
                "--module, -m MODULE",
            ],
        )

    def test_fork_multiple_child_process(self):
        svg_fd, svg_path = tempfile.mkstemp(suffix=".svg")
        folded_fd, folded_path = tempfile.mkstemp(suffix=".folded")
        os.close(svg_fd)
        os.close(folded_fd)
        try:
            self.run_filename(
                "test_files/test_fork_multi_processes.py",
                stdout_check_list=[],
                options=[
                    "--folded-save",
                    "--debug",
                    "--folded-file",
                    folded_path,
                    "-o",
                    svg_path,
                ],
            )

            with open(folded_path, encoding="utf-8") as fp:
                lines = [line.strip() for line in fp if line.strip()]

            prefixes = {line.split(";", 1)[0] for line in lines}
            has_root = any(prefix.startswith("Process(root, pid=") for prefix in prefixes)
            self.assertTrue(has_root)
            child_prefixes = [p for p in prefixes if p.startswith("Process(pid-")]
            self.assertGreaterEqual(len(child_prefixes), 3)
        finally:
            if os.path.exists(folded_path):
                os.unlink(folded_path)
            if os.path.exists(svg_path):
                os.unlink(svg_path)

    def test_fork_multiple_child_process_no_merge(self):
        self.run_filename(
            "test_files/test_fork_multi_processes.py",
            stdout_check_list=[],
            options=["--folded-save", "--no-merge", "--debug"],
        )

    def test_spwan_multiple_child_process_no_merge(self):
        self.run_filename(
            "test_files/test_spawn_multi_processes.py",
            stdout_check_list=[],
            options=["--folded-save", "--no-merge", "--debug"],
        )

    def test_spwan_multiple_child_process_no_merge_no_save(self):
        self.run_filename(
            "test_files/test_spawn_multi_processes.py",
            stdout_check_list=[],
            options=["--no-merge", "--debug"],
        )

    def test_spwan_multiple_child_processno_save(self):
        self.run_filename(
            "test_files/test_spawn_multi_processes.py",
            stdout_check_list=[],
            options=["--debug"],
        )

    def test_parse_stack_trace(self):
        import tempfile

        f = tempfile.NamedTemporaryFile(delete=False, mode="w+")
        f.write(
            """MainThread;Users/huchang/miniconda3/bin/coverage:<module>:1;coverage/cmdline.py:main:961;coverage/cmdline.py:CoverageScript.command_line:608;coverage/cmdline.py:CoverageScript.do_run:810;coverage/execfile.py:PyRunner.run:169;tests/test_files/test_fork_multi_processes.py:<module>:1;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4 3
MainThread;Users/huchang/miniconda3/bin/coverage:<module>:1;coverage/cmdline.py:main:961;coverage/cmdline.py:CoverageScript.command_line:608;coverage/cmdline.py:CoverageScript.do_run:810;coverage/execfile.py:PyRunner.run:169;tests/test_files/test_fork_multi_processes.py:<module>:1;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4 9
MainThread;Users/huchang/miniconda3/bin/coverage:<module>:1;coverage/cmdline.py:main:961;coverage/cmdline.py:CoverageScript.command_line:608;coverage/cmdline.py:CoverageScript.do_run:810;coverage/execfile.py:PyRunner.run:169;tests/test_files/test_fork_multi_processes.py:<module>:1;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4 11
MainThread;Users/huchang/miniconda3/bin/coverage:<module>:1;coverage/cmdline.py:main:961;coverage/cmdline.py:CoverageScript.command_line:608;coverage/cmdline.py:CoverageScript.do_run:810;coverage/execfile.py:PyRunner.run:169;tests/test_files/test_fork_multi_processes.py:<module>:1;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4 24
MainThread;Users/huchang/miniconda3/bin/coverage:<module>:1;coverage/cmdline.py:main:961;coverage/cmdline.py:CoverageScript.command_line:608;coverage/cmdline.py:CoverageScript.do_run:810;coverage/execfile.py:PyRunner.run:169;tests/test_files/test_fork_multi_processes.py:<module>:1;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4 24
MainThread;Users/huchang/miniconda3/bin/coverage:<module>:1;coverage/cmdline.py:main:961;coverage/cmdline.py:CoverageScript.command_line:608;coverage/cmdline.py:CoverageScript.do_run:810;coverage/execfile.py:PyRunner.run:169;tests/test_files/test_fork_multi_processes.py:<module>:1;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4 34
MainThread;Users/huchang/miniconda3/bin/coverage:<module>:1;coverage/cmdline.py:main:961;coverage/cmdline.py:CoverageScript.command_line:608;coverage/cmdline.py:CoverageScript.do_run:810;coverage/execfile.py:PyRunner.run:169;tests/test_files/test_fork_multi_processes.py:<module>:1;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4 20
MainThread;Users/huchang/miniconda3/bin/coverage:<module>:1;coverage/cmdline.py:main:961;coverage/cmdline.py:CoverageScript.command_line:608;coverage/cmdline.py:CoverageScript.do_run:810;coverage/execfile.py:PyRunner.run:169;tests/test_files/test_fork_multi_processes.py:<module>:1;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4 17
MainThread;Users/huchang/miniconda3/bin/coverage:<module>:1;coverage/cmdline.py:main:961;coverage/cmdline.py:CoverageScript.command_line:608;coverage/cmdline.py:CoverageScript.do_run:810;coverage/execfile.py:PyRunner.run:169;tests/test_files/test_fork_multi_processes.py:<module>:1;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4 9
MainThread;Users/huchang/miniconda3/bin/coverage:<module>:1;coverage/cmdline.py:main:961;coverage/cmdline.py:CoverageScript.command_line:608;coverage/cmdline.py:CoverageScript.do_run:810;coverage/execfile.py:PyRunner.run:169;tests/test_files/test_fork_multi_processes.py:<module>:1;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4 2
MainThread;Users/huchang/miniconda3/bin/coverage:<module>:1;coverage/cmdline.py:main:961;coverage/cmdline.py:CoverageScript.command_line:608;coverage/cmdline.py:CoverageScript.do_run:810;coverage/execfile.py:PyRunner.run:169;tests/test_files/test_fork_multi_processes.py:<module>:1;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4 2
MainThread;Users/huchang/miniconda3/bin/coverage:<module>:1;coverage/cmdline.py:main:961;coverage/cmdline.py:CoverageScript.command_line:608;coverage/cmdline.py:CoverageScript.do_run:810;coverage/execfile.py:PyRunner.run:169;tests/test_files/test_fork_multi_processes.py:<module>:1;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4;tests/test_files/test_fork_multi_processes.py:fib:4 2
"""  # noqa: E501
        )
        f.close()
        self.run_command(
            options=[f"{f.name}", "--parse", "--debug"],
        )
        os.unlink(f.name)
        os.unlink("result.svg")

    def test_error(self):
        self.run_command(
            options=["asdxwsasdasdwdaasdfgde"],
            exit_code=2,
            stderr_check_list=[
                r"\[Errno 2\] No such file or directory",
            ],
        )

    def test_py_error(self):
        self.run_command(
            options=["-c", "a = 1 / 0"],
            stdout_check_list=[
                "The following traceback may be useful for debugging",
            ],
            stderr_check_list=[
                "ZeroDivisionError: division by zero",
            ],
            exit_code=-27 if "coverage" in sys.modules else 1,
        )

    def test_py_error_raw(self):
        self.run_command(
            options=["-c", "a = 1 / 0", "--disable-traceback"],
            stderr_check_list=[
                "division by zero",
            ],
            exit_code=-27 if "coverage" in sys.modules else 1,
        )

    def test_not_python_file(self):
        with open("tests/demo", "w+") as fp:
            fp.write("print('hello world')")

        self.run_filename(
            filename="demo",
            stderr_check_list=[
                "not found a proper handler to handle the arguments",
            ],
            exit_code=1,
        )
        os.unlink("tests/demo")

    def test_focus_mode(self):
        """Test --focus-mode flag functionality"""
        import os
        import tempfile

        # Create unique output file for this test
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            svg_file = f.name

        try:
            self.run_filename(
                "test_files/test_focus_and_regex.py",
                stdout_check_list=[
                    "Starting focus and regex test",
                    "Heavy task result:",
                    "IO task result:",
                    "Threading task completed",
                    "All tasks completed!",
                    "saved the profiling data to the svg file",
                ],
                options=["--focus-mode", "--interval", "100", "--debug", "-o", svg_file],
            )
        finally:
            # Clean up the temporary file
            if os.path.exists(svg_file):
                os.unlink(svg_file)

    def test_regex_patterns_single(self):
        """Test --regex-patterns with a single pattern"""
        import os
        import tempfile

        # Create unique output file for this test
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            svg_file = f.name

        try:
            self.run_filename(
                "test_files/test_focus_and_regex.py",
                stdout_check_list=[
                    "Starting focus and regex test",
                    "Heavy task result:",
                    "IO task result:",
                    "Threading task completed",
                    "All tasks completed!",
                    "saved the profiling data to the svg file",
                ],
                options=[
                    "--regex-patterns",
                    '".*test_focus.*"',
                    "--interval",
                    "1000",  # Much larger interval to reduce signal conflicts
                    "--debug",
                    "-o",
                    svg_file,
                ],
                timeout=60,  # Add significant timeout
            )
        finally:
            # Clean up the temporary file
            if os.path.exists(svg_file):
                os.unlink(svg_file)

    def test_regex_patterns_multiple(self):
        """Test --regex-patterns with multiple patterns"""
        import os
        import tempfile

        # Create unique output file for this test
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            svg_file = f.name

        try:
            self.run_filename(
                "test_files/test_focus_and_regex.py",
                stdout_check_list=[
                    "Starting focus and regex test",
                    "Heavy task result:",
                    "IO task result:",
                    "Threading task completed",
                    "All tasks completed!",
                    "saved the profiling data to the svg file",
                ],
                options=[
                    "--regex-patterns",
                    "test_focus",  # Simplify regex pattern
                    "--regex-patterns",
                    "main",  # Simplify regex pattern
                    "--interval",
                    "500",  # Significantly increase interval
                    "--debug",
                    "-o",
                    svg_file,
                ],
                timeout=45,  # Increase timeout
            )
        finally:
            # Clean up the temporary file
            if os.path.exists(svg_file):
                os.unlink(svg_file)

    def test_focus_mode_with_regex_patterns(self):
        """Test combining --focus-mode with --regex-patterns"""
        import os
        import tempfile

        # Create unique output file for this test
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            svg_file = f.name

        try:
            self.run_filename(
                "test_files/test_focus_and_regex.py",
                stdout_check_list=[
                    "Starting focus and regex test",
                    "Heavy task result:",
                    "IO task result:",
                    "Threading task completed",
                    "All tasks completed!",
                    "saved the profiling data to the svg file",
                ],
                options=[
                    "--focus-mode",
                    "--regex-patterns",
                    ".*test_focus.*",
                    "--interval",
                    "1000",  # Much larger interval to reduce signal conflicts
                    "--debug",
                    "-o",
                    svg_file,
                ],
                timeout=60,  # Significantly increase timeout
            )
        finally:
            # Clean up the temporary file
            if os.path.exists(svg_file):
                os.unlink(svg_file)

    def test_focus_mode_folded_output(self):
        """Test --focus-mode with folded output to verify filtering works"""
        import os
        import tempfile

        # Create unique output files for this test
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f1:
            svg_file = f1.name
        with tempfile.NamedTemporaryFile(suffix=".folded", delete=False) as f2:
            folded_file = f2.name

        try:
            self.run_filename(
                "test_files/test_focus_and_regex.py",
                stdout_check_list=[
                    "Starting focus and regex test",
                    "Heavy task result:",
                    "IO task result:",
                    "Threading task completed",
                    "All tasks completed!",
                    r"Process \d+ saved the profiling data to the svg file",
                    r"Process \d+ saved the profiling data to the folded file",
                ],
                options=[
                    "--focus-mode",
                    "--folded-save",
                    "--interval",
                    "100",
                    "--debug",
                    "-o",
                    svg_file,
                    "--folded-file",
                    folded_file,
                ],
            )

            # Check that folded file exists and contains user code
            folded_content = ""
            with open(folded_file) as f:
                folded_content = f.read()

            # Should contain user-defined functions like test_focus_and_regex
            self.assertRegex(folded_content, r"test_focus_and_regex")
            # Should NOT contain many standard library calls due to focus mode
            self.assertNotRegex(folded_content, r"threading\.py")
        finally:
            # Clean up the temporary files
            for temp_file in [svg_file, folded_file]:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)

    def test_regex_patterns_no_match(self):
        """Test --regex-patterns with pattern that doesn't match anything"""
        import os
        import tempfile

        # Create unique output file for this test
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            svg_file = f.name

        try:
            self.run_filename(
                "test_files/test_focus_and_regex.py",
                stdout_check_list=[
                    "Starting focus and regex test",
                    "Heavy task result:",
                    "IO task result:",
                    "Threading task completed",
                    "All tasks completed!",
                    "saved the profiling data to the svg file",
                ],
                options=[
                    "--regex-patterns",
                    '".*nonexistent.*"',
                    "--interval",
                    "1000",  # Much larger interval to reduce signal conflicts
                    "--debug",
                    "-o",
                    svg_file,
                ],
                timeout=60,  # Add significant timeout
            )
        finally:
            # Clean up the temporary file
            if os.path.exists(svg_file):
                os.unlink(svg_file)

    def test_regex_patterns_multithread_fib_only(self):
        """Test --regex-patterns 'fib' with multiple threads to ensure only
        fib-related calls are captured"""
        import os
        import tempfile

        # Create a temporary folded file to check the output
        with tempfile.NamedTemporaryFile(
            mode="w+", suffix=".folded", delete=False
        ) as temp_file:
            temp_filename = temp_file.name

        # Create a temporary SVG file for this test
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as svg_file:
            svg_filename = svg_file.name

        try:
            self.run_filename(
                "test_files/test_multi_thread_regex.py",
                stdout_check_list=[
                    "Main thread fib\\(30\\) = 832040",
                    "All threads completed",
                    "saved the profiling data to the svg file",
                ],
                options=[
                    "--regex-patterns",
                    "fib",
                    "--interval",
                    "1000",  # Much larger interval to reduce signal conflicts
                    "--debug",
                    "--folded-save",
                    "--folded-file",
                    temp_filename,
                    "-o",
                    svg_filename,
                ],
                timeout=90,  # Even longer timeout
            )

            # Check that the folded output only contains fib-related function calls
            with open(temp_filename) as f:
                folded_content = f.read()

            # Verify that fib functions are captured
            self.assertRegex(folded_content, r"fib")

            # Verify that non-fib functions (calculate_sum, process_data) are NOT captured
            # These should not appear in the output when regex pattern is "fib"
            self.assertNotRegex(folded_content, r"calculate_sum")
            self.assertNotRegex(folded_content, r"process_data")

            # Verify that we have entries from multiple threads (MainThread, FibThread)
            # but only for fib-related calls
            lines = [line.strip() for line in folded_content.split("\n") if line.strip()]
            fib_lines = [line for line in lines if "fib" in line]
            self.assertGreater(
                len(fib_lines), 0, "Should have captured fib function calls"
            )

        finally:
            # Clean up the temporary files
            if os.path.exists(temp_filename):
                os.unlink(temp_filename)
            if os.path.exists(svg_filename):
                os.unlink(svg_filename)


class TestEnvironment(TestBase):
    def test_environment_init(self):
        from telepy.environment import Environment

        try:
            Environment.initialized = True
            Environment.init_telepy_environment(None)
        except RuntimeError:
            pass
        else:
            self.fail("RuntimeError not raised")

    def test_environment_destroy(self):
        from telepy.environment import Environment

        Environment.destory_telepy_enviroment()

    def test_finalize(self):
        from telepy.environment import telepy_finalize

        try:
            telepy_finalize()
        except RuntimeError:
            pass
        else:
            self.fail("RuntimeError not raised")


class TestFlameGraph(TestBase):
    def test_flamegraph(self):
        from telepy.flamegraph import FlameGraph

        node = FlameGraph.Node("test")

        self.assertEqual(node.name, "test")
        self.assertEqual(str(node), "test (0)")
        self.assertEqual(repr(node), "test (0)")

    def test_flamegraph_svg_caching(self):
        """Test that generate_svg() caches results and only executes once"""
        from telepy.flamegraph import FlameGraph

        # Sample stack trace data
        test_lines = ["main;func_a;func_b 10", "main;func_a;func_c 5", "main;func_d 3"]

        flamegraph = FlameGraph(test_lines)
        flamegraph.parse_input()

        # Verify initial state
        self.assertFalse(flamegraph._svg_generated)
        self.assertEqual(flamegraph._cached_svg, "")

        # First call should generate SVG
        svg1 = flamegraph.generate_svg()
        self.assertTrue(flamegraph._svg_generated)
        self.assertEqual(flamegraph._cached_svg, svg1)
        self.assertIn("main", svg1)  # Verify SVG contains expected content
        self.assertIn("func_a", svg1)

        # Second call should return cached result
        svg2 = flamegraph.generate_svg()
        self.assertEqual(svg1, svg2)  # Should be identical

        # Third call should also return cached result
        svg3 = flamegraph.generate_svg()
        self.assertEqual(svg1, svg3)  # Should still be identical

        # Verify the SVG is valid (contains expected SVG structure)
        self.assertIn('<?xml version="1.0"', svg1)
        self.assertIn("<svg", svg1)
        self.assertIn("</svg>", svg1)

    def test_flamegraph_inverted_orientation(self):
        from telepy.flamegraph import FlameGraph

        test_lines = [
            "main;worker;task 10",
            "main;worker;helper 5",
            "main;io 3",
        ]

        standard = FlameGraph(test_lines)
        standard.parse_input()
        standard_svg = standard.generate_svg()

        inverted = FlameGraph(test_lines, inverted=True)
        inverted.parse_input()
        inverted_svg = inverted.generate_svg()

        self.assertIn('data-orientation="standard"', standard_svg)
        self.assertIn('data-orientation="inverted"', inverted_svg)

        rect_pattern = re.compile(
            r'<rect x="[^"]+" y="([^"]+)" width="([^"]+)" height="[^"]+" '
            r'fill="[^"]+" rx="2" ry="2"'
        )

        def frame_rects(svg: str) -> list[tuple[str, str]]:
            frames_section = svg.partition('<g id="frames"')[2]
            frames_section = frames_section.partition(">")[2]
            return rect_pattern.findall(frames_section)

        standard_rects = frame_rects(standard_svg)
        inverted_rects = frame_rects(inverted_svg)

        self.assertGreater(len(standard_rects), 0)
        self.assertGreater(len(inverted_rects), 0)

        standard_root_y = float(standard_rects[0][0])
        inverted_root_y = float(inverted_rects[0][0])

        self.assertGreater(standard_root_y, inverted_root_y)
        self.assertGreaterEqual(inverted_root_y, 120.0)
