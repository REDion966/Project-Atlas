"""
Tests for the Tool Registry.

Phase 6.9 — Tool Intelligence Foundation.
"""

import unittest

from atlas.tools.models import Tool
from atlas.tools.registry import ToolRegistry


class TestToolRegistry(unittest.TestCase):
    """Unit tests for ToolRegistry."""

    def setUp(self):
        self.registry = ToolRegistry()
        self.tool_a = Tool(name="alpha", description="First tool", category="utility")
        self.tool_b = Tool(name="beta", description="Second tool", category="file", tags=["search"])
        self.tool_c = Tool(name="gamma", description="Third tool", category="utility", tags=["debug"])

    def test_empty_registry(self):
        """A new registry has no tools."""
        self.assertEqual(self.registry.count, 0)
        self.assertEqual(self.registry.list(), [])

    def test_register_and_get(self):
        """Registering a tool makes it retrievable by name."""
        self.registry.register(self.tool_a)
        self.assertEqual(self.registry.count, 1)
        self.assertIs(self.registry.get("alpha"), self.tool_a)

    def test_register_duplicate_raises(self):
        """Registering a duplicate name raises ValueError."""
        self.registry.register(self.tool_a)
        with self.assertRaises(ValueError):
            self.registry.register(self.tool_a)

    def test_get_nonexistent(self):
        """Getting a nonexistent tool returns None."""
        self.assertIsNone(self.registry.get("nonexistent"))

    def test_unregister(self):
        """Unregistering a tool removes it."""
        self.registry.register(self.tool_a)
        self.registry.unregister("alpha")
        self.assertEqual(self.registry.count, 0)
        self.assertIsNone(self.registry.get("alpha"))

    def test_unregister_nonexistent_raises(self):
        """Unregistering a nonexistent tool raises KeyError."""
        with self.assertRaises(KeyError):
            self.registry.unregister("nonexistent")

    def test_list_sorted(self):
        """list() returns tools sorted by name."""
        self.registry.register(self.tool_b)
        self.registry.register(self.tool_a)
        self.registry.register(self.tool_c)
        names = [t.name for t in self.registry.list()]
        self.assertEqual(names, ["alpha", "beta", "gamma"])

    def test_find_by_category(self):
        """find_by_category returns tools matching the category."""
        self.registry.register(self.tool_a)
        self.registry.register(self.tool_b)
        self.registry.register(self.tool_c)
        utility_tools = self.registry.find_by_category("utility")
        self.assertEqual(len(utility_tools), 2)
        self.assertEqual(utility_tools[0].name, "alpha")
        self.assertEqual(utility_tools[1].name, "gamma")

    def test_find_by_category_no_match(self):
        """find_by_category returns empty list when no match."""
        self.registry.register(self.tool_a)
        result = self.registry.find_by_category("network")
        self.assertEqual(result, [])

    def test_find_by_tag(self):
        """find_by_tag returns tools with the given tag."""
        self.registry.register(self.tool_a)
        self.registry.register(self.tool_b)
        self.registry.register(self.tool_c)
        search_tools = self.registry.find_by_tag("search")
        self.assertEqual(len(search_tools), 1)
        self.assertEqual(search_tools[0].name, "beta")

    def test_find_by_tag_no_match(self):
        """find_by_tag returns empty list when no match."""
        self.registry.register(self.tool_a)
        result = self.registry.find_by_tag("nonexistent")
        self.assertEqual(result, [])

    def test_clear(self):
        """clear() removes all tools."""
        self.registry.register(self.tool_a)
        self.registry.register(self.tool_b)
        self.registry.clear()
        self.assertEqual(self.registry.count, 0)
        self.assertEqual(self.registry.list(), [])


if __name__ == "__main__":
    unittest.main()