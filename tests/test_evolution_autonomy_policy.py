"""
Atlas Evolution Autonomy — Policy Engine Tests — Phase 16.3

Verifies the pure-logic autonomy policy envelope:

- Disabled policy refuses everything.
- Scope envelope (allowed_scopes) is enforced.
- Risk ceiling (max_risk_level) is enforced.
- Execution-level ceiling is enforced.
- Window open/closed behavior.
- Quota accounting.
- user-approval-required scopes.
- No mutation of the immutable AutonomyPolicy.

Pure logic. No infra. No AI.
"""

import unittest
from datetime import datetime, timedelta

from atlas.evolution.autonomy.autonomy_policy import AutonomyPolicyEngine, PolicyCheckResult
from atlas.evolution.autonomy.models import AutonomyPolicy, EvolutionWindow, RiskLevel
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import ExecutionLevel


class TestPolicyDisabled(unittest.TestCase):
    """A disabled policy is fail-closed for all autonomy checks."""

    def test_disabled_refuses_scope(self):
        policy = AutonomyPolicy(enabled=False)
        engine = AutonomyPolicyEngine(policy)
        self.assertFalse(engine.is_scope_in_envelope(ScopeType.CONFIG))

    def test_disabled_refuses_risk(self):
        policy = AutonomyPolicy(enabled=False)
        engine = AutonomyPolicyEngine(policy)
        self.assertFalse(engine.is_risk_acceptable(RiskLevel.LOW))

    def test_disabled_refuses_window(self):
        policy = AutonomyPolicy(enabled=False)
        engine = AutonomyPolicyEngine(policy)
        self.assertFalse(engine.is_window_open())

    def test_disabled_check_envelope(self):
        policy = AutonomyPolicy(enabled=False)
        engine = AutonomyPolicyEngine(policy)
        result = engine.check_envelope(
            ScopeType.CONFIG, RiskLevel.LOW, ExecutionLevel.SELF_CONFIG
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.violation_type, "disabled")

    def test_disabled_can_apply_autonomously(self):
        policy = AutonomyPolicy(enabled=False)
        engine = AutonomyPolicyEngine(policy)
        result = engine.can_apply_autonomously(
            ScopeType.CONFIG, RiskLevel.LOW, ExecutionLevel.SELF_CONFIG, 0
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.violation_type, "disabled")


class TestScopeEnvelope(unittest.TestCase):
    """allowed_scopes defines the autonomous envelope."""

    def test_scope_in_envelope(self):
        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CONFIG, ScopeType.MEMORY],
        )
        engine = AutonomyPolicyEngine(policy)
        self.assertTrue(engine.is_scope_in_envelope(ScopeType.CONFIG))
        self.assertTrue(engine.is_scope_in_envelope(ScopeType.MEMORY))
        self.assertFalse(engine.is_scope_in_envelope(ScopeType.KNOWLEDGE))

    def test_scope_envelope_fail_closed(self):
        policy = AutonomyPolicy(enabled=True, allowed_scopes=[])
        engine = AutonomyPolicyEngine(policy)
        self.assertFalse(engine.is_scope_in_envelope(ScopeType.CONFIG))


class TestRiskCeiling(unittest.TestCase):
    """max_risk_level is an inclusive ceiling."""

    def test_low_ceiling_allows_low(self):
        policy = AutonomyPolicy(enabled=True, max_risk_level=RiskLevel.LOW)
        engine = AutonomyPolicyEngine(policy)
        self.assertTrue(engine.is_risk_acceptable(RiskLevel.LOW))
        self.assertFalse(engine.is_risk_acceptable(RiskLevel.MEDIUM))

    def test_high_ceiling_allows_lower(self):
        policy = AutonomyPolicy(enabled=True, max_risk_level=RiskLevel.HIGH)
        engine = AutonomyPolicyEngine(policy)
        self.assertTrue(engine.is_risk_acceptable(RiskLevel.LOW))
        self.assertTrue(engine.is_risk_acceptable(RiskLevel.MEDIUM))
        self.assertTrue(engine.is_risk_acceptable(RiskLevel.HIGH))
        self.assertFalse(engine.is_risk_acceptable(RiskLevel.CRITICAL))


