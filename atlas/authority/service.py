"""Atlas Authority — AuthorityService (P1/B1.1).

The composition-root-owned service that establishes exactly one logical Owner
and manages ordinary Users. It is the authority authority boundary that future
orchestration consumes. This module contains NO tool/code execution, no AI, no
governance bypass, and no authentication — it only enforces deterministic
authority invariants.

Invariants (encoded as behavior, not comments):
  * Owner outranks every User.
  * A User cannot elevate itself to Owner.
  * A User cannot satisfy an OWNER-only requirement.
  * There is at most one Owner; a second designation fails closed.
  * Unknown principals carry no authority.
  * Authority checks are deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from atlas.authority.models import (
    AuthorityContext,
    AuthorityDecision,
    AuthorityLevel,
    Principal,
)

#: Stable, reserved id for the single logical Owner. Immutable.
_OWNER_ID: str = "owner"


@dataclass(frozen=True, slots=True)
class _OwnerDesignation:
    """Audit-safe record of the active Owner designation."""

    name: str
    created_at: Any


@dataclass(slots=True)
class _UserRegistry:
    """Bounded in-memory registry of ordinary Users (keyed by id)."""

    _users: dict[str, Principal] = field(default_factory=dict)

    def add(self, principal: Principal) -> None:
        self._users[principal.principal_id] = principal

    def get(self, principal_id: str) -> Principal | None:
        return self._users.get(principal_id)

    def __contains__(self, principal_id: str) -> bool:
        return principal_id in self._users

    def __len__(self) -> int:
        return len(self._users)


class AuthorityService:
    """Establishes the single Owner and manages ordinary Users.

    The Owner is designated once during construction. A user may be added or
    resolved later. The service never executes tools or code and never imports
    or calls the evolution gateway/approval/sandbox/promotion machinery.

    Args:
        owner_name: Human-readable label for the Owner. Must be non-empty.
        audit_store: Optional duck-typed store exposing ``store_record``
            (the existing ``EvolutionMemory`` surface). When provided,
            authority-sensitive decisions are recorded as auditable
            ``EvolutionRecord`` entries. Fail-soft: audit failures never block
            the deterministic decision.
    """

    def __init__(self, owner_name: str, audit_store: Any = None) -> None:
        if not isinstance(owner_name, str) or not owner_name.strip():
            raise ValueError("owner_name must be a non-empty string (fail-closed)")
        self._owner = Principal(
            principal_id=_OWNER_ID,
            name=owner_name.strip(),
            authority=AuthorityLevel.OWNER,
        )
        self._users = _UserRegistry()
        self._audit_store = audit_store

    # -- Owner ---------------------------------------------------------------

    @property
    def owner(self) -> Principal:
        """Return the single logical Owner principal."""
        return self._owner

    # -- Users ---------------------------------------------------------------

    def add_user(self, name: str, principal_id: str | None = None) -> Principal:
        """Create an ordinary User (never an Owner).

        The returned principal has ``AuthorityLevel.USER`` and is immutable;
        there is no path through this API to produce a second Owner.
        """
        if not isinstance(name, str) or not name.strip():
            raise ValueError("user name must be a non-empty string (fail-closed)")
        principal_id = (principal_id or name.strip()).strip()
        if not principal_id:
            raise ValueError("principal_id must be non-empty (fail-closed)")
        if principal_id == _OWNER_ID:
            raise ValueError("a User cannot share the reserved owner id (fail-closed)")
        principal = Principal(
            principal_id=principal_id,
            name=name.strip(),
            authority=AuthorityLevel.USER,
        )
        self._users.add(principal)
        return principal

    def resolve(self, principal_id: str) -> Principal | None:
        """Resolve a principal by id, or ``None`` when unknown."""
        if not isinstance(principal_id, str):
            return None
        if principal_id == _OWNER_ID:
            return self._owner
        return self._users.get(principal_id)

    def get_user(self, principal_id: str) -> Principal | None:
        """Return a User by id (never the Owner)."""
        principal = self._users.get(principal_id)
        return principal

    def users(self) -> list[Principal]:
        """Return the ordered list of ordinary Users (deterministic)."""
        return sorted(
            self._users._users.values(),
            key=lambda p: (p.created_at, p.principal_id),
        )

    # -- Authority checks ----------------------------------------------------

    def check(
        self,
        principal_id: str,
        required: AuthorityLevel,
        action: str = "",
    ) -> AuthorityDecision:
        """Deterministically authorize ``principal_id`` for ``required``.

        Fail-closed: an unknown or missing principal is denied. The decision is
        audited best-effort through the injected audit store.
        """
        principal = self.resolve(principal_id)
        if principal is None:
            return self._decision(
                required,
                AuthorityLevel.USER,
                False,
                "unknown or missing principal",
                action,
            )
        allowed = principal.authority >= required
        reason = "" if allowed else f"requires {required.value} authority"
        return self._decision(required, principal.authority, allowed, reason, action)

    def assert_owner(self, principal_id: str, action: str = "") -> AuthorityDecision:
        """Shorthand OWNER-only check."""
        return self.check(principal_id, AuthorityLevel.OWNER, action)

    def require_owner(self, principal_id: str, action: str = "") -> None:
        """Raise ``PermissionError`` unless the principal is the Owner."""
        decision = self.assert_owner(principal_id, action)
        if decision.denied:
            raise PermissionError(decision.reason or "owner authority required")

    def context(self, principal_id: str, action: str) -> AuthorityContext | None:
        """Build an attribution context for an authority-sensitive action.

        Returns ``None`` (fail-closed) for unknown principals so that a missing
        actor can never be attributed authority.
        """
        principal = self.resolve(principal_id)
        if principal is None:
            return None
        return AuthorityContext(principal=principal, action=action)

    # -- Audit ---------------------------------------------------------------

    def _decision(
        self,
        required: AuthorityLevel,
        held: AuthorityLevel,
        allowed: bool,
        reason: str,
        action: str,
    ) -> AuthorityDecision:
        decision = AuthorityDecision(
            allowed=allowed,
            required=required,
            held=held,
            reason=reason,
        )
        self._audit(decision, action)
        return decision

    def _audit(self, decision: AuthorityDecision, action: str) -> None:
        """Record an authority decision via the existing audit store.

        Reuses the ``EvolutionRecord`` shape so authority decisions live in the
        same auditable surface as other evolution events. Best-effort only:
        an audit-store failure never changes the decision.
        """
        if self._audit_store is None or not hasattr(self._audit_store, "store_record"):
            return
        try:
            from atlas.evolution.models import EvolutionRecord

            record = EvolutionRecord(
                record_id=f"auth-{action or decision.held.value}-{decision.allowed}",
                event_type="authority_decision",
                description=(
                    f"authority check ({action or ''}) -> "
                    f"{'allowed' if decision.allowed else 'denied'}"
                ),
                metadata=decision.to_dict(),
            )
            self._audit_store.store_record(record)
        except Exception:
            # Audit persistence must never break the deterministic decision.
            return

    def summary(self) -> dict:
        """Return a bounded, JSON-safe summary of the authority state."""
        return {
            "owner": self._owner.to_dict(),
            "user_count": len(self._users),
        }
