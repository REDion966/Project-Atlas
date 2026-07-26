"""
Tests for the Tool Executor.

Phase 6.9 — Tool Intelligence Foundation.
"""

import unittest

from atlas.tools.models import Tool, ToolResult
from atlas.tools.registry import ToolRegistry
from atlas.tools.executor import ToolExecutor


def _success_handler(params: dict) -> ToolResult:
    """A handler that always succeeds."""
    return ToolResult(
        tool_name="test_tool",
        success=True,
        output={"received": params},
        metadata={"handler": "success"},
    )


def _failing_handler(params: dict) -> ToolResult:
    """A handler that always fails."""
    return ToolResult(
        tool_name="test_tool",
        success=False,
        error="intentional failure",
    )


def _exception_handler(params: dict) -> ToolResult:
    """A handler that raises an exception."""
    msg = "something went wrong"
    raise RuntimeError(msg)


class TestToolExecutor(unittest.TestCase):
    """Unit tests for ToolExecutor."""

    def setUp(self):
        self.registry = ToolRegistry()
        self.executor = ToolExecutor(self.registry)
        self.success_tool = Tool(
            name="success_tool",
            description="Always succeeds",
            handler=_success_handler,
        )
        self.failing_tool = Tool(
            name="failing_tool",
            description="Always fails",
            handler=_failing_handler,
        )
        self.exception_tool = Tool(
            name="exception_tool",
            description="Raises exception",
            handler=_exception_handler,
        )
        self.no_handler_tool = Tool(
            name="no_handler_tool",
            description="No handler",
            handler=None,
        )

    def test_execute_success(self):
        """Executing a successful tool returns success."""
        result = self.executor.execute(self.success_tool, {"key": "val"})
        self.assertTrue(result.success)
        # Handler hardcodes tool_name; verify the result succeeded
        self.assertEqual(result.output, {"received": {"key": "val"}})

    def test_execute_no_handler(self):
        """Executing a tool with no handler returns error."""
        result = self.executor.execute(self.no_handler_tool)
        self.assertFalse(result.success)
        self.assertIn("no handler", result.error.lower())

    def test_execute_failing_handler(self):
        """Executing a failing handler returns error result."""
        result = self.executor.execute(self.failing_tool)
        self.assertFalse(result.success)
        self.assertEqual(result.error, "intentional failure")

    def test_execute_exception_handler(self):
        """Executing a handler that raises returns error result."""
        result = self.executor.execute(self.exception_tool)
        self.assertFalse(result.success)
        self.assertIn("something went wrong", result.error)

    def test_execute_captures_timing(self):
        """Execute captures execution time."""
        result = self.executor.execute(self.success_tool)
        self.assertGreater(result.execution_time_ms, 0)

    def test_execute_by_name_success(self):
        """execute_by_name looks up and executes a registered tool."""
        self.registry.register(self.success_tool)
        result = self.executor.execute_by_name("success_tool")
        self.assertTrue(result.success)

    def test_execute_by_name_not_found(self):
        """execute_by_name returns error for unregistered tool."""
        result = self.executor.execute_by_name("nonexistent")
        self.assertFalse(result.success)
        self.assertIn("not registered", result.error.lower())

    def test_execute_batch(self):
        """execute_batch runs all tools and returns all results."""
        tools = [self.success_tool, self.failing_tool]
        results = self.executor.execute_batch(tools)
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].success)
        self.assertFalse(results[1].success)

    def test_execute_batch_empty(self):
        """execute_batch with empty list returns empty list."""
        results = self.executor.execute_batch([])
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()