class TestExecutionLevel(unittest.TestCase):
    """effective_execution_level caps autonomous requests."""

    def test_level_at_ceiling_allowed(self):
        policy = AutonomyPolicy(
            enabled=True,
            effective_execution_level=ExecutionLevel.SELF_CONFIG,
        )
        engine = AutonomyPolicyEngine(policy)
        self.assertTrue(
            engine.is_execution_level_allowed(ExecutionLevel.SELF_CONFIG)
        )

    def test_level_above_ceiling_refused(self):
        policy = AutonomyPolicy(
            enabled=True,
            effective_execution_level=ExecutionLevel.SELF_CONFIG,
        )
        engine = AutonomyPolicyEngine(policy)
        self.assertFalse(
            engine.is_execution_level_allowed(ExecutionLevel.INFORMATION)
        )

    def test_non_execution_level_refused(self):
        policy = AutonomyPolicy(enabled=True)
        engine = AutonomyPolicyEngine(policy)
        self.assertFalse(engine.is_execution_level_allowed("SELF_CONFIG"))


class TestWindowChecking(unittest.TestCase):
    """Window checks are inclusive and deterministic."""

    def test_no_window_always_open(self):
        policy = AutonomyPolicy(enabled=True)
        engine = AutonomyPolicyEngine(policy)
        self.assertTrue(engine.is_window_open())

    def test_within_window(self):
        start = datetime(2026, 1, 1, 9, 0, 0)
        end = datetime(2026, 1, 1, 17, 0, 0)
        now = datetime(2026, 1, 1, 12, 0, 0)
        policy = AutonomyPolicy(
            enabled=True,
            window=EvolutionWindow(window_start=start, window_end=end),
        )
        engine = AutonomyPolicyEngine(policy)
        self.assertTrue(engine.is_window_open(now))

    def test_outside_window(self):
        start = datetime(2026, 1, 1, 9, 0, 0)
        end = datetime(2026, 1, 1, 17, 0, 0)
        now = datetime(2026, 1, 1, 18, 0, 0)
        policy = AutonomyPolicy(
            enabled=True,
            window=EvolutionWindow(window_start=start, window_end=end),
        )
        engine = AutonomyPolicyEngine(policy)
        self.assertFalse(engine.is_window_open(now))

    def test_check_window_both_bounds(self):
        start = datetime(2026, 1, 1, 9, 0, 0)
        end = datetime(2026, 1, 1, 17, 0, 0)
        now = datetime(2026, 1, 1, 12, 0, 0)
        policy = AutonomyPolicy(
            enabled=True,
            window=EvolutionWindow(window_start=start, window_end=end),
        )
        engine = AutonomyPolicyEngine(policy)
        scheduled_at = now
        result = engine.check_window(scheduled_at, now)
        self.assertTrue(result.allowed)

    def test_check_window_scheduled_outside(self):
        start = datetime(2026, 1, 1, 9, 0, 0)
        end = datetime(2026, 1, 1, 17, 0, 0)
        now = datetime(2026, 1, 1, 12, 0, 0)
        scheduled_at = datetime(2026, 1, 2, 12, 0, 0)
        policy = AutonomyPolicy(
            enabled=True,
            window=EvolutionWindow(window_start=start, window_end=end),
        )
        engine = AutonomyPolicyEngine(policy)
        result = engine.check_window(scheduled_at, now)
        self.assertFalse(result.allowed)
        self.assertEqual(result.violation_type, "window")


