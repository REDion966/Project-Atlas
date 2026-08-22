"""
Atlas Evolution Autonomy — Authorization Manager Tests — Phase 16.3

Verifies Gate 4 authorization logic:

- user:cli and user:policy authorizations are granted when policy enabled.
- system:autonomy authorization requires all envelope conditions.
- Protected scopes (UNKNOWN, IDENTITY, CODE) are refused.
- TTL is applied and expiry is detected.
- In-flight policy reload exclusion.
- No self-escalation: manager never mutates policy.
- Audit callback is invoked for grants.

Pure logic. No infra. No AI.
"""

import unittest
from datetime import datetime, timedelta
from typing import Any

from atlas.evolution.autonomy.authorization_manager import (
    AuthorizationManager,
    AuthorizationRequest,
    AuthorizationRefusal,
)
from atlas.evolution.autonomy.models import (
    AuthorizationMode,
    AutonomyPolicy,
    EvolutionAuthorization,
    EvolutionRequest,
    EvolutionWindow,
    RiskAssessment,
    RiskLevel,
    RollbackPlan,
    RollbackStrategy,
)
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import ExecutionLevel


class _FixedClock:
    """Deterministic clock for authorization tests."""

    def __init__(self, now: datetime):
        self._now = now

    def __call__(self) -> datetime:
        return self._now


class _RequestFactory:
    @staticmethod
    def request(
        scope: ScopeType = ScopeType.CONFIG,
        request_id: str = "AUTORQ-1",
        intended_level: ExecutionLevel = ExecutionLevel.SELF_CONFIG,
        risk_level: RiskLevel = RiskLevel.LOW,
        requires_user_approval: bool = False,
        rollback: RollbackPlan | None = None,
        authorization: EvolutionAuthorization | None = None,
    ) -> EvolutionRequest:
        return EvolutionRequest(
            request_id=request_id,
            source="cli",
            target_scope=scope,
            change_payload={"key": "x", "value": 1},
            intended_level=intended_level,
            risk=RiskAssessment(
                risk_level=risk_level,
                requires_user_approval=requires_user_approval,
                requires_rollback=risk_level in {
                    RiskLevel.MEDIUM,
                    RiskLevel.HIGH,
                    RiskLevel.CRITICAL,
                },
            ),
            rollback=rollback,
            authorization=authorization,
        )

    @staticmethod
    def risk(
        risk_level: RiskLevel = RiskLevel.LOW,
        requires_user_approval: bool = False,
    ) -> RiskAssessment:
        return RiskAssessment(
            risk_level=risk_level,
            requires_user_approval=requires_user_approval,
            requires_rollback=risk_level in {
                RiskLevel.MEDIUM,
                RiskLevel.HIGH,
                RiskLevel.CRITICAL,
            },
        )


