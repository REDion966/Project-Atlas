"""
Phase 7.0 — Self-Evolution Foundation: ImprovementPlanner Tests.
"""

import pytest

from atlas.evolution.improvement_planner import ImprovementPlanner
from atlas.evolution.models import (
    ImprovementPriority,
    Observation,
    ObservationCategory,
)


def make_observation(category, metric_name, value, **kwargs):
    return Observation(
        category=category,
        metric_name=metric_name,
        value=value,
        **kwargs,
    )


class TestImprovementPlannerDetectWeaknesses:

    def test_empty_observations(self):
        planner = ImprovementPlanner()
        weaknesses = planner.detect_weaknesses([])
        assert weaknesses == []

    def test_no_weaknesses_healthy_system(self):
        planner = ImprovementPlanner()
        obs = [
            make_observation(
                ObservationCategory.RUNTIME_METRICS, "runtime_summary",
                {"avg_response_time_ms": 100, "request_count": 100, "error_count": 1, "error_rate_percent": 1.0},
                source="test",
            ),
            make_observation(
                ObservationCategory.REASONING_QUALITY, "reasoning_quality",
                {"success_rate": 0.95, "total_outcomes": 100, "avg_capabilities_used": 2.0},
                source="test",
            ),
        ]
        weaknesses = planner.detect_weaknesses(obs)
        assert len(weaknesses) == 0

    def test_detects_high_error_rate(self):
        planner = ImprovementPlanner()
        obs = [
            make_observation(
                ObservationCategory.RUNTIME_METRICS, "runtime_summary",
                {"avg_response_time_ms": 100, "request_count": 100, "error_count": 25, "error_rate_percent": 25.0},
                source="test",
            ),
        ]
        weaknesses = planner.detect_weaknesses(obs)
        assert len(weaknesses) >= 1
        runtime_w = [w for w in weaknesses if w.area == "runtime"]
        assert len(runtime_w) == 1
        assert runtime_w[0].severity == ImprovementPriority.CRITICAL

    def test_detects_high_response_time(self):
        planner = ImprovementPlanner()
        obs = [
            make_observation(
                ObservationCategory.RUNTIME_METRICS, "runtime_summary",
                {"avg_response_time_ms": 8000, "request_count": 50, "error_count": 2, "error_rate_percent": 4.0},
                source="test",
            ),
        ]
        weaknesses = planner.detect_weaknesses(obs)
        runtime_w = [w for w in weaknesses if w.area == "runtime"]
        assert len(runtime_w) == 1
        assert "8000" in runtime_w[0].description

    def test_detects_low_reasoning_success(self):
        planner = ImprovementPlanner()
        obs = [
            make_observation(
                ObservationCategory.REASONING_QUALITY, "reasoning_quality",
                {"success_rate": 0.45, "total_outcomes": 50, "avg_capabilities_used": 1.5},
                source="test",
            ),
        ]
        weaknesses = planner.detect_weaknesses(obs)
        reasoning_w = [w for w in weaknesses if w.area == "reasoning"]
        assert len(reasoning_w) == 1
        # 0.45 is below 0.7 but above 0.4, so severity is HIGH (not CRITICAL)
        assert reasoning_w[0].severity == ImprovementPriority.HIGH

    def test_detects_failing_tools(self):
        planner = ImprovementPlanner()
        obs = [
            make_observation(
                ObservationCategory.TOOL_USAGE, "tool_usage:broken_tool",
                {"tool_name": "broken_tool", "invocation_count": 10, "success_count": 3, "success_rate_percent": 30.0, "avg_duration_ms": 100.0},
                source="test",
            ),
        ]
        weaknesses = planner.detect_weaknesses(obs)
        tool_w = [w for w in weaknesses if w.area == "tools"]
        assert len(tool_w) == 1
        assert "broken_tool" in tool_w[0].description

    def test_detects_low_memory_relevance(self):
        planner = ImprovementPlanner()
        obs = [
            make_observation(
                ObservationCategory.MEMORY_QUALITY, "memory_quality",
                {"total_memories": 100, "avg_relevance_score": 0.3, "retrieval_success_rate": 0.95},
                source="test",
            ),
        ]
        weaknesses = planner.detect_weaknesses(obs)
        memory_w = [w for w in weaknesses if w.area == "memory"]
        assert len(memory_w) == 1
        assert memory_w[0].severity == ImprovementPriority.MEDIUM

    def test_detects_low_retrieval_rate(self):
        planner = ImprovementPlanner()
        obs = [
            make_observation(
                ObservationCategory.MEMORY_QUALITY, "memory_quality",
                {"total_memories": 100, "avg_relevance_score": 0.75, "retrieval_success_rate": 0.6},
                source="test",
            ),
        ]
        weaknesses = planner.detect_weaknesses(obs)
        memory_w = [w for w in weaknesses if w.area == "memory"]
        assert len(memory_w) == 1

    def test_detects_unhealthy_components(self):
        planner = ImprovementPlanner()
        obs = [
            make_observation(
                ObservationCategory.SYSTEM_HEALTH, "health:ai_service",
                {"component": "ai_service", "status": "unhealthy", "message": "Provider unavailable"},
                source="test",
            ),
        ]
        weaknesses = planner.detect_weaknesses(obs)
        health_w = [w for w in weaknesses if w.area == "system_health"]
        assert len(health_w) == 1
        assert health_w[0].severity == ImprovementPriority.HIGH

    def test_skips_healthy_components(self):
        planner = ImprovementPlanner()
        obs = [
            make_observation(
                ObservationCategory.SYSTEM_HEALTH, "health:ai_service",
                {"component": "ai_service", "status": "healthy", "message": "All good"},
                source="test",
            ),
        ]
        weaknesses = planner.detect_weaknesses(obs)
        health_w = [w for w in weaknesses if w.area == "system_health"]
        assert len(health_w) == 0


