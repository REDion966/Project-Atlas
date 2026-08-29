"""Atlas Authority — Pure domain models (P1/B1.1).

Explicit Owner / User / Authority foundation. This module defines the data
types only; it contains no business logic beyond minimal invariants, no
infrastructure, no AI, and no execution. It is the attribution layer that
future orchestration (P2) and session work (P1/B1.2) will consume.

Design contract:
  * Single logical Owner; ordinary Users are distinct and lower authority.
  * Authority is a deterministic total order (OWNER > USER).
  * Self-elevation is impossible by construction (authority is immutable on
    a principal).
  * Identity is attributable via stable ids and explicit labels.
  * Unknown principals carry no authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def _utc_now() -> datetime:
    """Return the current UTC-aware datetime."""
    return datetime.now(timezone.utc)


class AuthorityLevel(str, Enum):
    """The minimal authority tier for a principal.

    ``OWNER`` outranks ``USER``. There is intentionally no third tier in this
    foundation; future roles/permissions will build ON TOP of this distinction
    rather than replacing it.
    """

    OWNER = "owner"
    USER = "user"

    def __ge__(self, other: "AuthorityLevel") -> bool:
        """OWNER >= USER, USER >= USER; deterministic total order."""
        if not isinstance(other, AuthorityLevel):
            return NotImplemented
        return _RANK[self] >= _RANK[other]

    def __gt__(self, other: "AuthorityLevel") -> bool:
        if not isinstance(other, AuthorityLevel):
            return NotImplemented
        return _RANK[self] > _RANK[other]

    def __le__(self, other: "AuthorityLevel") -> bool:
        if not isinstance(other, AuthorityLevel):
            return NotImplemented
        return _RANK[self] <= _RANK[other]

    def __lt__(self, other: "AuthorityLevel") -> bool:
        if not isinstance(other, AuthorityLevel):
            return NotImplemented
        return _RANK[self] < _RANK[other]


#: Deterministic rank backing the authority total order.
_RANK: dict[AuthorityLevel, int] = {
    AuthorityLevel.USER: 0,
    AuthorityLevel.OWNER: 1,
}


@dataclass(frozen=True, slots=True)
class Principal:
    """A stable, attributable acting identity.

    ``authority`` is immutable: a Principal never changes authority after
    construction, which makes self-elevation impossible by construction. A
    User is distinguished from an Owner solely by ``authority``, so the two
    cannot be conflated.

    Attributes:
        principal_id: Stable unique id.
        name: Human-readable label (non-authoritative).
        authority: The immutable authority tier (OWNER or USER).
        created_at: When the principal was created (attribution only).
    """

    principal_id: str
    name: str
    authority: AuthorityLevel
    created_at: datetime = field(default_factory=_utc_now)

    @property
    def is_owner(self) -> bool:
        """True only when this principal is an Owner."""
        return self.authority is AuthorityLevel.OWNER

    def to_dict(self) -> dict:
        """JSON-safe, provenance-preserving projection."""
        return {
            "principal_id": self.principal_id,
            "name": self.name,
            "authority": self.authority.value,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class AuthorityContext:
    """Attribution envelope for an authority-sensitive action.

    Captures WHO acted, at WHAT authority level, and WHAT action was intended.
    It is pure data; it never performs the action or grants authority on its
    own. Future orchestration records this alongside each executed step.
    """

    principal: Principal
    action: str

    def satisfies(self, required: AuthorityLevel) -> bool:
        """Return True when the acting principal meets ``required``."""
        return self.principal.authority >= required

    def to_dict(self) -> dict:
        """JSON-safe projection of the attribution context."""
        return {
            "principal": self.principal.to_dict(),
            "authority": self.principal.authority.value,
            "action": self.action,
        }


@dataclass(frozen=True, slots=True)
class AuthorityDecision:
    """Deterministic result of an authority check (fail-closed default)."""

    allowed: bool
    required: AuthorityLevel
    held: AuthorityLevel
    reason: str = ""

    @property
    def denied(self) -> bool:
        """True when the decision was refused."""
        return not self.allowed

    def to_dict(self) -> dict:
        """JSON-safe projection of the decision (for audit attachment)."""
        return {
            "allowed": self.allowed,
            "required": self.required.value,
            "held": self.held.value,
            "reason": self.reason,
        }
