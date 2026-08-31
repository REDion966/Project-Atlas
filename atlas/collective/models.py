"""Atlas Collective — Pure domain models (P4/Governed Collective Learning).

Bounded, frozen value objects for the collective-learning pipeline:

  Interaction record (principal-scoped)
    → Candidate collective record (bounded, provenance-preserving, CANDIDATE)
    → Governance approval  (OWNER-only, via existing ApprovalManager)
    → Collective knowledge (APPROVED, advisory only)

Design contract:
  * A candidate can be produced by any principal but can NEVER self-promote.
    Promotion requires OWNER authority through the existing AuthorityService
    → ApprovalManager seam.
  * Provenance is immutable and carried verbatim: the originating
    principal_id / authority / session_id / source / recorded_at survive
    candidate → collective promotion. Promotion changes STATUS, never identity.
  * Collective knowledge is advisory context, never an executable instruction.
    It carries no tool/capability/orchestration/dev/governance semantics.
  * No schema change, no migration, no AI dependency.

No infrastructure, no kernel, no runtime, no AI, no governance internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CollectiveKind(str, Enum):
    """What the candidate/collective record carries."""

    PREFERENCE = "preference"
    CORRECTION = "correction"
    INSIGHT = "insight"


class CollectiveStatus(str, Enum):
    """Lifecycle of a candidate / collective record."""

    CANDIDATE = "candidate"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class CollectiveProvenance:
    """Immutable per-record provenance carried into collective learning.

    Projected from a B3.1 PreferenceRecord / CorrectionRecord's Provenance at
    candidate-extraction time, plus the extraction timestamp. Provenance is
    never invented at promotion — promotion only transitions the status.

    Attributes:
        principal_id: The originating principal (scoping key).
        authority: The originating AuthorityLevel value (OWNER/USER).
        session_id: The originating session id.
        source: The originating capture source (e.g. "interaction").
        action: The originating capture action (e.g. "record_preference").
        recorded_at: When the underlying record was first captured.
        candidate_created_at: When the candidate was extracted.
    """

    principal_id: str
    authority: str
    session_id: str = ""
    source: str = ""
    action: str = ""
    recorded_at: datetime = field(default_factory=_utc_now)
    candidate_created_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "authority": self.authority,
            "session_id": self.session_id,
            "source": self.source,
            "action": self.action,
            "recorded_at": self.recorded_at.isoformat(),
            "candidate_created_at": self.candidate_created_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class CollectiveCandidate:
    """A bounded, provenance-preserving candidate for collective knowledge.

    Attributes:
        candidate_id: Stable unique id (monotonic).
        kind: PREFERENCE / CORRECTION / INSIGHT.
        key: Bounded structured summary key (e.g. preference key, correction target).
        value: Bounded structured summary value (e.g. preference value).
        description: Human-readable why-potentially-useful-collectively.
        evidence: Bounded structured evidence (e.g. source record provenance summary).
        provenance: The immutable origin provenance.
        source_record_id: The originating B3.1 record id.
        status: Always CANDIDATE while in this record.
        created_at: Candidate creation time (UTC).
        metadata: Optional bounded advisory metadata.
    """

    candidate_id: str
    kind: CollectiveKind
    key: str
    value: str
    description: str
    evidence: str
    provenance: CollectiveProvenance
    source_record_id: str
    status: CollectiveStatus = CollectiveStatus.CANDIDATE
    created_at: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "kind": self.kind.value,
            "key": self.key,
            "value": self.value,
            "description": self.description,
            "evidence": self.evidence,
            "provenance": self.provenance.to_dict(),
            "source_record_id": self.source_record_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class CollectiveKnowledge:
    """An approved, bounded, advisory collective-knowledge record.

    APPROVED copies of candidates. Never executable, never self-modifying.

    Attributes:
        knowledge_id: Stable unique id.
        candidate_id: The originating candidate id.
        kind / key / value / description / evidence: Copied from candidate.
        provenance: Copied verbatim from candidate (origin preserved).
        status: Always APPROVED.
        approved_at: When promotion was approved (UTC).
        approved_by: The approving principal id.
        metadata: Bounded advisory metadata (never executable).
    """

    knowledge_id: str
    candidate_id: str
    kind: CollectiveKind
    key: str
    value: str
    description: str
    evidence: str
    provenance: CollectiveProvenance
    status: CollectiveStatus = CollectiveStatus.APPROVED
    approved_at: datetime = field(default_factory=_utc_now)
    approved_by: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge_id": self.knowledge_id,
            "candidate_id": self.candidate_id,
            "kind": self.kind.value,
            "key": self.key,
            "value": self.value,
            "description": self.description,
            "evidence": self.evidence,
            "provenance": self.provenance.to_dict(),
            "status": self.status.value,
            "approved_at": self.approved_at.isoformat(),
            "approved_by": self.approved_by,
            "metadata": dict(self.metadata),
        }
