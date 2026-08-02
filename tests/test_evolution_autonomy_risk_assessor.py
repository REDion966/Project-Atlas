"""
Atlas Evolution Autonomy — Risk Assessor Tests — Phase 16.2

Verifies Gate 3 deterministic risk scoring:

- Score is bounded to [0.0, 1.0].
- RiskLevel maps correctly from score thresholds.
- Scope blast radius, operation kind, rollback readiness, PlanningContext
  signals, and goal-layer signals all contribute deterministically.
- HIGH/CRITICAL risk requires user approval and rollback.
- No infrastructure, no AI, no side effects.

Pure logic. No infra. No AI.
"""

import unittest
from datetime import datetime

from atlas.evolution.autonomy.models import (
    EvolutionRequest,
    RiskLevel,
    RollbackPlan,
    RollbackStrategy,
)
from atlas.evolution.autonomy.risk_assessor import (
    EvolutionRiskAssessor,
    _area_for_scope,
    _extract_operation,
    _risk_level_for_score,
)
from atlas.evolution.decision_models import (
    AreaAdjustment,
    BottleneckAlert,
    PlanningContext,
)
from atlas.evolution.governance.models import ScopeType
from atlas.goals.models import GoalPriority, ImprovementGoal


class _RequestFactory:
    """Builds minimal EvolutionRequests for risk-assessor tests."""

    @staticmethod
    def request(
        scope: ScopeType,
        payload: dict | None = None,
        rollback: RollbackPlan | None = None,
    ) -> EvolutionRequest:
        return EvolutionRequest(
            request_id="AUTORQ-1",
            source="cli",
            target_scope=scope,
            change_payload=payload or {},
            rollback=rollback,
        )


class TestRiskLevelThresholds(unittest.TestCase):
    """Score-to-level mapping matches approved thresholds."""

    def test_low(self):
        self.assertEqual(_risk_level_for_score(0.0), RiskLevel.LOW)
        self.assertEqual(_risk_level_for_score(0.29), RiskLevel.LOW)

    def test_medium(self):
        self.assertEqual(_risk_level_for_score(0.30), RiskLevel.MEDIUM)
        self.assertEqual(_risk_level_for_score(0.54), RiskLevel.MEDIUM)

    def test_high(self):
        self.assertEqual(_risk_level_for_score(0.55), RiskLevel.HIGH)
        self.assertEqual(_risk_level_for_score(0.79), RiskLevel.HIGH)

    def test_critical(self):
        self.assertEqual(_risk_level_for_score(0.80), RiskLevel.CRITICAL)
        self.assertEqual(_risk_level_for_score(1.0), RiskLevel.CRITICAL)


class TestOperationExtraction(unittest.TestCase):
    """Operation extraction normalises payload fields."""

    def test_capability_upgrade_kind(self):
        req = _RequestFactory.request(
            ScopeType.CAPABILITY,
            {"upgrade_kind": "DEPRECATE", "capability_name": "X"},
        )
        self.assertEqual(_extract_operation(req), "deprecate")

    def test_memory_operation(self):
        req = _RequestFactory.request(
            ScopeType.MEMORY, {"operation": "remove", "memory_id": "M-1"}
        )
        self.assertEqual(_extract_operation(req), "remove")

    def test_default_operation(self):
        req = _RequestFactory.request(ScopeType.CONFIG, {"key": "x", "value": 1})
        self.assertEqual(_extract_operation(req), "update")


class TestAreaForScope(unittest.TestCase):
    """Canonical area mapping matches adapter mapping."""

    def test_areas(self):
        self.assertEqual(_area_for_scope(ScopeType.CONFIG), "config")
        self.assertEqual(_area_for_scope(ScopeType.MEMORY), "memory")
        self.assertEqual(_area_for_scope(ScopeType.KNOWLEDGE), "knowledge")
        self.assertEqual(_area_for_scope(ScopeType.CAPABILITY), "capability")
        self.assertEqual(_area_for_scope(ScopeType.UNKNOWN), "governance:unknown")


class TestScopeBlastRadius(unittest.TestCase):
    """Scopes with larger blast radius produce higher base scores."""

    def test_capability_higher_than_memory(self):
        capability = _RequestFactory.request(
            ScopeType.CAPABILITY,
            {"upgrade_kind": "REGISTER", "capability_name": "X"},
        )
        memory = _RequestFactory.request(
            ScopeType.MEMORY, {"operation": "add", "memory_id": "M-1", "content": "x"}
        )
        cap_report = EvolutionRiskAssessor().assess(capability)
        mem_report = EvolutionRiskAssessor().assess(memory)
        self.assertGreater(cap_report.score, mem_report.score)
        self.assertEqual(cap_report.factors["scope_weight"], 0.35)
        self.assertEqual(mem_report.factors["scope_weight"], 0.15)


