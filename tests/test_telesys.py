import os
import sys
import unittest

from .base import TestBase  # type: ignore


class TestTelePySys(TestBase):
    def tearDown(self):
        """Clean up test files after each test."""
        super().tearDown()
        test_files = ["test_sampler.stack"]
        for file in test_files:
            if os.path.exists(file):
                os.remove(file)

    def test_telepysys_version(self):
        import telepy

        v = telepy.__version__
        self.assertTrue(v is not None and v != "")

    def test_telepysys_current_stacks(self):
        import telepy

        call_stack = telepy.current_stacks()

        self.assertGreater(len(call_stack), 0)
        for _, val in call_stack.items():
            self.assertTrue(val is not None and len(val) > 0)

    def test_telepysys_pretty_stack(self):
        import threading

        import telepy

        def fib(n: int) -> int:
            if n <= 1:
                return n
            else:
                return fib(n - 1) + fib(n - 2)

        tids = set()
        t = threading.Thread(target=fib, args=(30,))
        t.start()
        tids.add(t.ident)
        tids.add(threading.get_ident())
        call_stack = telepy.current_stacks()
        for key, value in telepy.join_current_stacks(call_stack).items():
            self.assertIn("fib", value)
            self.assertIn("tests/test_telesys.py", value)
            break
        t.join()
        # Check that our threads are in the call stack (may have other system threads)
        self.assertTrue(tids.issubset(set(call_stack.keys())))

    def test_current_frames(self):
        import threading

        import telepy

        def fib(n: int) -> int:
            if n <= 1:
                return n
            return fib(n - 1) + fib(n - 2)

        t = threading.Thread(target=fib, args=(10,))
        t.start()
        frames = telepy.current_frames()
        for tid, frame in frames.items():
            self.assertIn(tid, [t.ident, threading.get_ident()])
            if "telepy" not in frame.f_code.co_filename:
                self.assertIn("tests/test_telesys.py", frame.f_code.co_filename)
                self.assertIn("fib", frame.f_code.co_name)
        t.join()

    def test_static_cls_method(self):
        import threading

        import telepy

        class Fib:
            @staticmethod
            def fib(n):
                if n < 2:
                    return n
                return Fib.fib(n - 1) + Fib.fib(n - 2)

            @classmethod
            def bar(cls, n: int) -> int:
                if n < 2:
                    return n
                return cls.bar(n - 1) + cls.bar(n - 2)

        tids = set()
        t = threading.Thread(target=Fib.fib, args=(30,))
        t.start()
        tids.add(t.ident)
        tids.add(threading.get_ident())
        call_stack = telepy.current_stacks()
        for tid, value in telepy.join_current_stacks(call_stack).items():
            if tid != threading.get_ident():
                # In Python 3.9/3.10, static methods may not include class name
                self.assertTrue("Fib.fib" in value or "fib" in value)
            break
        t.join()
        # Check that our threads are in the call stack (may have other system threads)
        self.assertTrue(tids.issubset(set(call_stack.keys())))

        tids.clear()
        t = threading.Thread(target=Fib.bar, args=(30,))
        t.start()
        tids.add(t.ident)
        tids.add(threading.get_ident())
        call_stack = telepy.current_stacks()
        for tid, value in telepy.join_current_stacks(call_stack).items():
            if tid != threading.get_ident():
                # In Python 3.9/3.10, class methods may not include class name
                self.assertTrue("Fib.bar" in value or "bar" in value)
            break
        t.join()
        # Check that our threads are in the call stack (may have other system threads)
        self.assertTrue(tids.issubset(set(call_stack.keys())))


