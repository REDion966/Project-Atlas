"""ToolEffectivenessTracker tests."""

from datetime import datetime

import pytest

from atlas.toolchain.catalog import (
    DEFAULT_EFFECTIVENESS,
    EFFECTIVENESS_BASELINE_MS,
    EFFECTIVENESS_SPEED_WEIGHT,
    EFFECTIVENESS_SUCCESS_WEIGHT,
)
from atlas.toolchain.effectiveness import ToolEffectivenessTracker
from atlas.toolchain.models import ToolEffectivenessRecord, ToolEffectivenessScore


class TestRecording:
    def test_record_single_observation(self):
        tracker = ToolEffectivenessTracker()
        record = tracker.record("echo", success=True, execution_time_ms=50.0)
        assert record.tool_name == "echo"
        assert record.success is True
        assert record.execution_time_ms == 50.0
        assert tracker.total_observations == 1

    def test_record_multiple_observations(self):
        tracker = ToolEffectivenessTracker()
        tracker.record("echo", success=True)
        tracker.record("echo", success=False)
        tracker.record("echo", success=True)
        assert tracker.total_observations == 3
        assert tracker.observed_tool_count == 1

    def test_record_empty_tool_name_raises(self):
        tracker = ToolEffectivenessTracker()
        with pytest.raises(ValueError):
            tracker.record("", success=True)

    def test_record_negative_time_clamped_to_zero(self):
        tracker = ToolEffectivenessTracker()
        record = tracker.record("echo", success=True, execution_time_ms=-10.0)
        assert record.execution_time_ms == 0.0

    def test_record_with_context(self):
        tracker = ToolEffectivenessTracker()
        record = tracker.record(
            "echo",
            success=True,
            context={"path": "/tmp"},
        )
        assert record.context_hash != ""

    def test_record_with_skill_id(self):
        tracker = ToolEffectivenessTracker()
        record = tracker.record("echo", success=True, skill_id="sk1")
        assert record.skill_id == "sk1"

    def test_record_with_metadata(self):
        tracker = ToolEffectivenessTracker()
        record = tracker.record("echo", success=True, metadata={"k": "v"})
        assert record.metadata == {"k": "v"}

    def test_record_observation_prebuilt(self):
        tracker = ToolEffectivenessTracker()
        record = ToolEffectivenessRecord(
            record_id="r1",
            tool_name="echo",
            success=True,
        )
        tracker.record_observation(record)
        assert tracker.total_observations == 1

    def test_record_observation_empty_tool_name_raises(self):
        tracker = ToolEffectivenessTracker()
        record = ToolEffectivenessRecord(record_id="r1", tool_name="")
        with pytest.raises(ValueError):
            tracker.record_observation(record)


