"""
Atlas Evolution Autonomy — Autonomy Policy — Phase 16.3

Config mirror of the autonomy envelope plus pure-logic envelope checks.

Per Phase 16 Decision D7: the running system can never widen its own
envelope, alter the ConstraintRegistry, or change the gateway level.
``AutonomyPolicy`` is therefore an immutable snapshot of user
configuration. It is loaded once at startup and never mutated by Atlas
code.

The policy provides deterministic answers to authorization questions:
  - Is a scope inside the configured autonomous envelope?
  - Is a risk level acceptable for autonomous execution?
  - Is the current time within the configured application window?
  - Has the autonomous request quota for this window been exhausted?

Pure logic. No infrastructure. No AI. No gateway access.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from atlas.evolution.autonomy.models import AutonomyPolicy, EvolutionWindow, RiskLevel
from atlas.evolution.governance.models import ScopeType


class PolicyViolation(Exception):
    """Raised when a request or action violates the active AutonomyPolicy."""


@dataclass(frozen=True, slots=True)
class PolicyCheckResult:
    """Outcome of an envelope check against an AutonomyPolicy.

    Attributes:
        allowed: True when the action is permitted by policy.
        reason: Human-readable explanation of the decision.
        violation_type: Short category string (e.g. "scope", "risk",
            "window", "quota", "disabled") when disallowed.
    """

    allowed: bool
    reason: str = ""
    violation_type: str = ""


@dataclass(frozen=True, slots=True)
class AutonomyPolicyEngine:
    """Pure-logic policy engine for the autonomy envelope.

    Accepts an ``AutonomyPolicy`` via constructor injection. All methods
    are deterministic: the same policy + request always yields the same
    answer.

    The engine never mutates the policy. It provides the envelope checks
    required by ``AuthorizationManager`` to decide whether a request may
    be authorized under ``system:autonomy``.
    """

    policy: AutonomyPolicy

    def is_enabled(self) -> bool:
        """Return True when autonomous evolution is enabled."""
        return self.policy.enabled

    def is_scope_in_envelope(self, scope: ScopeType) -> bool:
        """Return True when ``scope`` is allowed for autonomous execution."""
        if not self.policy.enabled:
            return False
        return scope in set(self.policy.allowed_scopes)

    def is_risk_acceptable(self, risk_level: RiskLevel) -> bool:
        """Return True when ``risk_level`` does not exceed the policy ceiling."""
        if not self.policy.enabled:
            return False
        return _risk_rank(risk_level) <= _risk_rank(self.policy.max_risk_level)

    def is_window_open(self, now: datetime | None = None) -> bool:
        """Return True when ``now`` is inside the configured window, if any.

        A policy with no configured window is always open.
        """
        if not self.policy.enabled:
            return False
        window = self.policy.window
        if window is None:
            return True
        now = now if now is not None else datetime.now()
        return window.window_start <= now <= window.window_end

    def check_window(
        self,
        scheduled_at: datetime,
        now: datetime | None = None,
    ) -> PolicyCheckResult:
        """Check whether a scheduled request may apply at ``now``.

        If the policy defines a window, both ``scheduled_at`` and ``now``
        must fall within it. Requests scheduled outside the window are
        deferred; requests evaluated outside the window are deferred.
        """
        if not self.policy.enabled:
            return PolicyCheckResult(
                allowed=False,
                reason="Autonomy policy is disabled",
                violation_type="disabled",
            )

        window = self.policy.window
        if window is None:
            return PolicyCheckResult(allowed=True, reason="No window configured")

        now = now if now is not None else datetime.now()

        if scheduled_at < window.window_start or scheduled_at > window.window_end:
            return PolicyCheckResult(
                allowed=False,
                reason="Request scheduled outside the configured window",
                violation_type="window",
            )

        if now < window.window_start or now > window.window_end:
            return PolicyCheckResult(
                allowed=False,
                reason="Current time is outside the configured window",
                violation_type="window",
            )

        return PolicyCheckResult(
            allowed=True,
            reason="Within configured window",
        )

    def is_execution_level_allowed(
        self,
        intended_level: Any,
    ) -> bool:
        """Return True when ``intended_level`` does not exceed policy level.

        The policy ``effective_execution_level`` is the ceiling the user
        set at startup. A request requiring a higher level cannot be
        applied autonomously.
        """
        if not self.policy.enabled:
            return False
        from atlas.evolution.models import ExecutionLevel

        if not isinstance(intended_level, ExecutionLevel):
            return False
        return intended_level.value <= self.policy.effective_execution_level.value

    def is_user_approval_required(self, scope: ScopeType) -> bool:
        """Return True when the policy mandates user:cli for a scope."""
        return scope in set(self.policy.requires_user_approval_scopes)

    def check_envelope(
        self,
        scope: ScopeType,
        risk_level: RiskLevel,
        intended_level: Any,
    ) -> PolicyCheckResult:
        """Perform a combined envelope check for system:autonomy.

        Checks (in order):
          1. Policy enabled.
          2. Scope allowed.
          3. Risk acceptable.
          4. Execution level allowed.

        Returns the first violation encountered, or an allowed result.
        """
        if not self.policy.enabled:
            return PolicyCheckResult(
                allowed=False,
                reason="Autonomy policy is disabled",
                violation_type="disabled",
            )

        if not self.is_scope_in_envelope(scope):
            return PolicyCheckResult(
                allowed=False,
                reason=f"Scope {scope.name} is outside the autonomous envelope",
                violation_type="scope",
            )

        if not self.is_risk_acceptable(risk_level):
            return PolicyCheckResult(
                allowed=False,
                reason=f"Risk level {risk_level.name} exceeds policy ceiling",
                violation_type="risk",
            )

        if not self.is_execution_level_allowed(intended_level):
            return PolicyCheckResult(
                allowed=False,
                reason="Request intended level exceeds policy execution level",
                violation_type="level",
            )

        return PolicyCheckResult(
            allowed=True,
            reason="Request is within the autonomous envelope",
        )

    def can_apply_autonomously(
        self,
        scope: ScopeType,
        risk_level: RiskLevel,
        intended_level: Any,
        requests_used_this_window: int,
        now: datetime | None = None,
    ) -> PolicyCheckResult:
        """Full autonomous-application check including quota and window.

        This is the entry point ``AuthorizationManager`` uses when
        considering ``system:autonomy`` mode. It combines the envelope
        check with window and quota checks.
        """
        envelope = self.check_envelope(scope, risk_level, intended_level)
        if not envelope.allowed:
            return envelope

        if not self.is_window_open(now):
            return PolicyCheckResult(
                allowed=False,
                reason="Application window is closed",
                violation_type="window",
            )

        if self._quota_exhausted(requests_used_this_window):
            return PolicyCheckResult(
                allowed=False,
                reason="Autonomous request quota exhausted for this window",
                violation_type="quota",
            )

        return PolicyCheckResult(
            allowed=True,
            reason="Request may be authorized under system:autonomy",
        )

    def _quota_exhausted(self, used: int) -> bool:
        """Return True when the window quota has been used up.

        A ``max_requests_per_window`` of zero means "no autonomous
        requests allowed"; any positive value is a hard cap.
        """
        limit = self.policy.max_requests_per_window
        if limit <= 0:
            return True
        return used >= limit


def _risk_rank(level: RiskLevel) -> int:
    """Return an ordinal rank for RiskLevel comparison (LOW=0..CRITICAL=3)."""
    return {
        RiskLevel.LOW: 0,
        RiskLevel.MEDIUM: 1,
        RiskLevel.HIGH: 2,
        RiskLevel.CRITICAL: 3,
    }[level]