class TestSampler(TestBase):
    def tearDown(self):
        """Clean up test files after each test."""
        super().tearDown()
        test_files = ["test_sampler.stack"]
        for file in test_files:
            if os.path.exists(file):
                os.remove(file)

    def test_sampler(self):
        import telepy

        sampler = telepy.TelepySysSampler()
        self.assertEqual(sampler.sampling_interval, 10_000)
        sampler.sampling_interval = 1000
        self.assertEqual(sampler.sampling_interval, 1000)

    def test_sampler_start(self):
        import threading

        import telepy

        def fib(n: int) -> int:
            if n <= 1:
                return n
            return fib(n - 1) + fib(n - 2)

        sampler = telepy.TelepySysSampler()
        sampler.start()
        t = threading.Thread(target=fib, args=(30,))
        t.start()
        t.join()
        sampler.stop()

    def test_sampler_dump(self):
        import sys
        import threading

        import telepy

        def fib(n: int) -> int:
            if n < 2:
                return 1
            return fib(n - 1) + fib(n - 2)

        sampler = telepy.TelepySysSampler()
        sampler.sampling_interval = 500
        sampler.adjust()
        sampler.start()
        t1 = threading.Thread(target=fib, args=(35,))
        t1.start()

        t2 = threading.Thread(target=fib, args=(35,))
        t2.start()

        t1.join()
        t2.join()
        sampler.stop()
        sampler.join_sampling_thread()
        result = sampler.dumps()  # no need to eliminate newline anymore
        self.assertIn("fib", result)
        self.assertIn("MainThread", result)
        self.assertIn("Thread-", result)
        if "coverage" not in sys.modules and sys.version_info[:2] > (3, 9):
            self.assertIn("<frozen", result)
        with open("test_sampler.stack", "w") as f:
            f.write(result)

    def test_adjust(self):
        import sys

        import telepy

        sampler = telepy.TelepySysSampler()
        sampler.sampling_interval = 1000  # 1ms
        sys.setswitchinterval(0.005)  # 5ms
        self.assertTrue(sampler.adjust_interval())

        sys.setswitchinterval(0.001 / 4)
        self.assertFalse(sampler.adjust_interval())

    def test_ignore_froze(self):
        import threading

        import telepy

        sampler = telepy.TelepySysSampler(ignore_frozen=True)
        sampler.start()
        self.assertTrue(sampler.started)

        def fib(n: int) -> int:
            if n < 2:
                return 1
            return fib(n - 1) + fib(n - 2)

        t1 = threading.Thread(target=fib, args=(35,))
        t1.start()
        t1.join()
        sampler.stop()
        self.assertFalse(sampler.started)
        content = sampler.dumps()
        self.assertIn("fib", content)
        self.assertNotIn("frozen", content)
        sampler.save("test_sampler.stack")
        self.assertLessEqual(sampler.sampling_time_rate, 1)


class TelepyMainThread(TestBase):
    def test_main_thread(self):
        import io
        import threading

        from telepy import in_main_thread

        def bar():
            @in_main_thread
            def main_thread(buf: io.StringIO):
                print(threading.current_thread().name, file=buf)

            file = io.StringIO()
            main_thread(file)
            self.assertEqual(file.getvalue(), "MainThread\n")

        t = threading.Thread(target=bar)
        t.start()
        t.join()

    def test_in_main_thread_runtime_error(self):
        from telepy import in_main_thread

        try:
            in_main_thread([1, 2, 3])()
        except RuntimeError:
            pass
        else:
            self.fail("RuntimeError not raised")
        try:
            in_main_thread([1, 2, 3])
        except RuntimeError:
            pass
        else:
            self.fail("RuntimeError not raised")

    def test_in_main_thread_in_main(self):
        from telepy import in_main_thread

        @in_main_thread
        def bar():
            import threading

            assert threading.current_thread().name == "MainThread"

        bar()

    def test_in_main_in_non_main(self):
        import threading

        from telepy import in_main_thread

        def test():
            @in_main_thread
            def bar():
                import threading

                assert threading.current_thread().name == "MainThread"

            assert threading.current_thread().name != "MainThread"
            bar()

        t = threading.Thread(target=test)
        t.start()
        t.join()


