"""Track D — ReasoningTraceRecorder tests (Batch 2).

Covers bounded ring-buffer behavior, the read surface (recent/count/summary),
event-driven handler presence, fail-soft recording, and compatibility with
the meta-reasoning history protocol.
"""

import pytest

from atlas.advanced_reasoning.meta import MetaReasoningEngine, ReasoningHistoryProvider
from atlas.advanced_reasoning.models import ReasoningTrace
from atlas.advanced_reasoning.trace_recorder import ReasoningTraceRecorder
from tests._advanced_reasoning_fakes import FakeHistoryProvider


def _trace(trace_id: str = "t1", status: str = "COMPLETED") -> ReasoningTrace:
    return FakeHistoryProvider.build_trace(
        trace_id=trace_id,
        status_name=status,
        strategy_name="CAUSAL",
        step_count=2,
    )


class TestBoundedBuffer:
    def test_zero_size_rejected(self):
        with pytest.raises(ValueError):
            ReasoningTraceRecorder(max_size=0)

    def test_negative_size_rejected(self):
        with pytest.raises(ValueError):
            ReasoningTraceRecorder(max_size=-1)

    def test_eviction_discards_oldest(self):
        recorder = ReasoningTraceRecorder(max_size=2)
        recorder.record(_trace("t1"))
        recorder.record(_trace("t2"))
        recorder.record(_trace("t3"))
        assert recorder.count() == 2
        assert [t.trace_id for t in recorder.recent()] == ["t3", "t2"]

    def test_count_bounded_by_max_size(self):
        recorder = ReasoningTraceRecorder(max_size=10)
        for i in range(25):
            recorder.record(_trace(f"t{i}"))
        assert recorder.count() == 10
        assert recorder.max_size == 10


class TestReadSurface:
    def test_recent_returns_newest_first(self):
        recorder = ReasoningTraceRecorder()
        recorder.record(_trace("t1"))
        recorder.record(_trace("t2"))
        recent = recorder.recent()
        assert [t.trace_id for t in recent] == ["t2", "t1"]

    def test_recent_caps_at_n(self):
        recorder = ReasoningTraceRecorder()
        recorder.record(_trace("t1"))
        recorder.record(_trace("t2"))
        recorder.record(_trace("t3"))
        assert len(recorder.recent(2)) == 2
        assert [t.trace_id for t in recorder.recent(2)] == ["t3", "t2"]

    def test_recent_non_positive_returns_empty(self):
        recorder = ReasoningTraceRecorder()
        recorder.record(_trace("t1"))
        assert recorder.recent(0) == []
        assert recorder.recent(-3) == []

    def test_recent_empty_buffer(self):
        recorder = ReasoningTraceRecorder()
        assert recorder.recent() == []

    def test_count_empty(self):
        assert ReasoningTraceRecorder().count() == 0


class TestSummary:
    def test_empty_summary(self):
        recorder = ReasoningTraceRecorder()
        summary = recorder.summary()
        assert summary["count"] == 0
        assert summary["success_count"] == 0
        assert summary["failure_count"] == 0
        assert summary["success_rate"] is None
        assert summary["latest_timestamp"] is None
        assert summary["strategy_distribution"] == {}

    def test_summary_success_and_failure(self):
        recorder = ReasoningTraceRecorder()
        recorder.record(_trace("t1", status="COMPLETED"))
        recorder.record(_trace("t2", status="FAILED"))
        summary = recorder.summary()
        assert summary["count"] == 2
        assert summary["success_count"] == 1
        assert summary["failure_count"] == 1
        assert summary["success_rate"] == 0.5

    def test_summary_strategy_distribution(self):
        recorder = ReasoningTraceRecorder()
        recorder.record(_trace("t1"))  # CAUSAL
        recorder.record(_trace("t2"))  # CAUSAL
        summary = recorder.summary()
        assert summary["strategy_distribution"] == {"CAUSAL": 2}


class TestFailSoftAndEventSurface:
    def test_non_trace_record_ignored(self):
        recorder = ReasoningTraceRecorder()
        recorder.record("not a trace")  # type: ignore[arg-type]
        recorder.record(None)  # type: ignore[arg-type]
        assert recorder.count() == 0

    def test_on_pipeline_completed_is_noop(self):
        recorder = ReasoningTraceRecorder()
        assert recorder.on_pipeline_completed({}) is None
        assert recorder.count() == 0

    def test_clear_empties_buffer(self):
        recorder = ReasoningTraceRecorder()
        recorder.record(_trace("t1"))
        recorder.clear()
        assert recorder.count() == 0


class TestMetaCompatibility:
    def test_recorder_satisfies_history_protocol(self):
        recorder = ReasoningTraceRecorder()
        recorder.record(_trace("t1"))
        assert isinstance(recorder, ReasoningHistoryProvider)

    def test_meta_engine_consumes_recorder(self):
        recorder = ReasoningTraceRecorder()
        recorder.record(_trace("t1", status="COMPLETED"))
        recorder.record(_trace("t2", status="FAILED"))
        engine = MetaReasoningEngine(history_provider=recorder)
        assessment = engine.assess()
        assert assessment.metadata["history_count"] == 2
