"""
Atlas Capability Models

Data models for the capability selection layer.
Pure data containers with no service dependencies.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Capability:
    """
    A capability that can be selected to fulfill a reasoning step.

    Attributes:
        name: Unique identifier for the capability.
        priority: Numeric priority (higher = more preferred).
        reason: Human-readable explanation for selection.
        metadata: Optional additional context.
    """

    name: str = ""
    priority: int = 0
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)