@unittest.skipIf(sys.version_info >= (3, 13), "vm_read not supported on Python 3.13+")
class TestVMRead(TestBase):
    """Test cases for vm_read function."""

    def test_vm_read_local_variable(self):
        """Test reading local variable from a worker thread."""
        import threading
        import time

        from telepy import _telepysys

        def worker():
            local_var = "I am a local variable"  # noqa: F841
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        result = _telepysys.vm_read(worker_thread.ident, "local_var")
        self.assertEqual(result, "I am a local variable")

        worker_thread.join()

    def test_vm_read_global_variable(self):
        """Test reading global variable from a worker thread."""
        import threading
        import time

        from telepy import _telepysys

        global test_global_var
        test_global_var = "I am a global variable"

        def worker():
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        result = _telepysys.vm_read(worker_thread.ident, "test_global_var")
        self.assertEqual(result, "I am a global variable")

        worker_thread.join()

    def test_vm_read_nonexistent_variable(self):
        """Test reading non-existent variable returns None."""
        import threading
        import time

        from telepy import _telepysys

        def worker():
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        result = _telepysys.vm_read(worker_thread.ident, "nonexistent_var")
        self.assertIsNone(result)

        worker_thread.join()

    def test_vm_read_nonexistent_thread(self):
        """Test reading from non-existent thread returns None."""
        from telepy import _telepysys

        result = _telepysys.vm_read(99999, "some_var")
        self.assertIsNone(result)

    def test_vm_read_module(self):
        """Test reading module from worker thread."""
        import threading
        import time

        from telepy import _telepysys

        def worker():
            # Reference threading module so it's in the frame's globals
            _ = threading
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        result = _telepysys.vm_read(worker_thread.ident, "threading")
        self.assertIsNotNone(result)

        worker_thread.join()

    def test_vm_read_various_types(self):
        """Test reading different data types."""
        import threading
        import time

        from telepy import _telepysys

        def worker():
            int_var = 42  # noqa: F841
            str_var = "test string"  # noqa: F841
            list_var = [1, 2, 3]  # noqa: F841
            dict_var = {"key": "value"}  # noqa: F841
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        # Test int
        result = _telepysys.vm_read(worker_thread.ident, "int_var")
        self.assertEqual(result, 42)

        # Test string
        result = _telepysys.vm_read(worker_thread.ident, "str_var")
        self.assertEqual(result, "test string")

        # Test list
        result = _telepysys.vm_read(worker_thread.ident, "list_var")
        self.assertEqual(result, [1, 2, 3])

        # Test dict
        result = _telepysys.vm_read(worker_thread.ident, "dict_var")
        self.assertEqual(result, {"key": "value"})

        worker_thread.join()

    def test_vm_read_multiple_calls_same_object(self):
        """Test multiple reads return the same object."""
        import threading
        import time

        from telepy import _telepysys

        def worker():
            test_obj = [1, 2, 3]  # noqa: F841
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        # Read the same variable multiple times
        result1 = _telepysys.vm_read(worker_thread.ident, "test_obj")
        result2 = _telepysys.vm_read(worker_thread.ident, "test_obj")
        result3 = _telepysys.vm_read(worker_thread.ident, "test_obj")

        # All should be the same object
        self.assertIs(result1, result2)
        self.assertIs(result2, result3)

        worker_thread.join()

    def test_vm_read_with_level(self):
        """Test reading from different frame levels."""
        import threading
        import time

        from telepy import _telepysys

        def inner_function():
            inner_var = "inner_value"  # noqa: F841
            time.sleep(1)

        def outer_function():
            outer_var = "outer_value"  # noqa: F841
            inner_function()

        worker_thread = threading.Thread(target=outer_function)
        worker_thread.start()
        time.sleep(0.3)

        # Read from top frame (level=0, inside inner_function)
        result = _telepysys.vm_read(worker_thread.ident, "inner_var", 0)
        self.assertEqual(result, "inner_value")

        # Read from previous frame (level=1, inside outer_function)
        result = _telepysys.vm_read(worker_thread.ident, "outer_var", 1)
        self.assertEqual(result, "outer_value")

        # inner_var should not be accessible from level=1
        result = _telepysys.vm_read(worker_thread.ident, "inner_var", 1)
        self.assertIsNone(result)

        worker_thread.join()

    def test_vm_read_level_default(self):
        """Test that level defaults to 0 when not specified."""
        import threading
        import time

        from telepy import _telepysys

        def worker():
            test_var = "test_value"  # noqa: F841
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        # Call without level argument (should default to 0)
        result1 = _telepysys.vm_read(worker_thread.ident, "test_var")
        # Call with explicit level=0
        result2 = _telepysys.vm_read(worker_thread.ident, "test_var", 0)

        self.assertEqual(result1, result2)
        self.assertEqual(result1, "test_value")

        worker_thread.join()

    def test_vm_read_level_too_deep(self):
        """Test that reading from a level that's too deep returns None."""
        import threading
        import time

        from telepy import _telepysys

        def worker():
            local_var = "value"  # noqa: F841
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        # Try to read from a very deep level (should return None)
        result = _telepysys.vm_read(worker_thread.ident, "local_var", 100)
        self.assertIsNone(result)

        worker_thread.join()

    def test_vm_read_level_validation(self):
        """Test level parameter validation."""
        from telepy import _telepysys

        # Test with negative level
        with self.assertRaises(ValueError):
            _telepysys.vm_read(123, "var", -1)

        # Test with non-integer level
        with self.assertRaises(TypeError):
            _telepysys.vm_read(123, "var", "not_an_int")

    def test_vm_read_parameter_validation(self):
        """Test parameter validation."""
        from telepy import _telepysys

        # Test with wrong number of arguments
        with self.assertRaises(TypeError):
            _telepysys.vm_read(123)  # Missing name argument

        with self.assertRaises(TypeError):
            _telepysys.vm_read(123, "var", 0, "extra")  # Too many arguments

        # Test with wrong types
        with self.assertRaises(TypeError):
            _telepysys.vm_read("not_an_int", "var")  # tid must be int

        with self.assertRaises(TypeError):
            _telepysys.vm_read(123, 456)  # name must be string


