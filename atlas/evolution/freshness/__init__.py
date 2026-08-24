"""Atlas Post-Core F2 — Knowledge Freshness & Provenance Foundation.

Deterministic freshness/provenance overlay that consumes F1
``EnvironmentChange`` records and existing-knowledge provenance metadata to
produce bounded stale-knowledge candidates for a future governed adaptation
engine (F3/F4).

Reuses — never duplicates — the existing:
  * research provenance models (KnowledgeClaim / CitationRecord /
    ClaimVerification / ResearchSource)
  * F1 environment models (EnvironmentChange / EnvironmentEntity)

F2 performs NO research, NO mutation, NO governance, NO adaptation.
"""

from atlas.evolution.freshness.models import (
    FreshnessReason,
    FreshnessStatus,
    KnowledgeFreshnessAssessment,
    KnowledgeRef,
    RecommendedAction,
    StaleKnowledgeCandidate,
    coerce_utc,
    utc_now,
)
from atlas.evolution.freshness.policy import FreshnessPolicy
from atlas.evolution.freshness.assessor import (
    DEFAULT_POLICY,
    KnowledgeFreshnessAssessor,
)

__all__ = [
    "DEFAULT_POLICY",
    "FreshnessPolicy",
    "FreshnessReason",
    "FreshnessStatus",
    "KnowledgeFreshnessAssessment",
    "KnowledgeFreshnessAssessor",
    "KnowledgeRef",
    "RecommendedAction",
    "StaleKnowledgeCandidate",
    "coerce_utc",
    "utc_now",
]