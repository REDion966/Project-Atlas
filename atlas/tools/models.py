"""
Atlas Tool Models

Data models for the tool intelligence layer.
Pure data containers with no service dependencies.

Phase 6.9 — Tool Intelligence Foundation.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolParameter:
    """
    Defines a single parameter that a tool accepts.

    Attributes:
        name: Parameter name (used in invocation).
        description: Human-readable description of the parameter.
        type_hint: Expected type string ("string", "integer", "boolean",
            "dict", "list").
        required: Whether the parameter must be provided.
        default: Optional default value if not provided.
    """

    name: str
    description: str = ""
    type_hint: str = "string"
    required: bool = False
    default: Any = None


@dataclass
class ToolResult:
    """
    The result of executing a single tool.

    Attributes:
        tool_name: The name of the tool that was executed.
        success: Whether execution succeeded.
        output: Structured output data from the tool.
        error: Error message if execution failed.
        execution_time_ms: How long execution took, in milliseconds.
        metadata: Additional execution context.
    """

    tool_name: str = ""
    success: bool = False
    output: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    execution_time_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Tool:
    """
    A registered tool that can be selected and executed.

    Attributes:
        name: Unique identifier for the tool.
        description: Human-readable description of what the tool does.
        parameters: List of ToolParameter instances the tool accepts.
        category: Functional category (e.g. "file", "search", "code",
            "network", "system", "utility").
        handler: Callable that executes the tool. Accepts a dict of
            parameters, returns a ToolResult.
        tags: Optional list of tags for discovery and matching.
        metadata: Optional additional context.
    """

    name: str
    description: str = ""
    parameters: list[ToolParameter] = field(default_factory=list)
    category: str = "utility"
    handler: Callable[[dict[str, Any]], ToolResult] | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolRequest:
    """
    A request to find and execute a tool for a given purpose.

    Attributes:
        goal: The high-level goal the tool should help accomplish.
        context: Available context (e.g. planning data, metadata).
        preferred_category: Optional preferred tool category.
        max_results: Maximum number of tool suggestions to return.
    """

    goal: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    preferred_category: str = ""
    max_results: int = 5