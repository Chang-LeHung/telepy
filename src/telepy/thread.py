import functools
import threading
from collections.abc import Callable

from . import _telepysys


class PyMainTrampoline:
    """
    This class is used to call a callable object in main thread.
    """

    def __init__(self, func: Callable) -> None:
        self.func: Callable = func
        self.event = threading.Event()

    def __call__(self, *args, **kwds) -> None:
        """
        Call the callable in main thread.
        Raises:
            RuntimeError: if func is not callable or failed to register.
        """
        if not callable(self.func):
            raise RuntimeError(f"{self.func} is not callable")  # pragma: no cover
        if threading.current_thread() is threading.main_thread():
            self.func(*args, **kwds)
            return
        _telepysys.register_main(self.main_thread, *args, **kwds)
        self.event.wait()  # wait for the main thread to finish

    def main_thread(self, *args, **kwds):
        """Run in the main thread"""
        self.func(*args, **kwds)
        self.event.set()  # signal the other thread in main thread


def in_main_thread(func: Callable) -> Callable:
    """
    Decorator to run a function in the main thread.
    Be careful of the race condition and deadlock.
    If the main thread is blocked, the func will be blocked as well.
    """

    if not callable(func):
        raise RuntimeError(f"{func} is not callable")

    @functools.wraps(func)
    def _decorator(*args, **kwargs):
        return PyMainTrampoline(func)(*args, **kwargs)

    return _decorator
