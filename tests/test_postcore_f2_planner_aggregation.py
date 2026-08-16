"""Post-Core F2 — Planner Observation Aggregation.

Verifies ImprovementPlanner detects weaknesses from the mean of the
relevant metric across the bounded per-category observation window rather
than only the newest observation.

Runtime/reasoning/memory detectors aggregate:
  - avg_response_time_ms / error_rate_percent
  - success_rate
  - avg_relevance_score / retrieval_success_rate

Single observation yields mean == value, so single-observation behavior is
preserved exactly. Tool and health detectors are unchanged (they already
operate over the whole window). Insight feedback adjustment is preserved.
"""

from datetime import datetime

from atlas.evolution.improvement_planner import ImprovementPlanner
from atlas.evolution.models import (
    EvolutionInsight,
    ImprovementPriority,
    Observation,
    ObservationCategory,
)


def make_observation(
    category: ObservationCategory,
    value: dict,
    metric_name: str = "m",
    timestamp: datetime | None = None,
) -> Observation:
    return Observation(
        category=category,
        metric_name=metric_name,
        value=value,
        timestamp=timestamp or datetime.now(),
        source="test",
    )


def runtime_obs(avg_time: float, error_rate: float) -> Observation:
    return make_observation(
        ObservationCategory.RUNTIME_METRICS,
        {
            "avg_response_time_ms": avg_time,
            "request_count": 10,
            "error_count": 0,
            "error_rate_percent": error_rate,
        },
        metric_name="runtime_summary",
    )


def reasoning_obs(success_rate: float) -> Observation:
    return make_observation(
        ObservationCategory.REASONING_QUALITY,
        {
            "success_rate": success_rate,
            "total_outcomes": 10,
            "avg_capabilities_used": 1.0,
        },
        metric_name="reasoning_quality",
    )


def memory_obs(relevance: float, retrieval: float) -> Observation:
    return make_observation(
        ObservationCategory.MEMORY_QUALITY,
        {
            "total_memories": 100,
            "avg_relevance_score": relevance,
            "retrieval_success_rate": retrieval,
        },
        metric_name="memory_quality",
    )


def areas(weaknesses) -> list[str]:
    return [w.area for w in weaknesses]


class TestSpikeSuppression:
    def test_healthy_runtime_window_with_bad_latest_spike(self):
        planner = ImprovementPlanner()
        observations = [
            runtime_obs(100.0, 1.0),
            runtime_obs(150.0, 2.0),
            runtime_obs(200.0, 1.5),
            runtime_obs(9000.0, 3.0),
        ]
        # mean = 2362.5ms <= 5000, mean error = 1.875 <= 10 -> no weakness
        assert "runtime" not in areas(planner.detect_weaknesses(observations))

    def test_healthy_reasoning_window_with_bad_latest_spike(self):
        planner = ImprovementPlanner()
        observations = [
            reasoning_obs(0.95),
            reasoning_obs(0.90),
            reasoning_obs(0.85),
            reasoning_obs(0.30),
        ]
        # mean = 0.75 >= 0.7 -> no weakness
        assert "reasoning" not in areas(planner.detect_weaknesses(observations))

    def test_sustained_bad_window_creates_weakness(self):
        planner = ImprovementPlanner()
        observations = [
            runtime_obs(6000.0, 5.0),
            runtime_obs(7000.0, 6.0),
            runtime_obs(8000.0, 7.0),
        ]
        # mean = 7000ms > 5000 -> weakness sustained
        assert "runtime" in areas(planner.detect_weaknesses(observations))

    def test_sustained_bad_reasoning_creates_weakness(self):
        planner = ImprovementPlanner()
        observations = [
            reasoning_obs(0.5),
            reasoning_obs(0.6),
            reasoning_obs(0.4),
        ]
        # mean = 0.5 < 0.7 -> weakness sustained
        assert "reasoning" in areas(planner.detect_weaknesses(observations))


