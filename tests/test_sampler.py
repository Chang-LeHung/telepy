import threading

import telepy

from .base import TestBase  # type: ignore


class TestAsyncSampler(TestBase):
    def test_sampler(self):
        self.assertEqual(threading.current_thread(), threading.main_thread())

        def fib(n: int) -> int:
            if n < 2:
                return n
            return fib(n - 1) + fib(n - 2)

        async_sampler = telepy.TelepySysAsyncSampler(
            sampling_interval=10,
            ignore_frozen=True,
        )
        async_sampler.start()
        t = threading.Thread(target=fib, args=(38,))
        t.start()
        t.join()
        async_sampler.stop()
        async_sampler.save("test_async_sampler.stack")
        print(f"{async_sampler.sampling_times = }")

    def test_worker_sampler(self):
        import threading

        from telepy import TelepySysAsyncWorkerSampler

        def fib(n: int) -> int:
            if n < 2:
                return n
            return fib(n - 1) + fib(n - 2)

        finished = False

        def profiling_in_non_main_thread():
            nonlocal finished

            sampler = TelepySysAsyncWorkerSampler(sampling_interval=100)

            adjusted = sampler.adjust()
            self.assertTrue(adjusted)
            sampler.start()
            t = threading.Thread(target=fib, args=(20,))
            t.start()
            t.join()
            sampler.stop()
            content = sampler.dumps()
            self.assertGreater(len(content), 0)
            self.assertIn("MainThread", content)
            self.assertIn("fib", content)
            sampler.save("test_worker_sampler.stack")
            self.assertLessEqual(sampler.sampling_time_rate, 1)
            finished = True

        t = threading.Thread(target=profiling_in_non_main_thread)
        t.start()
        # using busy wait to avoid deadlock
        while not finished:
            pass
        # do not join the thread before, which will cause the deadlock
        t.join()

    def test_switch_interval(self):
        import sys

        async_sampler = telepy.TelepySysAsyncSampler()
        async_sampler.setswitchinterval(0.001)
        self.assertEqual(sys.getswitchinterval(), async_sampler.getswitchinterval())

        async_sampler = telepy.TelepySysAsyncSampler(sampling_interval=1000000)
        async_sampler.adjust()
        self.assertEqual(async_sampler.getswitchinterval(), 0.001)

    def test_sampler_runtime_error(self):
        async_sampler = telepy.TelepySysAsyncSampler()
        async_sampler.start()
        try:
            async_sampler.start()
        except RuntimeError:
            pass
        else:
            self.fail("RuntimeError not raised")
        async_sampler.stop()

        def spawn_sampler():
            async_sampler = telepy.TelepySysAsyncSampler()

            try:
                async_sampler.start()
            except RuntimeError:
                pass
            else:
                self.fail("RuntimeError not raised")

        t = threading.Thread(target=spawn_sampler)
        t.start()
        t.join()
        print(async_sampler.sampling_time_rate)

    def test_async_sampler_not_in_main(self):
        import threading

        def bar():
            async_sampler = telepy.TelepySysAsyncSampler()
            try:
                async_sampler.start()
            except RuntimeError:
                pass
            else:
                self.fail("RuntimeError not raised")

        t = threading.Thread(target=bar)
        t.start()
        t.join()