class TestScoring:
    def test_score_no_observations_returns_default(self):
        tracker = ToolEffectivenessTracker()
        score = tracker.score("echo")
        assert score.tool_name == "echo"
        assert score.total_observations == 0
        assert score.effectiveness == DEFAULT_EFFECTIVENESS
        assert score.last_observed_at is None

    def test_score_all_success(self):
        tracker = ToolEffectivenessTracker()
        for _ in range(5):
            tracker.record("echo", success=True, execution_time_ms=0.0)
        score = tracker.score("echo")
        assert score.total_observations == 5
        assert score.success_count == 5
        assert score.failure_count == 0
        assert score.success_rate == 1.0
        # With 0ms execution time, speed_score = 1.0
        expected = EFFECTIVENESS_SUCCESS_WEIGHT * 1.0 + EFFECTIVENESS_SPEED_WEIGHT * 1.0
        assert score.effectiveness == pytest.approx(expected)

    def test_score_all_failure(self):
        tracker = ToolEffectivenessTracker()
        for _ in range(3):
            tracker.record("echo", success=False, execution_time_ms=0.0)
        score = tracker.score("echo")
        assert score.success_rate == 0.0
        assert score.failure_count == 3
        # success_rate=0, speed_score=1.0
        expected = EFFECTIVENESS_SUCCESS_WEIGHT * 0.0 + EFFECTIVENESS_SPEED_WEIGHT * 1.0
        assert score.effectiveness == pytest.approx(expected)

    def test_score_mixed(self):
        tracker = ToolEffectivenessTracker()
        tracker.record("echo", success=True, execution_time_ms=0.0)
        tracker.record("echo", success=False, execution_time_ms=0.0)
        score = tracker.score("echo")
        assert score.total_observations == 2
        assert score.success_count == 1
        assert score.failure_count == 1
        assert score.success_rate == 0.5

    def test_score_avg_execution_time(self):
        tracker = ToolEffectivenessTracker()
        tracker.record("echo", success=True, execution_time_ms=100.0)
        tracker.record("echo", success=True, execution_time_ms=200.0)
        score = tracker.score("echo")
        assert score.avg_execution_time_ms == 150.0

    def test_score_last_observed_at(self):
        tracker = ToolEffectivenessTracker()
        tracker.record("echo", success=True)
        tracker.record("echo", success=True)
        score = tracker.score("echo")
        assert score.last_observed_at is not None
        assert isinstance(score.last_observed_at, datetime)

    def test_score_effectiveness_formula(self):
        tracker = ToolEffectivenessTracker()
        # 4 successes, 1 failure → success_rate = 0.8
        # avg_time = 200ms → speed_score = 1 - 200/1000 = 0.8
        tracker.record("echo", success=True, execution_time_ms=100.0)
        tracker.record("echo", success=True, execution_time_ms=200.0)
        tracker.record("echo", success=True, execution_time_ms=300.0)
        tracker.record("echo", success=True, execution_time_ms=100.0)
        tracker.record("echo", success=False, execution_time_ms=300.0)
        score = tracker.score("echo")
        expected = (
            EFFECTIVENESS_SUCCESS_WEIGHT * 0.8
            + EFFECTIVENESS_SPEED_WEIGHT * 0.8
        )
        assert score.effectiveness == pytest.approx(expected, rel=1e-6)

    def test_score_effectiveness_capped_at_one(self):
        """When avg_time is very low and success_rate is 1.0, effectiveness = 1.0."""
        tracker = ToolEffectivenessTracker()
        tracker.record("echo", success=True, execution_time_ms=0.0)
        score = tracker.score("echo")
        assert score.effectiveness == pytest.approx(1.0)

    def test_score_speed_floor_zero(self):
        """When avg_time exceeds baseline, speed_score floors at 0.0."""
        tracker = ToolEffectivenessTracker()
        tracker.record("echo", success=True, execution_time_ms=2000.0)
        score = tracker.score("echo")
        # speed_score = max(0, 1 - 2000/1000) = max(0, -1) = 0
        expected = EFFECTIVENESS_SUCCESS_WEIGHT * 1.0 + EFFECTIVENESS_SPEED_WEIGHT * 0.0
        assert score.effectiveness == pytest.approx(expected)


class TestScoreAll:
    def test_score_all_multiple_tools(self):
        tracker = ToolEffectivenessTracker()
        tracker.record("echo", success=True)
        tracker.record("search", success=False)
        scores = tracker.score_all()
        assert len(scores) == 2
        assert {s.tool_name for s in scores} == {"echo", "search"}

    def test_score_all_sorted_by_name(self):
        tracker = ToolEffectivenessTracker()
        tracker.record("zeta", success=True)
        tracker.record("alpha", success=True)
        scores = tracker.score_all()
        assert [s.tool_name for s in scores] == ["alpha", "zeta"]

    def test_score_all_empty(self):
        tracker = ToolEffectivenessTracker()
        assert tracker.score_all() == []


class TestTopTools:
    def test_top_tools_sorted_by_effectiveness(self):
        tracker = ToolEffectivenessTracker()
        # echo: high effectiveness (all success, fast)
        for _ in range(5):
            tracker.record("echo", success=True, execution_time_ms=10.0)
        # slow: low effectiveness (all failure, slow)
        for _ in range(5):
            tracker.record("slow", success=False, execution_time_ms=900.0)
        top = tracker.top_tools(limit=2)
        assert len(top) == 2
        assert top[0].tool_name == "echo"
        assert top[0].effectiveness > top[1].effectiveness

    def test_top_tools_respects_limit(self):
        tracker = ToolEffectivenessTracker()
        for name in ("a", "b", "c", "d", "e"):
            tracker.record(name, success=True)
        top = tracker.top_tools(limit=3)
        assert len(top) <= 3

    def test_top_tools_tie_breaker_alphabetical(self):
        tracker = ToolEffectivenessTracker()
        tracker.record("zeta", success=True, execution_time_ms=0.0)
        tracker.record("alpha", success=True, execution_time_ms=0.0)
        top = tracker.top_tools(limit=2)
        # Both have effectiveness 1.0 → tie broken alphabetically
        assert top[0].tool_name == "alpha"
        assert top[1].tool_name == "zeta"

    def test_top_tools_empty(self):
        tracker = ToolEffectivenessTracker()
        assert tracker.top_tools() == []