class TestMeanCalculation:
    def test_runtime_mean_calculation(self):
        planner = ImprovementPlanner()
        observations = [
            runtime_obs(2000.0, 3.0),
            runtime_obs(8000.0, 25.0),
            runtime_obs(3000.0, 2.0),
        ]
        # mean time = 4333.33 <= 5000; mean error = 10.0 (not > 10) -> none
        assert "runtime" not in areas(planner.detect_weaknesses(observations))

    def test_runtime_mean_error_rate_trigger(self):
        planner = ImprovementPlanner()
        observations = [
            runtime_obs(1000.0, 20.0),
            runtime_obs(1000.0, 30.0),
            runtime_obs(1000.0, 25.0),
        ]
        # mean error = 25.0 > 20 -> CRITICAL
        runtime = [w for w in planner.detect_weaknesses(observations) if w.area == "runtime"]
        assert len(runtime) == 1
        assert runtime[0].severity == ImprovementPriority.CRITICAL

    def test_reasoning_mean_borderline(self):
        planner = ImprovementPlanner()
        observations = [
            reasoning_obs(0.50),
            reasoning_obs(0.80),
            reasoning_obs(0.80),
        ]
        # mean = 0.7 >= 0.7 -> none
        assert "reasoning" not in areas(planner.detect_weaknesses(observations))

    def test_reasoning_mean_below_threshold(self):
        planner = ImprovementPlanner()
        observations = [
            reasoning_obs(0.40),
            reasoning_obs(0.60),
            reasoning_obs(0.50),
        ]
        # mean = 0.5 < 0.7 -> HIGH (>= 0.4)
        reasoning = [w for w in planner.detect_weaknesses(observations) if w.area == "reasoning"]
        assert len(reasoning) == 1
        assert reasoning[0].severity == ImprovementPriority.HIGH

    def test_memory_mean_calculation(self):
        planner = ImprovementPlanner()
        observations = [
            memory_obs(0.9, 0.75),
            memory_obs(0.9, 0.85),
            memory_obs(0.9, 0.95),
        ]
        # mean retrieval = 0.85 >= 0.8; mean relevance = 0.9 >= 0.5 -> none
        assert "memory" not in areas(planner.detect_weaknesses(observations))

    def test_memory_mean_below_threshold(self):
        planner = ImprovementPlanner()
        observations = [
            memory_obs(0.3, 0.5),
            memory_obs(0.3, 0.5),
            memory_obs(0.3, 0.5),
        ]
        memory = [w for w in planner.detect_weaknesses(observations) if w.area == "memory"]
        assert len(memory) == 1
        assert "relevance" in memory[0].description
        assert "retrieval" in memory[0].description


class TestSingleObservationCompatibility:
    def test_single_runtime_matches_previous_behavior(self):
        planner = ImprovementPlanner()
        assert "runtime" in areas(planner.detect_weaknesses([runtime_obs(9000.0, 3.0)]))

    def test_single_reasoning_matches_previous_behavior(self):
        planner = ImprovementPlanner()
        assert "reasoning" in areas(planner.detect_weaknesses([reasoning_obs(0.65)]))

    def test_single_memory_matches_previous_behavior(self):
        planner = ImprovementPlanner()
        memory = [w for w in planner.detect_weaknesses([memory_obs(0.3, 0.5)]) if w.area == "memory"]
        assert len(memory) == 1
        assert "relevance" in memory[0].description
        assert "retrieval" in memory[0].description


class TestMixedWindow:
    def test_mixed_runtime_uses_aggregate_not_latest(self):
        planner = ImprovementPlanner()
        # healthy latest but mostly bad -> weakness via mean
        mostly_bad = [
            runtime_obs(9000.0, 3.0),
            runtime_obs(9000.0, 3.0),
            runtime_obs(9000.0, 3.0),
            runtime_obs(100.0, 1.0),
        ]
        assert "runtime" in areas(planner.detect_weaknesses(mostly_bad))

        # bad latest but mostly healthy -> no weakness via mean
        mostly_healthy = [
            runtime_obs(100.0, 1.0),
            runtime_obs(100.0, 1.0),
            runtime_obs(100.0, 1.0),
            runtime_obs(9000.0, 3.0),
        ]
        assert "runtime" not in areas(planner.detect_weaknesses(mostly_healthy))


