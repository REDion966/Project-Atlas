"""
Atlas Goal Execution Models — Phase 15.0

Pure data models for the adaptive goal execution loop.

These dataclasses carry the goal-to-action translation, user
authorization, and typed execution feedback between the goal layer
and the evolution execution infrastructure. They are intentionally
executor-agnostic: no executor request object (e.g. ToolRequest) is
embedded — binders translate the generic ``ExecutionAction`` envelope
into executor-specific requests.

Pure data. No business logic. No infrastructure. No AI.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any

from atlas.goals.models import GoalCategory


class ActionType(Enum):
    """
    Discriminator for the execution mechanism an action targets.

    Phase 15 defines exactly one member: ``TOOL_INVOCATION``, bound by
    the registered ToolExecutionActionBinder. Future phases add
    ``TASK_INVOCATION``, ``CAPABILITY_INVOCATION``, and
    ``AGENT_INVOCATION`` without changing this model.
    """

    TOOL_INVOCATION = auto()


class ExecutionOutcome(Enum):
    """
    Terminal outcome of a goal execution attempt.

    ``COMPLETED`` — the executor ran and reported success.
    ``FAILED`` — the executor ran and reported failure.
    ``REFUSED`` — the execution gateway refused before any executor ran.
    """

    COMPLETED = auto()
    FAILED = auto()
    REFUSED = auto()


@dataclass(frozen=True, slots=True)
class GoalAuthorization:
    """
    User authorization record — the only ticket that permits activation.

    Snapshot of planning provenance at activation time so every
    execution record of this goal carries the same deterministic
    strategy and planning-context identifiers without re-querying the
    knowledge layer mid-execution.

    Attributes:
        goal_id: The ID of the authorized ImprovementGoal.
        authorized_by: The authorizing actor. Phase 15 only accepts
            "user:cli" — never "system".
        authorized_at: When the authorization was granted.
        comment: Optional user comment on the authorization.
        strategy_key: Normalized key of the top strategy suggestion
            for the goal's area at activation time (may be empty).
        strategy_name: Human-readable name of that strategy (may be
            empty).
        planning_context_version: Identifier of the PlanningContext
            used at activation, e.g. its generated_at ISO timestamp
            (may be empty).
    """

    goal_id: str
    authorized_by: str = "user:cli"
    authorized_at: datetime = field(default_factory=datetime.now)
    comment: str = ""
    strategy_key: str = ""
    strategy_name: str = ""
    planning_context_version: str = ""


@dataclass(frozen=True, slots=True)
class ExecutionAction:
    """
    Generic executor-agnostic action envelope for a goal.

    Attributes:
        action_id: Unique identifier for this action.
        goal_id: The owning ImprovementGoal ID.
        action_type: The ActionType discriminator used to resolve an
            ExecutionActionBinder. Phase 15: TOOL_INVOCATION.
        payload: Executor-agnostic data (e.g. goal description,
            category, evidence summary).
        context: Additional execution context (goal_id, category,
            priority score, authorization metadata).
        expected_impact: Expected impact of the goal, 0.0-1.0.
        risk: Estimated risk of the goal, 0.0-1.0.
        confidence: Confidence in the goal, 0.0-1.0.
        created_at: When the action was created.
    """

    action_id: str
    goal_id: str
    action_type: ActionType = ActionType.TOOL_INVOCATION
    payload: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    expected_impact: float = 0.5
    risk: float = 0.5
    confidence: float = 0.5
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class GoalExecutionRecord:
    """
    Typed execution feedback record — the Phase 17 evidence contract.

    Captures everything Phase 17 needs to compute historical strategy
    effectiveness from real executed outcomes. Phase 15 only persists
    these records; it never aggregates them into insights.

    Attributes:
        record_id: Unique identifier for this record.
        goal_id: The executed ImprovementGoal ID.
        category: The goal's GoalCategory.
        area: The canonical evolution area derived from the category.
        strategy_key: Strategy key snapshot from GoalAuthorization.
        strategy_name: Strategy name snapshot from GoalAuthorization.
        planning_context_version: Planning-context identifier snapshot
            from GoalAuthorization.
        action_type: The ActionType that was executed.
        action_tool: The tool name selected by the executor, or "" for
            refusals.
        success: Whether execution completed successfully.
        outcome: ExecutionOutcome — completed, failed, or refused.
        effectiveness_proxy: 1.0 when completed, 0.0 otherwise.
        execution_time_ms: Executor duration in milliseconds.
        confidence: Goal confidence carried into the record.
        error: Error/refusal message, if any.
        related_ids: tracked_goal_id, evolution_record_id, proposal_id.
        started_at: When the execution attempt started.
        finished_at: When the execution attempt finished.
        metadata: Additional context (governance decision, gateway
            status, binder name, bounded executor output).
    """

    record_id: str
    goal_id: str
    category: GoalCategory
    area: str
    strategy_key: str = ""
    strategy_name: str = ""
    planning_context_version: str = ""
    action_type: ActionType = ActionType.TOOL_INVOCATION
    action_tool: str = ""
    success: bool = False
    outcome: ExecutionOutcome = ExecutionOutcome.REFUSED
    effectiveness_proxy: float = 0.0
    execution_time_ms: float = 0.0
    confidence: float = 0.0
    error: str = ""
    related_ids: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GoalExecutorResult:
    """
    Result of a goal execution attempt, normalized for the goal layer.

    Never carries an executor-proprietary result object; the executor
    output is summarized into ``execution_summary``.

    Attributes:
        success: Whether execution completed successfully.
        goal_id: The executed ImprovementGoal ID.
        status: The GoalStatus name the goal transitioned to.
        record_id: The GoalExecutionRecord ID, if persisted.
        tracked_goal_id: The TrackedGoal ID, if updated.
        execution_summary: Normalized executor result summary.
        error: Error/refusal message, if any.
    """

    success: bool
    goal_id: str = ""
    status: str = ""
    record_id: str = ""
    tracked_goal_id: str = ""
    execution_summary: dict[str, Any] = field(default_factory=dict)
    error: str = ""
