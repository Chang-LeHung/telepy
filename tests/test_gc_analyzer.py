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
            self.assertGreaterEqual(
                stats[i]["avg_memory"], stats[i + 1]["avg_memory"]
            )

        # Keep test_data alive
        self.assertIsNotNone(test_data)

    def test_get_object_stats_with_memory_percentage(self):
        """Test that memory percentage is calculated correctly."""
        stats = self.analyzer.get_object_stats(
            limit=5, calculate_memory=True
        )

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


if __name__ == "__main__":
    unittest.main()
