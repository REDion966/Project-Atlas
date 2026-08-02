"""
Atlas Evolution Autonomy — Authorization Manager — Phase 16.3

Gate 4 of the governance pipeline (see ``PHASE_16_ARCHITECTURE.md`` §7).

The authorization manager decides how an ``EvolutionRequest`` may be
authorized for application. It supports three authorization modes:

  - ``user:cli`` — explicit per-request approval.
  - ``user:policy`` — declarative pre-authorization from a policy rule.
  - ``system:autonomy`` — autonomous grant inside the configured envelope.

Per Decision D7/D14: no request, applier, or engine may modify the
policy, the registry, or the gateway level. AuthorizationManager only
*reads* the policy; it never writes to it. In-flight exclusion is
enforced here: policy reload is rejected while any request is in
``APPLIED`` or ``PENDING_EFFECTIVE`` state.

The manager is pure logic: it does not touch storage, does not call the
gateway, and does not schedule. It produces an immutable
``EvolutionAuthorization`` record or a deterministic refusal reason.

Pure logic. No infrastructure. No AI. No gateway access.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from atlas.evolution.autonomy.autonomy_policy import AutonomyPolicyEngine
from atlas.evolution.autonomy.models import (
    AuthorizationMode,
    AutonomyPolicy,
    EvolutionAuthorization,
    EvolutionRequest,
    RiskAssessment,
    RiskLevel,
)
from atlas.evolution.governance.models import ScopeType


class AuthorizationRefusal(Exception):
    """Raised when an authorization request cannot be granted."""


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    """Outcome of an authorization attempt.

    Attributes:
        authorized: True when an ``EvolutionAuthorization`` was produced.
        authorization: The authorization record when authorized is True.
        reason: Human-readable explanation of the decision.
        requires_user_approval: True when only user:cli/user:policy can
            authorize this request (system:autonomy was denied).
    """

    authorized: bool
    authorization: EvolutionAuthorization | None = None
    reason: str = ""
    requires_user_approval: bool = False


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    """User-facing authorization request parameters.

    This carries the minimum information needed for a ``user:cli`` or
    ``user:policy`` approval decision. It is intentionally separate from
    ``EvolutionRequest`` so the manager can be tested in isolation.

    Attributes:
        authorized_by: Approval actor ("user:cli" or "user:policy").
        mode: EXPLICIT or POLICY.
        comment: Optional human comment.
        policy_ref: Optional reference into the policy configuration.
    """

    authorized_by: str = "user:cli"
    mode: AuthorizationMode = AuthorizationMode.EXPLICIT
    comment: str = ""
    policy_ref: str = ""

    def __post_init__(self) -> None:
        if self.mode not in {AuthorizationMode.EXPLICIT, AuthorizationMode.POLICY}:
            raise ValueError("AuthorizationRequest mode must be EXPLICIT or POLICY")


@dataclass(frozen=True, slots=True)
class AuthorizationManager:
    """Deterministic authorization manager for ``EvolutionRequest``.

    Dependencies (constructor-injected):
      - policy: the active ``AutonomyPolicy`` snapshot.
      - audit_callback: optional callable invoked with a structured audit
        dict whenever an authorization is granted or refused. This keeps
        the manager pure while allowing later sub-phases to persist audit
        records.
      - clock: optional callable returning ``datetime.now()``; used for
        deterministic tests.

    The manager is stateless except for the immutable policy. All
    mutable authorization state (request status, counters) is expected to
    live in the schedule store / storage layer (Phase 16.4).
    """

    policy: AutonomyPolicy
    audit_callback: Any | None = None
    clock: Any = field(default_factory=lambda: datetime.now)

    def __post_init__(self) -> None:
        if self.policy is None:
            raise ValueError("AutonomyPolicy is required")

    def can_reload_policy(
        self,
        in_flight_request_ids: list[str],
    ) -> AuthorizationResult:
        """Check whether the policy may be reloaded right now.

        Per the architecture, policy reload is user-only and is rejected
        while any request is in ``APPLIED`` or ``PENDING_EFFECTIVE``.
        """
        if in_flight_request_ids:
            return AuthorizationResult(
                authorized=False,
                reason=(
                    "Policy reload blocked: requests in flight "
                    f"({', '.join(in_flight_request_ids)})"
                ),
                requires_user_approval=False,
            )
        return AuthorizationResult(
            authorized=True,
            reason="Policy reload permitted",
            requires_user_approval=False,
        )

    def request_user_authorization(
        self,
        request: EvolutionRequest,
        auth_request: AuthorizationRequest,
    ) -> AuthorizationResult:
        """Grant ``user:cli`` or ``user:policy`` authorization.

        Validates that the request is eligible for user approval and
        produces a time-bounded ``EvolutionAuthorization``.
        """
        self._ensure_policy_enabled()

        if request.target_scope in {ScopeType.UNKNOWN, ScopeType.IDENTITY, ScopeType.CODE}:
            return AuthorizationResult(
                authorized=False,
                reason=(
                    f"Scope {request.target_scope.name} is constitutionally "
                    "protected and cannot be authorized"
                ),
                requires_user_approval=False,
            )

        auth = self._build_authorization(
            request_id=request.request_id,
            authorized_by=auth_request.authorized_by,
            mode=auth_request.mode,
            comment=auth_request.comment,
            policy_ref=auth_request.policy_ref,
        )
        self._audit(
            event="authorization.granted.user",
            request_id=request.request_id,
            mode=auth.mode.name,
            authorized_by=auth.authorized_by,
        )
        return AuthorizationResult(
            authorized=True,
            authorization=auth,
            reason=f"{auth_request.mode.name} authorization granted",
            requires_user_approval=False,
        )

    def authorize_autonomously(
        self,
        request: EvolutionRequest,
        risk_assessment: RiskAssessment,
        requests_used_this_window: int,
        rollback_ready: bool,
    ) -> AuthorizationResult:
        """Attempt to grant ``system:autonomy`` authorization.

        All of the following must hold (per §8 of the architecture):
          - Policy enabled.
          - Scope in allowed_scopes.
          - Risk ≤ max_risk_level.
          - Risk does not require user approval.
          - Execution level ≤ policy level.
          - Request is not listed in requires_user_approval_scopes.
          - Documentable rollback plan present.
          - Window active.
          - Quota available.

        If any condition fails, the result reports that user approval is
        required instead of failing outright — this lets the caller route
        the request to ``request_user_authorization``.
        """
        engine = self._engine()

        if not engine.is_enabled():
            return AuthorizationResult(
                authorized=False,
                reason="Autonomy policy is disabled",
                requires_user_approval=False,
            )

        refusal_reason = self._why_not_autonomous(
            request=request,
            risk_assessment=risk_assessment,
            requests_used_this_window=requests_used_this_window,
            rollback_ready=rollback_ready,
        )
        if refusal_reason:
            return AuthorizationResult(
                authorized=False,
                reason=refusal_reason,
                requires_user_approval=True,
            )

        auth = self._build_authorization(
            request_id=request.request_id,
            authorized_by="system:autonomy",
            mode=AuthorizationMode.AUTONOMY,
            comment="Granted within autonomous envelope",
            policy_ref=self.policy.version,
        )
        self._audit(
            event="authorization.granted.autonomy",
            request_id=request.request_id,
            mode=auth.mode.name,
            authorized_by=auth.authorized_by,
        )
        return AuthorizationResult(
            authorized=True,
            authorization=auth,
            reason="Granted under system:autonomy",
            requires_user_approval=False,
        )

    def classify_authorization_path(
        self,
        request: EvolutionRequest,
        risk_assessment: RiskAssessment,
    ) -> AuthorizationResult:
        """Classify what authorization path a request requires.

        This is a read-only advisory method. It does not grant anything.
        It is useful for CLI/presentation layers to show whether a
        request can be autonomous or needs explicit user approval.
        """
        if request.target_scope in {ScopeType.UNKNOWN, ScopeType.IDENTITY, ScopeType.CODE}:
            return AuthorizationResult(
                authorized=False,
                reason="Protected scope — cannot be authorized",
                requires_user_approval=False,
            )

        engine = self._engine()
        if not engine.is_enabled():
            return AuthorizationResult(
                authorized=False,
                reason="Autonomy disabled — explicit user approval required",
                requires_user_approval=True,
            )

        if engine.is_user_approval_required(request.target_scope):
            return AuthorizationResult(
                authorized=False,
                reason="Policy mandates user approval for this scope",
                requires_user_approval=True,
            )

        if risk_assessment.requires_user_approval:
            return AuthorizationResult(
                authorized=False,
                reason="Risk level requires user approval",
                requires_user_approval=True,
            )

        envelope = engine.check_envelope(
            request.target_scope,
            risk_assessment.risk_level,
            request.intended_level,
        )
        if not envelope.allowed:
            return AuthorizationResult(
                authorized=False,
                reason=f"Outside autonomous envelope: {envelope.reason}",
                requires_user_approval=True,
            )

        return AuthorizationResult(
            authorized=False,
            reason="Eligible for system:autonomy authorization",
            requires_user_approval=False,
        )

    def is_authorized(
        self,
        request: EvolutionRequest,
        now: datetime | None = None,
    ) -> AuthorizationResult:
        """Validate an existing authorization on a request.

        Returns ``authorized=True`` only when:
          - The request carries an ``EvolutionAuthorization``.
          - The authorization has not expired.
          - The authorization matches the request ID.
          - For ``system:autonomy`` mode, the policy is still enabled.
        """
        auth = request.authorization
        if auth is None:
            return AuthorizationResult(
                authorized=False,
                reason="Request has no authorization",
                requires_user_approval=True,
            )

        if auth.request_id != request.request_id:
            return AuthorizationResult(
                authorized=False,
                reason="Authorization request ID mismatch",
                requires_user_approval=False,
            )

        if auth.mode == AuthorizationMode.AUTONOMY and not self.policy.enabled:
            return AuthorizationResult(
                authorized=False,
                reason="Autonomous authorization invalid while policy disabled",
                requires_user_approval=False,
            )

        if now is None:
            now = self.clock()
        expires_at: datetime | None = auth.expires_at
        if expires_at is not None and now > expires_at:
            return AuthorizationResult(
                authorized=False,
                reason="Authorization has expired",
                requires_user_approval=True,
            )

        return AuthorizationResult(
            authorized=True,
            authorization=auth,
            reason="Authorization is valid",
            requires_user_approval=False,
        )

    def _why_not_autonomous(
        self,
        request: EvolutionRequest,
        risk_assessment: RiskAssessment,
        requests_used_this_window: int,
        rollback_ready: bool,
    ) -> str:
        """Return a refusal reason, or empty string if autonomous grant is OK.

        The checks are ordered from most specific to most general so the
        returned reason is actionable.
        """
        engine = self._engine()

        if engine.is_user_approval_required(request.target_scope):
            return "Policy requires user approval for this scope"

        if risk_assessment.requires_user_approval:
            return "Risk assessment requires user approval"

        if not rollback_ready:
            return "No rollback plan present"

        envelope = engine.check_envelope(
            request.target_scope,
            risk_assessment.risk_level,
            request.intended_level,
        )
        if not envelope.allowed:
            return f"Outside autonomous envelope: {envelope.reason}"

        if not engine.is_window_open(self.clock()):
            return "Application window is closed"

        if engine._quota_exhausted(requests_used_this_window):
            return "Autonomous request quota exhausted"

        return ""

    def _build_authorization(
        self,
        request_id: str,
        authorized_by: str,
        mode: AuthorizationMode,
        comment: str,
        policy_ref: str,
    ) -> EvolutionAuthorization:
        """Construct a time-bounded authorization record."""
        granted_at = self.clock()
        ttl = self.policy.authorization_ttl_minutes
        expires_at = granted_at + timedelta(minutes=ttl)
        return EvolutionAuthorization(
            request_id=request_id,
            authorized_by=authorized_by,
            mode=mode,
            granted_at=granted_at,
            expires_at=expires_at,
            policy_ref=policy_ref,
            comment=comment,
        )

    def _engine(self) -> AutonomyPolicyEngine:
        """Return a pure-logic policy engine backed by this manager's policy."""
        return AutonomyPolicyEngine(policy=self.policy)

    def _ensure_policy_enabled(self) -> None:
        """Fail when attempting user authorization while autonomy is disabled.

        user:cli/user:policy authorizations are still gate 4 decisions;
        if the autonomy subsystem is disabled entirely, no evolution
        requests should be authorized.
        """
        if not self.policy.enabled:
            raise AuthorizationRefusal("Autonomy policy is disabled")

    def _audit(self, event: str, request_id: str, **kwargs: Any) -> None:
        """Emit an audit record via the injected callback, if any."""
        if self.audit_callback is None:
            return
        record = {
            "event": f"phase16.{event}",
            "request_id": request_id,
            "timestamp": self.clock().isoformat(),
            **kwargs,
        }
        self.audit_callback(record)
