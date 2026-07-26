"""
Atlas Planning Models

Data models for the planning engine layer.
Pure data containers with no service dependencies.

Phase 6.8 — Planning Engine.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlanningStep:
    """
    A single step within a PlanningPlan with dependency and status tracking.

    Attributes:
        id: Unique identifier for this step within the plan.
        description: Human-readable description of the step.
        action: The type of action to perform.
        parameters: Optional structured data for the step.
        depends_on: List of step IDs that must complete before this step.
        status: Current status (pending, in_progress, completed, failed,
            blocked).
        validation_errors: List of validation issues, if any.
    """

    id: str
    description: str = ""
    action: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class PlanningPlan:
    """
    A decomposed, structured plan with sub-goals and dependency tracking.

    Attributes:
        goal: The high-level goal (inherited from ReasoningPlan).
        sub_goals: List of sub-goals that decompose the main goal.
        steps: Ordered list of PlanningStep instances.
        dependencies: Adjacency mapping of step_id -> list[depends_on_ids].
        status: Overall plan status (pending, active, completed, failed).
        metadata: Optional additional context.
        validation_errors: List of plan-level validation issues, if any.
    """

    goal: str = ""
    sub_goals: list[str] = field(default_factory=list)
    steps: list[PlanningStep] = field(default_factory=list)
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    status: str = "pending"
    metadata: dict[str, Any] = field(default_factory=dict)
    validation_errors: list[str] = field(default_factory=list)