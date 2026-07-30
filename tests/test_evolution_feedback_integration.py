"""
Phase 12.4 — Evolution Feedback Integration Tests.

Tests that ImprovementPlanner correctly consumes EvolutionInsight objects
to adjust weakness detection and plan generation based on past outcomes.

Backward compatibility: all existing call patterns without insights must
produce identical results.
"""

from datetime import datetime

import pytest

from atlas.evolution.improvement_planner import ImprovementPlanner, _boost_priority, _reduce_priority
from atlas.evolution.models import (
    EvolutionInsight,
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    Observation,
    ObservationCategory,
    Weakness,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_observation(
    category: ObservationCategory = ObservationCategory.RUNTIME_METRICS,
    value: dict | None = None,
) -> Observation:
    """Create a test Observation."""
    return Observation(
        category=category,
        metric_name="test_metric",
        value=value or {"avg_response_time_ms": 8200, "error_rate_percent": 15.0},
        timestamp=datetime.now(),
        source="test",
    )


def make_successful_insight(
    title: str = "Improve Memory Retrieval Ranking",
    summary: str = "Improve the ranking algorithm for memory retrieval",
    effectiveness: float = 0.85,
    confidence: float = 0.7,
) -> EvolutionInsight:
    """Create a successful evolution insight."""
    return EvolutionInsight(
        insight_id="INS-SUCCESS-001",
        proposal_id="PROP-SUCCESS",
        execution_record_id="EVR-SUCCESS",
        tracked_goal_id="TRK-SUCCESS",
        outcome="success",
        confidence=confidence,
        effectiveness_score=effectiveness,
        evidence_summary="Improvement succeeded.",
        evidence_count=30,
        evidence_quality=0.8,
        regression_risk=0.1,
        analyzed_at=datetime.now(),
        proposal_title=title,
        proposal_summary=summary,
    )


def make_failed_insight(
    title: str = "Tool Retry Strategy",
    summary: str = "Implement retry logic for tool failures to improve reliability",
    effectiveness: float = 0.2,
    confidence: float = 0.75,
    regression_risk: float = 0.7,
) -> EvolutionInsight:
    """Create a failed evolution insight with high regression risk."""
    return EvolutionInsight(
        insight_id="INS-FAIL-001",
        proposal_id="PROP-FAIL",
        execution_record_id="EVR-FAIL",
        tracked_goal_id="TRK-FAIL",
        outcome="failure",
        confidence=confidence,
        effectiveness_score=effectiveness,
        evidence_summary="Improvement introduced regressions.",
        evidence_count=25,
        evidence_quality=0.6,
        regression_risk=regression_risk,
        analyzed_at=datetime.now(),
        proposal_title=title,
        proposal_summary=summary,
    )


def make_low_confidence_insight(
    title: str = "System Health Monitoring",
    summary: str = "Add monitoring for system components",
    confidence: float = 0.2,
) -> EvolutionInsight:
    """Create an insight with low confidence (should be ignored)."""
    return EvolutionInsight(
        insight_id="INS-LOW-001",
        proposal_id="PROP-LOW",
        execution_record_id="EVR-LOW",
        tracked_goal_id="TRK-LOW",
        outcome="success",
        confidence=confidence,
        effectiveness_score=0.6,
        evidence_summary="Some evidence.",
        evidence_count=3,
        evidence_quality=0.4,
        regression_risk=0.1,
        analyzed_at=datetime.now(),
        proposal_title=title,
        proposal_summary=summary,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:

    def test_planner_works_normally_without_insights(self):
        """Planner without insights produces identical results to Phase 11."""
        planner = ImprovementPlanner()
        observations = [
            make_observation(
                ObservationCategory.RUNTIME_METRICS,
                {"avg_response_time_ms": 8200, "error_rate_percent": 15.0},
            ),
        ]

        weaknesses = planner.detect_weaknesses(observations)
        assert len(weaknesses) >= 1
        assert weaknesses[0].area == "runtime"

        plan = planner.create_improvement_plan(weaknesses)
        assert plan is not None
        assert plan.priority == ImprovementPriority.HIGH

    def test_detect_weaknesses_no_insights_default_param(self):
        """Calling detect_weaknesses without insights param works (defaults to None)."""
        planner = ImprovementPlanner()
        weaknesses = planner.detect_weaknesses([])
        assert weaknesses == []

    def test_create_plan_no_insights_default_param(self):
        """Calling create_improvement_plan without insights param works."""
        planner = ImprovementPlanner()
        observations = [
            make_observation(
                ObservationCategory.RUNTIME_METRICS,
                {"avg_response_time_ms": 8200, "error_rate_percent": 15.0},
            ),
        ]
        weaknesses = planner.detect_weaknesses(observations)
        plan = planner.create_improvement_plan(weaknesses)
        assert plan is not None


class TestSuccessfulInsightInfluence:

    def test_successful_insight_influences_planning(self):
        """
        A successful insight about memory ranking should boost priority
        for a memory weakness.
        """
        planner = ImprovementPlanner()
        observations = [
            make_observation(
                ObservationCategory.MEMORY_QUALITY,
                {"avg_relevance_score": 0.3, "retrieval_success_rate": 0.6},
            ),
        ]
        insights = [make_successful_insight()]

        weaknesses = planner.detect_weaknesses(observations, insights=insights)

        # Memory weakness with MEDIUM default should be boosted
        memory_weaknesses = [w for w in weaknesses if w.area == "memory"]
        assert len(memory_weaknesses) >= 1
        # MEDIUM boosted by success → HIGH
        assert memory_weaknesses[0].severity == ImprovementPriority.HIGH
        assert "Evolution feedback" in memory_weaknesses[0].description

    def test_successful_insight_in_plan_description(self):
        """
        A successful insight should appear in the plan description
        when that area has a weakness.
        """
        planner = ImprovementPlanner()
        observations = [
            make_observation(
                ObservationCategory.MEMORY_QUALITY,
                {"avg_relevance_score": 0.3, "retrieval_success_rate": 0.6},
            ),
        ]
        insights = [make_successful_insight()]

        weaknesses = planner.detect_weaknesses(observations, insights=insights)
        plan = planner.create_improvement_plan(weaknesses, insights=insights)

        assert plan is not None
        assert "Evolution history" in plan.description


class TestFailedInsightInfluence:

    def test_failed_insight_influences_planning(self):
        """
        A failed insight about tools should reduce priority for a
        tool weakness.
        """
        planner = ImprovementPlanner()
        observations = [
            make_observation(
                ObservationCategory.TOOL_USAGE,
                {"tool_name": "search", "success_rate_percent": 40},
            ),
        ]
        insights = [make_failed_insight()]

        weaknesses = planner.detect_weaknesses(observations, insights=insights)

        # Tool weakness with MEDIUM default should be reduced
        tool_weaknesses = [w for w in weaknesses if w.area == "tools"]
        assert len(tool_weaknesses) >= 1
        # MEDIUM reduced by failure → LOW
        assert tool_weaknesses[0].severity == ImprovementPriority.LOW


class TestLowConfidenceInsight:

    def test_low_confidence_insight_is_ignored(self):
        """Insights with confidence < 0.3 should not affect planning."""
        planner = ImprovementPlanner()
        observations = [
            make_observation(
                ObservationCategory.MEMORY_QUALITY,
                {"avg_relevance_score": 0.3, "retrieval_success_rate": 0.6},
            ),
        ]
        insights = [make_low_confidence_insight()]

        weaknesses = planner.detect_weaknesses(observations, insights=insights)

        memory_weaknesses = [w for w in weaknesses if w.area == "memory"]
        assert len(memory_weaknesses) >= 1
        # Should remain MEDIUM (default) — low confidence insight ignored
        assert memory_weaknesses[0].severity == ImprovementPriority.MEDIUM


class TestRegressionRisk:

    def test_regression_risk_affects_prioritization(self):
        """High regression risk influences planning priority reduction."""
        planner = ImprovementPlanner()
        observations = [
            make_observation(
                ObservationCategory.TOOL_USAGE,
                {"tool_name": "search", "success_rate_percent": 40},
            ),
        ]
        # Failed tool insight with high regression risk
        insights = [make_failed_insight(
            regression_risk=0.85,
        )]

        weaknesses = planner.detect_weaknesses(observations, insights=insights)

        tool_weaknesses = [w for w in weaknesses if w.area == "tools"]
        assert len(tool_weaknesses) >= 1
        # MEDIUM → LOW because of high regression risk failure
        assert tool_weaknesses[0].severity == ImprovementPriority.LOW


class TestPriorityHelpers:

    def test_boost_priority(self):
        """_boost_priority increases severity one level."""
        assert _boost_priority(ImprovementPriority.LOW) == ImprovementPriority.MEDIUM
        assert _boost_priority(ImprovementPriority.MEDIUM) == ImprovementPriority.HIGH
        assert _boost_priority(ImprovementPriority.HIGH) == ImprovementPriority.CRITICAL
        assert _boost_priority(ImprovementPriority.CRITICAL) == ImprovementPriority.CRITICAL

    def test_reduce_priority(self):
        """_reduce_priority decreases severity one level."""
        assert _reduce_priority(ImprovementPriority.CRITICAL) == ImprovementPriority.HIGH
        assert _reduce_priority(ImprovementPriority.HIGH) == ImprovementPriority.MEDIUM
        assert _reduce_priority(ImprovementPriority.MEDIUM) == ImprovementPriority.LOW
        assert _reduce_priority(ImprovementPriority.LOW) == ImprovementPriority.LOW

    def test_boost_no_change_at_max(self):
        """_boost_priority at CRITICAL stays CRITICAL."""
        assert _boost_priority(ImprovementPriority.CRITICAL) == ImprovementPriority.CRITICAL

    def test_reduce_no_change_at_min(self):
        """_reduce_priority at LOW stays LOW."""
        assert _reduce_priority(ImprovementPriority.LOW) == ImprovementPriority.LOW


class TestAllPlansWithInsights:

    def test_create_all_plans_with_insights(self):
        """create_all_plans accepts optional insights parameter."""
        planner = ImprovementPlanner()
        observations = [
            make_observation(
                ObservationCategory.RUNTIME_METRICS,
                {"avg_response_time_ms": 8200, "error_rate_percent": 15.0},
            ),
        ]
        insights = [make_successful_insight()]

        weaknesses = planner.detect_weaknesses(observations, insights=insights)
        plans = planner.create_all_plans(weaknesses, insights=insights)

        assert len(plans) >= 1

    def test_create_all_plans_without_insights(self):
        """create_all_plans without insights behaves as before."""
        planner = ImprovementPlanner()
        observations = [
            make_observation(
                ObservationCategory.RUNTIME_METRICS,
                {"avg_response_time_ms": 8200, "error_rate_percent": 15.0},
            ),
        ]

        weaknesses = planner.detect_weaknesses(observations)
        plans = planner.create_all_plans(weaknesses)

        assert len(plans) >= 1