class TestDeterminism:
    def test_detection_deterministic(self):
        observations = [
            runtime_obs(2000.0, 3.0),
            runtime_obs(9000.0, 30.0),
            reasoning_obs(0.5),
            memory_obs(0.3, 0.6),
        ]
        a = ImprovementPlanner().detect_weaknesses(observations)
        b = ImprovementPlanner().detect_weaknesses(observations)
        assert [(w.area, w.severity, w.description) for w in a] == [
            (w.area, w.severity, w.description) for w in b
        ]

    def test_mean_value_helper(self):
        observations = [runtime_obs(100.0, 1.0), runtime_obs(300.0, 3.0)]
        assert ImprovementPlanner._mean_value(observations, "avg_response_time_ms", 0.0) == 200.0
        assert ImprovementPlanner._mean_value([], "avg_response_time_ms", 0.0) == 0.0
        assert ImprovementPlanner._mean_value([], "success_rate", 1.0) == 1.0


class TestFeedbackPreserved:
    def test_failure_insight_reduces_tool_weakness(self):
        planner = ImprovementPlanner()
        observations = [
            make_observation(
                ObservationCategory.TOOL_USAGE,
                {"tool_name": "search", "success_rate_percent": 40.0},
                metric_name="tool_usage:search",
            ),
        ]
        insight = EvolutionInsight(
            insight_id="INS-F2-001",
            proposal_id="PROP-F2",
            execution_record_id="EVR-F2",
            tracked_goal_id="TRK-F2",
            outcome="failure",
            confidence=0.8,
            effectiveness_score=0.2,
            evidence_summary="failed",
            evidence_count=2,
            evidence_quality=0.6,
            regression_risk=0.7,
            analyzed_at=datetime.now(),
            proposal_title="Tool Retry Strategy",
            proposal_summary="implement retry logic for tool failures",
        )
        tool = [w for w in planner.detect_weaknesses(observations, insights=[insight]) if w.area == "tools"]
        assert len(tool) == 1
        assert tool[0].severity == ImprovementPriority.LOW

    def test_success_insight_boosts_memory_weakness(self):
        planner = ImprovementPlanner()
        observations = [memory_obs(0.3, 0.6)]
        success = EvolutionInsight(
            insight_id="INS-F2-002",
            proposal_id="PROP-F2",
            execution_record_id="EVR-F2",
            tracked_goal_id="TRK-F2",
            outcome="success",
            confidence=0.8,
            effectiveness_score=0.9,
            evidence_summary="succeeded",
            evidence_count=3,
            evidence_quality=0.8,
            regression_risk=0.1,
            analyzed_at=datetime.now(),
            proposal_title="Improve Memory Retrieval Ranking",
            proposal_summary="improve ranking algorithm for memory retrieval",
        )
        memory = [w for w in planner.detect_weaknesses(observations, insights=[success]) if w.area == "memory"]
        assert len(memory) == 1
        assert memory[0].severity == ImprovementPriority.HIGH


class TestEmptyCategories:
    def test_no_observations_returns_empty(self):
        assert ImprovementPlanner().detect_weaknesses([]) == []

    def test_missing_runtime_category_no_runtime_weakness(self):
        planner = ImprovementPlanner()
        weaknesses = planner.detect_weaknesses([reasoning_obs(0.5)])
        assert "runtime" not in areas(weaknesses)
        assert "reasoning" in areas(weaknesses)

    def test_missing_category_values_use_defaults(self):
        planner = ImprovementPlanner()
        observations = [
            make_observation(
                ObservationCategory.RUNTIME_METRICS,
                {"request_count": 1, "error_count": 0},
                metric_name="runtime_summary",
            )
        ]
        assert "runtime" not in areas(planner.detect_weaknesses(observations))
