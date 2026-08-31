"""Atlas Interaction — Pure domain models (P3/B3.1).

Per-user preference and correction records with provenance. These are the
raw-material records that Phase 3 interaction learning will consume. This
module defines data types only: no infrastructure, no AI, no execution, no
storage.

Design contract:
  * Every record carries immutable provenance (principal + authority +
    session + action) so a preference/correction can never be self-elevating
    or unattributed.
  * Records are per-user: ``principal_id`` is the scoping key and is part of
    the record identity, never derived from free text.
  * Authority is the immutable ``AuthorityLevel`` on the originating
    SessionContext's principal (OWNER > USER), never from user input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _utc_now() -> datetime:
    """Return the current UTC-aware datetime."""
    return datetime.now(timezone.utc)


class InteractionKind(str, Enum):
    """The kind of an interaction record (preference or correction)."""

    PREFERENCE = "preference"
    CORRECTION = "correction"


@dataclass(frozen=True, slots=True)
class Provenance:
    """Immutable attribution envelope for an interaction record.

    Carries WHO acted (``principal_id``), at WHAT authority (``authority``,
    the immutable ``AuthorityLevel`` value of the originating session), in
    WHICH session (``session_id``), for WHAT action, and from WHERE
    (``source``). Provenance is projected from the P1 SessionContext — never
    derived from free text and never mutable after construction.
    """

    principal_id: str
    authority: str
    session_id: str = ""
    action: str = ""
    source: str = ""
    recorded_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe projection (attribution only)."""
        return {
            "principal_id": self.principal_id,
            "authority": self.authority,
            "session_id": self.session_id,
            "action": self.action,
            "source": self.source,
            "recorded_at": self.recorded_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class PreferenceRecord:
    """A single, bounded, per-user preference statement.

    Attributes:
        record_id: Stable unique id within the repository.
        principal_id: The owning user (scoping key; immutable).
        key: Bounded preference key (e.g. "response_length").
        value: Bounded preference value (e.g. "concise").
        provenance: Immutable attribution envelope.
    """

    record_id: str
    principal_id: str
    key: str
    value: str
    provenance: Provenance

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe projection."""
        return {
            "record_id": self.record_id,
            "kind": InteractionKind.PREFERENCE.value,
            "principal_id": self.principal_id,
            "key": self.key,
            "value": self.value,
            "provenance": self.provenance.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class CorrectionRecord:
    """A single, bounded, per-user correction of an Atlas mistake.

    Attributes:
        record_id: Stable unique id within the repository.
        principal_id: The owning user (scoping key; immutable).
        target: Bounded subject of the correction (what was wrong).
        description: Bounded description of the observed mistake.
        correction: Bounded correction the user provided.
        provenance: Immutable attribution envelope.
    """

    record_id: str
    principal_id: str
    target: str
    description: str
    correction: str
    provenance: Provenance

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe projection."""
        return {
            "record_id": self.record_id,
            "kind": InteractionKind.CORRECTION.value,
            "principal_id": self.principal_id,
            "target": self.target,
            "description": self.description,
            "correction": self.correction,
            "provenance": self.provenance.to_dict(),
        }
