"""
Atlas Evolution — Development Plan Models — Phase E3

Pure data models for the development task planning layer.

A DevelopmentPlan is produced by DevelopmentPlanner from an approved
EvolutionProposal. It contains an ordered sequence of DevelopmentSteps
that carry only the information required by the current architecture.

The plan is an inspectable, deterministic bridge between:

    EvolutionProposal (approved)
        → DevelopmentPlan
        → ordered DevelopmentSteps
        → E2 sandbox execution primitives (future)

Pure data. No business logic. No infrastructure. No AI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


# ---------------------------------------------------------------------------
# Step phase enumeration
# ---------------------------------------------------------------------------


class StepPhase(Enum):
    """The lifecycle phase a DevelopmentStep belongs to.

    The seven phases mirror the E2 safety sequence:
    inspect → define → identify → test_spec → implement → verify → accept.
    """

    INSPECT = auto()        # Research existing implementation
    DEFINE = auto()         # Define the intended change
    IDENTIFY = auto()       # Identify affected files / resources
    TEST_SPEC = auto()      # Define verification / test requirement
    IMPLEMENT = auto()      # Implement change inside E2 sandbox
    VERIFY = auto()         # Verify in sandbox (read-back probe)
    ACCEPT = auto()         # Accept or roll back


class StepStatus(Enum):
    """Execution status of a DevelopmentStep."""

    PENDING = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
    FAILED = auto()
    SKIPPED = auto()


# ---------------------------------------------------------------------------
# DevelopmentStep
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DevelopmentStep:
    """A single ordered step in a DevelopmentPlan.

    Attributes:
        step_id:    Unique identifier within the plan, e.g. "STEP-001".
        phase:      Which lifecycle phase this step belongs to.
        order:      1-based execution order within the plan.
        objective:  Human-readable goal of this step.
        intent:     Implementation or verification intent (may be empty for
                    non-implementation phases).
        affected_files: Paths of files this step reads or modifies, when
                    known at plan time.  Empty list when unknown.
        depends_on: step_ids that must complete before this step starts.
        status:     Current execution status; always PENDING at plan time.
        metadata:   Optional additional context for the step.
    """

    step_id: str
    phase: StepPhase
    order: int
    objective: str
    intent: str = ""
    affected_files: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# DevelopmentPlan
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DevelopmentPlan:
    """An ordered, inspectable development task plan.

    Produced exclusively by DevelopmentPlanner.plan() from an approved
    EvolutionProposal.  Execution is NOT part of this model.

    Attributes:
        plan_id:       Unique identifier, e.g. "DEVPLAN-20260824-0001".
        proposal_id:   The EvolutionProposal this plan was derived from.
        title:         Concise title copied from the proposal.
        summary:       Human-readable summary of what this plan will do.
        steps:         Ordered DevelopmentSteps. Consumers must iterate in
                       ``step.order`` order.
        affected_files: Union of affected_files across all IMPLEMENT steps.
        created_at:    When the plan was created.
        metadata:      Optional additional context.
    """

    plan_id: str
    proposal_id: str
    title: str
    summary: str
    steps: list[DevelopmentStep] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    adjusted: bool = False  # L2: Whether this plan was autonomously adjusted
    adjustment_reason: str = ""  # L2: Reason for adjustment


# ---------------------------------------------------------------------------
# E5 — Development outcome and workload models
# ---------------------------------------------------------------------------


class DevelopmentOutcomeStatus(Enum):
    """Terminal status of a development run / iteration.

    ``SUCCESS`` — the change was implemented, verified, and tests passed
        inside the sandbox.
    ``FAILED`` — implementation or verification failed in the sandbox.
    ``GOVERNANCE_DENIED`` — the objective was not approved, or an explicit
        promotion gate refused promotion.
    ``INVALID_OBJECTIVE`` — the proposal or workload is malformed.
    ``ITERATIONS_EXHAUSTED`` — the iteration budget was consumed without
        success.
    ``UNAVAILABLE_CAPABILITY`` — a required capability (implementer or
        verifier) is unavailable.
    """

    SUCCESS = auto()
    FAILED = auto()
    GOVERNANCE_DENIED = auto()
    INVALID_OBJECTIVE = auto()
    ITERATIONS_EXHAUSTED = auto()
    UNAVAILABLE_CAPABILITY = auto()


@dataclass(frozen=True, slots=True)
class SandboxWorkload:
    """The sandbox content for one development iteration.

    Attributes:
        code_changes: Tuple of ``{"path": rel, "content": str}`` dicts —
            the implementation to apply inside the sandbox.
        test_files: Mapping of relative path → content for the tests that
            must pass before acceptance.
        verify_target: Optional confined relative path pytest should run
            against (empty string = whole workspace).
    """

    code_changes: tuple[dict[str, Any], ...] = ()
    test_files: dict[str, str] = field(default_factory=dict)
    verify_target: str = ""


@dataclass(frozen=True, slots=True)
class DevelopmentOutcome:
    """Bounded, secret-free record of one development iteration.

    Attributes:
        outcome: Terminal status of the iteration.
        proposal_id: The originating EvolutionProposal ID.
        plan_id: The DevelopmentPlan ID.
        iteration: 1-based iteration number within the run.
        message: Human-readable summary.
        changed_files: Relative paths applied inside the sandbox.
        verification_passed: Whether the E2 read-back probe passed.
        rollback_occurred: Whether the sandbox was restored after failure.
        test_outcome: pytest outcome (passed/failed/error/timeout/skipped).
        effectiveness_proxy: 1.0 on accepted success, 0.0 otherwise.
        recorded_at: When the outcome was recorded.
        metadata: Optional additional context (bounded, secret-free).
    """

    outcome: DevelopmentOutcomeStatus
    proposal_id: str
    plan_id: str
    iteration: int
    message: str = ""
    changed_files: list[str] = field(default_factory=list)
    verification_passed: bool = False
    rollback_occurred: bool = False
    test_outcome: str = ""
    effectiveness_proxy: float = 0.0
    recorded_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    autonomous: bool = False  # Whether this outcome was produced autonomously (L1/L2)
    chained_from: str | None = None  # L2: ID of previous workflow if chained