class TestQuerying:
    def test_observations_returns_insertion_order(self):
        tracker = ToolEffectivenessTracker()
        tracker.record("echo", success=True)
        tracker.record("echo", success=False)
        tracker.record("echo", success=True)
        obs = tracker.observations("echo")
        assert len(obs) == 3
        assert obs[0].success is True
        assert obs[1].success is False
        assert obs[2].success is True

    def test_observations_empty_for_unknown(self):
        tracker = ToolEffectivenessTracker()
        assert tracker.observations("unknown") == []

    def test_observed_tools_sorted(self):
        tracker = ToolEffectivenessTracker()
        tracker.record("zeta", success=True)
        tracker.record("alpha", success=True)
        assert tracker.observed_tools() == ["alpha", "zeta"]

    def test_total_observations(self):
        tracker = ToolEffectivenessTracker()
        tracker.record("a", success=True)
        tracker.record("b", success=True)
        tracker.record("a", success=False)
        assert tracker.total_observations == 3

    def test_observed_tool_count(self):
        tracker = ToolEffectivenessTracker()
        tracker.record("a", success=True)
        tracker.record("b", success=True)
        assert tracker.observed_tool_count == 2


class TestMaintenance:
    def test_clear(self):
        tracker = ToolEffectivenessTracker()
        tracker.record("echo", success=True)
        tracker.record("search", success=True)
        tracker.clear()
        assert tracker.total_observations == 0
        assert tracker.observed_tool_count == 0

    def test_reset_tool(self):
        tracker = ToolEffectivenessTracker()
        tracker.record("echo", success=True)
        tracker.record("search", success=True)
        tracker.reset_tool("echo")
        assert tracker.observations("echo") == []
        assert tracker.observations("search") != []
        assert tracker.observed_tool_count == 1

    def test_reset_unknown_tool_is_noop(self):
        tracker = ToolEffectivenessTracker()
        tracker.reset_tool("unknown")  # should not raise
        assert tracker.total_observations == 0


class TestDeterminism:
    def test_same_observations_same_score(self):
        tracker1 = ToolEffectivenessTracker()
        tracker2 = ToolEffectivenessTracker()
        for t in (tracker1, tracker2):
            t.record("echo", success=True, execution_time_ms=100.0)
            t.record("echo", success=False, execution_time_ms=200.0)
            t.record("echo", success=True, execution_time_ms=150.0)
        s1 = tracker1.score("echo")
        s2 = tracker2.score("echo")
        assert s1.success_rate == s2.success_rate
        assert s1.avg_execution_time_ms == s2.avg_execution_time_ms
        assert s1.effectiveness == s2.effectiveness

    def test_context_hash_deterministic(self):
        h1 = ToolEffectivenessTracker._context_hash({"a": 1, "b": 2})
        h2 = ToolEffectivenessTracker._context_hash({"b": 2, "a": 1})
        assert h1 == h2  # order-independent


class TestSerialization:
    def test_score_to_dict(self):
        tracker = ToolEffectivenessTracker()
        tracker.record("echo", success=True, execution_time_ms=50.0)
        score = tracker.score("echo")
        data = score.to_dict()
        assert data["tool_name"] == "echo"
        assert data["total_observations"] == 1
        assert data["success_count"] == 1
        assert isinstance(data["last_observed_at"], str)

    def test_record_to_dict(self):
        tracker = ToolEffectivenessTracker()
        record = tracker.record("echo", success=True, metadata={"k": "v"})
        data = record.to_dict()
        assert data["tool_name"] == "echo"
        assert data["success"] is True
        assert data["metadata"] == {"k": "v"}