"""
Tests for the Tool Engine orchestrator.

Phase 6.9 — Tool Intelligence Foundation.
"""

import unittest

from atlas.tools.models import Tool, ToolRequest, ToolResult
from atlas.tools.registry import ToolRegistry
from atlas.tools.selector import ToolSelector
from atlas.tools.executor import ToolExecutor
from atlas.tools.engine import ToolEngine


def _echo_handler(params: dict) -> ToolResult:
    """A handler that echoes parameters."""
    return ToolResult(
        tool_name="echo",
        success=True,
        output={"echoed": params},
    )


def _failing_handler(params: dict) -> ToolResult:
    """A handler that always fails."""
    return ToolResult(
        tool_name="failing_tool",
        success=False,
        error="handler error",
    )


class TestToolEngine(unittest.TestCase):
    """Unit tests for ToolEngine."""

    def setUp(self):
        self.registry = ToolRegistry()
        self.selector = ToolSelector()
        self.executor = ToolExecutor(self.registry)
        self.engine = ToolEngine(self.registry, self.selector, self.executor)

        self.echo_tool = Tool(
            name="echo",
            description="Echoes input back",
            category="utility",
            handler=_echo_handler,
            tags=["echo"],
        )
        self.failing_tool = Tool(
            name="failing_tool",
            description="Always fails",
            category="utility",
            handler=_failing_handler,
        )
        self.registry.register(self.echo_tool)

    def test_fulfill_with_matching_tool(self):
        """Fulfill finds and executes the best matching tool."""
        request = ToolRequest(goal="echo my message")
        result = self.engine.fulfill(request)
        self.assertTrue(result.success)
        self.assertEqual(result.tool_name, "echo")

    def test_fulfill_no_registered_tools(self):
        """Fulfill returns error when no tools are registered."""
        empty_engine = ToolEngine(
            ToolRegistry(), ToolSelector(), ToolExecutor(ToolRegistry())
        )
        request = ToolRequest(goal="do something")
        result = empty_engine.fulfill(request)
        self.assertFalse(result.success)
        self.assertIn("no tools", result.error.lower())

    def test_fulfill_selects_lowest_ranked_when_only_match(self):
        """Fulfill selects and executes the only available tool even with low relevance."""
        registry = ToolRegistry()
        executor = ToolExecutor(registry)
        engine = ToolEngine(registry, ToolSelector(), executor)

        def _zzz_handler(params: dict) -> ToolResult:
            return ToolResult(tool_name="zzz", success=True, output={"done": True})

        registry.register(
            Tool(name="zzz", description="unrelated", handler=_zzz_handler)
        )
        request = ToolRequest(goal="python programming")
        result = engine.fulfill(request)
        self.assertTrue(result.success)
        self.assertEqual(result.tool_name, "zzz")

    def test_fulfill_with_fallback_first_succeeds(self):
        """Fulfill_with_fallback returns first successful result."""
        self.registry.register(self.failing_tool)
        request = ToolRequest(goal="echo test")
        result = self.engine.fulfill_with_fallback(request)
        self.assertTrue(result.success)
        self.assertEqual(result.tool_name, "echo")

    def test_fulfill_with_fallback_all_fail(self):
        """Fulfill_with_fallback returns last failure when all fail."""
        registry = ToolRegistry()
        executor = ToolExecutor(registry)
        engine = ToolEngine(registry, ToolSelector(), executor)
        registry.register(self.failing_tool)
        request = ToolRequest(goal="failing_tool")
        result = engine.fulfill_with_fallback(request)
        self.assertFalse(result.success)

    def test_fulfill_with_fallback_no_tools(self):
        """Fulfill_with_fallback returns error when no tools."""
        empty_engine = ToolEngine(
            ToolRegistry(), ToolSelector(), ToolExecutor(ToolRegistry())
        )
        request = ToolRequest(goal="do something")
        result = empty_engine.fulfill_with_fallback(request)
        self.assertFalse(result.success)

    def test_available_tools(self):
        """available_tools returns all registered tools."""
        tools = self.engine.available_tools()
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0].name, "echo")

    def test_registry_property(self):
        """registry property returns the underlying ToolRegistry."""
        self.assertIs(self.engine.registry, self.registry)


if __name__ == "__main__":
    unittest.main()