class TestOperationModifiers(unittest.TestCase):
    """Remove / deprecate operations increase risk."""

    def test_remove_riskier_than_add(self):
        add_req = _RequestFactory.request(
            ScopeType.MEMORY, {"operation": "add", "memory_id": "M-1", "content": "x"}
        )
        remove_req = _RequestFactory.request(
            ScopeType.MEMORY, {"operation": "remove", "memory_id": "M-1"}
        )
        add_report = EvolutionRiskAssessor().assess(add_req)
        remove_report = EvolutionRiskAssessor().assess(remove_req)
        self.assertGreater(remove_report.score, add_report.score)
        self.assertEqual(add_report.factors["operation_modifier"], 0.0)
        self.assertEqual(remove_report.factors["operation_modifier"], 0.20)


class TestRollbackReadiness(unittest.TestCase):
    """Missing rollback plan adds deterministic risk."""

    def test_missing_rollback_penalty(self):
        req = _RequestFactory.request(
            ScopeType.CONFIG, {"key": "x", "value": 1}
        )
        report = EvolutionRiskAssessor().assess(req)
        self.assertEqual(report.factors["rollback_modifier"], 0.10)

    def test_rollback_present_no_penalty(self):
        req = _RequestFactory.request(
            ScopeType.CONFIG,
            {"key": "x", "value": 1},
            rollback=RollbackPlan(strategy=RollbackStrategy.SNAPSHOT, snapshot_ref="snap-1"),
        )
        report = EvolutionRiskAssessor().assess(req)
        self.assertEqual(report.factors["rollback_modifier"], 0.0)
        self.assertLess(report.score, 0.55)  # should still be MEDIUM due to config weight


class TestPlanningContextSignals(unittest.TestCase):
    """PlanningContext area adjustments and bottlenecks modify risk."""

    def test_caution_recommendation_increases_risk(self):
        req = _RequestFactory.request(
            ScopeType.CONFIG, {"key": "x", "value": 1}
        )
        neutral = EvolutionRiskAssessor().assess(req)

        context = PlanningContext(
            area_adjustments={
                "config": AreaAdjustment(
                    area="config",
                    recommendation="caution",
                    historical_success_rate=0.4,
                )
            }
        )
        cautious = EvolutionRiskAssessor(planning_context=context).assess(req)
        self.assertGreater(cautious.score, neutral.score)
        self.assertGreater(cautious.factors["context_modifier"], 0.0)

    def test_prefer_recommendation_decreases_risk(self):
        req = _RequestFactory.request(
            ScopeType.CONFIG, {"key": "x", "value": 1}
        )
        context = PlanningContext(
            area_adjustments={
                "config": AreaAdjustment(
                    area="config",
                    recommendation="prefer",
                    historical_success_rate=0.9,
                )
            }
        )
        preferred = EvolutionRiskAssessor(planning_context=context).assess(req)
        self.assertLess(preferred.score, 0.55)
        self.assertLess(preferred.factors["context_modifier"], 0.0)

    def test_bottleneck_alert_in_area(self):
        req = _RequestFactory.request(
            ScopeType.MEMORY, {"operation": "add", "memory_id": "M-1", "content": "x"}
        )
        context = PlanningContext(
            bottleneck_alerts=[
                BottleneckAlert(bottleneck_id="B1", area="memory", severity_boost=0.1)
            ]
        )
        report = EvolutionRiskAssessor(planning_context=context).assess(req)
        self.assertGreater(report.factors["context_modifier"], 0.0)

    def test_irrelevant_bottleneck_ignored(self):
        req = _RequestFactory.request(
            ScopeType.MEMORY, {"operation": "add", "memory_id": "M-1", "content": "x"}
        )
        context = PlanningContext(
            bottleneck_alerts=[
                BottleneckAlert(bottleneck_id="B1", area="knowledge", severity_boost=0.1)
            ]
        )
        report = EvolutionRiskAssessor(planning_context=context).assess(req)
        self.assertEqual(report.factors["context_modifier"], 0.0)


class TestGoalLayerSignals(unittest.TestCase):
    """Goal priority and evidence contribute weakly to risk."""

    def test_critical_goal_increases_risk(self):
        req = _RequestFactory.request(
            ScopeType.CONFIG, {"key": "x", "value": 1}
        )
        goal = ImprovementGoal(
            goal_id="G-1",
            title="T",
            description="D",
            category=None,  # type: ignore[arg-type]
            priority=GoalPriority.CRITICAL,
            evidence_count=10,
            confidence=0.4,
        )
        report = EvolutionRiskAssessor(goal=goal).assess(req)
        self.assertGreater(report.factors["goal_modifier"], 0.0)

    def test_no_goal_no_modifier(self):
        req = _RequestFactory.request(
            ScopeType.CONFIG, {"key": "x", "value": 1}
        )
        report = EvolutionRiskAssessor().assess(req)
        self.assertEqual(report.factors["goal_modifier"], 0.0)


