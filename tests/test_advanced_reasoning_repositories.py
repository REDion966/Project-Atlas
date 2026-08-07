"""Track D — ReasoningTraceRepository tests (Batch 3)."""

from atlas.advanced_reasoning.models import (
    Hypothesis,
    HypothesisSet,
    MetaAssessment,
    ReasoningStrategy,
    ReasoningTrace,
    TraceStatus,
    VerificationReport,
    VerificationVerdict,
)
from atlas.advanced_reasoning.trace_repository import ReasoningTraceRepository


class _FakeStorage:
    """Minimal AdvancedReasoningStorage adapter stand-in for dual-write tests."""

    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.traces: dict[str, ReasoningTrace] = {}
        self.sets: dict[str, HypothesisSet] = {}
        self.reports: dict[str, VerificationReport] = {}
        self.assessments: dict[str, MetaAssessment] = {}
        self.calls: list[tuple[str, str]] = []

    def is_available(self) -> bool:
        return self.available

    def store_trace(self, trace: ReasoningTrace) -> None:
        self.calls.append(("store_trace", trace.trace_id))
        self.traces[trace.trace_id] = trace

    def store_hypothesis_set(self, hs: HypothesisSet) -> None:
        self.calls.append(("store_hypothesis_set", hs.set_id))
        self.sets[hs.set_id] = hs

    def store_verification_report(self, report: VerificationReport) -> None:
        self.calls.append(("store_verification_report", report.report_id))
        self.reports[report.report_id] = report

    def store_meta_assessment(self, assessment: MetaAssessment) -> None:
        self.calls.append(("store_meta_assessment", assessment.assessment_id))
        self.assessments[assessment.assessment_id] = assessment

    def load_traces(self) -> list[ReasoningTrace]:
        return sorted(self.traces.values(), key=lambda t: t.trace_id)


def _make_trace(trace_id: str = "trace-1") -> ReasoningTrace:
    return ReasoningTrace(
        trace_id=trace_id,
        question="Q",
        strategy=ReasoningStrategy.DECOMPOSE,
        status=TraceStatus.COMPLETED,
        conclusion="c",
        confidence=0.8,
    )


def _make_set(set_id: str = "hset-1") -> HypothesisSet:
    return HypothesisSet(
        set_id=set_id,
        claim="claim",
        hypotheses=(Hypothesis(hypothesis_id="h1", claim="Directly: claim"),),
        top_hypothesis_id="h1",
    )


def _make_report(report_id: str = "verify-1") -> VerificationReport:
    return VerificationReport(
        report_id=report_id,
        target_id="target-1",
        verdict=VerificationVerdict.PASSED,
    )


def _make_assessment(assessment_id: str = "meta-1") -> MetaAssessment:
    return MetaAssessment(
        assessment_id=assessment_id,
        strategy_scores=(),
        recommended_strategy=ReasoningStrategy.DECOMPOSE,
    )


class TestTraceStorage:
    def test_store_and_get(self):
        repo = ReasoningTraceRepository()
        repo.store_trace(_make_trace("t1"))
        assert repo.get_trace("t1").trace_id == "t1"
        assert repo.trace_count == 1

    def test_recent_traces_newest_first(self):
        repo = ReasoningTraceRepository()
        repo.store_trace(_make_trace("t1"))
        repo.store_trace(_make_trace("t2"))
        assert [t.trace_id for t in repo.recent_traces(10)] == ["t2", "t1"]

    def test_upsert_does_not_evict(self):
        repo = ReasoningTraceRepository(max_traces=2)
        repo.store_trace(_make_trace("t1"))
        repo.store_trace(_make_trace("t2"))
        # Replacing an existing trace is idempotent and does not evict.
        repo.store_trace(_make_trace("t1"))
        assert repo.trace_count == 2
        assert repo.get_trace("t1") is not None

    def test_bounded_eviction(self):
        repo = ReasoningTraceRepository(max_traces=3)
        for i in range(4):
            repo.store_trace(_make_trace(f"t{i}"))
        assert repo.trace_count == 3
        assert repo.get_trace("t0") is None
        assert repo.get_trace("t3") is not None

    def test_invalid_max_traces(self):
        try:
            ReasoningTraceRepository(max_traces=0)
            assert False, "expected ValueError"
        except ValueError:
            pass

    def test_clear(self):
        repo = ReasoningTraceRepository()
        repo.store_trace(_make_trace("t1"))
        repo.clear()
        assert repo.trace_count == 0


class TestOtherArtifacts:
    def test_hypothesis_sets(self):
        repo = ReasoningTraceRepository()
        repo.store_hypothesis_set(_make_set())
        assert repo.get_hypothesis_set("hset-1").set_id == "hset-1"
        assert repo.hypothesis_set_count == 1

    def test_verification_reports(self):
        repo = ReasoningTraceRepository()
        repo.store_verification_report(_make_report())
        assert repo.get_verification_report("verify-1").report_id == "verify-1"
        assert repo.verification_report_count == 1

    def test_meta_assessments(self):
        repo = ReasoningTraceRepository()
        repo.store_meta_assessment(_make_assessment())
        assert repo.get_meta_assessment("meta-1").assessment_id == "meta-1"
        assert repo.meta_assessment_count == 1


class TestDualWrite:
    def test_writes_route_to_storage(self):
        storage = _FakeStorage()
        repo = ReasoningTraceRepository(storage=storage)
        repo.store_trace(_make_trace("t1"))
        repo.store_hypothesis_set(_make_set())
        repo.store_verification_report(_make_report())
        repo.store_meta_assessment(_make_assessment())
        assert storage.traces.get("t1") is not None
        assert storage.sets.get("hset-1") is not None
        assert storage.reports.get("verify-1") is not None
        assert storage.assessments.get("meta-1") is not None

    def test_unavailable_storage_is_skipped(self):
        storage = _FakeStorage(available=False)
        repo = ReasoningTraceRepository(storage=storage)
        repo.store_trace(_make_trace("t1"))
        assert storage.calls == []
        assert repo.trace_count == 1  # in-memory path intact

    def test_failing_storage_does_not_break_memory(self):
        class _Boom:
            def is_available(self):
                return True

            def store_trace(self, trace):
                raise RuntimeError("disk full")

        repo = ReasoningTraceRepository(storage=_Boom())
        repo.store_trace(_make_trace("t1"))
        assert repo.get_trace("t1") is not None

    def test_restore_loads_traces(self):
        storage = _FakeStorage()
        storage.store_trace(_make_trace("persisted-1"))
        repo = ReasoningTraceRepository(storage=storage)
        assert repo.restore()["restored_artifacts"] == 1
        assert repo.get_trace("persisted-1") is not None

    def test_restore_without_storage_returns_zero(self):
        repo = ReasoningTraceRepository()
        assert repo.restore() == {"restored_artifacts": 0}

    def test_summary_reports_state(self):
        repo = ReasoningTraceRepository(storage=_FakeStorage())
        repo.store_trace(_make_trace("t1"))
        summary = repo.summary()
        assert summary["trace_count"] == 1
        assert summary["storage_available"] is True