"""
Atlas Tool Engine

Coordinates tool selection and execution as a single operation.
Orchestrates the tool intelligence pipeline.

Phase 6.9 — Tool Intelligence Foundation.
"""

from atlas.tools.models import Tool, ToolRequest, ToolResult
from atlas.tools.registry import ToolRegistry
from atlas.tools.selector import ToolSelector
from atlas.tools.executor import ToolExecutor


class ToolEngine:
    """
    Coordinates tool selection and execution as a single operation.

    Sits between the reasoning pipeline and real tool execution.
    Delegates selection to ToolSelector and execution to ToolExecutor.

    This component is infrastructure-aware via its dependency on
    ToolExecutor, but does not directly import AI providers, memory
    services, knowledge managers, or EventBus.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        selector: ToolSelector,
        executor: ToolExecutor,
    ) -> None:
        """
        Initialise the tool engine with its dependencies.

        Args:
            registry: The ToolRegistry containing available tools.
            selector: The ToolSelector for matching requests to tools.
            executor: The ToolExecutor for running tools.
        """
        self._registry = registry
        self._selector = selector
        self._executor = executor

    def fulfill(
        self,
        request: ToolRequest,
    ) -> ToolResult:
        """
        Select the best tool for a request and execute it.

        Selection strategy:
        1. Get all available tools from the registry.
        2. Use the selector to find the best match.
        3. Execute the top-ranked tool.
        4. Return the result.

        Args:
            request: The ToolRequest describing what is needed.

        Returns:
            A ToolResult from executing the best-matching tool.
            Returns an error result if no matching tool is found.
        """
        available = self._registry.list()
        if not available:
            return ToolResult(
                tool_name="",
                success=False,
                error="No tools are registered.",
            )

        matches = self._selector.select(request, available)
        if not matches:
            return ToolResult(
                tool_name="",
                success=False,
                error=(
                    f"No matching tool found for goal: "
                    f"'{request.goal}'."
                ),
            )

        best_tool = matches[0]
        return self._executor.execute(best_tool, request.context)

    def fulfill_with_fallback(
        self,
        request: ToolRequest,
    ) -> ToolResult:
        """
        Select and execute the best tool, falling back to alternatives.

        If the best-matching tool fails, tries the next best match.
        Continues until a tool succeeds or no alternatives remain.

        Args:
            request: The ToolRequest describing what is needed.

        Returns:
            A ToolResult from the first successful execution, or
            the last failure result if all tools fail.
        """
        available = self._registry.list()
        if not available:
            return ToolResult(
                tool_name="",
                success=False,
                error="No tools are registered.",
            )

        matches = self._selector.select(request, available)
        if not matches:
            return ToolResult(
                tool_name="",
                success=False,
                error=(
                    f"No matching tool found for goal: "
                    f"'{request.goal}'."
                ),
            )

        last_result = ToolResult(
            tool_name="",
            success=False,
            error="No tools were executed.",
        )

        for tool in matches:
            result = self._executor.execute(tool, request.context)
            if result.success:
                return result
            last_result = result

        return last_result

    @property
    def registry(self) -> ToolRegistry:
        """
        Return the underlying tool registry.

        Returns:
            The ToolRegistry instance used by this engine.
        """
        return self._registry

    def available_tools(self) -> list[Tool]:
        """
        Return all registered tools.

        Returns:
            A list of all registered Tool instances.
        """
        return self._registry.list()