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


CapabilityHandler = Callable[[dict[str, Any]], ExecutionResult]
"""
A callable that accepts parameters and returns an ExecutionResult.

Type alias for capability handler functions. Each handler receives
a dictionary of parameters and must return an ExecutionResult.

This is a pure type alias with no infrastructure dependencies.
"""