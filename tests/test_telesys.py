import os

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
        self.assertEqual(tids, set(call_stack.keys()))

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
                self.assertIn("Fib.fib", value)
            break
        t.join()
        self.assertEqual(tids, set(call_stack.keys()))

        tids.clear()
        t = threading.Thread(target=Fib.bar, args=(30,))
        t.start()
        tids.add(t.ident)
        tids.add(threading.get_ident())
        call_stack = telepy.current_stacks()
        for tid, value in telepy.join_current_stacks(call_stack).items():
            if tid != threading.get_ident():
                self.assertIn("Fib.bar", value)
            break
        t.join()
        self.assertEqual(tids, set(call_stack.keys()))


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
        result = sampler.dumps()[:-1]  # eliminate newline
        self.assertIn("fib", result)
        self.assertIn("MainThread", result)
        self.assertIn("Thread-", result)
        if "coverage" not in sys.modules:
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
