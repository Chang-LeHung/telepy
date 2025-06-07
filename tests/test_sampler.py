import threading
import unittest

import telepy


class TestAsyncSampler(unittest.TestCase):
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
        print(async_sampler.dumps())
        print(f"{async_sampler.sampling_times = }")


def fib(n: int) -> int:
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


async_sampler = telepy.TelepySysAsyncSampler(
    sampling_interval=5000,
    ignore_frozen=True,
)
async_sampler.start()
t = threading.Thread(target=fib, args=(38,))
t.start()
t.join()
async_sampler.stop()
print(async_sampler.dumps())
print(f"{async_sampler.sampling_times = }")
