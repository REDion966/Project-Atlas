"""Atlas Post-Core F2 — Knowledge Freshness & Provenance Models.

Pure data models for the deterministic freshness/provenance overlay.

These models reuse (never duplicate) the existing research/knowledge
provenance surface:

  * ``atlas.research.models.KnowledgeClaim`` / ``CitationRecord`` /
    ``ClaimVerification`` / ``ResearchSource``
  * ``atlas.evolution.environment.models.EnvironmentChange`` (F1)

``KnowledgeRef`` is a normalized, read-only projection of an existing
knowledge artifact (knowledge ID + provenance metadata). It is NOT a store —
callers build it from existing knowledge/claim/source objects. The assessor
never mutates the underlying artifacts.

Pure data. No logic beyond shape validation. No infrastructure. No AI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any


def utc_now() -> datetime:
    """Return the current time as a UTC-aware datetime (determinism-friendly)."""
    return datetime.now(timezone.utc)


def coerce_utc(value: datetime | None) -> datetime | None:
    """Return a UTC-aware datetime, attaching UTC when the input is naive.

    Existing research models create ``datetime.now()`` (naive) values, so
    age math against a UTC-aware ``now`` requires normalization.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class FreshnessStatus(Enum):
    """Deterministic freshness classification of one knowledge artifact."""

    FRESH = auto()
    STALE = auto()
    UNCERTAIN = auto()
    UNASSESSED = auto()


class FreshnessReason(Enum):
    """Deterministic reason why an artifact was (not) classified as fresh."""

    SOURCE_AGE = auto()          # Source/citation retrieved too long ago
    VERIFICATION_AGE = auto()    # Verification performed too long ago
    ENVIRONMENT_CHANGE = auto()  # A relevant F1 environment change occurred
    SOURCE_CHANGED = auto()      # The source environment/entity changed
    MISSING_PROVENANCE = auto()  # Provenance (retrieved/verified) is absent
    LOW_CONFIDENCE = auto()      # Confidence below the policy threshold
    POLICY_THRESHOLD = auto()    # A configured policy threshold was exceeded
    UNKNOWN = auto()             # No deterministic reason can be assigned


class RecommendedAction(Enum):
    """Recommended next step for a stale/uncertain candidate.

    Categories are deliberately coarse; the governed F3/F4 engine decides
    whether and how to act. This is never an authorization.
    """

    RESEARCH = auto()  # Re-research / re-retrieve the source
    VERIFY = auto()    # Re-verify an existing claim
    REVIEW = auto()    # Human/governed review is warranted
    NONE = auto()      # No action recommended


@dataclass(frozen=True, slots=True)
class KnowledgeRef:
    """Normalized, read-only projection of one knowledge artifact.

    Attributes:
        knowledge_id: Stable ID of the assessed artifact (entry/claim/record).
        domain: Optional subject domain (e.g. ``MODEL``, ``TOOL``). Must match
            the F1 ``EnvironmentDomain`` name vocabulary when cross-referencing.
        entity_key: Optional canonical subject key (e.g. ``MODEL:openai:gpt-4``).
        source_uris: Provenance source URIs (references, not full content).
        claim_id: Optional existing research claim ID.
        verification_id: Optional existing claim verification ID.
        retrieved_at: When the source was retrieved (UTC-normalized).
        verified_at: When the claim was verified (UTC-normalized).
        confidence: Optional confidence score (0.0 to 1.0).
        affected_domains: Domains the artifact depends on; an F1 change in one
            of these deterministically invalidates this artifact.
        affected_entity_keys: Subject keys the artifact depends on; an F1
            change of one of these deterministically invalidates this artifact.
        metadata: Optional bounded additional context.
    """

    knowledge_id: str
    domain: str = ""
    entity_key: str = ""
    source_uris: tuple[str, ...] = ()
    claim_id: str = ""
    verification_id: str = ""
    retrieved_at: datetime | None = None
    verified_at: datetime | None = None
    confidence: float | None = None
    affected_domains: frozenset[str] = frozenset()
    affected_entity_keys: frozenset[str] = frozenset()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.knowledge_id, str) or not self.knowledge_id.strip():
            raise ValueError("knowledge_id must be a non-empty string")
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be in [0.0, 1.0]")
        # Normalize timestamps to UTC at construction (no assessment mutation).
        if isinstance(self.retrieved_at, datetime):
            object.__setattr__(self, "retrieved_at", coerce_utc(self.retrieved_at))
        if isinstance(self.verified_at, datetime):
            object.__setattr__(self, "verified_at", coerce_utc(self.verified_at))


@dataclass(frozen=True, slots=True)
class KnowledgeFreshnessAssessment:
    """Deterministic freshness assessment of a single knowledge artifact.

    Attributes:
        knowledge_id: The assessed artifact.
        status: FRESH / STALE / UNCERTAIN / UNASSESSED.
        assessed_at: UTC assessment timestamp.
        retrieved_at: UTC source-retrieval timestamp (if available).
        verified_at: UTC verification timestamp (if available).
        confidence: Confidence used for the assessment (if available).
        triggering_environment_change_id: Optional ID of the F1 change that
            triggered/invalidated this assessment.
        triggering_environment_entity_key: Optional subject key of that change.
        reasons: Ordered tuple of ALL deterministic reasons (never only the
            first one found).
        source_uris: Provenance references preserved for downstream action.
        claim_id / verification_id: Existing provenance references.
        rationale: Stable, keyword-based rationale string (not free-form AI).
    """

    knowledge_id: str
    status: FreshnessStatus
    assessed_at: datetime
    retrieved_at: datetime | None = None
    verified_at: datetime | None = None
    confidence: float | None = None
    triggering_environment_change_id: str = ""
    triggering_environment_entity_key: str = ""
    reasons: tuple[FreshnessReason, ...] = ()
    source_uris: tuple[str, ...] = ()
    claim_id: str = ""
    verification_id: str = ""
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class StaleKnowledgeCandidate:
    """Bounded, deterministic candidate for future governed re-research.

    Attributes:
        knowledge_id: The artifact that may be stale.
        priority: Deterministic severity in [0.0, 1.0].
        recommended_action: RESEARCH / VERIFY / REVIEW / NONE.
        reasons: All deterministic reasons.
        provenance_refs: Tuple of URI/citation references.
        triggering_environment_change_id: Optional F1 change ID.
        triggering_environment_entity_key: Optional F1 entity key.
        rationale: Stable keyword-based rationale.
    """

    knowledge_id: str
    priority: float
    recommended_action: RecommendedAction
    reasons: tuple[FreshnessReason, ...] = ()
    provenance_refs: tuple[str, ...] = ()
    triggering_environment_change_id: str = ""
    triggering_environment_entity_key: str = ""
    rationale: str = ""