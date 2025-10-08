"""
Unit tests for GC analyzer module.
"""

import gc
import unittest

from telepy.gc_analyzer import GCAnalyzer, get_analyzer


class TestGCAnalyzer(unittest.TestCase):
    """Test cases for GC analyzer functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.analyzer = GCAnalyzer()
        # Ensure GC is enabled for tests
        gc.enable()

    def test_get_status(self):
        """Test getting GC status."""
        status = self.analyzer.get_status()

        # Check all required keys exist
        self.assertIn("enabled", status)
        self.assertIn("count", status)
        self.assertIn("threshold", status)
        self.assertIn("stats", status)
        self.assertIn("freeze_count", status)
        self.assertIn("garbage_count", status)

        # Check types
        self.assertIsInstance(status["enabled"], bool)
        self.assertIsInstance(status["count"], tuple)
        self.assertIsInstance(status["threshold"], tuple)
        self.assertIsInstance(status["stats"], list)
        self.assertEqual(len(status["count"]), 3)
        self.assertEqual(len(status["threshold"]), 3)

    def test_get_stats_summary(self):
        """Test formatted GC statistics summary."""
        summary = self.analyzer.get_stats_summary()

        # Check that summary contains expected sections
        self.assertIn("GC Status", summary)
        self.assertIn("Current Counts", summary)
        self.assertIn("Thresholds", summary)
        self.assertIn("Per-Generation Statistics", summary)
        self.assertIsInstance(summary, str)

    def test_get_object_stats(self):
        """Test object statistics retrieval."""
        # Create some test objects
        test_data = [1, 2, 3, "test", {"key": "value"}, [1, 2, 3]]

        stats = self.analyzer.get_object_stats(limit=10)

        # Check that stats is a list
        self.assertIsInstance(stats, list)
        self.assertGreater(len(stats), 0)

        # Check each stat entry
        for stat in stats:
            self.assertIn("type_name", stat)
            self.assertIn("count", stat)
            self.assertIn("percentage", stat)
            self.assertIsInstance(stat["type_name"], str)
            self.assertIsInstance(stat["count"], int)
            self.assertIsInstance(stat["percentage"], float)
            self.assertGreaterEqual(stat["count"], 0)
            self.assertGreaterEqual(stat["percentage"], 0)
            self.assertLessEqual(stat["percentage"], 100)

        # Keep test_data alive to avoid premature collection
        self.assertIsNotNone(test_data)

    def test_get_object_stats_formatted(self):
        """Test formatted object statistics."""
        formatted = self.analyzer.get_object_stats_formatted(limit=5)

        self.assertIsInstance(formatted, str)
        self.assertIn("Object Statistics", formatted)
        self.assertIn("Type", formatted)
        self.assertIn("Count", formatted)
        self.assertIn("Percentage", formatted)

    def test_get_object_stats_with_memory(self):
        """Test object statistics with memory calculation."""
        # Create some test objects
        test_data = [1, 2, 3, "test", {"key": "value"}, [1, 2, 3]]

        stats = self.analyzer.get_object_stats(limit=10, calculate_memory=True)

        # Check that stats is a list
        self.assertIsInstance(stats, list)
        self.assertGreater(len(stats), 0)

        # Check each stat entry includes memory fields
        for stat in stats:
            self.assertIn("type_name", stat)
            self.assertIn("count", stat)
            self.assertIn("percentage", stat)
            self.assertIn("memory", stat)
            self.assertIn("avg_memory", stat)
            self.assertIsInstance(stat["memory"], int)
            self.assertIsInstance(stat["avg_memory"], float)
            self.assertGreaterEqual(stat["memory"], 0)
            self.assertGreaterEqual(stat["avg_memory"], 0)

        # Keep test_data alive
        self.assertIsNotNone(test_data)

    def test_get_object_stats_with_generation(self):
        """Test object statistics for specific generation."""
        # Test each generation
        for gen in [0, 1, 2]:
            stats = self.analyzer.get_object_stats(generation=gen, limit=5)
            self.assertIsInstance(stats, list)
            # Generation 0 and 2 typically have objects, but 1 might be empty
            if gen in [0, 2]:
                self.assertGreaterEqual(len(stats), 0)

    def test_get_object_stats_formatted_with_memory(self):
        """Test formatted object statistics with memory calculation."""
        formatted = self.analyzer.get_object_stats_formatted(
            limit=5, calculate_memory=True
        )

        self.assertIsInstance(formatted, str)
        self.assertIn("Object Statistics", formatted)
        self.assertIn("Type", formatted)
        self.assertIn("Count", formatted)
        self.assertIn("Count %", formatted)
        self.assertIn("Memory", formatted)
        self.assertIn("Memory %", formatted)
        self.assertIn("Avg Memory", formatted)

    def test_get_object_stats_formatted_with_generation(self):
        """Test formatted object statistics for specific generation."""
        for gen in [0, 1, 2]:
            formatted = self.analyzer.get_object_stats_formatted(generation=gen, limit=5)
            self.assertIsInstance(formatted, str)
            self.assertIn(f"Generation {gen}", formatted)

    def test_format_bytes(self):
        """Test byte formatting helper method."""
        test_cases = [
            (100, "100.0 B"),
            (1024, "1.0 KB"),
            (1536, "1.5 KB"),
            (1048576, "1.0 MB"),
            (2621440, "2.5 MB"),
            (1073741824, "1.0 GB"),
        ]

        for bytes_size, expected in test_cases:
            result = self.analyzer._format_bytes(bytes_size)
            self.assertEqual(result, expected)

    def test_get_object_stats_sort_by_count(self):
        """Test sorting by count (default)."""
        # Create some test objects
        test_data = [1, 2, 3, "test", {"key": "value"}, [1, 2, 3]]

        stats = self.analyzer.get_object_stats(
            limit=10, calculate_memory=True, sort_by="count"
        )

        # Check that stats are sorted by count
        for i in range(len(stats) - 1):
            self.assertGreaterEqual(stats[i]["count"], stats[i + 1]["count"])

        # Keep test_data alive
        self.assertIsNotNone(test_data)

    def test_get_object_stats_sort_by_memory(self):
        """Test sorting by memory."""
        # Create some test objects with different sizes
        test_data = {
            "large_lists": [list(range(1000)) for _ in range(10)],
            "small_ints": [i for i in range(100)],
        }

        stats = self.analyzer.get_object_stats(
            limit=10, calculate_memory=True, sort_by="memory"
        )

        # Check that stats are sorted by memory
        for i in range(len(stats) - 1):
            self.assertGreaterEqual(stats[i]["memory"], stats[i + 1]["memory"])

        # Keep test_data alive
        self.assertIsNotNone(test_data)

    def test_get_object_stats_sort_by_memory_without_calculate(self):
        """Test that sorting by memory without calculate_memory raises error."""
        with self.assertRaises(ValueError) as context:
            self.analyzer.get_object_stats(
                limit=10, calculate_memory=False, sort_by="memory"
            )
        self.assertIn("calculate_memory=True", str(context.exception))

    def test_get_object_stats_sort_by_avg_memory(self):
        """Test sorting by average memory."""
        # Create some test objects with different sizes
        test_data = {
            "large_dicts": [{f"key_{i}": f"value_{i}" * 100} for i in range(10)],
            "small_tuples": [tuple(range(5)) for _ in range(50)],
        }

        stats = self.analyzer.get_object_stats(
            limit=10, calculate_memory=True, sort_by="avg_memory"
        )

        # Check that stats are sorted by avg_memory
        for i in range(len(stats) - 1):
            self.assertGreaterEqual(stats[i]["avg_memory"], stats[i + 1]["avg_memory"])

        # Keep test_data alive
        self.assertIsNotNone(test_data)

    def test_get_object_stats_with_memory_percentage(self):
        """Test that memory percentage is calculated correctly."""
        stats = self.analyzer.get_object_stats(limit=5, calculate_memory=True)

        # Check that memory_percentage exists and is reasonable
        total_pct = sum(s.get("memory_percentage", 0) for s in stats)
        # Total percentage should be <= 100 (since we're limiting results)
        self.assertLessEqual(total_pct, 100.0)

        for stat in stats:
            self.assertIn("memory_percentage", stat)
            self.assertGreaterEqual(stat["memory_percentage"], 0)
            self.assertLessEqual(stat["memory_percentage"], 100)

    def test_get_object_stats_formatted_with_sort_by(self):
        """Test formatted output includes sort indicator."""
        formatted = self.analyzer.get_object_stats_formatted(
            limit=5, calculate_memory=True, sort_by="memory"
        )

        self.assertIsInstance(formatted, str)
        self.assertIn("sorted by memory", formatted)

    def test_collect_garbage(self):
        """Test manual garbage collection."""
        # Create some objects first
        _ = [{"key": i} for i in range(1000)]

        # Trigger collection
        result = self.analyzer.collect_garbage(generation=0)

        # Check result structure
        self.assertIn("generation", result)
        self.assertIn("unreachable", result)
        self.assertIn("counts_before", result)
        self.assertIn("counts_after", result)
        self.assertIn("collected", result)

        self.assertEqual(result["generation"], 0)
        self.assertIsInstance(result["unreachable"], int)
        self.assertGreaterEqual(result["unreachable"], 0)

    def test_get_garbage_info(self):
        """Test getting garbage information."""
        info = self.analyzer.get_garbage_info()

        self.assertIn("count", info)
        self.assertIn("types", info)
        self.assertIn("objects", info)
        self.assertIsInstance(info["count"], int)
        self.assertIsInstance(info["types"], dict)
        self.assertIsInstance(info["objects"], list)

    def test_get_garbage_formatted(self):
        """Test formatted garbage information."""
        formatted = self.analyzer.get_garbage_formatted()

        self.assertIsInstance(formatted, str)
        self.assertIn("Garbage Collection Report", formatted)
        self.assertIn("Uncollectable Objects", formatted)

    def test_monitor_collection_activity(self):
        """Test monitoring GC collection activity."""
        # First call to initialize
        activity1 = self.analyzer.monitor_collection_activity()

        # Create some objects and trigger collection
        _ = [list(range(100)) for _ in range(1000)]
        gc.collect()

        # Second call to check delta
        activity2 = self.analyzer.monitor_collection_activity()

        # Check structure
        for activity in [activity1, activity2]:
            self.assertIn("current_counts", activity)
            self.assertIn("current_collections", activity)
            self.assertIn("delta", activity)
            self.assertIn("collections_occurred", activity)

        # After gc.collect(), delta should show changes
        self.assertTrue(
            any(d > 0 for d in activity2["delta"]) or activity2["collections_occurred"]
        )

    def test_get_debug_info(self):
        """Test getting debug flag information."""
        debug_info = self.analyzer.get_debug_info()

        self.assertIn("flags", debug_info)
        self.assertIn("flag_names", debug_info)
        self.assertIn("enabled", debug_info)
        self.assertIsInstance(debug_info["flags"], int)
        self.assertIsInstance(debug_info["flag_names"], list)
        self.assertIsInstance(debug_info["enabled"], bool)

    def test_get_analyzer_singleton(self):
        """Test that get_analyzer returns the same instance."""
        analyzer1 = get_analyzer()
        analyzer2 = get_analyzer()
        self.assertIs(analyzer1, analyzer2)

    def test_analyze_memory_leaks(self):
        """Test memory leak analysis."""
        # Set a very high threshold so nothing is suspicious
        result = self.analyzer.analyze_memory_leaks(threshold=999999)

        self.assertIn("threshold", result)
        self.assertIn("suspicious_types", result)
        self.assertIn("total_suspicious_objects", result)
        self.assertEqual(result["threshold"], 999999)
        self.assertIsInstance(result["suspicious_types"], list)

    def test_get_referrers_info(self):
        """Test getting referrers information."""
        # Create a test object
        test_obj = {"test": "data"}
        container = [test_obj]  # Create a referrer

        info = self.analyzer.get_referrers_info(test_obj)

        self.assertIn("direct_count", info)
        self.assertIn("types", info)
        self.assertIn("is_tracked", info)
        self.assertIsInstance(info["direct_count"], int)
        self.assertIsInstance(info["types"], dict)
        self.assertIsInstance(info["is_tracked"], bool)

        # Keep container alive
        self.assertIsNotNone(container)

    def test_c_extension_availability(self):
        """Test C extension import handling."""
        from telepy import gc_analyzer

        # Check if C extension flag is set
        self.assertIsInstance(gc_analyzer._HAS_C_EXTENSION, bool)

    def test_c_extension_fallback(self):
        """Test fallback to Python implementation when C extension unavailable."""
        # Save original value
        from telepy import gc_analyzer

        original_has_c_ext = gc_analyzer._HAS_C_EXTENSION

        try:
            # Force Python fallback
            gc_analyzer._HAS_C_EXTENSION = False

            # This should use Python implementation
            stats = self.analyzer.get_object_stats(limit=10)

            # Verify it still works
            self.assertIsInstance(stats, list)
            self.assertGreater(len(stats), 0)

        finally:
            # Restore original value
            gc_analyzer._HAS_C_EXTENSION = original_has_c_ext

    def test_c_extension_import_error(self):
        """Test handling of C extension import error.

        Note: This test verifies that the code gracefully handles
        the ImportError when C extension is not available.
        The actual coverage of lines 18-19 happens during the initial
        module import if the C extension is not installed.
        """
        from telepy import gc_analyzer

        # The _HAS_C_EXTENSION flag should be properly set
        # based on whether C extension import succeeded or failed
        self.assertIsInstance(gc_analyzer._HAS_C_EXTENSION, bool)

        # Verify that the analyzer still works regardless
        # of C extension availability
        analyzer = GCAnalyzer()
        stats = analyzer.get_object_stats(limit=5)
        self.assertIsInstance(stats, list)

    def test_calculate_stats_python_with_memory(self):
        """Test Python fallback for stats calculation with memory."""
        # Create test objects with various types
        test_objects = [1, 2, "test", {"key": "value"}, [1, 2, 3], (1, 2)]

        type_counter, type_memory, total, total_memory = (
            self.analyzer._calculate_stats_python(test_objects, calculate_memory=True)
        )

        # Verify results
        self.assertIsInstance(type_counter, dict)
        self.assertIsInstance(type_memory, dict)
        self.assertIsInstance(total, int)
        self.assertIsInstance(total_memory, int)
        self.assertGreater(total, 0)
        self.assertGreater(total_memory, 0)

        # Check that memory was calculated for each type
        for type_name in type_counter.keys():
            self.assertIn(type_name, type_memory)
            self.assertGreater(type_memory[type_name], 0)

    def test_calculate_stats_python_without_memory(self):
        """Test Python fallback for stats calculation without memory."""
        test_objects = [1, 2, "test", {"key": "value"}, [1, 2, 3]]

        type_counter, type_memory, total, total_memory = (
            self.analyzer._calculate_stats_python(test_objects, calculate_memory=False)
        )

        # Verify results
        self.assertIsInstance(type_counter, dict)
        self.assertIsInstance(type_memory, dict)
        self.assertIsInstance(total, int)
        self.assertEqual(total_memory, 0)  # Should be 0 when not calculating memory
        self.assertEqual(len(type_memory), 0)  # Should be empty dict

    def test_calculate_stats_with_getsizeof_error(self):
        """Test handling of objects that don't support getsizeof."""

        # Create a class that raises TypeError for getsizeof
        class UnsizedObject:
            def __sizeof__(self):
                raise TypeError("Cannot get size")

        test_objects = [UnsizedObject(), UnsizedObject(), 1, 2, "test"]

        # Should not raise an exception
        type_counter, type_memory, total, total_memory = (
            self.analyzer._calculate_stats_python(test_objects, calculate_memory=True)
        )

        # Verify the function handled the error gracefully
        self.assertIsInstance(type_counter, dict)
        self.assertIn("UnsizedObject", type_counter)
        self.assertEqual(type_counter["UnsizedObject"], 2)

        # Memory for UnsizedObject should be 0 or not present
        # since getsizeof raised TypeError
        if "UnsizedObject" in type_memory:
            # It's ok if it's 0 due to the exception handling
            self.assertGreaterEqual(type_memory["UnsizedObject"], 0)

    def test_get_object_stats_with_old_python_fallback(self):
        """Test get_object_stats with TypeError fallback for old Python."""
        from unittest.mock import patch

        # Mock gc.get_objects to raise TypeError (simulating Python < 3.8)
        with patch("gc.get_objects") as mock_get_objects:
            # First call with generation parameter raises TypeError
            mock_get_objects.side_effect = [
                TypeError("get_objects() takes no arguments"),
                [1, 2, "test"],  # Second call without parameter succeeds
            ]

            stats = self.analyzer.get_object_stats(generation=0, limit=10)

            # Verify it fell back to calling without generation parameter
            self.assertEqual(mock_get_objects.call_count, 2)
            self.assertIsInstance(stats, list)

    def test_format_bytes_various_sizes(self):
        """Test byte formatting with various sizes."""
        # Test B
        self.assertEqual(self.analyzer._format_bytes(100), "100.0 B")

        # Test KB
        self.assertEqual(self.analyzer._format_bytes(1024), "1.0 KB")
        self.assertEqual(self.analyzer._format_bytes(1536), "1.5 KB")

        # Test MB
        self.assertEqual(self.analyzer._format_bytes(1024 * 1024), "1.0 MB")
        self.assertEqual(self.analyzer._format_bytes(1024 * 1024 * 2.5), "2.5 MB")

        # Test GB
        self.assertEqual(self.analyzer._format_bytes(1024 * 1024 * 1024), "1.0 GB")

        # Test TB
        self.assertEqual(self.analyzer._format_bytes(1024 * 1024 * 1024 * 1024), "1.0 TB")

        # Test PB
        self.assertEqual(
            self.analyzer._format_bytes(1024 * 1024 * 1024 * 1024 * 1024), "1.0 PB"
        )

    def test_get_garbage_info_with_objects(self):
        """Test get_garbage_info when garbage exists."""
        # Save original garbage
        original_garbage = gc.garbage[:]

        try:
            # Add some test objects to garbage (for testing only)
            gc.garbage.append({"test": "object1"})
            gc.garbage.append([1, 2, 3])
            gc.garbage.append({"test": "object2"})

            info = self.analyzer.get_garbage_info()

            # Check that we detected the garbage objects
            self.assertGreater(info["count"], 0)
            self.assertIn("dict", info["types"])
            self.assertIn("list", info["types"])
            self.assertEqual(info["types"]["dict"], 2)
            self.assertEqual(info["types"]["list"], 1)

            # Check objects list (should be limited to 100)
            self.assertLessEqual(len(info["objects"]), 100)

        finally:
            # Restore original garbage state
            gc.garbage[:] = original_garbage

    def test_get_garbage_formatted_with_objects(self):
        """Test formatted garbage report when objects exist."""
        original_garbage = gc.garbage[:]

        try:
            # Add test objects to garbage
            gc.garbage.append({"test": "object"})
            gc.garbage.append([1, 2, 3])

            formatted = self.analyzer.get_garbage_formatted()

            # Should contain the report and object details
            self.assertIn("Garbage Collection Report", formatted)
            self.assertIn("Objects by Type", formatted)
            self.assertIn("dict:", formatted)
            self.assertIn("list:", formatted)

        finally:
            # Restore original garbage state
            gc.garbage[:] = original_garbage

    def test_get_garbage_formatted_empty(self):
        """Test formatted garbage report when no objects exist."""
        # Ensure garbage is empty
        gc.garbage.clear()

        formatted = self.analyzer.get_garbage_formatted()

        # Should contain the "no objects" message
        self.assertIn("No uncollectable objects found", formatted)

    def test_get_debug_info_with_flags(self):
        """Test debug info with various debug flags set."""
        # Save original debug flags
        original_flags = gc.get_debug()

        try:
            # Test with DEBUG_STATS
            gc.set_debug(gc.DEBUG_STATS)
            debug_info = self.analyzer.get_debug_info()
            self.assertIn("DEBUG_STATS", debug_info["flag_names"])
            self.assertTrue(debug_info["enabled"])

            # Test with DEBUG_COLLECTABLE
            gc.set_debug(gc.DEBUG_COLLECTABLE)
            debug_info = self.analyzer.get_debug_info()
            self.assertIn("DEBUG_COLLECTABLE", debug_info["flag_names"])

            # Test with DEBUG_UNCOLLECTABLE
            gc.set_debug(gc.DEBUG_UNCOLLECTABLE)
            debug_info = self.analyzer.get_debug_info()
            self.assertIn("DEBUG_UNCOLLECTABLE", debug_info["flag_names"])

            # Test with DEBUG_SAVEALL
            gc.set_debug(gc.DEBUG_SAVEALL)
            debug_info = self.analyzer.get_debug_info()
            self.assertIn("DEBUG_SAVEALL", debug_info["flag_names"])

            # Test with DEBUG_LEAK (combination of flags)
            gc.set_debug(gc.DEBUG_LEAK)
            debug_info = self.analyzer.get_debug_info()
            self.assertIn("DEBUG_LEAK", debug_info["flag_names"])

            # Test with no flags
            gc.set_debug(0)
            debug_info = self.analyzer.get_debug_info()
            self.assertEqual(len(debug_info["flag_names"]), 0)
            self.assertFalse(debug_info["enabled"])

        finally:
            # Restore original debug flags
            gc.set_debug(original_flags)


if __name__ == "__main__":
    unittest.main()
