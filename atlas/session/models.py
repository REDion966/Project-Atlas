"""Atlas Session — Session identity (P1/B1.2).

In-memory, immutable session abstraction. A Session is always bound to a
valid Principal via AuthorityService and never changes its principal.

No schema change, no persistence, no authentication — the session layer
exists so P2 can safely attribute Principal/User → Session → Conversation →
Context → Memory queries.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from atlas.authority.models import AuthorityLevel, Principal


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class Session:
    """Immutable session identity bound to a single Principal.

    Attributes:
        session_id: Stable unique id (uuid4 hex, assigned once).
        principal: The attributable Principal (frozen, never reassigned).
        created_at: When the session was created (UTC, attribution only).

    The ``principal`` reference is the source of truth for authority;
    ``principal_id`` and ``authority`` are derived read-only projections.
    """

    session_id: str
    principal: Principal
    created_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, str) or not self.session_id.strip():
            raise ValueError("session_id must be a non-empty string (fail-closed)")
        if not isinstance(self.principal, Principal):
            raise ValueError("principal must be a valid Principal (fail-closed)")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (fail-closed)")

    @property
    def principal_id(self) -> str:
        return self.principal.principal_id

    @property
    def authority(self) -> AuthorityLevel:
        return self.principal.authority

    @property
    def is_owner(self) -> bool:
        return self.principal.is_owner

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "principal_id": self.principal.principal_id,
            "principal": self.principal.to_dict(),
            "authority": self.principal.authority.value,
            "created_at": self.created_at.isoformat(),
        }


def new_session_id() -> str:
    return str(uuid.uuid4())
