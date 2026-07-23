"""
Atlas Reasoning Models

Data models for the adaptive reasoning layer.
Pure data containers with no service dependencies.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReasoningStep:
    """
    A single step within a reasoning plan.

    Attributes:
        description: Human-readable description of the step.
        action: The type of action to perform.
        parameters: Optional structured data for the step.
    """

    description: str = ""
    action: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningPlan:
    """
    A structured plan produced from a CognitionDecision.

    Contains zero or more steps that can be executed
    to fulfill the cognition decision's intent.

    Attributes:
        goal: The high-level goal derived from the decision.
        steps: Ordered list of ReasoningStep instances.
        metadata: Optional additional context about the plan.
    """

    goal: str = ""
    steps: list[ReasoningStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)