class TestExplicitInformationGrant(unittest.TestCase):
    """Batch 10 — explicit user:cli INFORMATION grants while policy disabled."""

    @staticmethod
    def _info_request(
        scope: ScopeType, request_id: str = "AUTORQ-INFO"
    ) -> EvolutionRequest:
        return EvolutionRequest(
            request_id=request_id,
            source="cli",
            target_scope=scope,
            change_payload={"operation": "add", "entry_id": "x", "content": "y"},
            intended_level=ExecutionLevel.INFORMATION,
        )

    def test_knowledge_user_cli_granted_policy_disabled(self):
        policy = AutonomyPolicy(enabled=False)
        manager = AuthorizationManager(policy=policy)
        req = self._info_request(ScopeType.KNOWLEDGE)
        result = manager.request_user_authorization(
            req,
            AuthorizationRequest(
                authorized_by="user:cli", mode=AuthorizationMode.EXPLICIT
            ),
        )

        self.assertTrue(result.authorized)
        auth = result.authorization
        self.assertIsNotNone(auth)
        self.assertEqual(auth.mode, AuthorizationMode.EXPLICIT)
        self.assertEqual(auth.authorized_by, "user:cli")
        self.assertEqual(auth.request_id, req.request_id)

    def test_memory_user_cli_granted_policy_disabled(self):
        policy = AutonomyPolicy(enabled=False)
        manager = AuthorizationManager(policy=policy)
        req = self._info_request(ScopeType.MEMORY)
        result = manager.request_user_authorization(
            req,
            AuthorizationRequest(
                authorized_by="user:cli", mode=AuthorizationMode.EXPLICIT
            ),
        )

        self.assertTrue(result.authorized)
        auth = result.authorization
        self.assertIsNotNone(auth)
        self.assertEqual(auth.mode, AuthorizationMode.EXPLICIT)
        self.assertEqual(auth.authorized_by, "user:cli")

    def test_user_grant_emits_audit_event(self):
        records: list[dict] = []
        policy = AutonomyPolicy(enabled=False)
        manager = AuthorizationManager(policy=policy, audit_callback=records.append)
        req = self._info_request(ScopeType.KNOWLEDGE)
        manager.request_user_authorization(
            req,
            AuthorizationRequest(
                authorized_by="user:cli", mode=AuthorizationMode.EXPLICIT
            ),
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["event"], "phase16.authorization.granted.user")
        self.assertEqual(records[0]["request_id"], req.request_id)

    def test_user_grant_preserves_ttl(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        policy = AutonomyPolicy(enabled=False, authorization_ttl_minutes=30)
        manager = AuthorizationManager(policy=policy, clock=_FixedClock(now))
        req = self._info_request(ScopeType.MEMORY)
        auth = manager.request_user_authorization(
            req,
            AuthorizationRequest(
                authorized_by="user:cli", mode=AuthorizationMode.EXPLICIT
            ),
        ).authorization

        self.assertIsNotNone(auth)
        self.assertEqual(auth.granted_at, now)
        self.assertEqual(auth.expires_at, now + timedelta(minutes=30))

    def test_policy_remains_disabled_after_grant(self):
        policy = AutonomyPolicy(enabled=False, version="v1")
        manager = AuthorizationManager(policy=policy)
        req = self._info_request(ScopeType.KNOWLEDGE)
        manager.request_user_authorization(
            req,
            AuthorizationRequest(
                authorized_by="user:cli", mode=AuthorizationMode.EXPLICIT
            ),
        )

        self.assertFalse(policy.enabled)
        self.assertEqual(policy.version, "v1")

    def test_config_self_config_denied_when_policy_disabled(self):
        # CONFIG is the SELF_CONFIG boundary, NOT INFORMATION — still denied
        # when the policy is disabled.
        policy = AutonomyPolicy(enabled=False)
        manager = AuthorizationManager(policy=policy)
        req = EvolutionRequest(
            request_id="AUTORQ-CFG",
            source="cli",
            target_scope=ScopeType.CONFIG,
            change_payload={"key": "x", "value": 1},
            intended_level=ExecutionLevel.SELF_CONFIG,
        )
        with self.assertRaises(AuthorizationRefusal):
            manager.request_user_authorization(
                req,
                AuthorizationRequest(
                    authorized_by="user:cli", mode=AuthorizationMode.EXPLICIT
                ),
            )

    def test_information_scope_wrong_level_denied_when_policy_disabled(self):
        # MEMORY at ADMINISTRATIVE (not INFORMATION) — outside the carve-out.
        policy = AutonomyPolicy(enabled=False)
        manager = AuthorizationManager(policy=policy)
        req = EvolutionRequest(
            request_id="AUTORQ-ADMIN",
            source="cli",
            target_scope=ScopeType.MEMORY,
            change_payload={"operation": "add", "entry_id": "x", "content": "y"},
            intended_level=ExecutionLevel.ADMINISTRATIVE,
        )
        with self.assertRaises(AuthorizationRefusal):
            manager.request_user_authorization(
                req,
                AuthorizationRequest(
                    authorized_by="user:cli", mode=AuthorizationMode.EXPLICIT
                ),
            )


class TestUserAuthorization(unittest.TestCase):
    """user:cli / user:policy authorizations."""

    def test_user_cli_granted(self):
        policy = AutonomyPolicy(enabled=True, version="v1")
        manager = AuthorizationManager(policy=policy)
        req = _RequestFactory.request()
        auth_request = AuthorizationRequest(
            authorized_by="user:cli", mode=AuthorizationMode.EXPLICIT
        )
        result = manager.request_user_authorization(req, auth_request)

        self.assertTrue(result.authorized)
        self.assertIsNotNone(result.authorization)
        auth = result.authorization
        self.assertEqual(auth.mode, AuthorizationMode.EXPLICIT)
        self.assertEqual(auth.authorized_by, "user:cli")
        self.assertEqual(auth.request_id, req.request_id)

    def test_user_policy_granted(self):
        policy = AutonomyPolicy(enabled=True, version="v1")
        manager = AuthorizationManager(policy=policy)
        req = _RequestFactory.request()
        auth_request = AuthorizationRequest(
            authorized_by="user:policy",
            mode=AuthorizationMode.POLICY,
            policy_ref="policy-rule-1",
        )
        result = manager.request_user_authorization(req, auth_request)

        self.assertTrue(result.authorized)
        auth = result.authorization
        self.assertEqual(auth.mode, AuthorizationMode.POLICY)
        self.assertEqual(auth.policy_ref, "policy-rule-1")

    def test_user_authorization_disabled_policy_raises(self):
        policy = AutonomyPolicy(enabled=False)
        manager = AuthorizationManager(policy=policy)
        req = _RequestFactory.request()
        auth_request = AuthorizationRequest()

        with self.assertRaises(AuthorizationRefusal):
            manager.request_user_authorization(req, auth_request)

    def test_protected_scope_refused(self):
        policy = AutonomyPolicy(enabled=True)
        manager = AuthorizationManager(policy=policy)
        for scope in (ScopeType.UNKNOWN, ScopeType.IDENTITY, ScopeType.CODE):
            req = _RequestFactory.request(scope=scope)
            result = manager.request_user_authorization(req, AuthorizationRequest())
            self.assertFalse(result.authorized, scope)

    def test_authorization_has_ttl(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        policy = AutonomyPolicy(
            enabled=True, authorization_ttl_minutes=30
        )
        manager = AuthorizationManager(policy=policy, clock=_FixedClock(now))
        req = _RequestFactory.request()
        result = manager.request_user_authorization(req, AuthorizationRequest())

        auth = result.authorization
        self.assertEqual(auth.granted_at, now)
        self.assertEqual(auth.expires_at, now + timedelta(minutes=30))


class TestAutonomousAuthorization(unittest.TestCase):
    """system:autonomy authorization inside the envelope."""

    def _policy(self, **kwargs: Any) -> AutonomyPolicy:
        defaults = {
            "enabled": True,
            "allowed_scopes": [ScopeType.CONFIG],
            "max_risk_level": RiskLevel.MEDIUM,
            "effective_execution_level": ExecutionLevel.SELF_CONFIG,
            "max_requests_per_window": 10,
            "authorization_ttl_minutes": 60,
            "version": "v1",
        }
        defaults.update(kwargs)
        return AutonomyPolicy(**defaults)

    def test_autonomous_grant(self):
        policy = self._policy()
        manager = AuthorizationManager(policy=policy)
        req = _RequestFactory.request(
            scope=ScopeType.CONFIG,
            risk_level=RiskLevel.LOW,
            rollback=RollbackPlan(),
        )
        result = manager.authorize_autonomously(
            request=req,
            risk_assessment=_RequestFactory.risk(RiskLevel.LOW),
            requests_used_this_window=0,
            rollback_ready=True,
        )

        self.assertTrue(result.authorized)
        auth = result.authorization
        self.assertEqual(auth.mode, AuthorizationMode.AUTONOMY)
        self.assertEqual(auth.authorized_by, "system:autonomy")

    def test_disabled_policy_refuses(self):
        policy = self._policy(enabled=False)
        manager = AuthorizationManager(policy=policy)
        req = _RequestFactory.request()
        result = manager.authorize_autonomously(
            request=req,
            risk_assessment=_RequestFactory.risk(),
            requests_used_this_window=0,
            rollback_ready=True,
        )
        self.assertFalse(result.authorized)
        self.assertFalse(result.requires_user_approval)

    def test_out_of_envelope_requires_user_approval(self):
        policy = self._policy(allowed_scopes=[ScopeType.MEMORY])
        manager = AuthorizationManager(policy=policy)
        req = _RequestFactory.request(scope=ScopeType.CONFIG)
        result = manager.authorize_autonomously(
            request=req,
            risk_assessment=_RequestFactory.risk(),
            requests_used_this_window=0,
            rollback_ready=True,
        )
        self.assertFalse(result.authorized)
        self.assertTrue(result.requires_user_approval)

    def test_high_risk_requires_user_approval(self):
        policy = self._policy(max_risk_level=RiskLevel.MEDIUM)
        manager = AuthorizationManager(policy=policy)
        req = _RequestFactory.request(risk_level=RiskLevel.HIGH)
        result = manager.authorize_autonomously(
            request=req,
            risk_assessment=_RequestFactory.risk(RiskLevel.HIGH),
            requests_used_this_window=0,
            rollback_ready=True,
        )
        self.assertFalse(result.authorized)
        self.assertTrue(result.requires_user_approval)

    def test_requires_user_approval_scope(self):
        policy = self._policy(requires_user_approval_scopes=[ScopeType.CONFIG])
        manager = AuthorizationManager(policy=policy)
        req = _RequestFactory.request()
        result = manager.authorize_autonomously(
            request=req,
            risk_assessment=_RequestFactory.risk(),
            requests_used_this_window=0,
            rollback_ready=True,
        )
        self.assertFalse(result.authorized)
        self.assertTrue(result.requires_user_approval)

    def test_missing_rollback_requires_user_approval(self):
        policy = self._policy()
        manager = AuthorizationManager(policy=policy)
        req = _RequestFactory.request()
        result = manager.authorize_autonomously(
            request=req,
            risk_assessment=_RequestFactory.risk(),
            requests_used_this_window=0,
            rollback_ready=False,
        )
        self.assertFalse(result.authorized)
        self.assertTrue(result.requires_user_approval)

    def test_window_closed_requires_user_approval(self):
        start = datetime(2026, 1, 1, 9, 0, 0)
        end = datetime(2026, 1, 1, 17, 0, 0)
        now = datetime(2026, 1, 1, 20, 0, 0)
        policy = self._policy(
            window=EvolutionWindow(window_start=start, window_end=end)
        )
        manager = AuthorizationManager(policy=policy, clock=_FixedClock(now))
        req = _RequestFactory.request()
        result = manager.authorize_autonomously(
            request=req,
            risk_assessment=_RequestFactory.risk(),
            requests_used_this_window=0,
            rollback_ready=True,
        )
        self.assertFalse(result.authorized)
        self.assertTrue(result.requires_user_approval)

    def test_quota_exhausted_requires_user_approval(self):
        policy = self._policy(max_requests_per_window=2)
        manager = AuthorizationManager(policy=policy)
        req = _RequestFactory.request()
        result = manager.authorize_autonomously(
            request=req,
            risk_assessment=_RequestFactory.risk(),
            requests_used_this_window=2,
            rollback_ready=True,
        )
        self.assertFalse(result.authorized)
        self.assertTrue(result.requires_user_approval)


class TestAuthorizationValidation(unittest.TestCase):
    """Validating existing authorizations (TTL, mismatch, disabled)."""

    def test_valid_authorization(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        policy = AutonomyPolicy(enabled=True)
        manager = AuthorizationManager(policy=policy, clock=_FixedClock(now))
        req = _RequestFactory.request()
        req = _RequestFactory.request(
            authorization=manager.request_user_authorization(
                req, AuthorizationRequest()
            ).authorization
        )
        result = manager.is_authorized(req, now)
        self.assertTrue(result.authorized)

    def test_expired_authorization(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        later = datetime(2026, 1, 1, 14, 0, 0)
        policy = AutonomyPolicy(
            enabled=True, authorization_ttl_minutes=60
        )
        manager = AuthorizationManager(policy=policy, clock=_FixedClock(now))
        req = _RequestFactory.request()
        auth = manager.request_user_authorization(
            req, AuthorizationRequest()
        ).authorization
        req = _RequestFactory.request(authorization=auth)

        result = manager.is_authorized(req, later)
        self.assertFalse(result.authorized)
        self.assertTrue(result.requires_user_approval)

    def test_request_id_mismatch(self):
        policy = AutonomyPolicy(enabled=True)
        manager = AuthorizationManager(policy=policy)
        auth = EvolutionAuthorization(
            request_id="OTHER", authorized_by="user:cli"
        )
        req = _RequestFactory.request(authorization=auth)
        result = manager.is_authorized(req)
        self.assertFalse(result.authorized)

    def test_autonomous_auth_invalid_when_policy_disabled(self):
        policy = AutonomyPolicy(enabled=False)
        manager = AuthorizationManager(policy=policy)
        auth = EvolutionAuthorization(
            request_id="AUTORQ-1",
            authorized_by="system:autonomy",
            mode=AuthorizationMode.AUTONOMY,
        )
        req = _RequestFactory.request(authorization=auth)
        result = manager.is_authorized(req)
        self.assertFalse(result.authorized)


class TestPolicyReloadExclusion(unittest.TestCase):
    """In-flight requests block policy reload."""

    def test_reload_allowed_when_no_in_flight(self):
        policy = AutonomyPolicy(enabled=True)
        manager = AuthorizationManager(policy=policy)
        result = manager.can_reload_policy([])
        self.assertTrue(result.authorized)

    def test_reload_blocked_with_in_flight(self):
        policy = AutonomyPolicy(enabled=True)
        manager = AuthorizationManager(policy=policy)
        result = manager.can_reload_policy(["AUTORQ-1", "AUTORQ-2"])
        self.assertFalse(result.authorized)


class TestAuthorizationPathClassification(unittest.TestCase):
    """classify_authorization_path advisory method."""

    def test_eligible_for_autonomy(self):
        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CONFIG],
            max_risk_level=RiskLevel.MEDIUM,
            effective_execution_level=ExecutionLevel.SELF_CONFIG,
        )
        manager = AuthorizationManager(policy=policy)
        req = _RequestFactory.request(risk_level=RiskLevel.LOW)
        result = manager.classify_authorization_path(
            req, _RequestFactory.risk(RiskLevel.LOW)
        )
        self.assertFalse(result.authorized)  # advisory only
        self.assertFalse(result.requires_user_approval)

    def test_requires_user_approval_by_scope(self):
        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CONFIG],
            requires_user_approval_scopes=[ScopeType.CONFIG],
        )
        manager = AuthorizationManager(policy=policy)
        req = _RequestFactory.request()
        result = manager.classify_authorization_path(req, _RequestFactory.risk())
        self.assertTrue(result.requires_user_approval)

    def test_requires_user_approval_by_risk(self):
        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CONFIG],
            max_risk_level=RiskLevel.CRITICAL,
        )
        manager = AuthorizationManager(policy=policy)
        req = _RequestFactory.request(
            risk_level=RiskLevel.HIGH, requires_user_approval=True
        )
        result = manager.classify_authorization_path(
            req, _RequestFactory.risk(RiskLevel.HIGH, requires_user_approval=True)
        )
        self.assertTrue(result.requires_user_approval)


