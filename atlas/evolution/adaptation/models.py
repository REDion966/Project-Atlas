"""Atlas Post-Core F4 — Adaptation Decision Models.

Pure data models for the governed adaptation decision layer.

These models reuse (never duplicate) the existing:
  * F3 ``LifecycleAssessment`` / ``LifecycleAction`` / ``LifecycleReason``
  * existing ``EvolutionProposal`` / ``ImprovementPlan`` / ``ProposalStatus``

``AdaptationProposalCandidate`` is the smallest pure intermediate between a
deterministic lifecycle assessment and the EXISTING ``EvolutionProposal``
boundary. It is NOT an ``EvolutionProposal`` and is never approved/executed
here. Only an existing governance/approval flow may convert a candidate into
an approved proposal.

Pure data. No logic beyond shape validation. No infrastructure. No AI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from atlas.evolution.lifecycle.models import (
    LifecycleAction,
    LifecycleReason,
    LifecycleTargetKind,
)


def utc_now() -> datetime:
    """Return the current time as a UTC-aware datetime."""
    return datetime.now(timezone.utc)


class AdaptationRisk(Enum):
    """Deterministic risk classification of a proposal candidate.

    These are recommendation risks only — they never authorize anything.
    """

    LOW = "LOW"       # Reversible / non-executing review or deprecation
    MEDIUM = "MEDIUM" # Capability/tool/model replacement or fallback
    HIGH = "HIGH"     # Affects core behavior / runtime / governance


class AdaptationProposalCandidate:
    """Bounded, deterministic candidate for a future governed proposal.

    Attributes:
        candidate_id: Deterministic identity (target key + action). Never a
            random UUID.
        target_kind / target_identifier / target_key: Assessed F3 target.
        action: Assessed deterministic lifecycle action.
        reason: Primary deterministic reason.
        reasons: All deterministic reasons.
        priority: Bounded confidence/severity in [0.0, 1.0].
        risk: Deterministic risk classification.
        evidence_change_ids: F1 environment-change evidence IDs.
        evidence_knowledge_ids: F2 freshness/knowledge evidence IDs.
        title / objective / rationale / expected_benefit: deterministic text.
        proposed_scope: Governed scope string (e.g. ``CAPABILITY``).
        recommended_validation: Human-readable validation approach.
        metadata: Optional bounded extra context.
    """

    __slots__ = (
        "candidate_id", "target_kind", "target_identifier", "target_key",
        "action", "reason", "reasons", "priority", "risk",
        "evidence_change_ids", "evidence_knowledge_ids",
        "title", "objective", "rationale", "expected_benefit",
        "proposed_scope", "recommended_validation", "metadata",
    )

    def __init__(
        self,
        *,
        target_kind: LifecycleTargetKind,
        target_identifier: str,
        action: LifecycleAction,
        reason: LifecycleReason,
        priority: float,
        risk: AdaptationRisk,
        reasons: tuple[LifecycleReason, ...] = (),
        evidence_change_ids: tuple[str, ...] = (),
        evidence_knowledge_ids: tuple[str, ...] = (),
        candidate_id: str = "",
        title: str = "",
        objective: str = "",
        rationale: str = "",
        expected_benefit: str = "",
        proposed_scope: str = "",
        recommended_validation: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not isinstance(target_kind, LifecycleTargetKind):
            raise TypeError("target_kind must be a LifecycleTargetKind")
        if not isinstance(target_identifier, str) or not target_identifier.strip():
            raise ValueError("target_identifier must be a non-empty string")
        if not (0.0 <= priority <= 1.0):
            raise ValueError("priority must be within [0.0, 1.0]")
        self.target_kind = target_kind
        self.target_identifier = target_identifier
        self.target_key = f"{target_kind.name}:{target_identifier}"
        self.action = action
        self.reason = reason
        self.priority = priority
        self.risk = risk
        self.reasons = tuple(reasons) if reasons else (reason,)
        self.evidence_change_ids = tuple(dict.fromkeys(evidence_change_ids))
        self.evidence_knowledge_ids = tuple(dict.fromkeys(evidence_knowledge_ids))
        self.candidate_id = (
            candidate_id or f"ADAPT-{self.target_key}:{action.name}"
        )
        self.title = title or f"[Adaptation] {action.name} {self.target_key}"
        self.objective = objective or (
            f"Assess and prepare {action.name.lower()} of "
            f"{self.target_key} for governed review."
        )
        self.rationale = rationale or (
            f"Lifecycle action {action.name} recommended for "
            f"{self.target_key} with priority {priority:.2f}."
        )
        self.expected_benefit = expected_benefit or (
            f"Keep {self.target_key} aligned with the current environment "
            f"and knowledge."
        )
        self.proposed_scope = proposed_scope or target_kind.name
        self.recommended_validation = recommended_validation or "governed-review"
        self.metadata = dict(metadata or {})

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"AdaptationProposalCandidate("
            f"target={self.target_key!r}, action={self.action.name!r}, "
            f"priority={self.priority:.2f}, risk={self.risk.value!r})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AdaptationProposalCandidate):
            return NotImplemented
        return self.candidate_id == other.candidate_id

    def __hash__(self) -> int:
        return hash(self.candidate_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "target_kind": self.target_kind.name,
            "target_identifier": self.target_identifier,
            "target_key": self.target_key,
            "action": self.action.name,
            "reason": self.reason.name,
            "priority": self.priority,
            "risk": self.risk.value,
            "reasons": [r.name for r in self.reasons],
            "evidence_change_ids": list(self.evidence_change_ids),
            "evidence_knowledge_ids": list(self.evidence_knowledge_ids),
            "title": self.title,
            "objective": self.objective,
            "rationale": self.rationale,
            "expected_benefit": self.expected_benefit,
            "proposed_scope": self.proposed_scope,
            "recommended_validation": self.recommended_validation,
        }