@unittest.skipIf(sys.version_info >= (3, 13), "vm_write not supported on Python 3.13+")
class TestVMWrite(TestBase):
    """Test cases for vm_write function.

    Note: vm_write only supports modifying GLOBAL variables, not local variables.
    This is due to Python's internal design where f_locals is a snapshot dict.
    """

    def test_vm_write_local_variable_not_supported(self):
        """Test that writing local variable returns False (not supported)."""
        import threading
        import time

        from telepy import _telepysys

        def worker():
            local_var = "initial_value"  # noqa: F841
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        # Try to write to a local variable (should fail)
        success = _telepysys.vm_write(worker_thread.ident, "local_var", "updated_value")
        self.assertFalse(success)  # Local variables cannot be modified

        # Verify the local was not modified
        result = _telepysys.vm_read(worker_thread.ident, "local_var")
        self.assertEqual(result, "initial_value")

        worker_thread.join()

    def test_vm_write_global_variable(self):
        """Test writing global variable in a worker thread."""
        import threading
        import time

        from telepy import _telepysys

        # Create a unique global variable for this test
        globals()["test_vm_write_global_var"] = "initial_global"

        def worker():
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        # Write to the global variable
        success = _telepysys.vm_write(
            worker_thread.ident, "test_vm_write_global_var", "updated_global"
        )
        self.assertTrue(success)

        # Verify the write was successful
        result = _telepysys.vm_read(worker_thread.ident, "test_vm_write_global_var")
        self.assertEqual(result, "updated_global")

        worker_thread.join()

        # Cleanup
        del globals()["test_vm_write_global_var"]

    def test_vm_write_nonexistent_variable(self):
        """Test writing to nonexistent variable returns False."""
        import threading
        import time

        from telepy import _telepysys

        def worker():
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        # Try to write to a variable that doesn't exist
        success = _telepysys.vm_write(
            worker_thread.ident, "nonexistent_global_var", "some_value"
        )
        self.assertFalse(success)

        # Verify the nonexistent variable still doesn't exist
        result = _telepysys.vm_read(worker_thread.ident, "nonexistent_global_var")
        self.assertIsNone(result)

        worker_thread.join()

    def test_vm_write_nonexistent_thread(self):
        """Test writing to nonexistent thread returns False."""
        from telepy import _telepysys

        # Use a thread ID that definitely doesn't exist
        nonexistent_tid = 999999999
        success = _telepysys.vm_write(nonexistent_tid, "some_var", "some_value")
        self.assertFalse(success)

    def test_vm_write_various_types(self):
        """Test writing various Python types to global variables."""
        import threading
        import time

        from telepy import _telepysys

        # Create global variables for testing
        globals()["test_int_var"] = 0
        globals()["test_str_var"] = ""
        globals()["test_list_var"] = []
        globals()["test_dict_var"] = {}
        globals()["test_none_var"] = None

        def worker():
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        # Test int
        success = _telepysys.vm_write(worker_thread.ident, "test_int_var", 42)
        self.assertTrue(success)
        result = _telepysys.vm_read(worker_thread.ident, "test_int_var")
        self.assertEqual(result, 42)

        # Test string
        success = _telepysys.vm_write(worker_thread.ident, "test_str_var", "test string")
        self.assertTrue(success)
        result = _telepysys.vm_read(worker_thread.ident, "test_str_var")
        self.assertEqual(result, "test string")

        # Test list
        success = _telepysys.vm_write(worker_thread.ident, "test_list_var", [1, 2, 3])
        self.assertTrue(success)
        result = _telepysys.vm_read(worker_thread.ident, "test_list_var")
        self.assertEqual(result, [1, 2, 3])

        # Test dict
        success = _telepysys.vm_write(
            worker_thread.ident, "test_dict_var", {"key": "value"}
        )
        self.assertTrue(success)
        result = _telepysys.vm_read(worker_thread.ident, "test_dict_var")
        self.assertEqual(result, {"key": "value"})

        # Test None
        success = _telepysys.vm_write(worker_thread.ident, "test_none_var", None)
        self.assertTrue(success)
        result = _telepysys.vm_read(worker_thread.ident, "test_none_var")
        self.assertIsNone(result)

        worker_thread.join()

        # Cleanup
        del globals()["test_int_var"]
        del globals()["test_str_var"]
        del globals()["test_list_var"]
        del globals()["test_dict_var"]
        del globals()["test_none_var"]

    def test_vm_write_multiple_updates(self):
        """Test multiple writes to the same global variable."""
        import threading
        import time

        from telepy import _telepysys

        # Create a global variable
        globals()["test_counter_var"] = 0

        def worker():
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        # Write multiple times
        for i in range(1, 6):
            success = _telepysys.vm_write(worker_thread.ident, "test_counter_var", i * 10)
            self.assertTrue(success)
            result = _telepysys.vm_read(worker_thread.ident, "test_counter_var")
            self.assertEqual(result, i * 10)

        worker_thread.join()

        # Cleanup
        del globals()["test_counter_var"]

    def test_vm_write_global_when_local_shadows(self):
        """Test that globals can be modified even when locals shadow them."""
        import threading
        import time

        from telepy import _telepysys

        # Create a global variable
        globals()["test_shadowed_var"] = "global_value"

        def worker():
            test_shadowed_var = "local_value"  # noqa: F841
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        # Write to the global (will succeed - writes to f_globals, not f_locals)
        success = _telepysys.vm_write(
            worker_thread.ident, "test_shadowed_var", "updated_value"
        )
        self.assertTrue(success)  # Should succeed - writes to globals

        # vm_read will return the local value (locals take priority in read)
        result = _telepysys.vm_read(worker_thread.ident, "test_shadowed_var")
        self.assertEqual(result, "local_value")

        # But the global was actually updated
        self.assertEqual(globals()["test_shadowed_var"], "updated_value")

        worker_thread.join()

        # Cleanup
        del globals()["test_shadowed_var"]

    def test_vm_write_parameter_validation(self):
        """Test parameter validation."""
        from telepy import _telepysys

        # Test with wrong number of arguments
        with self.assertRaises(TypeError):
            _telepysys.vm_write(123, "var")  # Missing value argument

        with self.assertRaises(TypeError):
            _telepysys.vm_write(123, "var", "value", "extra")  # Too many arguments

        # Test with wrong types
        with self.assertRaises(TypeError):
            _telepysys.vm_write("not_an_int", "var", "value")  # tid must be int

        with self.assertRaises(TypeError):
            _telepysys.vm_write(123, 456, "value")  # name must be string

    def test_vm_write_read_roundtrip(self):
        """Test write followed by read to verify data integrity for globals."""
        import threading
        import time

        from telepy import _telepysys

        # Create a global variable
        globals()["test_roundtrip_data"] = None

        def worker():
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        # Test various data structures
        test_cases = [
            42,
            "hello world",
            [1, 2, 3, 4, 5],
            {"a": 1, "b": 2, "c": 3},
            (1, 2, 3),
            {1, 2, 3, 4},
            True,
            False,
            None,
        ]

        for test_value in test_cases:
            success = _telepysys.vm_write(
                worker_thread.ident, "test_roundtrip_data", test_value
            )
            self.assertTrue(success, f"Failed to write {test_value}")
            result = _telepysys.vm_read(worker_thread.ident, "test_roundtrip_data")
            self.assertEqual(result, test_value, f"Roundtrip failed for {test_value}")

        worker_thread.join()

        # Cleanup
        del globals()["test_roundtrip_data"]


