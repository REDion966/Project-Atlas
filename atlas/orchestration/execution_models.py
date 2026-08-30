"""Atlas Orchestration — Execution Models (P2/B2.2).

Frozen, deterministic value objects for the governed orchestration
execution layer. B2.2 executes the B2.1 planning graph through EXISTING
Atlas infrastructure (ToolExecutor, CapabilityDispatcher, WorkspaceService
metadata, InformationAcquisitionService) with authority attribution and
fail-closed bounds.

Planning-vs-execution boundary: the planner decides WHAT should happen; the
executor performs HOW the existing capability is invoked. These models are
the executor's data contract.

No infrastructure dependencies. No AI. No storage. No kernel. No runtime.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from atlas.authority.models import AuthorityLevel
from atlas.orchestration.models import NodeKind, OrchestrationPlan

if TYPE_CHECKING:
    from atlas.session.context import SessionContext


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExecutionState(str, Enum):
    """Deterministic lifecycle state of a single executed step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class StepFailureKind(str, Enum):
    """Deterministic failure classification for a step.

    ``DENIED_SURFACE`` is the defense-in-depth classification for targets
    that would reach governance/evolution/approval machinery the executor
    must never touch.
    """

    INVALID_PLAN = "invalid_plan"
    MISSING_TARGET = "missing_target"
    INVALID_INPUT = "invalid_input"
    AUTHORIZATION_FAILED = "authorization_failed"
    DEPENDENCY_FAILED = "dependency_failed"
    EXECUTION_FAILED = "execution_failed"
    BOUND_EXCEEDED = "bound_exceeded"
    DENIED_SURFACE = "denied_surface"


class ExecutionStatus(str, Enum):
    """Overall result status of an orchestration run."""

    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    EMPTY = "empty"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ExecutionStep:
    """One bounded, attributable step of an orchestration run.

    Attributes:
        step_id: Stable unique id within the run.
        kind: The step kind (CAPABILITY / TOOL / WORKSPACE / RESEARCH / GOAL).
        target: Registered capability or tool name (or workspace/research
            action key).
        inputs: Explicit parameter dict for the step (data only).
        depends_on: Step IDs that must complete before this step.
        description: Human-readable description.
    """

    step_id: str
    kind: NodeKind
    target: str
    inputs: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "kind": self.kind.value,
            "target": self.target,
            "inputs": dict(self.inputs),
            "depends_on": tuple(self.depends_on),
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class StepExecutionResult:
    """Deterministic result of executing one step.

    Attribution (``principal_id``, ``authority``, ``allowed``) is projected
    from the run's immutable SessionContext — never from handler output.
    """

    step_id: str
    kind: NodeKind
    target: str
    state: ExecutionState
    failure_kind: StepFailureKind | None = None
    output: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    execution_time_ms: float = 0.0
    principal_id: str | None = None
    authority: str | None = None
    allowed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def completed(self) -> bool:
        return self.state is ExecutionState.COMPLETED

    @property
    def failed(self) -> bool:
        return self.state is ExecutionState.FAILED

    @property
    def skipped(self) -> bool:
        return self.state is ExecutionState.SKIPPED

    @property
    def blocked(self) -> bool:
        return self.state is ExecutionState.BLOCKED

    def to_dict(self) -> dict[str, Any]:
        fk = self.failure_kind
        fk_value = None
        if fk is not None:
            fk_value = fk.value if hasattr(fk, "value") else str(fk)
        return {
            "step_id": self.step_id,
            "kind": self.kind.value,
            "target": self.target,
            "state": self.state.value,
            "failure_kind": fk_value,
            "output": dict(self.output),
            "error": self.error,
            "execution_time_ms": round(self.execution_time_ms, 3),
            "principal_id": self.principal_id,
            "authority": self.authority,
            "allowed": self.allowed,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    """Structured, inspectable result of a full orchestration run.

    Consumable by B2.3 (reporting) and B2.4 (experience capture).
    """

    run_id: str
    status: ExecutionStatus
    steps: tuple[StepExecutionResult, ...] = ()
    error: str = ""
    session_id: str | None = None
    principal_id: str | None = None
    authority: str | None = None
    required_authority: str = "user"
    max_steps: int = 0
    continue_on_failure: bool = False
    elapsed_ms: float = 0.0
    created_at: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def completed_count(self) -> int:
        return sum(1 for s in self.steps if s.completed)

    @property
    def failed_count(self) -> int:
        return sum(1 for s in self.steps if s.failed)

    @property
    def skipped_count(self) -> int:
        return sum(1 for s in self.steps if s.skipped)

    @property
    def blocked_count(self) -> int:
        return sum(1 for s in self.steps if s.blocked)

    @property
    def all_completed(self) -> bool:
        return bool(self.steps) and all(s.completed for s in self.steps)

    @property
    def failure_kinds(self) -> tuple[str, ...]:
        vals: set[str] = set()
        for step in self.steps:
            fk = getattr(step, "failure_kind", None)
            if fk is None:
                continue
            vals.add(fk.value if hasattr(fk, "value") else str(fk))
        return tuple(sorted(vals))

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "steps": tuple(s.to_dict() for s in self.steps),
            "error": self.error,
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "blocked_count": self.blocked_count,
            "session_id": self.session_id,
            "principal_id": self.principal_id,
            "authority": self.authority,
            "required_authority": self.required_authority,
            "max_steps": self.max_steps,
            "continue_on_failure": self.continue_on_failure,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "created_at": self.created_at.isoformat(),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    """A bounded request to execute an orchestration plan or explicit steps.

    ``steps`` takes precedence over ``plan`` when non-empty. The executor
    never synthesizes steps that were not present in the request.

    Attributes:
        plan: A B2.1 OrchestrationPlan whose graph nodes become steps 1:1.
        steps: Explicit steps (used when non-empty).
        session_context: The B1.2 attribution envelope (REQUIRED; missing
            fails closed at run level).
        required_authority: Minimum AuthorityLevel for every step. Comes
            from the request, never from user-provided text or a plan step.
        max_steps: Bound on executed steps (default 10).
        continue_on_failure: When False (default), the run stops at the
            first failed step. Authority failures are ALWAYS terminal.
        metadata: Additional context.
    """

    plan: OrchestrationPlan | None = None
    steps: tuple[ExecutionStep, ...] = ()
    session_context: SessionContext | None = None
    required_authority: AuthorityLevel = AuthorityLevel.USER
    max_steps: int = 10
    continue_on_failure: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.max_steps, int) or self.max_steps < 1:
            raise ValueError("max_steps must be a positive integer (fail-closed)")
        if not isinstance(self.required_authority, AuthorityLevel):
            raise ValueError("required_authority must be an AuthorityLevel (fail-closed)")


def new_run_id() -> str:
    return str(uuid.uuid4())
