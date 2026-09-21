"""Atlas Evolution — Development Usefulness Assessment (Phase 5.2).

Replaces the hard-coded development ``effectiveness_proxy`` with a structured,
EVIDENCE-BASED assessment. The primary artifact is the structured fields
(objective, demonstrated capability improvement, regression evidence,
reproducibility, verification evidence); a bounded numeric
``effectiveness_score`` is a DERIVED summary only.

Deterministic and model-free. Stdlib only. No AI, no network, no storage.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class UsefulnessOutcome(str, Enum):
    """Overall usefulness verdict (evidence-backed)."""

    USEFUL = "useful"
    PARTIAL = "partial"
    LIMITED = "limited"
    INCONCLUSIVE = "inconclusive"


class CapabilityImprovement(str, Enum):
    """Whether the requested capability was demonstrably gained."""

    DEMONSTRATED = "demonstrated"
    REGRESSED = "regressed"
    UNCHANGED = "unchanged"
    UNKNOWN = "unknown"


def _stable_id(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class UsefulnessAssessment:
    """Structured, evidence-based usefulness judgment of one development run."""

    assessment_id: str
    proposal_id: str
    objective: str
    outcome: UsefulnessOutcome
    capability_improvement: CapabilityImprovement
    verification_status: str = ""
    regression_evidence: str = ""
    reproducibility: str = ""
    evidence_summary: str = ""
    evidence_count: int = 0
    evidence_quality: float = 0.0
    regression_risk: float = 0.0
    effectiveness_score: float = 0.0
    confidence: float = 0.0
    assessed_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "proposal_id": self.proposal_id,
            "objective": self.objective,
            "outcome": self.outcome.value,
            "capability_improvement": self.capability_improvement.value,
            "verification_status": self.verification_status,
            "regression_evidence": self.regression_evidence,
            "reproducibility": self.reproducibility,
            "evidence_summary": self.evidence_summary,
            "evidence_count": self.evidence_count,
            "evidence_quality": round(self.evidence_quality, 4),
            "regression_risk": round(self.regression_risk, 4),
            "effectiveness_score": round(self.effectiveness_score, 4),
            "confidence": round(self.confidence, 4),
            "assessed_at": self.assessed_at.isoformat(),
        }


def _capability_improvement(
    before: bool | None, after: bool | None
) -> CapabilityImprovement:
    if before is None or after is None:
        return CapabilityImprovement.UNKNOWN
    if not before and after:
        return CapabilityImprovement.DEMONSTRATED
    if before and not after:
        return CapabilityImprovement.REGRESSED
    return CapabilityImprovement.UNCHANGED


def assess_usefulness(
    *,
    proposal_id: str,
    objective: str,
    verification_status: str = "",
    capability_present_before: bool | None = None,
    capability_present_after: bool | None = None,
    regression_detected: bool = False,
    regression_detail: str = "",
    reproducible: bool | None = None,
    evidence_count: int = 0,
    now: datetime | None = None,
) -> UsefulnessAssessment:
    """Deterministically assess whether a completed change was useful.

    Evidence categories (all required inputs to the verdict):
      * objective — what was asked for;
      * demonstrated capability improvement (absent-before/present-after);
      * regression evidence;
      * reproducibility (bounded deterministic repeat);
      * verification evidence (``DevelopmentVerification`` status).
    """
    verified = str(verification_status or "").lower() == "verified"
    improvement = _capability_improvement(
        capability_present_before, capability_present_after
    )

    # --- verdict (deterministic precedence) --------------------------------
    if not verified:
        outcome = UsefulnessOutcome.INCONCLUSIVE
    elif improvement is CapabilityImprovement.REGRESSED:
        outcome = UsefulnessOutcome.LIMITED
    elif improvement is CapabilityImprovement.DEMONSTRATED:
        outcome = (
            UsefulnessOutcome.PARTIAL if regression_detected
            else UsefulnessOutcome.USEFUL
        )
    elif regression_detected:
        outcome = UsefulnessOutcome.LIMITED
    else:
        outcome = UsefulnessOutcome.LIMITED

    # --- derived numeric summary (bounded) --------------------------------
    score = 0.0
    if verified:
        score += 0.4
    if improvement is CapabilityImprovement.DEMONSTRATED:
        score += 0.4
    elif improvement is CapabilityImprovement.UNCHANGED:
        score += 0.2
    if reproducible is True:
        score += 0.2
    elif reproducible is False:
        score -= 0.1
    if regression_detected:
        score -= 0.35
    if improvement is CapabilityImprovement.REGRESSED:
        score -= 0.2
    score = max(0.0, min(1.0, score))
    if outcome is UsefulnessOutcome.INCONCLUSIVE:
        score = min(score, 0.4)

    reproducible_text = (
        "not_applicable" if reproducible is None
        else ("reproduced" if reproducible else "not_reproduced")
    )
    regression_text = (
        regression_detail.strip()
        or ("regression detected" if regression_detected else "no regression detected")
    )
    summary = (
        f"objective={objective or '(unspecified)'}; "
        f"capability_improvement={improvement.value}; "
        f"verification={verification_status or 'unknown'}; "
        f"regression={regression_text}; "
        f"reproducibility={reproducible_text}"
    )

    try:
        count = max(0, int(evidence_count))
    except (TypeError, ValueError):
        count = 0
    quality = min(1.0, 0.25 * count) if count else 0.0
    confidence = round(min(1.0, 0.3 + 0.7 * quality), 4)

    stamp = now or datetime.now()
    return UsefulnessAssessment(
        assessment_id="useful:" + _stable_id(
            f"{proposal_id}:{objective}:{improvement.value}:{verification_status}:{regression_detected}"
        ),
        proposal_id=proposal_id,
        objective=objective,
        outcome=outcome,
        capability_improvement=improvement,
        verification_status=verification_status,
        regression_evidence=regression_text,
        reproducibility=reproducible_text,
        evidence_summary=summary,
        evidence_count=count,
        evidence_quality=quality,
        regression_risk=1.0 if regression_detected else 0.0,
        effectiveness_score=score,
        confidence=confidence,
        assessed_at=stamp,
    )
