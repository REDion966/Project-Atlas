"""Atlas Evolution — Development Envelope & Authority (Phase 5.2).

A bounded, opt-in, revocable policy that authorizes ONLY sandbox-scoped
development. It is modelled on the existing ``AutonomyPolicy`` shapes
(enabled / allowed operations / risk ceiling / quota-per-window / TTL) but is
deliberately SEPARATE from the Phase-16 autonomy machinery:

  * it never routes through ``EvolutionAutonomyDispatcher`` or
    ``AuthorizationManager.authorize_autonomously`` (those remain untouched);
  * it authorizes only bounded sandbox development (``SANDBOX_AUTHORIZED``);
  * it can NEVER authorize promotion or any live-repository mutation.

Disabled by default. Fail-closed on every malformed/absent input.

Pure logic: stdlib only. No AI, no network, no storage, no kernel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from atlas.evolution.development_authorization import (
    DevelopmentAuthorization,
    DevelopmentAuthorizationMode,
    build_development_authorization,
)

#: The only operation class the envelope may authorize.
SANDBOX_DEVELOPMENT: str = "sandbox_development"

#: Operations the envelope must NEVER authorize (documented + enforced).
FORBIDDEN_OPERATIONS: frozenset[str] = frozenset(
    {
        "promotion",
        "live_repository_write",
        "governance_change",
        "authority_change",
        "config_change",
        "identity_change",
    }
)

_RISK_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass(frozen=True, slots=True)
class DevelopmentEnvelope:
    """Immutable, operator-configured development-authority policy.

    Attributes:
        enabled: Master switch (default False — no autonomy).
        allowed_operations: Operation classes the envelope may authorize.
        max_risk_level: Ceiling on the risk level of authorized work.
        max_runs_per_window: Quota; ``<= 0`` means "no autonomous runs".
        window_seconds: Quota window length; required for quota to apply.
        authorization_ttl_minutes: TTL applied to envelope authorizations.
        policy_ref: Stable reference recorded on authorizations/audit.
    """

    enabled: bool = False
    allowed_operations: frozenset[str] = frozenset({SANDBOX_DEVELOPMENT})
    max_risk_level: str = "low"
    max_runs_per_window: int = 0
    window_seconds: int | None = 3600
    authorization_ttl_minutes: int = 60
    policy_ref: str = "development-envelope"

    def __post_init__(self) -> None:
        if self.max_risk_level not in _RISK_RANK:
            raise ValueError(f"unknown max_risk_level: {self.max_risk_level!r}")
        if self.authorization_ttl_minutes < 1:
            raise ValueError("authorization_ttl_minutes must be >= 1")
        if self.max_runs_per_window < 0:
            raise ValueError("max_runs_per_window must be >= 0")
        if self.window_seconds is not None and self.window_seconds < 1:
            raise ValueError("window_seconds must be >= 1 when set")
        # Never allow a forbidden operation to be listed as permitted.
        overlap = set(self.allowed_operations) & FORBIDDEN_OPERATIONS
        if overlap:
            raise ValueError(
                f"forbidden operation(s) cannot be enabled: {sorted(overlap)}"
            )

    @classmethod
    def from_mapping(cls, data: Any) -> "DevelopmentEnvelope":
        """Build an envelope from a config mapping, fail-closed to disabled."""
        if not isinstance(data, dict):
            return cls()
        enabled = bool(data.get("enabled", False))
        raw_ops = data.get("allowed_operations", [SANDBOX_DEVELOPMENT])
        ops = frozenset(
            str(op) for op in (raw_ops if isinstance(raw_ops, (list, tuple, set)) else [])
        ) or frozenset({SANDBOX_DEVELOPMENT})
        ttl = data.get("authorization_ttl_minutes", 60)
        quota = data.get("max_runs_per_window", 0)
        window = data.get("window_seconds", 3600)
        return cls(
            enabled=enabled,
            allowed_operations=ops,
            max_risk_level=str(data.get("max_risk_level", "low")).lower(),
            max_runs_per_window=int(quota) if isinstance(quota, int) else 0,
            window_seconds=(
                int(window) if isinstance(window, int) and window > 0 else None
            ),
            authorization_ttl_minutes=int(ttl) if isinstance(ttl, int) and ttl > 0 else 60,
            policy_ref=str(data.get("policy_ref", "development-envelope")),
        )


@dataclass(frozen=True, slots=True)
class DevelopmentEnvelopeDecision:
    """Outcome of evaluating the envelope for one operation."""

    allowed: bool
    reason: str = ""
    requires_owner: bool = True


class DevelopmentAuthority:
    """Deterministic evaluation of the Development Envelope.

    Args:
        envelope: The immutable policy.
        now: Optional clock callable (injectable for tests).
        usage_provider: Optional callable returning the number of authorized
            runs already consumed in the current window (drives the quota).
            Defaults to ``0`` when unwired (fail-closed once quota is 0).
    """

    def __init__(
        self,
        envelope: DevelopmentEnvelope,
        *,
        now: Callable[[], datetime] | None = None,
        usage_provider: Callable[[], int] | None = None,
    ) -> None:
        self._envelope = envelope or DevelopmentEnvelope()
        self._now = now or datetime.now
        self._usage = usage_provider

    @property
    def envelope(self) -> DevelopmentEnvelope:
        return self._envelope

    def check(self, operation: str = SANDBOX_DEVELOPMENT) -> DevelopmentEnvelopeDecision:
        """Return whether the envelope permits ``operation`` (fail-closed)."""
        env = self._envelope
        if not env.enabled:
            return DevelopmentEnvelopeDecision(False, "envelope disabled", True)
        if operation in FORBIDDEN_OPERATIONS:
            return DevelopmentEnvelopeDecision(
                False, f"operation '{operation}' is outside the envelope", True
            )
        if operation not in env.allowed_operations:
            return DevelopmentEnvelopeDecision(
                False, f"operation '{operation}' not permitted", True
            )
        if env.window_seconds is None:
            return DevelopmentEnvelopeDecision(
                False, "quota window is not configured", True
            )
        if env.max_runs_per_window <= 0:
            return DevelopmentEnvelopeDecision(False, "quota is zero", True)
        used = self._usage() if callable(self._usage) else 0
        try:
            used = int(used)
        except (TypeError, ValueError):
            used = env.max_runs_per_window  # fail-closed
        if used >= env.max_runs_per_window:
            return DevelopmentEnvelopeDecision(False, "quota exhausted", True)
        return DevelopmentEnvelopeDecision(True, "", False)

    def authorize(self, proposal: Any) -> DevelopmentAuthorization | None:
        """Return an ENVELOPE authorization for ``proposal``, or ``None``."""
        decision = self.check(SANDBOX_DEVELOPMENT)
        if not decision.allowed:
            return None
        granted_at = self._now()
        return build_development_authorization(
            proposal,
            mode=DevelopmentAuthorizationMode.ENVELOPE,
            granted_at=granted_at,
            ttl_minutes=self._envelope.authorization_ttl_minutes,
            policy_ref=self._envelope.policy_ref,
            comment="bounded development envelope",
        )