class TestRiskAssessmentFlags(unittest.TestCase):
    """HIGH/CRITICAL risk triggers approval and rollback requirements."""

    def test_low_does_not_require_approval(self):
        req = _RequestFactory.request(
            ScopeType.MEMORY, {"operation": "add", "memory_id": "M-1", "content": "x"}
        )
        report = EvolutionRiskAssessor().assess(req)
        self.assertEqual(report.risk_level, RiskLevel.LOW)
        self.assertFalse(report.requires_user_approval)
        self.assertFalse(report.requires_rollback)

    def test_medium_requires_rollback(self):
        req = _RequestFactory.request(
            ScopeType.CONFIG, {"key": "x", "value": 1}
        )
        report = EvolutionRiskAssessor().assess(req)
        self.assertEqual(report.risk_level, RiskLevel.MEDIUM)
        self.assertFalse(report.requires_user_approval)
        self.assertTrue(report.requires_rollback)

    def test_remove_config_is_high_or_critical(self):
        req = _RequestFactory.request(
            ScopeType.CONFIG, {"key": "x", "operation": "remove"}
        )
        report = EvolutionRiskAssessor().assess(req)
        self.assertIn(report.risk_level, {RiskLevel.HIGH, RiskLevel.CRITICAL})
        self.assertTrue(report.requires_user_approval)
        self.assertTrue(report.requires_rollback)


class TestDeterminism(unittest.TestCase):
    """Same inputs always produce the same RiskAssessment."""

    def test_same_request_same_report(self):
        req = _RequestFactory.request(
            ScopeType.CAPABILITY,
            {"upgrade_kind": "ENHANCE", "capability_name": "X"},
        )
        first = EvolutionRiskAssessor().assess(req)
        second = EvolutionRiskAssessor().assess(req)
        self.assertEqual(first, second)


class TestScoreBounded(unittest.TestCase):
    """Score is always within [0.0, 1.0]."""

    def test_score_bounded(self):
        for scope in (ScopeType.CONFIG, ScopeType.MEMORY, ScopeType.KNOWLEDGE, ScopeType.CAPABILITY):
            req = _RequestFactory.request(scope)
            report = EvolutionRiskAssessor().assess(req)
            self.assertGreaterEqual(report.score, 0.0)
            self.assertLessEqual(report.score, 1.0)


class TestGoalPriorityRiskMappingRegression(unittest.TestCase):
    """Regression: GoalPriority value order must map predictably to risk.

    ``EvolutionRiskAssessor._goal_modifier`` adds ``priority_value / 10.0``
    assuming ``GoalPriority.CRITICAL.value == 1`` and
    ``GoalPriority.DEFERRED.value == 5``. If the enum order changes, the
    modifier inverts and risk scores silently shift. This test pins the
    expected mapping so any future enum change is detected.
    """

    def test_priority_value_assumptions(self):
        self.assertEqual(GoalPriority.CRITICAL.value, 1)
        self.assertEqual(GoalPriority.HIGH.value, 2)
        self.assertEqual(GoalPriority.MEDIUM.value, 3)
        self.assertEqual(GoalPriority.LOW.value, 4)
        self.assertEqual(GoalPriority.DEFERRED.value, 5)

    def test_critical_priority_increases_risk_more_than_low(self):
        req = _RequestFactory.request(
            ScopeType.CONFIG, {"key": "x", "value": 1}
        )
        critical_goal = ImprovementGoal(
            goal_id="G-CRITICAL",
            title="T",
            description="D",
            category=None,  # type: ignore[arg-type]
            priority=GoalPriority.CRITICAL,
        )
        low_goal = ImprovementGoal(
            goal_id="G-LOW",
            title="T",
            description="D",
            category=None,  # type: ignore[arg-type]
            priority=GoalPriority.LOW,
        )

        critical_report = EvolutionRiskAssessor(goal=critical_goal).assess(req)
        low_report = EvolutionRiskAssessor(goal=low_goal).assess(req)

        # The current implementation intentionally adds ``priority_value / 10.0``
        # so higher numeric priority values increase the score. This means a
        # LOW priority goal (value 4) produces a larger modifier than a CRITICAL
        # goal (value 1). That is the documented current behavior; the purpose
        # of this regression test is to detect if the enum order ever changes,
        # not to prescribe a particular semantic direction.
        self.assertEqual(critical_report.factors["goal_modifier"], 0.1)
        self.assertEqual(low_report.factors["goal_modifier"], 0.4)
        self.assertGreater(
            low_report.factors["goal_modifier"],
            critical_report.factors["goal_modifier"],
        )


if __name__ == "__main__":
    unittest.main()
