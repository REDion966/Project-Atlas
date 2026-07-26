"""
Phase 7.0 — Self-Evolution Foundation: SelfObservationEngine Tests.
"""

import pytest

from atlas.evolution.models import ObservationCategory
from atlas.evolution.self_observation import SelfObservationEngine


class TestSelfObservationEngineInit:

    def test_default_max_observations(self):
        engine = SelfObservationEngine()
        assert engine.observation_count == 0

    def test_custom_max_observations(self):
        engine = SelfObservationEngine(max_observations=50)
        assert engine.observation_count == 0

    def test_invalid_max_observations(self):
        with pytest.raises(ValueError, match="positive integer"):
            SelfObservationEngine(max_observations=0)

        with pytest.raises(ValueError, match="positive integer"):
            SelfObservationEngine(max_observations=-1)


class TestSelfObservationEngineObserve:

    def test_observe_runtime_metrics(self):
        engine = SelfObservationEngine()
        obs = engine.observe_runtime_metrics(
            avg_response_time_ms=150.0,
            request_count=100,
            error_count=5,
        )
        assert obs.category == ObservationCategory.RUNTIME_METRICS
        assert obs.metric_name == "runtime_summary"
        assert obs.value["avg_response_time_ms"] == 150.0
        assert obs.value["request_count"] == 100
        assert obs.value["error_count"] == 5
        assert obs.value["error_rate_percent"] == 5.0
        assert engine.observation_count == 1

    def test_observe_runtime_metrics_zero_requests(self):
        engine = SelfObservationEngine()
        obs = engine.observe_runtime_metrics(
            avg_response_time_ms=0.0,
            request_count=0,
            error_count=0,
        )
        assert obs.value["error_rate_percent"] == 0.0
        assert obs.unit == "composite"

    def test_observe_reasoning_quality(self):
        engine = SelfObservationEngine()
        obs = engine.observe_reasoning_quality(
            success_rate=0.85,
            total_outcomes=100,
            avg_capabilities_used=2.5,
        )
        assert obs.category == ObservationCategory.REASONING_QUALITY
        assert obs.value["success_rate"] == 0.85
        assert obs.value["total_outcomes"] == 100
        assert obs.value["avg_capabilities_used"] == 2.5
        assert engine.observation_count == 1

    def test_observe_tool_usage(self):
        engine = SelfObservationEngine()
        obs = engine.observe_tool_usage(
            tool_name="echo",
            invocation_count=50,
            success_count=48,
            avg_duration_ms=12.5,
        )
        assert obs.category == ObservationCategory.TOOL_USAGE
        assert obs.metric_name == "tool_usage:echo"
        assert obs.value["tool_name"] == "echo"
        assert obs.value["invocation_count"] == 50
        assert obs.value["success_count"] == 48
        assert obs.value["success_rate_percent"] == 96.0
        assert obs.value["avg_duration_ms"] == 12.5
        assert engine.observation_count == 1

    def test_observe_tool_usage_zero_invocations(self):
        engine = SelfObservationEngine()
        obs = engine.observe_tool_usage(
            tool_name="never_used",
            invocation_count=0,
            success_count=0,
            avg_duration_ms=0.0,
        )
        assert obs.value["success_rate_percent"] == 0.0

    def test_observe_memory_quality(self):
        engine = SelfObservationEngine()
        obs = engine.observe_memory_quality(
            total_memories=500,
            avg_relevance_score=0.75,
            retrieval_success_rate=0.95,
        )
        assert obs.category == ObservationCategory.MEMORY_QUALITY
        assert obs.value["total_memories"] == 500
        assert obs.value["avg_relevance_score"] == 0.75
        assert obs.value["retrieval_success_rate"] == 0.95
        assert engine.observation_count == 1

    def test_observe_system_health(self):
        engine = SelfObservationEngine()
        obs = engine.observe_system_health(
            component="ai_service",
            status="healthy",
            message="All providers operational",
        )
        assert obs.category == ObservationCategory.SYSTEM_HEALTH
        assert obs.metric_name == "health:ai_service"
        assert obs.value["component"] == "ai_service"
        assert obs.value["status"] == "healthy"
        assert obs.value["message"] == "All providers operational"
        assert obs.unit == "status"
        assert engine.observation_count == 1

    def test_observe_system_health_degraded(self):
        engine = SelfObservationEngine()
        obs = engine.observe_system_health(
            component="memory_service",
            status="degraded",
            message="High latency detected",
        )
        assert obs.value["status"] == "degraded"


