"""Atlas Evolution — Development Authorization (Phase 5.2).

A distinct, deterministic authorization representation that separates:

  * OWNER (human) approval of a development proposal, and
  * bounded **Development Envelope** authorization of sandbox-only development.

It deliberately does NOT overload :class:`~atlas.evolution.models.ProposalStatus.APPROVED`.
An OWNER authorization accompanies ``ProposalStatus.APPROVED``; an envelope
authorization accompanies ``ProposalStatus.SANDBOX_AUTHORIZED`` and can NEVER
authorize promotion or any live-repository mutation.

Pure data + deterministic helpers. No AI, no network, no storage, no kernel.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class DevelopmentAuthorizationMode(str, Enum):
    """Who authorized the bounded sandbox development action."""

    OWNER = "owner"        # human OWNER approval (ProposalStatus.APPROVED)
    ENVELOPE = "envelope"  # bounded Development Envelope (SANDBOX_AUTHORIZED)


OWNER_PRINCIPAL: str = "user:owner"
ENVELOPE_PRINCIPAL: str = "system:development-envelope"


def _stable_id(seed: str) -> str:
    """Deterministic short identifier for a seed string."""
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _proposal_fingerprint(proposal: Any) -> str:
    """Best-effort deterministic fingerprint of a proposal's content."""
    fingerprint = getattr(proposal, "proposal_fingerprint", "") or ""
    if fingerprint:
        return str(fingerprint)
    compute = getattr(proposal, "compute_fingerprint", None)
    if callable(compute):
        try:
            return str(compute())
        except Exception:
            return ""
    return ""


@dataclass(frozen=True, slots=True)
class DevelopmentAuthorization:
    """A bounded development authorization bound to one proposal version.

    Attributes:
        authorization_id: Deterministic identifier.
        proposal_id: The proposal this authorization applies to.
        proposal_fingerprint: Proposal content fingerprint (binds the grant
            to an exact proposal version; a changed proposal invalidates it).
        mode: OWNER or ENVELOPE.
        authorized_by: ``user:owner`` or ``system:development-envelope``.
        granted_at: When the authorization was granted.
        expires_at: Envelope-TTL expiry (``None`` for OWNER authorizations).
        policy_ref: Reference into the Development Envelope policy.
        scope_fingerprint: Optional scope binding.
        comment: Optional human/system note.
    """

    authorization_id: str
    proposal_id: str
    proposal_fingerprint: str = ""
    mode: DevelopmentAuthorizationMode = DevelopmentAuthorizationMode.OWNER
    authorized_by: str = OWNER_PRINCIPAL
    granted_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None
    policy_ref: str = ""
    scope_fingerprint: str = ""
    comment: str = ""

    @property
    def is_owner(self) -> bool:
        """True only for a human OWNER authorization."""
        return self.mode is DevelopmentAuthorizationMode.OWNER

    def is_expired(self, now: datetime | None = None) -> bool:
        """True when an envelope authorization's TTL has elapsed."""
        if self.expires_at is None:
            return False
        return (now or datetime.now()) > self.expires_at

    def is_valid_for(self, proposal: Any, now: datetime | None = None) -> bool:
        """True when this authorization is valid for ``proposal`` right now.

        Valid == same proposal id + matching fingerprint + not expired. A
        missing/empty fingerprint never validates (fail-closed).
        """
        if proposal is None:
            return False
        if getattr(proposal, "proposal_id", "") != self.proposal_id:
            return False
        if not self.proposal_fingerprint:
            return False
        if _proposal_fingerprint(proposal) != self.proposal_fingerprint:
            return False
        return not self.is_expired(now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorization_id": self.authorization_id,
            "proposal_id": self.proposal_id,
            "proposal_fingerprint": self.proposal_fingerprint,
            "mode": self.mode.value,
            "authorized_by": self.authorized_by,
            "granted_at": self.granted_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "policy_ref": self.policy_ref,
            "scope_fingerprint": self.scope_fingerprint,
            "comment": self.comment,
        }


def build_development_authorization(
    proposal: Any,
    *,
    mode: DevelopmentAuthorizationMode,
    granted_at: datetime,
    ttl_minutes: int | None = None,
    policy_ref: str = "",
    comment: str = "",
) -> DevelopmentAuthorization:
    """Build a deterministic authorization for ``proposal``.

    OWNER authorizations never expire; ENVELOPE authorizations require a
    positive ``ttl_minutes`` (fail-closed otherwise).
    """
    proposal_id = str(getattr(proposal, "proposal_id", "") or "")
    fingerprint = _proposal_fingerprint(proposal)
    if mode is DevelopmentAuthorizationMode.ENVELOPE:
        if not ttl_minutes or ttl_minutes <= 0:
            raise ValueError(
                "ENVELOPE authorization requires a positive ttl_minutes"
            )
        expires_at: datetime | None = granted_at + timedelta(minutes=ttl_minutes)
        authorized_by = ENVELOPE_PRINCIPAL
    else:
        expires_at = None
        authorized_by = OWNER_PRINCIPAL
    authorization_id = "devauth:" + _stable_id(
        f"{proposal_id}:{fingerprint}:{mode.value}:{granted_at.isoformat()}:{policy_ref}"
    )
    return DevelopmentAuthorization(
        authorization_id=authorization_id,
        proposal_id=proposal_id,
        proposal_fingerprint=fingerprint,
        mode=mode,
        authorized_by=authorized_by,
        granted_at=granted_at,
        expires_at=expires_at,
        policy_ref=policy_ref,
        comment=comment,
    )