class TestImprovementPlannerPlanGeneration:

    def test_create_improvement_plan_none_for_empty(self):
        planner = ImprovementPlanner()
        plan = planner.create_improvement_plan([])
        assert plan is None

    def test_create_improvement_plan(self):
        planner = ImprovementPlanner()
        obs = [
            make_observation(
                ObservationCategory.RUNTIME_METRICS, "runtime_summary",
                {"avg_response_time_ms": 100, "request_count": 100, "error_count": 30, "error_rate_percent": 30.0},
                source="test",
            ),
        ]
        weaknesses = planner.detect_weaknesses(obs)
        plan = planner.create_improvement_plan(weaknesses)
        assert plan is not None
        assert plan.title == "Improve Runtime Performance"
        assert plan.priority == ImprovementPriority.CRITICAL
        assert len(plan.target_components) > 0

    def test_create_all_plans(self):
        planner = ImprovementPlanner()
        obs = [
            make_observation(
                ObservationCategory.RUNTIME_METRICS, "runtime_summary",
                {"avg_response_time_ms": 100, "request_count": 100, "error_count": 25, "error_rate_percent": 25.0},
                source="test",
            ),
            make_observation(
                ObservationCategory.REASONING_QUALITY, "reasoning_quality",
                {"success_rate": 0.45, "total_outcomes": 50, "avg_capabilities_used": 1.5},
                source="test",
            ),
        ]
        weaknesses = planner.detect_weaknesses(obs)
        plans = planner.create_all_plans(weaknesses)
        assert len(plans) >= 2
        # Plans should be sorted by priority ascending
        assert plans[0].priority.value <= plans[1].priority.value

    def test_create_all_plans_empty(self):
        planner = ImprovementPlanner()
        plans = planner.create_all_plans([])
        assert plans == []

    def test_plan_has_expected_fields(self):
        planner = ImprovementPlanner()
        obs = [
            make_observation(
                ObservationCategory.RUNTIME_METRICS, "runtime_summary",
                {"avg_response_time_ms": 6000, "request_count": 50, "error_count": 5, "error_rate_percent": 10.0},
                source="test",
            ),
        ]
        weaknesses = planner.detect_weaknesses(obs)
        plan = planner.create_improvement_plan(weaknesses)
        assert plan.plan_id.startswith("IMP-")
        assert plan.description != ""
        assert plan.expected_benefit != ""
        assert plan.complexity_estimate in ("low", "medium", "high")