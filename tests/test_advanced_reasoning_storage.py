"""Track D — AdvancedReasoningSQLiteStorage tests (Batch 2)."""

from datetime import datetime

import pytest

from atlas.advanced_reasoning.models import (
    CausalPath,
    CounterfactualResult,
    Hypothesis,
    HypothesisSet,
    MetaAssessment,
    ReasoningStrategy,
    ReasoningTrace,
    ReasoningTraceStep,
    StrategyScore,
    TraceStatus,
    VerificationFinding,
    VerificationReport,
    VerificationVerdict,
)
from atlas.storage.advanced_reasoning_storage import AdvancedReasoningSQLiteStorage


@pytest.fixture()
def storage(tmp_path):
    adapter = AdvancedReasoningSQLiteStorage(db_path=tmp_path / "atlas_experience.db")
    adapter.initialize()
    yield adapter
    adapter.close()


def _make_trace(trace_id: str = "t1") -> ReasoningTrace:
    return ReasoningTrace(
        trace_id=trace_id,
        question="Is X supported?",
        strategy=ReasoningStrategy.DECOMPOSE,
        steps=(
            ReasoningTraceStep(
                step_id="step:0000",
                description="Resolve sub-goal: X",
                premise_step_ids=(),
                evidence_refs=("source:doc",),
                confidence=0.8,
                conclusion="X supported",
            ),
        ),
        status=TraceStatus.COMPLETED,
        conclusion="X supported",
        confidence=0.8,
        evidence_refs=("source:doc",),
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        completed_at=datetime(2026, 1, 1, 12, 0, 5),
        reasoner_version="0.1.0",
        metadata={"sub_goals": ["X"]},
    )


def _make_path(path_id: str = "p1") -> CausalPath:
    return CausalPath(
        path_id=path_id,
        source="a",
        target="c",
        entity_ids=("a", "b", "c"),
        relation_types=("CAUSES", "CAUSES"),
        confidence=0.7,
        metadata={"source": "world_model"},
    )


def _make_counterfactual(result_id: str = "cf1") -> CounterfactualResult:
    return CounterfactualResult(
        result_id=result_id,
        source_event="a",
        assumption="without b",
        paths_before=(_make_path(),),
        paths_after=(),
        changed=True,
        effect_summary="Blocking without b removes 1 causal path(s): 1 -> 0.",
        metadata={"blocked_tokens": ("b",)},
    )


def _make_hypothesis_set(set_id: str = "hset1") -> HypothesisSet:
    return HypothesisSet(
        set_id=set_id,
        claim="The yield dropped.",
        hypotheses=(
            Hypothesis(
                hypothesis_id="h1",
                claim="Directly: The yield dropped.",
                kind="direct",
                score=0.8,
                evidence_refs=("source:doc",),
            ),
        ),
        top_hypothesis_id="h1",
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        metadata={"reasoner_version": "0.1.0"},
    )


def _make_report(report_id: str = "verify1") -> VerificationReport:
    return VerificationReport(
        report_id=report_id,
        target_id="t1",
        verdict=VerificationVerdict.PASSED,
        findings=(
            VerificationFinding(
                finding_id="finding:circularity",
                check_type="circularity",
                passed=True,
                message="No circular dependencies detected.",
                severity="warning",
            ),
        ),
        confidence_before=0.8,
        confidence_after=0.8,
        verified_at=datetime(2026, 1, 1, 12, 0, 0),
        metadata={"checks_run": ["circularity"]},
    )


def _make_assessment(assessment_id: str = "meta1") -> MetaAssessment:
    return MetaAssessment(
        assessment_id=assessment_id,
        strategy_scores=(),
        recommended_strategy=ReasoningStrategy.DECOMPOSE,
        recommendation_reason="No strategy evidence available.",
        assessed_at=datetime(2026, 1, 1, 12, 0, 0),
        metadata={"window_size": 0},
    )


class TestLifecycle:
    def test_initialize_and_available(self, storage):
        assert storage.is_available()

    def test_close_marks_unavailable(self, tmp_path):
        adapter = AdvancedReasoningSQLiteStorage(db_path=tmp_path / "db.sqlite")
        adapter.initialize()
        adapter.close()
        assert not adapter.is_available()

    def test_schema_version_is_ten(self, tmp_path):
        adapter = AdvancedReasoningSQLiteStorage(db_path=tmp_path / "db.sqlite")
        adapter.initialize()
        assert adapter.get_schema_version() == 11
        adapter.close()


