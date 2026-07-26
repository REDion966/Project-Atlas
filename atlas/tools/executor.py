"""
Atlas Tool Executor

Invokes a tool and captures its result with timing and error handling.
Infrastructure-aware component — calls tool handlers and captures
execution results.

Phase 6.9 — Tool Intelligence Foundation.
"""

import time
import traceback

from atlas.tools.models import Tool, ToolResult
from atlas.tools.registry import ToolRegistry


class ToolExecutor:
    """
    Invokes a tool and captures its result.

    This component is infrastructure-aware: it calls tool handlers
    which may perform real system operations. It captures timing,
    errors, and results.

    It does NOT import AI providers, memory services, knowledge
    managers, or EventBus.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        """
        Initialise the executor with a tool registry.

        Args:
            registry: A ToolRegistry instance to look up tools from.
        """
        self._registry = registry

    def execute(
        self,
        tool: Tool,
        params: dict | None = None,
    ) -> ToolResult:
        """
        Run a tool's handler with the given parameters.

        Captures execution time and wraps errors gracefully.

        Args:
            tool: The Tool instance to execute.
            params: Optional parameters to pass to the handler.

        Returns:
            A ToolResult with success status, output, timing, and
            error information.
        """
        if tool.handler is None:
            return ToolResult(
                tool_name=tool.name,
                success=False,
                error=f"Tool '{tool.name}' has no handler registered.",
            )

        params = params or {}
        start = time.perf_counter()

        try:
            result = tool.handler(params)
            elapsed = (time.perf_counter() - start) * 1000

            if isinstance(result, ToolResult):
                result.execution_time_ms = elapsed
                return result

            # Handler returned unexpected type
            elapsed_ms = (time.perf_counter() - start) * 1000
            return ToolResult(
                tool_name=tool.name,
                success=False,
                error=(
                    f"Handler returned unexpected type: "
                    f"{type(result).__name__}. Expected ToolResult."
                ),
                execution_time_ms=elapsed_ms,
            )

        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return ToolResult(
                tool_name=tool.name,
                success=False,
                error=str(exc),
                execution_time_ms=elapsed,
                metadata={"traceback": traceback.format_exc()},
            )

    def execute_by_name(
        self,
        name: str,
        params: dict | None = None,
    ) -> ToolResult:
        """
        Look up a tool by name and execute it.

        Args:
            name: The name of the tool to execute.
            params: Optional parameters to pass to the handler.

        Returns:
            A ToolResult from execution, or an error result if the
            tool is not found.
        """
        tool = self._registry.get(name)
        if tool is None:
            return ToolResult(
                tool_name=name,
                success=False,
                error=f"Tool '{name}' is not registered.",
            )
        return self.execute(tool, params)

    def execute_batch(
        self,
        tools: list[Tool],
        params: dict | None = None,
    ) -> list[ToolResult]:
        """
        Execute multiple tools sequentially.

        Args:
            tools: The list of Tool instances to execute.
            params: Optional parameters to pass to each handler.

        Returns:
            A list of ToolResult instances, one per tool, in the
            same order as the input tools.
        """
        params = params or {}
        return [self.execute(tool, params) for tool in tools]