@unittest.skipIf(
    sys.version_info >= (3, 13), "top_namespace not supported on Python 3.13+"
)
class TestTopNamespace(TestBase):
    """Test cases for top_namespace function."""

    def test_top_namespace_get_locals(self):
        """Test getting locals from a worker thread."""
        import sys
        import threading
        import time

        from telepy import _telepysys

        def worker():
            local_var1 = "test"  # noqa: F841
            local_var2 = 42  # noqa: F841
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        # Get locals (flag=0)
        locals_dict = _telepysys.top_namespace(worker_thread.ident, 0)
        self.assertIsNotNone(locals_dict)
        if sys.version < "3.13":
            self.assertIsInstance(locals_dict, dict)
        self.assertIn("local_var1", locals_dict)
        self.assertEqual(locals_dict["local_var1"], "test")
        self.assertIn("local_var2", locals_dict)
        self.assertEqual(locals_dict["local_var2"], 42)

        worker_thread.join()

    def test_top_namespace_get_globals(self):
        """Test getting globals from a worker thread."""
        import threading
        import time

        from telepy import _telepysys

        def worker():
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        # Get globals (flag=1)
        globals_dict = _telepysys.top_namespace(worker_thread.ident, 1)
        self.assertIsNotNone(globals_dict)
        self.assertIsInstance(globals_dict, dict)
        # Should have standard globals like __name__, __builtins__, etc.
        self.assertIn("__name__", globals_dict)
        self.assertIn("__builtins__", globals_dict)

        worker_thread.join()

    def test_top_namespace_nonexistent_thread(self):
        """Test with nonexistent thread returns None."""
        from telepy import _telepysys

        nonexistent_tid = 999999999
        result = _telepysys.top_namespace(nonexistent_tid, 0)
        self.assertIsNone(result)

        result = _telepysys.top_namespace(nonexistent_tid, 1)
        self.assertIsNone(result)

    def test_top_namespace_parameter_validation(self):
        """Test parameter validation."""
        from telepy import _telepysys

        # Test with wrong number of arguments
        with self.assertRaises(TypeError):
            _telepysys.top_namespace(123)  # Missing flag argument

        with self.assertRaises(TypeError):
            _telepysys.top_namespace(123, 0, "extra")  # Too many arguments

        # Test with wrong types
        with self.assertRaises(TypeError):
            _telepysys.top_namespace("not_an_int", 0)  # tid must be int

        with self.assertRaises(TypeError):
            _telepysys.top_namespace(123, "not_an_int")  # flag must be int

        # Test with invalid flag value
        with self.assertRaises(ValueError):
            _telepysys.top_namespace(123, 3)  # flag must be 0, 1, or 2

        with self.assertRaises(ValueError):
            _telepysys.top_namespace(123, -1)  # flag must be 0, 1, or 2

    def test_top_namespace_locals_vs_globals(self):
        """Test that locals and globals are different."""
        import threading
        import time

        from telepy import _telepysys

        def worker():
            local_only = "local"  # noqa: F841
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        locals_dict = _telepysys.top_namespace(worker_thread.ident, 0)
        globals_dict = _telepysys.top_namespace(worker_thread.ident, 1)

        # Local variable should be in locals but not in globals
        self.assertIn("local_only", locals_dict)
        self.assertNotIn("local_only", globals_dict)

        # Globals should have __name__ but locals shouldn't
        self.assertNotIn("__name__", locals_dict)
        self.assertIn("__name__", globals_dict)

        worker_thread.join()

    def test_top_namespace_modify_globals(self):
        """Test that modifying returned globals affects the thread."""
        import threading
        import time

        from telepy import _telepysys

        # Create a global variable
        globals()["test_top_namespace_var"] = "initial"

        def worker():
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        # Get globals and modify it
        globals_dict = _telepysys.top_namespace(worker_thread.ident, 1)
        self.assertEqual(globals_dict["test_top_namespace_var"], "initial")

        # Modify through the returned dict
        globals_dict["test_top_namespace_var"] = "modified"

        # Verify the modification took effect
        result = _telepysys.vm_read(worker_thread.ident, "test_top_namespace_var")
        self.assertEqual(result, "modified")

        worker_thread.join()

        # Cleanup
        del globals()["test_top_namespace_var"]

    def test_top_namespace_with_various_local_types(self):
        """Test with various types of local variables."""
        import threading
        import time

        from telepy import _telepysys

        def worker():
            int_var = 42  # noqa: F841
            str_var = "test"  # noqa: F841
            list_var = [1, 2, 3]  # noqa: F841
            dict_var = {"key": "value"}  # noqa: F841
            none_var = None  # noqa: F841
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        locals_dict = _telepysys.top_namespace(worker_thread.ident, 0)

        self.assertEqual(locals_dict["int_var"], 42)
        self.assertEqual(locals_dict["str_var"], "test")
        self.assertEqual(locals_dict["list_var"], [1, 2, 3])
        self.assertEqual(locals_dict["dict_var"], {"key": "value"})
        self.assertIsNone(locals_dict["none_var"])

        worker_thread.join()

    def test_top_namespace_get_both(self):
        """Test getting both locals and globals from a worker thread (flag=2)."""
        import sys
        import threading
        import time

        from telepy import _telepysys

        # Create a global variable for this test
        globals()["test_both_global_var"] = "global_value"

        def worker():
            local_var1 = "local_test"  # noqa: F841
            local_var2 = 99  # noqa: F841
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        # Get both locals and globals (flag=2)
        result = _telepysys.top_namespace(worker_thread.ident, 2)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

        locals_dict, globals_dict = result

        if sys.version < "3.13":
            self.assertIsInstance(locals_dict, dict)
        self.assertIn("local_var1", locals_dict)
        self.assertEqual(locals_dict["local_var1"], "local_test")
        self.assertIn("local_var2", locals_dict)
        self.assertEqual(locals_dict["local_var2"], 99)

        # Verify globals
        self.assertIsInstance(globals_dict, dict)
        self.assertIn("__name__", globals_dict)
        self.assertIn("test_both_global_var", globals_dict)
        self.assertEqual(globals_dict["test_both_global_var"], "global_value")

        worker_thread.join()

        # Cleanup
        del globals()["test_both_global_var"]

    def test_top_namespace_flag2_nonexistent_thread(self):
        """Test flag=2 with nonexistent thread returns None."""
        from telepy import _telepysys

        nonexistent_tid = 999999999
        result = _telepysys.top_namespace(nonexistent_tid, 2)
        self.assertIsNone(result)

    def test_top_namespace_flag2_locals_vs_globals(self):
        """Test that flag=2 returns distinct locals and globals."""
        import threading
        import time

        from telepy import _telepysys

        def worker():
            local_only = "local_value"  # noqa: F841
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        result = _telepysys.top_namespace(worker_thread.ident, 2)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, tuple)

        locals_dict, globals_dict = result

        # Local variable should be in locals but not in globals
        self.assertIn("local_only", locals_dict)
        self.assertNotIn("local_only", globals_dict)

        # Globals should have __name__ but locals shouldn't
        self.assertNotIn("__name__", locals_dict)
        self.assertIn("__name__", globals_dict)

        worker_thread.join()

    def test_top_namespace_flag2_modify_globals(self):
        """Test that modifying globals from flag=2 result affects the thread."""
        import threading
        import time

        from telepy import _telepysys

        # Create a global variable
        globals()["test_flag2_modify_var"] = "initial"

        def worker():
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        # Get both locals and globals
        result = _telepysys.top_namespace(worker_thread.ident, 2)
        _locals_dict, globals_dict = result

        self.assertEqual(globals_dict["test_flag2_modify_var"], "initial")

        # Modify through the returned globals dict
        globals_dict["test_flag2_modify_var"] = "modified"

        # Verify the modification took effect
        read_result = _telepysys.vm_read(worker_thread.ident, "test_flag2_modify_var")
        self.assertEqual(read_result, "modified")

        worker_thread.join()

        # Cleanup
        del globals()["test_flag2_modify_var"]

    def test_top_namespace_flag2_all_flags_consistency(self):
        """Test that flag=2 returns the same data as flag=0 and flag=1 separately."""
        import threading
        import time

        from telepy import _telepysys

        # Create a global variable
        globals()["test_consistency_var"] = "consistent"

        def worker():
            local_var = "local_data"  # noqa: F841
            time.sleep(1)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()
        time.sleep(0.3)

        # Get locals only (flag=0)
        locals_only = _telepysys.top_namespace(worker_thread.ident, 0)

        # Get globals only (flag=1)
        globals_only = _telepysys.top_namespace(worker_thread.ident, 1)

        # Get both (flag=2)
        both = _telepysys.top_namespace(worker_thread.ident, 2)
        locals_from_both, globals_from_both = both

        # Verify consistency
        self.assertEqual(locals_only, locals_from_both)
        self.assertEqual(globals_only, globals_from_both)

        worker_thread.join()

        # Cleanup
        del globals()["test_consistency_var"]
