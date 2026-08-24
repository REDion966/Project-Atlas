"""Atlas Post-Core F2 — Freshness Policy.

Deterministic, injectable freshness thresholds. A policy describes when a
knowledge artifact is considered FRESH/STALE/UNCERTAIN and which F1
EnvironmentChange will invalidate what. It never assesses anything itself (the
``KnowledgeFreshnessAssessor`` consumes it).

Bounds:
* max_source_age
* max_verification_age
* min_confidence
* missing_provenance_status            (default UNCERTAIN)
* low_confidence_status                (default UNCERTAIN)
* environment_invalidated_status       (default STALE)
* invalidating_domains: frozenset[str]  (domain-name vocabulary)
* invalidating_entity_keys: frozenset[str]

No hard-coded global assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from atlas.evolution.freshness.models import FreshnessStatus


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    """Deterministic freshness policy.

    A policy is pure config: it owns no assessor, imports no research/external
    surface, and never executes anything.
    """

    max_source_age: timedelta
    max_verification_age: timedelta
    min_confidence: float
    missing_provenance_status: FreshnessStatus = FreshnessStatus.UNCERTAIN
    low_confidence_status: FreshnessStatus = FreshnessStatus.UNCERTAIN
    environment_invalidated_status: FreshnessStatus = FreshnessStatus.STALE
    invalidating_domains: frozenset[str] = frozenset()
    invalidating_entity_keys: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.max_source_age <= timedelta(0):
            raise ValueError("max_source_age must be positive")
        if self.max_verification_age <= timedelta(0):
            raise ValueError("max_verification_age must be positive")
        if not (0.0 <= self.min_confidence <= 1.0):
            raise ValueError("min_confidence must be in [0.0, 1.0]")
        for name in (
            "missing_provenance_status",
            "low_confidence_status",
            "environment_invalidated_status",
        ):
            if not isinstance(getattr(self, name), FreshnessStatus):
                raise ValueError(f"{name} must be a FreshnessStatus")