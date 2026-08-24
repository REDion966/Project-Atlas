"""Atlas Post-Core F5 — Adaptation Evaluation & Feedback Models.

Pure data models for the deterministic observer/evaluator layer that closes
the governed adaptation loop:

    proposal
      -> approval decision
      -> execution outcome
      -> effectiveness evaluation      (this module's models)
      -> learning / memory
      -> future assessment (F2/F3 bridge signals)

F5 is an observer/evaluator, never an executor. These models carry only
bounded, secret-free records that the existing memory/outcome infrastructure
can persist.

Reuses (never creates a parallel subsystem):
  * existing ``ProposalStatus`` values (governance state)
  * existing ``DevelopmentOutcome`` / ``DevelopmentOutcomeStatus`` /
    ``effectiveness_proxy`` (Phase E execution outcomes)
  * existing ``EvolutionMemory.store_record`` and
    ``LearningMemory.store_recommendation`` (memory bridge)

Pure data. No logic beyond shape validation. No infrastructure. No AI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any


def utc_now() -> datetime:
    """Return the current time as a UTC-aware datetime."""
    return datetime.now(timezone.utc)


class AdaptationEvaluationState(Enum):
    """Deterministic evaluation state of one adaptation.

    Deliberately distinguishes governance outcome from technical outcome —
    a REJECTED proposal is a governance outcome, never a code failure.
    """

    NOT_EXECUTED = auto()             # DRAFT / PENDING_APPROVAL
    APPROVED_NOT_EXECUTED = auto()    # APPROVED, no execution outcome yet
    GOVERNANCE_REJECTED = auto()      # REJECTED (not a technical failure)
    DEFERRED = auto()                 # DEFERRED (no technical conclusion)
    SUPERSEDED = auto()               # SUPERSEDED (governance decision)
    SUCCESSFUL = auto()               # executed + verification passed
    FAILED = auto()                   # executed + verification failed


class AdaptationFeedbackSignal(Enum):
    """Deterministic feedback signal emitted after evaluating an outcome."""

    RETAIN = auto()          # successful adaptation; keep the change
    RECONSIDER = auto()      # failed; the target remains actionable
    INEFFECTIVE = auto()     # ran but low effectiveness / insufficient proof
    DEPRIORITIZE = auto()    # healthy; future lifecycle priority may drop
    REJECTED = auto()        # governance rejected; no technical conclusion
    DEFERRED = auto()        # governance deferred; no conclusion
    NOT_EXECUTED = auto()    # not yet executed; nothing to conclude
    SUPERSEDED = auto()      # superseded; no conclusion


@dataclass(frozen=True, slots=True)
class AdaptationEvaluation:
    """Deterministic evaluation of one proposal's lifecycle + outcome.

    Attributes:
        evaluation_id: Deterministic ID (``proposal_id`` + optional outcome).
        proposal_id: The originating EvolutionProposal ID.
        target_key: Canonical target key (e.g. ``MODEL:openai:gpt-4``).
        state: Lifecycle/execution state.
        effectiveness: Bounded effectiveness in [0.0, 1.0], or None when no
            execution exists.
        confidence: Bounded confidence in [0.0, 1.0].
        reason: Stable keyword-based reason (never free-form AI).
        approval_occurred: Whether approval (APPROVED) was observed.
        execution_occurred: Whether an execution outcome was attached.
        verification_passed: Whether E2 read-back verification passed.
        rollback_occurred: Whether the sandbox was restored after failure.
        evidence_change_ids: F1 environment-change evidence IDs.
        evidence_knowledge_ids: F2 freshness/knowledge evidence IDs.
        evaluated_at: UTC evaluation timestamp.
    """

    evaluation_id: str
    proposal_id: str
    target_key: str
    state: AdaptationEvaluationState
    effectiveness: float | None = None
    confidence: float = 0.0
    reason: str = ""
    outcome_id: str = ""
    approval_occurred: bool = False
    execution_occurred: bool = False
    verification_passed: bool | None = None
    rollback_occurred: bool | None = None
    evidence_change_ids: tuple[str, ...] = ()
    evidence_knowledge_ids: tuple[str, ...] = ()
    evaluated_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "proposal_id": self.proposal_id,
            "outcome_id": self.outcome_id,
            "target_key": self.target_key,
            "state": self.state.name,
            "effectiveness": self.effectiveness,
            "confidence": self.confidence,
            "reason": self.reason,
            "approval_occurred": self.approval_occurred,
            "execution_occurred": self.execution_occurred,
            "verification_passed": self.verification_passed,
            "rollback_occurred": self.rollback_occurred,
            "evidence_change_ids": list(self.evidence_change_ids),
            "evidence_knowledge_ids": list(self.evidence_knowledge_ids),
            "evaluated_at": self.evaluated_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class AdaptationFeedback:
    """Bounded, deterministic feedback for the F2/F3 reassessment bridges.

    Attributes:
        feedback_id: Deterministic ID (``evaluation_id``).
        proposal_id / target_key / outcome_id: Identity + provenance.
        signal: Deterministic feedback signal.
        retain_adaptation: True when the adaptation should stay.
        reconsider_adaptation: True when the adaptation should be reconsidered.
        appears_ineffective: True when effectiveness is low.
        freshness_signal: Deterministic F2 bridge signal
            (``"reassess"`` | ``"refresh"`` | ``"none"``).
        lifecycle_signal: Deterministic F3 bridge signal
            (``"reassess"`` | ``"deprioritize"`` | ``"prioritize"`` | ``"none"``).
        reason: Stable keyword reason.
        evidence_refs: Evidence/reference identifiers (never copied content).
        evaluated_at: UTC timestamp.
    """

    feedback_id: str
    proposal_id: str
    evaluation_id: str
    target_key: str
    outcome_id: str = ""
    signal: AdaptationFeedbackSignal = AdaptationFeedbackSignal.NOT_EXECUTED
    retain_adaptation: bool = False
    reconsider_adaptation: bool = False
    appears_ineffective: bool = False
    freshness_signal: str = "none"
    lifecycle_signal: str = "none"
    reason: str = ""
    evidence_refs: tuple[str, ...] = ()
    evaluated_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feedback_id": self.feedback_id,
            "proposal_id": self.proposal_id,
            "evaluation_id": self.evaluation_id,
            "outcome_id": self.outcome_id,
            "target_key": self.target_key,
            "signal": self.signal.name,
            "retain_adaptation": self.retain_adaptation,
            "reconsider_adaptation": self.reconsider_adaptation,
            "appears_ineffective": self.appears_ineffective,
            "freshness_signal": self.freshness_signal,
            "lifecycle_signal": self.lifecycle_signal,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
            "evaluated_at": self.evaluated_at.isoformat(),
        }