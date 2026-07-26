"""
Tests for the Tool Intelligence data models.

Phase 6.9 — Tool Intelligence Foundation.
"""

import unittest

from atlas.tools.models import Tool, ToolParameter, ToolRequest, ToolResult


class TestToolParameter(unittest.TestCase):
    """Unit tests for ToolParameter dataclass."""

    def test_default_values(self):
        """ToolParameter has sensible defaults."""
        param = ToolParameter(name="test")
        self.assertEqual(param.name, "test")
        self.assertEqual(param.description, "")
        self.assertEqual(param.type_hint, "string")
        self.assertFalse(param.required)
        self.assertIsNone(param.default)

    def test_custom_values(self):
        """ToolParameter accepts custom values."""
        param = ToolParameter(
            name="count",
            description="Number of items",
            type_hint="integer",
            required=True,
            default=5,
        )
        self.assertEqual(param.name, "count")
        self.assertEqual(param.description, "Number of items")
        self.assertEqual(param.type_hint, "integer")
        self.assertTrue(param.required)
        self.assertEqual(param.default, 5)


class TestToolResult(unittest.TestCase):
    """Unit tests for ToolResult dataclass."""

    def test_default_values(self):
        """ToolResult has sensible defaults."""
        result = ToolResult()
        self.assertEqual(result.tool_name, "")
        self.assertFalse(result.success)
        self.assertEqual(result.output, {})
        self.assertEqual(result.error, "")
        self.assertEqual(result.execution_time_ms, 0.0)
        self.assertEqual(result.metadata, {})

    def test_custom_values(self):
        """ToolResult accepts custom values."""
        result = ToolResult(
            tool_name="echo",
            success=True,
            output={"key": "val"},
            execution_time_ms=42.5,
            metadata={"handler": "echo"},
        )
        self.assertEqual(result.tool_name, "echo")
        self.assertTrue(result.success)
        self.assertEqual(result.output, {"key": "val"})
        self.assertEqual(result.execution_time_ms, 42.5)
        self.assertEqual(result.metadata, {"handler": "echo"})


class TestTool(unittest.TestCase):
    """Unit tests for Tool dataclass."""

    def test_default_values(self):
        """Tool has sensible defaults."""
        tool = Tool(name="test")
        self.assertEqual(tool.name, "test")
        self.assertEqual(tool.description, "")
        self.assertEqual(tool.parameters, [])
        self.assertEqual(tool.category, "utility")
        self.assertIsNone(tool.handler)
        self.assertEqual(tool.tags, [])
        self.assertEqual(tool.metadata, {})

    def test_custom_values(self):
        """Tool accepts custom values."""
        param = ToolParameter(name="msg", description="Message")
        handler = lambda p: ToolResult(tool_name="test", success=True)

        tool = Tool(
            name="custom",
            description="A custom tool",
            parameters=[param],
            category="file",
            handler=handler,
            tags=["tag1", "tag2"],
            metadata={"version": "1.0"},
        )
        self.assertEqual(tool.name, "custom")
        self.assertEqual(tool.description, "A custom tool")
        self.assertEqual(len(tool.parameters), 1)
        self.assertEqual(tool.category, "file")
        self.assertIsNotNone(tool.handler)
        self.assertEqual(tool.tags, ["tag1", "tag2"])
        self.assertEqual(tool.metadata, {"version": "1.0"})


class TestToolRequest(unittest.TestCase):
    """Unit tests for ToolRequest dataclass."""

    def test_default_values(self):
        """ToolRequest has sensible defaults."""
        request = ToolRequest()
        self.assertEqual(request.goal, "")
        self.assertEqual(request.context, {})
        self.assertEqual(request.preferred_category, "")
        self.assertEqual(request.max_results, 5)

    def test_custom_values(self):
        """ToolRequest accepts custom values."""
        request = ToolRequest(
            goal="find file",
            context={"path": "/tmp"},
            preferred_category="file",
            max_results=3,
        )
        self.assertEqual(request.goal, "find file")
        self.assertEqual(request.context, {"path": "/tmp"})
        self.assertEqual(request.preferred_category, "file")
        self.assertEqual(request.max_results, 3)


if __name__ == "__main__":
    unittest.main()