# telepysys.pyi

"""
An utility module for telepysys
"""

from collections.abc import Callable
from threading import Thread
from types import FrameType

__version__: str

def current_frames() -> dict[int, FrameType]: ...
def unix_micro_time() -> int: ...
def register_main(callable: Callable, /, *args, **kwargs) -> None:
    """
    register a callable object to be called when the main thread is available
    Raises:
        RuntimeError: if the callable is not callable or failed to register
    """
    ...

def sched_yield() -> None:
    """
    Yield the current thread to other threads.
    Relax to call me, we handle the GIL properly.
    """

def vm_read(tid: int, name: str) -> object | None:
    """
    Read a variable from the specified thread's frame.

    Args:
        tid: Thread ID (thread identifier)
        name: Variable name to read

    Returns:
        The value of the variable if found in the thread's locals or globals,
        None otherwise (including when the thread doesn't exist)

    Example:
        >>> import threading
        >>> from telepy import _telepysys
        >>> def worker():
        ...     local_var = "Hello"
        ...     time.sleep(2)
        >>> thread = threading.Thread(target=worker)
        >>> thread.start()
        >>> value = _telepysys.vm_read(thread.ident, "local_var")
        >>> print(value)  # "Hello"
    """
    ...

def vm_write(tid: int, name: str, value: object) -> bool:
    """
    Write a variable to the specified thread's frame.

    Args:
        tid: Thread ID (thread identifier)
        name: Variable name to write
        value: Value to assign to the variable

    Returns:
        True if the variable was successfully updated,
        False if the variable was not found or the thread doesn't exist

    Note:
        - This function can only UPDATE existing GLOBAL variables reliably
        - Local variables in frames cannot be modified due to Python's design
        - Frame locals are stored in fast locals (C-level) which are read-only
        - Only variables in f_globals can be reliably updated

    Limitations:
        - Modifying local variables is not supported (f_locals is a snapshot)
        - Only works for global variables in the thread's f_globals

    Example:
        >>> import threading
        >>> from telepy import _telepysys
        >>> global_counter = 0
        >>> def worker():
        ...     global global_counter
        ...     time.sleep(5)
        >>> thread = threading.Thread(target=worker)
        >>> thread.start()
        >>> success = _telepysys.vm_write(thread.ident, "global_counter", 42)
        >>> print(success)  # True
        >>> value = _telepysys.vm_read(thread.ident, "global_counter")
        >>> print(value)  # 42
    """
    ...

def top_namespace(tid: int, flag: int) -> dict[str, object] | None:
    """
    Get the top frame's namespace (locals or globals) for a thread.

    Args:
        tid: Thread ID (thread identifier)
        flag: 0 for locals, 1 for globals

    Returns:
        The namespace dictionary (f_locals or f_globals), or None if the
        thread doesn't exist

    Note:
        - flag=0 returns f_locals (a snapshot of local variables)
        - flag=1 returns f_globals (the actual global namespace)
        - The returned dict is the actual namespace object, modifications
          to f_globals will affect the thread's global variables
        - Modifications to f_locals won't affect actual local variables

    Example:
        >>> import threading
        >>> from telepy import _telepysys
        >>> def worker():
        ...     local_var = "test"
        ...     global_var = "global"
        ...     time.sleep(5)
        >>> thread = threading.Thread(target=worker)
        >>> thread.start()
        >>> locals_dict = _telepysys.top_namespace(thread.ident, 0)
        >>> globals_dict = _telepysys.top_namespace(thread.ident, 1)
        >>> print(locals_dict.get('local_var'))  # "test"
        >>> print(globals_dict.get('__name__'))  # "__main__"
    """
    ...

class Sampler:
    def __init__(self) -> None:
        # sampling interval in microseconds
        self.sampling_interval = 10_000  # 10ms
        self.sampling_thread: None | Thread
        self.sampler_life_time: int
        self.acc_sampling_time: int
        self.sampling_times: int
        self.debug: bool = False
        self.ignore_frozen: bool = False
        self.ignore_self: bool = False
        self.tree_mode: bool = False
        self.focus_mode: bool = False
        self.regex_patterns: list | None = None

    def start(self) -> None:
        """start the sampler"""
        ...

    def stop(self) -> None:
        """stop the sampler and join the sampling thread"""
        ...

    def clear(self) -> None:
        """clear the sampler"""
        ...

    def enabled(self) -> bool:
        """check if the sampler is enabled"""
        ...

    def join_sampling_thread(self) -> None:
        """join the sampling thread, you should not call
        this method unless you know what you are doing
        """
        ...

    def save(self, path: str) -> None:
        """save the sampled frames to a file"""
        ...

    def dumps(self) -> str:
        """dump the sampled frames to a string"""
        ...

class AsyncSampler:
    def __init__(self) -> None:
        # sampling interval in microseconds
        self.sampling_interval = 10_000  # 10ms
        self.sampler_life_time: int
        self.acc_sampling_time: int
        self.sampling_times: int
        self.debug: bool = False
        self.ignore_frozen: bool = False
        self.sampling_tid: int
        self.start_time: int
        self.end_time: int
        self.ignore_self: bool = False
        self.tree_mode: bool = False
        self.focus_mode: bool = False
        self.regex_patterns: list | None = None

    def start(self) -> None:
        """start the sampler"""
        ...

    def stop(self) -> None:
        """stop the sampler"""
        ...

    def clear(self) -> None:
        """clear the sampler, using a async thread to release the resources"""
        ...

    def enabled(self) -> bool:
        """check if the sampler is enabled"""
        ...

    def save(self, path: str) -> None:
        """save the sampled frames to a file"""
        ...

    def dumps(self) -> str:
        """
        dump the sampled frames to a string
        a stack trace per line, last line is empty.
        """
        ...

    def _async_routine(self, sig_num: int, frame: FrameType | None) -> None:
        """async routine"""
        ...
