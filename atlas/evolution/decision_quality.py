"""Atlas Evolution — Decision Quality Scoring — Stage G.

A pure, deterministic, advisory scoring layer that synthesizes the
evidence Atlas already collects into bounded decision-quality metrics for
a development plan:

    confidence_score            from the kernel planning-context confidence
    historical_evidence_score   success ratio of previous attempts
    impact_score                repository dependency expansion magnitude
    risk_score                  unknown targets / prior failures
    research_evidence_strength  presence + confidence of F8 evidence
    final_priority_score        weighted combination of the above

Guarantees:

* Deterministic: identical inputs produce identical outputs.
* Bounded: every score is clamped to [0.0, 1.0].
* Advisory only: scores NEVER change approval, execution, or governance
  behavior; they are recorded as JSON-safe plan/proposal metadata so
  humans and future planners can reason about decision quality.
* Fail-soft: malformed or missing evidence degrades to neutral defaults.

Pure logic. No AI. No infrastructure. No side effects.
"""

from __future__ import annotations

from typing import Any

# Weighted-combination coefficients (sum to 1.0). Module-level constants:
# auditable, never per-request tunable.
WEIGHT_HISTORICAL: float = 0.35
WEIGHT_CONFIDENCE: float = 0.20
WEIGHT_RESEARCH: float = 0.15
WEIGHT_INVERSE_RISK: float = 0.15
WEIGHT_IMPACT: float = 0.15

NEUTRAL_SCORE: float = 0.5


def _clamp01(value: Any) -> float:
    """Clamp to [0.0, 1.0]; non-numeric input becomes 0.0."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    if value != value:  # NaN guard
        return 0.0
    return max(0.0, min(1.0, value))


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def compute_decision_quality(
    overall_confidence: float | None,
    previous_attempts: list[dict] | None,
    unknown_target_count: int,
    known_target_count: int,
    dependency_count: int,
    research_confidence: float | None,
    has_research_claim_support: bool,
) -> dict[str, float]:
    """
    Compute bounded advisory decision-quality scores.

    Args:
        overall_confidence: Kernel planning-context confidence [0..1]
            (None → neutral 0.5).
        previous_attempts: History-section attempt dicts, each carrying an
            ``outcome`` key ("success" vs anything else).
        unknown_target_count: Targets the repository map could not resolve.
        known_target_count: Targets successfully resolved against the map.
        dependency_count: Discovered transitive dependents (impact size).
        research_confidence: Confidence reported by F8 research (None → 0).
        has_research_claim_support: True when claims backed the findings.

    Returns:
        Dict of bounded floats plus the weighted ``final_priority_score``.
    """
    confidence_score = (
        NEUTRAL_SCORE if overall_confidence is None else _clamp01(overall_confidence)
    )

    attempts = [
        attempt
        for attempt in (previous_attempts or [])
        if isinstance(attempt, dict)
    ]
    successes = sum(
        1 for attempt in attempts if attempt.get("outcome") == "success"
    )
    failures = len(attempts) - successes
    historical_evidence_score = (
        successes / len(attempts) if attempts else NEUTRAL_SCORE
    )

    total_targets = _safe_int(known_target_count) + _safe_int(
        unknown_target_count
    )
    known = _safe_int(known_target_count)
    unknown = _safe_int(unknown_target_count)
    unknown_ratio = unknown / total_targets if total_targets else 0.0
    prior_failure_pressure = min(1.0, failures * 0.25) if attempts else 0.0
    risk_score = _clamp01(unknown_ratio * 0.6 + prior_failure_pressure * 0.4)

    impact_score = _clamp01(_safe_int(dependency_count) * 0.25)

    if research_confidence is None:
        research_strength = 0.0
    else:
        support = 1.0 if has_research_claim_support else 0.5
        research_strength = _clamp01(_clamp01(research_confidence) * support)

    final_priority_score = round(
        WEIGHT_HISTORICAL * historical_evidence_score
        + WEIGHT_CONFIDENCE * confidence_score
        + WEIGHT_RESEARCH * research_strength
        + WEIGHT_INVERSE_RISK * (1.0 - risk_score)
        + WEIGHT_IMPACT * impact_score,
        4,
    )
    final_priority_score = max(0.0, min(1.0, final_priority_score))

    return {
        "confidence_score": round(confidence_score, 4),
        "historical_evidence_score": round(historical_evidence_score, 4),
        "impact_score": round(impact_score, 4),
        "risk_score": round(risk_score, 4),
        "research_evidence_strength": round(research_strength, 4),
        "final_priority_score": final_priority_score,
    }