class TestAuditCallback(unittest.TestCase):
    """Audit records are emitted for authorization grants."""

    def test_user_authorization_audit(self):
        records: list[dict] = []
        policy = AutonomyPolicy(enabled=True)
        manager = AuthorizationManager(policy=policy, audit_callback=records.append)
        req = _RequestFactory.request()
        manager.request_user_authorization(req, AuthorizationRequest())

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["event"], "phase16.authorization.granted.user")
        self.assertEqual(records[0]["request_id"], req.request_id)

    def test_autonomous_authorization_audit(self):
        records: list[dict] = []
        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CONFIG],
            max_risk_level=RiskLevel.MEDIUM,
            effective_execution_level=ExecutionLevel.SELF_CONFIG,
            max_requests_per_window=10,
        )
        manager = AuthorizationManager(policy=policy, audit_callback=records.append)
        req = _RequestFactory.request(
            risk_level=RiskLevel.LOW, rollback=RollbackPlan()
        )
        manager.authorize_autonomously(
            request=req,
            risk_assessment=_RequestFactory.risk(RiskLevel.LOW),
            requests_used_this_window=0,
            rollback_ready=True,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["event"], "phase16.authorization.granted.autonomy")


class TestPolicyImmutability(unittest.TestCase):
    """AuthorizationManager never mutates the policy."""

    def test_manager_does_not_mutate_policy(self):
        policy = AutonomyPolicy(enabled=True, version="v1")
        manager = AuthorizationManager(policy=policy)
        req = _RequestFactory.request()
        manager.request_user_authorization(req, AuthorizationRequest())
        self.assertEqual(policy.version, "v1")
        self.assertTrue(policy.enabled)


if __name__ == "__main__":
    unittest.main()
