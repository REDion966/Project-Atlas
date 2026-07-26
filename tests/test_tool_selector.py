"""
Tests for the Tool Selector.

Phase 6.9 — Tool Intelligence Foundation.
"""

import unittest

from atlas.tools.models import Tool, ToolRequest
from atlas.tools.selector import ToolSelector


class TestToolSelector(unittest.TestCase):
    """Unit tests for ToolSelector."""

    def setUp(self):
        self.selector = ToolSelector()
        self.echo_tool = Tool(
            name="echo",
            description="Returns input as output",
            category="utility",
            tags=["debug", "test"],
        )
        self.search_tool = Tool(
            name="search",
            description="Searches for files",
            category="file",
            tags=["search", "find"],
        )
        self.analyze_tool = Tool(
            name="analyze",
            description="Analyzes data and produces reports",
            category="analysis",
            tags=["analysis", "report"],
        )

    def test_select_empty_available(self):
        """Selecting from an empty list returns empty."""
        request = ToolRequest(goal="do something")
        result = self.selector.select(request, [])
        self.assertEqual(result, [])

    def test_select_no_preferred_category(self):
        """Without preferred category, tools are ranked by goal relevance."""
        request = ToolRequest(goal="search for files")
        tools = [self.echo_tool, self.search_tool, self.analyze_tool]
        result = self.selector.select(request, tools)
        # search tool should rank highest (name match)
        self.assertEqual(result[0].name, "search")

    def test_select_with_preferred_category(self):
        """With preferred category, only matching category tools are considered."""
        request = ToolRequest(
            goal="do something",
            preferred_category="file",
        )
        tools = [self.echo_tool, self.search_tool, self.analyze_tool]
        result = self.selector.select(request, tools)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "search")

    def test_select_respects_max_results(self):
        """Select returns at most max_results tools."""
        request = ToolRequest(goal="echo", max_results=1)
        tools = [self.echo_tool, self.search_tool, self.analyze_tool]
        result = self.selector.select(request, tools)
        self.assertLessEqual(len(result), 1)

    def test_select_preferred_category_no_match(self):
        """When preferred category has no matches, falls back to all tools."""
        request = ToolRequest(
            goal="do something",
            preferred_category="network",
        )
        tools = [self.echo_tool, self.search_tool]
        result = self.selector.select(request, tools)
        # Category had no matches, so all tools are considered
        self.assertGreater(len(result), 0)

    def test_rank_by_goal_name_match(self):
        """Name match gives +2 score."""
        tools = [self.echo_tool, self.search_tool]
        ranked = self.selector.rank_by_goal("echo", tools)
        self.assertEqual(ranked[0].name, "echo")

    def test_rank_by_goal_tag_match(self):
        """Tag match gives +1 score."""
        tools = [self.echo_tool, self.analyze_tool]
        ranked = self.selector.rank_by_goal("debug mode", tools)
        self.assertEqual(ranked[0].name, "echo")

    def test_rank_by_goal_description_match(self):
        """Description word match gives +1 score."""
        tools = [self.echo_tool, self.search_tool]
        ranked = self.selector.rank_by_goal("input and output", tools)
        self.assertEqual(ranked[0].name, "echo")

    def test_rank_by_goal_tie_breaker(self):
        """Ties are broken alphabetically by name."""
        tool_x = Tool(name="alpha", description="zzz")
        tool_y = Tool(name="beta", description="zzz")
        ranked = self.selector.rank_by_goal("zzz", [tool_y, tool_x])
        self.assertEqual(ranked[0].name, "alpha")
        self.assertEqual(ranked[1].name, "beta")

    def test_rank_by_goal_empty_goal(self):
        """Empty goal returns tools in original order."""
        tools = [self.echo_tool, self.search_tool]
        ranked = self.selector.rank_by_goal("", tools)
        self.assertEqual(len(ranked), 2)

    def test_rank_by_goal_empty_tools(self):
        """Empty tools list returns empty list."""
        ranked = self.selector.rank_by_goal("test", [])
        self.assertEqual(ranked, [])


if __name__ == "__main__":
    unittest.main()