import logging
import os
import subprocess
import sys

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
        self.assertEqual(output.returncode, exit_code)
        stdout = output.stdout.decode("utf-8")
        if debug:
            logging.debug(stdout)
        for check in stdout_check_list:
            self.assertRegex(stdout, check)
        stderr = output.stderr.decode("utf-8")
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
        self.assertEqual(output.returncode, exit_code)
        stdout = output.stdout.decode("utf-8")
        for check in stdout_check_list:
            self.assertRegex(stdout, check)
        stderr = output.stderr.decode("utf-8")
        for check in stderr_check_list:
            self.assertRegex(stderr, check)
        return output


class TestCommand(CommandTemplate):
    def test_fib(self):
        self.run_filename(
            "test_files/test_fib.py",
            ["3524578", "saved the profiling data to the svg file result.svg"],
        )

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
            ],
            stdout_check_list=[
                "hello bob",
                "saved the profiling data to the svg file result.svg",
                "TelePySampler Metrics",
                "Accumulated Sampling Time",
                "TelePy Sampler Start Time",
                "TelePy Sampler End Time",
                "Sampling Count",
            ],
        )

    def test_help(self):
        expected = [
            "-h, --help",
            "--no-verbose",
            "-p, --parse",
            "--interval INTERVAL",
            "--debug",
            "--full-path",
            "--ignore-frozen",
            "--include-telepy",
            "--folded-save",
            "--folded-file FOLDED_FILE",
            "-o, --output OUTPUT",
            "--merge",
            "--no-merge",
            "--timeout TIMEOUT",
            "--tree-mode",
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
                "--interval INTERVAL",
                "--debug",
                "--full-path",
                "--ignore-frozen",
                "--include-telepy",
                "--folded-save",
                "--folded-file FOLDED_FILE",
                "-o, --output OUTPUT",
                "--merge",
                "--no-merge",
                "--timeout TIMEOUT",
                "--tree-mode",
                "--disable-traceback",
                "-c, --cmd CMD",
                "--module, -m MODULE",
            ],
        )

    def test_fork_multiple_child_process(self):
        self.run_filename(
            "test_files/test_fork_multi_processes.py",
            stdout_check_list=[],
            options=["--folded-save", "--debug"],
        )

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
            options=[f"{f.name}", "--parse", "--debug", "--reverse"],
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