class TestQuota(unittest.TestCase):
    """Window quota is a hard cap; zero means no autonomous requests."""

    def test_zero_quota_refuses(self):
        policy = AutonomyPolicy(enabled=True, max_requests_per_window=0)
        engine = AutonomyPolicyEngine(policy)
        self.assertTrue(engine._quota_exhausted(0))

    def test_quota_allows_under_cap(self):
        policy = AutonomyPolicy(
            enabled=True,
            max_requests_per_window=3,
            allowed_scopes=[ScopeType.CONFIG],
            max_risk_level=RiskLevel.MEDIUM,
            effective_execution_level=ExecutionLevel.SELF_CONFIG,
        )
        engine = AutonomyPolicyEngine(policy)
        result = engine.can_apply_autonomously(
            ScopeType.CONFIG,
            RiskLevel.LOW,
            ExecutionLevel.SELF_CONFIG,
            requests_used_this_window=2,
        )
        self.assertTrue(result.allowed)

    def test_quota_refuses_at_cap(self):
        policy = AutonomyPolicy(
            enabled=True,
            max_requests_per_window=3,
            allowed_scopes=[ScopeType.CONFIG],
            max_risk_level=RiskLevel.MEDIUM,
            effective_execution_level=ExecutionLevel.SELF_CONFIG,
        )
        engine = AutonomyPolicyEngine(policy)
        result = engine.can_apply_autonomously(
            ScopeType.CONFIG,
            RiskLevel.LOW,
            ExecutionLevel.SELF_CONFIG,
            requests_used_this_window=3,
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.violation_type, "quota")


class TestUserApprovalScopes(unittest.TestCase):
    """requires_user_approval_scopes forces user authorization."""

    def test_scope_requires_user_approval(self):
        policy = AutonomyPolicy(
            enabled=True,
            requires_user_approval_scopes=[ScopeType.CAPABILITY],
        )
        engine = AutonomyPolicyEngine(policy)
        self.assertTrue(engine.is_user_approval_required(ScopeType.CAPABILITY))
        self.assertFalse(engine.is_user_approval_required(ScopeType.CONFIG))


class TestCheckEnvelope(unittest.TestCase):
    """Combined envelope check returns first violation."""

    def test_allowed(self):
        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CONFIG],
            max_risk_level=RiskLevel.MEDIUM,
            effective_execution_level=ExecutionLevel.SELF_CONFIG,
        )
        engine = AutonomyPolicyEngine(policy)
        result = engine.check_envelope(
            ScopeType.CONFIG, RiskLevel.LOW, ExecutionLevel.SELF_CONFIG
        )
        self.assertTrue(result.allowed)

    def test_scope_violation_first(self):
        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.MEMORY],
            max_risk_level=RiskLevel.CRITICAL,
            effective_execution_level=ExecutionLevel.AUTONOMOUS,
        )
        engine = AutonomyPolicyEngine(policy)
        result = engine.check_envelope(
            ScopeType.CONFIG, RiskLevel.LOW, ExecutionLevel.SELF_CONFIG
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.violation_type, "scope")

    def test_risk_violation(self):
        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CONFIG],
            max_risk_level=RiskLevel.LOW,
        )
        engine = AutonomyPolicyEngine(policy)
        result = engine.check_envelope(
            ScopeType.CONFIG, RiskLevel.HIGH, ExecutionLevel.SELF_CONFIG
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.violation_type, "risk")

    def test_level_violation(self):
        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CONFIG],
            max_risk_level=RiskLevel.CRITICAL,
            effective_execution_level=ExecutionLevel.ADMINISTRATIVE,
        )
        engine = AutonomyPolicyEngine(policy)
        result = engine.check_envelope(
            ScopeType.CONFIG, RiskLevel.LOW, ExecutionLevel.SELF_CONFIG
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.violation_type, "level")


class TestPolicyImmutability(unittest.TestCase):
    """The engine does not mutate the policy dataclass."""

    def test_policy_unchanged_after_checks(self):
        policy = AutonomyPolicy(
            enabled=True,
            allowed_scopes=[ScopeType.CONFIG],
            max_risk_level=RiskLevel.LOW,
        )
        engine = AutonomyPolicyEngine(policy)
        engine.check_envelope(
            ScopeType.CONFIG, RiskLevel.LOW, ExecutionLevel.SELF_CONFIG
        )
        self.assertEqual(policy.allowed_scopes, [ScopeType.CONFIG])
        self.assertEqual(policy.max_risk_level, RiskLevel.LOW)


if __name__ == "__main__":
    unittest.main()
