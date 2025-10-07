"""
Garbage Collection Analyzer Module

Provides comprehensive GC analysis functionality for TelePy profiler.
"""

from __future__ import annotations

import gc
from collections import Counter
from typing import Any


class GCAnalyzer:
    """Analyzer for Python garbage collection diagnostics."""

    def __init__(self) -> None:
        """Initialize the GC analyzer."""
        self._last_collection_count = [0, 0, 0]
        self._collection_history: list[tuple[int, int, int]] = []

    def get_status(self) -> dict[str, Any]:
        """Get current GC status and configuration.

        Returns:
            dict: Dictionary containing GC enabled status, counts, thresholds,
                  and statistics for all generations.

        Example:
            >>> analyzer = GCAnalyzer()
            >>> status = analyzer.get_status()
            >>> print(f"GC Enabled: {status['enabled']}")
            >>> print(f"Gen0 objects: {status['count'][0]}")
        """
        return {
            "enabled": gc.isenabled(),
            "count": gc.get_count(),
            "threshold": gc.get_threshold(),
            "stats": gc.get_stats(),
            "freeze_count": gc.get_freeze_count(),
            "garbage_count": len(gc.garbage),
        }

    def get_stats_summary(self) -> str:
        """Get formatted GC statistics summary.

        Returns:
            str: Human-readable multi-line string containing:
                - GC enabled/disabled status
                - Current object counts per generation
                - Collection thresholds
                - Collection statistics (collections, collected, uncollectable)
                - Permanent generation count
                - Garbage list size

        Example output:
            GC Status: Enabled
            Current Counts: Gen0=123, Gen1=45, Gen2=6
            Thresholds: Gen0=700, Gen1=10, Gen2=10
            ...
        """
        info = self.get_status()
        lines = []
        lines.append(f"GC Status: {'Enabled' if info['enabled'] else 'Disabled'}")
        lines.append(
            f"Current Counts: Gen0={info['count'][0]}, "
            f"Gen1={info['count'][1]}, Gen2={info['count'][2]}"
        )
        lines.append(
            f"Thresholds: Gen0={info['threshold'][0]}, "
            f"Gen1={info['threshold'][1]}, Gen2={info['threshold'][2]}"
        )
        lines.append("\nPer-Generation Statistics:")

        for i, stat in enumerate(info["stats"]):
            lines.append(f"  Generation {i}:")
            lines.append(f"    Collections: {stat['collections']}")
            lines.append(f"    Collected: {stat['collected']}")
            lines.append(f"    Uncollectable: {stat['uncollectable']}")

        lines.append(f"\nPermanent Generation: {info['freeze_count']} objects")
        lines.append(f"Garbage List: {info['garbage_count']} objects")

        return "\n".join(lines)

    def get_object_stats(
        self,
        generation: int | None = None,
        limit: int = 20,
        calculate_memory: bool = False,
        sort_by: str = "count",
    ) -> list[dict[str, Any]]:
        """Get statistics about tracked objects by type.

        Args:
            generation: Which generation to analyze (0, 1, 2, or None for all).
            limit: Maximum number of object types to return.
            calculate_memory: If True, calculate memory usage for each type.
            sort_by: Sort method - 'count' (default), 'memory', or 'avg_memory'.
                    Note: 'memory' and 'avg_memory' sorts require calculate_memory=True.

        Returns:
            list[dict]: List of dictionaries with type_name, count, and
                        percentage, sorted by specified key (descending).
                        If calculate_memory is True, also includes 'memory',
                        'avg_memory', and 'memory_percentage' fields.

        Example:
            >>> analyzer = GCAnalyzer()
            >>> stats = analyzer.get_object_stats(limit=5)
            >>> for stat in stats:
            ...     msg = f"{stat['type_name']}: {stat['count']}"
            ...     print(f"{msg} ({stat['percentage']:.1f}%)")
            dict: 1234 (45.2%)
            list: 890 (32.6%)
            ...
        """
        import sys

        try:
            objects = gc.get_objects(generation)
        except TypeError:
            # Python < 3.8 doesn't support generation parameter
            objects = gc.get_objects()

        type_counter: Counter[str] = Counter()
        type_memory: dict[str, int] = {}

        if calculate_memory:
            for obj in objects:
                type_name = type(obj).__name__
                type_counter[type_name] += 1
                try:
                    size = sys.getsizeof(obj)
                    type_memory[type_name] = type_memory.get(type_name, 0) + size
                except (TypeError, AttributeError):
                    # Some objects don't support getsizeof
                    pass
        else:
            for obj in objects:
                type_counter[type(obj).__name__] += 1

        total = sum(type_counter.values())
        total_memory = sum(type_memory.values()) if calculate_memory else 0

        # Build result list with all type information
        all_stats: list[dict[str, Any]] = []
        for type_name, count in type_counter.items():
            percentage = (count / total * 100) if total > 0 else 0
            stat_dict: dict[str, Any] = {
                "type_name": type_name,
                "count": count,
                "percentage": percentage,
            }

            if calculate_memory:
                memory = type_memory.get(type_name, 0)
                stat_dict["memory"] = memory
                stat_dict["avg_memory"] = memory / count if count > 0 else 0
                stat_dict["memory_percentage"] = (
                    (memory / total_memory * 100) if total_memory > 0 else 0
                )

            all_stats.append(stat_dict)

        # Sort by specified key
        if sort_by in ["memory", "avg_memory"]:
            if not calculate_memory:
                raise ValueError(
                    f"sort_by='{sort_by}' requires calculate_memory=True"
                )
            all_stats.sort(key=lambda x: x[sort_by], reverse=True)
        else:  # sort by count (default)
            all_stats.sort(key=lambda x: x["count"], reverse=True)

        # Return limited results
        return all_stats[:limit]

    def get_object_stats_formatted(
        self,
        generation: int | None = None,
        limit: int = 20,
        calculate_memory: bool = False,
        sort_by: str = "count",
    ) -> str:
        """Get formatted object statistics.

        Args:
            generation: Which generation to analyze (0, 1, 2, or None for all).
            limit: Maximum number of types to include in output.
            calculate_memory: If True, include memory usage in the output.
            sort_by: Sort method - 'count' (default), 'memory', or 'avg_memory'.

        Returns:
            str: Human-readable table of object types and counts.

        Example output:
            Object Statistics (Top 20):
            Generation: All
            Total Objects: 12345

            Type                Count      Percentage
            ─────────────────────────────────────────
            dict                1234       45.2%
            list                890        32.6%
            ...
        """
        stats = self.get_object_stats(generation, limit, calculate_memory, sort_by)
        total = sum(s["count"] for s in stats)

        lines = []
        sort_desc = f" (sorted by {sort_by})" if sort_by != "count" else ""
        lines.append(f"Object Statistics (Top {limit}{sort_desc}):")
        gen_str = f"Generation {generation}" if generation is not None else "All"
        lines.append(f"Generation: {gen_str}")
        lines.append(f"Total Objects: {total}")
        lines.append("")

        # 使用动态列宽以适应最长的类型名
        max_type_len = max((len(s["type_name"]) for s in stats), default=20)
        type_width = max(max_type_len + 2, 25)

        if calculate_memory:
            # 添加内存列
            header = (
                f"{'Type':<{type_width}} "
                f"{'Count':>10}   "
                f"{'Count %':>10}   "
                f"{'Memory':>12}   "
                f"{'Memory %':>10}   "
                f"{'Avg Memory':>12}"
            )
            lines.append(header)
            lines.append("─" * (type_width + 75))

            for stat in stats:
                memory_str = self._format_bytes(stat.get("memory", 0))
                avg_memory_str = self._format_bytes(stat.get("avg_memory", 0))
                memory_pct = stat.get("memory_percentage", 0)
                lines.append(
                    f"{stat['type_name']:<{type_width}} "
                    f"{stat['count']:>10}   "
                    f"{stat['percentage']:>9.1f}%   "
                    f"{memory_str:>12}   "
                    f"{memory_pct:>9.1f}%   "
                    f"{avg_memory_str:>12}"
                )
        else:
            lines.append(f"{'Type':<{type_width}} {'Count':>10}   {'Percentage':>10}")
            lines.append("─" * (type_width + 25))

            for stat in stats:
                lines.append(
                    f"{stat['type_name']:<{type_width}} "
                    f"{stat['count']:>10}   "
                    f"{stat['percentage']:>9.1f}%"
                )

        return "\n".join(lines)

    def _format_bytes(self, bytes_size: float) -> str:
        """Format bytes to human-readable format.

        Args:
            bytes_size: Size in bytes.

        Returns:
            str: Formatted size string (e.g., "1.5 KB", "2.3 MB").
        """
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} PB"

    def collect_garbage(self, generation: int = 2) -> dict[str, Any]:
        """Manually trigger garbage collection.

        Args:
            generation: Which generation to collect (0, 1, or 2).
                       Default is 2 (full collection).

        Returns:
            dict: Contains 'collected' (number of objects collected) and
                 'unreachable' (number of unreachable objects found).

        Example:
            >>> analyzer = GCAnalyzer()
            >>> result = analyzer.collect_garbage(generation=0)
            >>> print(f"Collected {result['collected']} objects")
        """
        counts_before = gc.get_count()
        unreachable = gc.collect(generation)
        counts_after = gc.get_count()

        return {
            "generation": generation,
            "unreachable": unreachable,
            "counts_before": counts_before,
            "counts_after": counts_after,
            "collected": counts_before[0] - counts_after[0],
        }

    def get_garbage_info(self) -> dict[str, Any]:
        """Get information about uncollectable objects.

        Returns:
            dict: Contains:
                - 'count': Number of objects in gc.garbage
                - 'types': Counter of object types in garbage
                - 'objects': List of garbage objects (limited to 100)

        Example:
            >>> analyzer = GCAnalyzer()
            >>> info = analyzer.get_garbage_info()
            >>> if info['count'] > 0:
            ...     print("Warning: Uncollectable objects detected!")
        """
        garbage_count = len(gc.garbage)
        type_counter: Counter[str] = Counter()

        for obj in gc.garbage:
            type_counter[type(obj).__name__] += 1

        return {
            "count": garbage_count,
            "types": dict(type_counter),
            "objects": [str(type(obj).__name__) for obj in gc.garbage[:100]],
        }

    def get_garbage_formatted(self) -> str:
        """Get formatted garbage information.

        Returns:
            str: Human-readable report of uncollectable objects.

        Example output:
            Garbage Collection Report:
            Total Uncollectable Objects: 5

            Objects by Type:
            dict: 3
            list: 2
        """
        info = self.get_garbage_info()
        lines = []
        lines.append("Garbage Collection Report:")
        lines.append(f"Total Uncollectable Objects: {info['count']}")

        if info["count"] > 0:
            lines.append("\nObjects by Type:")
            for type_name, count in sorted(
                info["types"].items(), key=lambda x: x[1], reverse=True
            ):
                lines.append(f"  {type_name}: {count}")
        else:
            lines.append("\n✓ No uncollectable objects found")

        return "\n".join(lines)

    def get_referrers_info(
        self, obj: Any, max_depth: int = 2, limit: int = 10
    ) -> dict[str, Any]:
        """Get information about objects referring to the given object.

        Args:
            obj: Object to analyze referrers for.
            max_depth: Maximum depth to traverse referrer chain.
            limit: Maximum number of referrers to return per level.

        Returns:
            dict: Contains referrer information with types and counts.

        Example:
            >>> import sys
            >>> analyzer = GCAnalyzer()
            >>> info = analyzer.get_referrers_info(sys.modules)
            >>> print(f"Found {info['direct_count']} direct referrers")
        """
        referrers = gc.get_referrers(obj)
        type_counter: Counter[str] = Counter()

        for ref in referrers[:limit]:
            type_counter[type(ref).__name__] += 1

        return {
            "direct_count": len(referrers),
            "types": dict(type_counter),
            "is_tracked": gc.is_tracked(obj),
        }

    def analyze_memory_leaks(self, threshold: int = 100) -> dict[str, Any]:
        """Analyze potential memory leaks by identifying large object collections.

        Args:
            threshold: Minimum count to consider as potential leak.

        Returns:
            dict: Contains suspicious object types that exceed threshold.

        Example:
            >>> analyzer = GCAnalyzer()
            >>> leaks = analyzer.analyze_memory_leaks(threshold=1000)
            >>> if leaks['suspicious_types']:
            ...     print("Potential memory leaks detected!")
        """
        stats = self.get_object_stats(limit=100)
        suspicious = [s for s in stats if s["count"] >= threshold]

        return {
            "threshold": threshold,
            "suspicious_types": suspicious,
            "total_suspicious_objects": sum(s["count"] for s in suspicious),
        }

    def monitor_collection_activity(self) -> dict[str, Any]:
        """Monitor GC collection activity since last check.

        Returns:
            dict: Contains:
                - 'current_counts': Current generation counts
                - 'delta': Change since last check
                - 'collections_occurred': Whether any collections happened

        Example:
            >>> analyzer = GCAnalyzer()
            >>> # ... run some code ...
            >>> activity = analyzer.monitor_collection_activity()
            >>> if activity['collections_occurred']:
            ...     print(f"Collections: {activity['delta']}")
        """
        current_counts = gc.get_count()
        stats = gc.get_stats()

        current_collections = [s["collections"] for s in stats]
        delta = [
            current_collections[i] - self._last_collection_count[i] for i in range(3)
        ]

        collections_occurred = any(d > 0 for d in delta)
        self._last_collection_count = current_collections

        return {
            "current_counts": current_counts,
            "current_collections": current_collections,
            "delta": delta,
            "collections_occurred": collections_occurred,
        }

    def get_debug_info(self) -> dict[str, Any]:
        """Get GC debug flag information.

        Returns:
            dict: Contains current debug flags and their meanings.

        Example:
            >>> analyzer = GCAnalyzer()
            >>> debug = analyzer.get_debug_info()
            >>> print(f"Debug flags: {debug['flags']}")
        """
        flags = gc.get_debug()
        flag_names = []

        if flags & gc.DEBUG_STATS:
            flag_names.append("DEBUG_STATS")
        if flags & gc.DEBUG_COLLECTABLE:
            flag_names.append("DEBUG_COLLECTABLE")
        if flags & gc.DEBUG_UNCOLLECTABLE:
            flag_names.append("DEBUG_UNCOLLECTABLE")
        if flags & gc.DEBUG_SAVEALL:
            flag_names.append("DEBUG_SAVEALL")
        if flags & gc.DEBUG_LEAK:
            flag_names.append("DEBUG_LEAK")

        return {"flags": flags, "flag_names": flag_names, "enabled": flags > 0}


# Global analyzer instance
_analyzer = GCAnalyzer()


def get_analyzer() -> GCAnalyzer:
    """Get the global GC analyzer instance.

    Returns:
        GCAnalyzer: The singleton analyzer instance.
    """
    return _analyzer