class TestSelfObservationEngineRetrieval:

    def test_recent_observations(self):
        engine = SelfObservationEngine()
        for i in range(5):
            engine.observe_runtime_metrics(
                avg_response_time_ms=float(i * 10),
                request_count=10,
                error_count=i,
            )
        recent = engine.recent_observations(3)
        assert len(recent) == 3

    def test_recent_observations_invalid_n(self):
        engine = SelfObservationEngine()
        assert engine.recent_observations(0) == []
        assert engine.recent_observations(-1) == []

    def test_recent_observations_more_than_available(self):
        engine = SelfObservationEngine()
        engine.observe_runtime_metrics(100.0, 10, 1)
        assert len(engine.recent_observations(10)) == 1

    def test_observations_by_category(self):
        engine = SelfObservationEngine()
        engine.observe_runtime_metrics(100.0, 10, 1)
        engine.observe_reasoning_quality(0.9, 50, 2.0)
        engine.observe_runtime_metrics(200.0, 20, 2)

        runtime_obs = engine.observations_by_category(ObservationCategory.RUNTIME_METRICS)
        assert len(runtime_obs) == 2

        reasoning_obs = engine.observations_by_category(ObservationCategory.REASONING_QUALITY)
        assert len(reasoning_obs) == 1

        tool_obs = engine.observations_by_category(ObservationCategory.TOOL_USAGE)
        assert len(tool_obs) == 0

    def test_observations_by_category_limit(self):
        engine = SelfObservationEngine()
        for _ in range(10):
            engine.observe_runtime_metrics(100.0, 10, 1)

        obs = engine.observations_by_category(ObservationCategory.RUNTIME_METRICS, n=3)
        assert len(obs) == 3

    def test_latest_observation_found(self):
        engine = SelfObservationEngine()
        engine.observe_runtime_metrics(100.0, 10, 1)
        engine.observe_tool_usage("echo", 50, 48, 12.5)

        latest = engine.latest_observation("tool_usage:echo")
        assert latest is not None
        assert latest.value["tool_name"] == "echo"

    def test_latest_observation_not_found(self):
        engine = SelfObservationEngine()
        assert engine.latest_observation("nonexistent") is None

    def test_observation_count(self):
        engine = SelfObservationEngine()
        assert engine.observation_count == 0
        engine.observe_runtime_metrics(100.0, 10, 1)
        assert engine.observation_count == 1
        engine.observe_runtime_metrics(200.0, 20, 2)
        assert engine.observation_count == 2

    def test_record_observation_directly(self):
        engine = SelfObservationEngine()
        engine.observe_runtime_metrics(100.0, 10, 1)
        assert engine.observation_count == 1

    def test_clear(self):
        engine = SelfObservationEngine()
        engine.observe_runtime_metrics(100.0, 10, 1)
        engine.observe_reasoning_quality(0.9, 50, 2.0)
        assert engine.observation_count == 2
        engine.clear()
        assert engine.observation_count == 0

    def test_max_observations_enforced(self):
        engine = SelfObservationEngine(max_observations=3)
        for i in range(5):
            engine.observe_runtime_metrics(
                avg_response_time_ms=float(i * 10),
                request_count=10,
                error_count=i,
            )
        assert engine.observation_count == 3