class TestTraces:
    def test_store_and_load_trace(self, storage):
        storage.store_trace(_make_trace("t1"))
        loaded = storage.load_trace("t1")
        assert loaded is not None
        assert loaded.question == "Is X supported?"
        assert loaded.status == TraceStatus.COMPLETED
        assert loaded.step_count == 1
        assert loaded.steps[0].step_id == "step:0000"

    def test_load_traces_sorted(self, storage):
        storage.store_trace(_make_trace("t1"))
        storage.store_trace(_make_trace("t2"))
        traces = storage.load_traces()
        assert [t.trace_id for t in traces] == ["t1", "t2"]

    def test_load_missing_returns_none(self, storage):
        assert storage.load_trace("missing") is None

    def test_upsert_replaces(self, storage):
        storage.store_trace(_make_trace("t1"))
        updated = ReasoningTrace(
            trace_id="t1",
            question="Updated question",
            strategy=ReasoningStrategy.CAUSAL,
            status=TraceStatus.FAILED,
            conclusion="",
            confidence=0.0,
            started_at=datetime(2026, 3, 3, 3, 3, 3),
        )
        storage.store_trace(updated)
        loaded = storage.load_trace("t1")
        assert loaded is not None
        assert loaded.question == "Updated question"
        assert loaded.strategy == ReasoningStrategy.CAUSAL
        assert loaded.status == TraceStatus.FAILED


class TestCausal:
    def test_store_and_load_path(self, storage):
        storage.store_causal_path(_make_path("p1"))
        paths = storage.load_causal_paths()
        assert len(paths) == 1
        assert paths[0].path_id == "p1"
        assert paths[0].entity_ids == ("a", "b", "c")

    def test_counterfactual_round_trip(self, storage):
        storage.store_counterfactual_result(_make_counterfactual())
        results = storage.load_counterfactual_results()
        assert len(results) == 1
        assert results[0].changed is True
        assert len(results[0].paths_before) == 1
        assert len(results[0].paths_after) == 0

    def test_duplicate_counterfactual_ignored(self, storage):
        result = _make_counterfactual()
        storage.store_counterfactual_result(result)
        storage.store_counterfactual_result(result)
        assert len(storage.load_counterfactual_results()) == 1


class TestHypotheses:
    def test_store_and_load_set(self, storage):
        storage.store_hypothesis_set(_make_hypothesis_set())
        loaded = storage.load_hypothesis_set("hset1")
        assert loaded is not None
        assert loaded.claim == "The yield dropped."
        assert loaded.count == 1
        assert loaded.top_hypothesis_id == "h1"

    def test_load_sets_sorted(self, storage):
        storage.store_hypothesis_set(_make_hypothesis_set("hset1"))
        storage.store_hypothesis_set(_make_hypothesis_set("hset2"))
        assert [s.set_id for s in storage.load_hypothesis_sets()] == ["hset1", "hset2"]

    def test_load_hypotheses_ranked(self, storage):
        storage.store_hypothesis_set(_make_hypothesis_set())
        hypotheses = storage.load_hypotheses("hset1")
        assert [h.hypothesis_id for h in hypotheses] == ["h1"]
        assert hypotheses[0].score == 0.8


class TestVerifications:
    def test_store_and_load_report(self, storage):
        storage.store_verification_report(_make_report())
        loaded = storage.load_verification_report("verify1")
        assert loaded is not None
        assert loaded.verdict == VerificationVerdict.PASSED
        assert loaded.findings[0].check_type == "circularity"

    def test_load_reports_sorted(self, storage):
        storage.store_verification_report(_make_report("verify1"))
        storage.store_verification_report(_make_report("verify2"))
        assert [r.report_id for r in storage.load_verification_reports()] == [
            "verify1",
            "verify2",
        ]

    def test_duplicate_report_ignored(self, storage):
        report = _make_report()
        storage.store_verification_report(report)
        storage.store_verification_report(report)
        assert len(storage.load_verification_reports()) == 1

    def test_findings_loaded(self, storage):
        storage.store_verification_report(_make_report())
        findings = storage.load_verification_findings("verify1")
        assert [f.finding_id for f in findings] == ["finding:circularity"]
        assert findings[0].passed is True


class TestMetaAssessments:
    def test_store_and_load_assessment(self, storage):
        storage.store_meta_assessment(_make_assessment())
        loaded = storage.load_meta_assessments()
        assert len(loaded) == 1
        assert loaded[0].assessment_id == "meta1"
        assert loaded[0].recommended_strategy == ReasoningStrategy.DECOMPOSE

    def test_duplicate_assessment_ignored(self, storage):
        assessment = _make_assessment()
        storage.store_meta_assessment(assessment)
        storage.store_meta_assessment(assessment)
        assert len(storage.load_meta_assessments()) == 1

    def test_strategy_scores_round_trip(self, storage):
        assessment = MetaAssessment(
            assessment_id="meta-with-scores",
            strategy_scores=(
                StrategyScore(
                    strategy=ReasoningStrategy.DECOMPOSE,
                    success_count=2,
                    failure_count=1,
                    total_count=3,
                    success_rate=0.6667,
                    avg_verification_pass_rate=0.5,
                    avg_steps=2.0,
                    score=0.5,
                ),
            ),
            recommended_strategy=ReasoningStrategy.DECOMPOSE,
            assessed_at=datetime(2026, 1, 1, 12, 0, 0),
        )
        storage.store_meta_assessment(assessment)
        loaded = storage.load_meta_assessments()[0]
        scores = storage.load_strategy_scores("meta-with-scores")
        assert len(scores) == 1
        assert scores[0].strategy == ReasoningStrategy.DECOMPOSE
        assert loaded.assessment_id == "meta-with-scores"
