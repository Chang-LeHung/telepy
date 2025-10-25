"""
Type stubs for telepy._gc_stats C extension module.

This module provides high-performance GC statistics collection
implemented in C for better performance.
"""

from typing import Any, TypedDict

class StatsResult(TypedDict):
    """Result dictionary returned by calculate_stats.

    Attributes:
        type_counter: Dictionary mapping type names to object counts
        type_memory: Dictionary mapping type names to total memory
            usage (if calculate_memory=True)
        total_objects: Total number of objects analyzed
        total_memory: Total memory usage in bytes
            (if calculate_memory=True)
    """

    type_counter: dict[str, int]
    type_memory: dict[str, int] | None
    total_objects: int
    total_memory: int

def calculate_stats(
    objects: list[Any],
    calculate_memory: bool = False,
) -> StatsResult:
    """Calculate object statistics efficiently using C implementation.

    This function analyzes a list of Python objects and returns statistics
    about their types and optionally their memory usage. It provides
    significantly better performance than pure Python implementations.

    Args:
        objects: List of Python objects to analyze. Typically obtained
            from gc.get_objects() or gc.get_objects(generation).
        calculate_memory: If True, calculates memory usage for each object
            using sys.getsizeof(). If False, only counts objects by type.
            Default is False.

    Returns:
        A dictionary containing:
        - type_counter: Dict mapping type names (str) to counts (int)
        - type_memory: Dict mapping type names (str) to total memory
          (int) in bytes, or None if calculate_memory=False
        - total_objects: Total number of objects analyzed (int)
        - total_memory: Total memory usage in bytes (int), or 0 if
          calculate_memory=False

    Example:
        >>> import gc
        >>> from telepy import _gc_stats
        >>>
        >>> # Get all objects
        >>> objects = gc.get_objects()
        >>>
        >>> # Calculate statistics without memory
        >>> result = _gc_stats.calculate_stats(objects, False)
        >>> print(f"Total objects: {result['total_objects']}")
        >>> print(f"dict count: {result['type_counter']['dict']}")
        >>>
        >>> # Calculate statistics with memory
        >>> result = _gc_stats.calculate_stats(objects, True)
        >>> print(f"Total memory: {result['total_memory']} bytes")
        >>> print(f"dict memory: {result['type_memory']['dict']} bytes")

    Performance:
        This C implementation is approximately 1.5-2x faster than the
        equivalent pure Python implementation, especially when analyzing
        large numbers of objects (>10,000).

    Note:
        - The function iterates through all objects twice if
          calculate_memory=True: once to count types and once to
          calculate memory.
        - Memory calculation uses sys.getsizeof() which may not include
          memory used by nested objects.
        - Type names are fully qualified (e.g., 'builtins.dict',
          'collections.OrderedDict').
    """
    ...

__version__: str
"""Version of the _gc_stats module."""
