"""
Atlas Execution Models

Data models for the capability execution layer.
Pure data containers with no service dependencies.
"""

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ExecutionResult:
    """
    The result of executing a single capability.

    Attributes:
        capability: The name of the capability that was executed.
        success: Whether the execution succeeded.
        output: Optional structured output from the execution.
        error: Optional error message if execution failed.
        metadata: Optional additional context about the execution.
    """

    capability: str = ""
    success: bool = False
    output: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionRoute:
    """
    A routing decision for a single capability.

    Carries the handler to invoke, parameters to pass, and the
    routing strategy used. The strategy and metadata fields are
    extension points for future model routing (Phase 6.5+).

    Attributes:
        capability: The name of the capability being routed.
        handler_name: The handler to execute (looked up in registry).
        parameters: Parameters to pass to the handler.
        strategy: Routing strategy identifier (e.g. "default").
        metadata: Additional routing context (priority, reason, etc.).
    """

    capability: str = ""
    handler_name: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    strategy: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)


CapabilityHandler = Callable[[dict[str, Any]], ExecutionResult]
"""
A callable that accepts parameters and returns an ExecutionResult.

Type alias for capability handler functions. Each handler receives
a dictionary of parameters and must return an ExecutionResult.

This is a pure type alias with no infrastructure dependencies.
"""
