"""Track D — Advanced Reasoning data model tests (Batch 1).

Covers immutability (frozen + slots), defaults, enum membership, and
serialization compatibility for atlas/advanced_reasoning/models.py.
"""

import json
from datetime import datetime
from enum import Enum

import pytest

from atlas.advanced_reasoning.models import (
    CausalPath,
    CounterfactualResult,
    Hypothesis,
    HypothesisSet,
    HypothesisSupport,
    MetaAssessment,
    ReasoningConfig,
    ReasoningStrategy,
    ReasoningTrace,
    ReasoningTraceStep,
    StrategyScore,
    TraceStatus,
    VerificationFinding,
    VerificationReport,
    VerificationVerdict,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestReasoningStrategy:
    def test_members(self):
        expected = {
            ReasoningStrategy.DECOMPOSE,
            ReasoningStrategy.CAUSAL,
            ReasoningStrategy.HYPOTHESIS,
            ReasoningStrategy.VERIFY,
            ReasoningStrategy.META,
        }
        assert set(ReasoningStrategy) == expected

    def test_members_are_enum(self):
        assert issubclass(ReasoningStrategy, Enum)


class TestTraceStatus:
    def test_members(self):
        expected = {
            TraceStatus.DRAFT,
            TraceStatus.COMPLETED,
            TraceStatus.RAN_OUT_OF_BUDGET,
            TraceStatus.FAILED,
        }
        assert set(TraceStatus) == expected


class TestHypothesisSupport:
    def test_members(self):
        expected = {
            HypothesisSupport.SUPPORTED,
            HypothesisSupport.CONTRADICTED,
            HypothesisSupport.UNVERIFIED,
        }
        assert set(HypothesisSupport) == expected


class TestVerificationVerdict:
    def test_members(self):
        expected = {
            VerificationVerdict.PASSED,
            VerificationVerdict.FAILED,
            VerificationVerdict.INCONCLUSIVE,
        }
        assert set(VerificationVerdict) == expected


# ---------------------------------------------------------------------------
# ReasoningTraceStep
# ---------------------------------------------------------------------------


class TestReasoningTraceStep:
    def test_create_minimal(self):
        step = ReasoningTraceStep(step_id="s1")
        assert step.step_id == "s1"
        assert step.description == ""
        assert step.premise_step_ids == ()
        assert step.evidence_refs == ()
        assert step.confidence == 0.0
        assert step.conclusion == ""
        assert step.metadata == {}

    def test_create_full(self):
        step = ReasoningTraceStep(
            step_id="s2",
            description="Establish premise",
            premise_step_ids=("s0",),
            evidence_refs=("ev1", "ev2"),
            confidence=0.9,
            conclusion="A implies B",
            metadata={"k": "v"},
        )
        assert step.description == "Establish premise"
        assert step.premise_step_ids == ("s0",)
        assert step.evidence_refs == ("ev1", "ev2")
        assert step.confidence == 0.9
        assert step.conclusion == "A implies B"
        assert step.metadata == {"k": "v"}

    def test_immutability(self):
        step = ReasoningTraceStep(step_id="s3")
        with pytest.raises(AttributeError):
            step.description = "changed"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            step.new_field = 1  # type: ignore[attr-defined]

    def test_to_dict(self):
        step = ReasoningTraceStep(
            step_id="s4",
            description="d",
            premise_step_ids=("s1",),
            evidence_refs=("e1",),
            confidence=0.8,
        )
        data = step.to_dict()
        assert data["step_id"] == "s4"
        assert data["premise_step_ids"] == ("s1",)
        assert data["evidence_refs"] == ("e1",)
        assert data["confidence"] == 0.8


# ---------------------------------------------------------------------------
# ReasoningTrace
# ---------------------------------------------------------------------------


class TestReasoningTrace:
    def test_create_minimal(self):
        trace = ReasoningTrace(trace_id="t1", question="Is X true?")
        assert trace.trace_id == "t1"
        assert trace.question == "Is X true?"
        assert trace.strategy == ReasoningStrategy.DECOMPOSE
        assert trace.steps == ()
        assert trace.status == TraceStatus.DRAFT
        assert trace.conclusion == ""
        assert trace.confidence == 0.0
        assert trace.evidence_refs == ()
        assert isinstance(trace.started_at, datetime)
        assert trace.completed_at is None
        assert trace.reasoner_version == ""
        assert trace.metadata == {}

    def test_create_full(self):
        step = ReasoningTraceStep(step_id="s1", description="d")
        trace = ReasoningTrace(
            trace_id="t2",
            question="Q",
            strategy=ReasoningStrategy.CAUSAL,
            steps=(step,),
            status=TraceStatus.COMPLETED,
            conclusion="X is true",
            confidence=0.85,
            evidence_refs=("ev1",),
            completed_at=datetime(2026, 1, 1, 0, 0, 0),
            reasoner_version="0.1.0",
            metadata={"k": "v"},
        )
        assert trace.strategy == ReasoningStrategy.CAUSAL
        assert trace.step_count == 1
        assert trace.status == TraceStatus.COMPLETED
        assert trace.conclusion == "X is true"
        assert trace.confidence == 0.85
        assert trace.evidence_refs == ("ev1",)
        assert trace.reasoner_version == "0.1.0"
        assert trace.metadata == {"k": "v"}
        assert trace.is_completed is True

    def test_immutability(self):
        trace = ReasoningTrace(trace_id="t3", question="Q")
        with pytest.raises(AttributeError):
            trace.conclusion = "changed"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            trace.new_field = 1  # type: ignore[attr-defined]

    def test_to_dict(self):
        step = ReasoningTraceStep(step_id="s1", description="d")
        trace = ReasoningTrace(
            trace_id="t4",
            question="Q",
            strategy=ReasoningStrategy.VERIFY,
            steps=(step,),
            status=TraceStatus.COMPLETED,
            metadata={"k": "v"},
        )
        data = trace.to_dict()
        assert data["trace_id"] == "t4"
        assert data["strategy"] == "VERIFY"
        assert data["steps"][0]["step_id"] == "s1"
        assert data["status"] == "COMPLETED"
        assert data["metadata"] == {"k": "v"}
        assert isinstance(data["started_at"], datetime)

    def test_step_count_property(self):
        trace = ReasoningTrace(trace_id="t5", question="Q")
        assert trace.step_count == 0
        step = ReasoningTraceStep(step_id="s1")
        trace2 = ReasoningTrace(trace_id="t5", question="Q", steps=(step,))
        assert trace2.step_count == 1

    def test_is_completed_false_for_draft(self):
        trace = ReasoningTrace(trace_id="t6", question="Q")
        assert trace.is_completed is False


# ---------------------------------------------------------------------------
# CausalPath
# ---------------------------------------------------------------------------


class TestCausalPath:
    def test_create_minimal(self):
        path = CausalPath(path_id="c1", source="a", target="b")
        assert path.path_id == "c1"
        assert path.source == "a"
        assert path.target == "b"
        assert path.entity_ids == ()
        assert path.relation_types == ()
        assert path.confidence == 0.0
        assert path.metadata == {}

    def test_create_full(self):
        path = CausalPath(
            path_id="c2",
            source="a",
            target="d",
            entity_ids=("a", "b", "c", "d"),
            relation_types=("causes", "enables"),
            confidence=0.7,
        )
        assert path.entity_ids == ("a", "b", "c", "d")
        assert path.relation_types == ("causes", "enables")
        assert path.confidence == 0.7
        assert path.length == 3

    def test_immutability(self):
        path = CausalPath(path_id="c3", source="a", target="b")
        with pytest.raises(AttributeError):
            path.source = "x"  # type: ignore[misc]

    def test_to_dict(self):
        path = CausalPath(
            path_id="c4",
            source="a",
            target="b",
            entity_ids=("a", "b"),
        )
        data = path.to_dict()
        assert data["path_id"] == "c4"
        assert data["source"] == "a"
        assert data["entity_ids"] == ("a", "b")

    def test_length_empty(self):
        path = CausalPath(path_id="c5", source="a", target="b")
        assert path.length == 0


# ---------------------------------------------------------------------------
# CounterfactualResult
# ---------------------------------------------------------------------------


class TestCounterfactualResult:
    def test_create_minimal(self):
        result = CounterfactualResult(result_id="cf1", source_event="e1")
        assert result.result_id == "cf1"
        assert result.source_event == "e1"
        assert result.assumption == ""
        assert result.paths_before == ()
        assert result.paths_after == ()
        assert result.changed is False
        assert result.effect_summary == ""
        assert result.metadata == {}

    def test_create_full(self):
        path = CausalPath(path_id="c1", source="a", target="b")
        result = CounterfactualResult(
            result_id="cf2",
            source_event="e1",
            assumption="brake applied",
            paths_before=(path,),
            paths_after=(),
            changed=True,
            effect_summary="car stopped",
        )
        assert result.assumption == "brake applied"
        assert result.paths_before == (path,)
        assert result.changed is True
        assert result.effect_summary == "car stopped"

    def test_immutability(self):
        result = CounterfactualResult(result_id="cf3", source_event="e1")
        with pytest.raises(AttributeError):
            result.changed = True  # type: ignore[misc]

    def test_to_dict(self):
        path = CausalPath(path_id="c1", source="a", target="b")
        result = CounterfactualResult(
            result_id="cf4",
            source_event="e1",
            paths_before=(path,),
            changed=True,
        )
        data = result.to_dict()
        assert data["result_id"] == "cf4"
        assert data["paths_before"][0]["path_id"] == "c1"
        assert data["changed"] is True


# ---------------------------------------------------------------------------
# Hypothesis
# ---------------------------------------------------------------------------


class TestHypothesis:
    def test_create_minimal(self):
        hypothesis = Hypothesis(hypothesis_id="h1", claim="C")
        assert hypothesis.hypothesis_id == "h1"
        assert hypothesis.claim == "C"
        assert hypothesis.kind == ""
        assert hypothesis.support == HypothesisSupport.UNVERIFIED
        assert hypothesis.score == 0.0
        assert hypothesis.evidence_refs == ()
        assert hypothesis.metadata == {}

    def test_create_full(self):
        hypothesis = Hypothesis(
            hypothesis_id="h2",
            claim="C",
            kind="direct",
            support=HypothesisSupport.SUPPORTED,
            score=0.9,
            evidence_refs=("ev1",),
            metadata={"k": "v"},
        )
        assert hypothesis.kind == "direct"
        assert hypothesis.support == HypothesisSupport.SUPPORTED
        assert hypothesis.score == 0.9
        assert hypothesis.evidence_refs == ("ev1",)
        assert hypothesis.metadata == {"k": "v"}

    def test_immutability(self):
        hypothesis = Hypothesis(hypothesis_id="h3", claim="C")
        with pytest.raises(AttributeError):
            hypothesis.score = 1.0  # type: ignore[misc]

    def test_to_dict(self):
        hypothesis = Hypothesis(
            hypothesis_id="h4",
            claim="C",
            support=HypothesisSupport.CONTRADICTED,
            score=0.2,
        )
        data = hypothesis.to_dict()
        assert data["hypothesis_id"] == "h4"
        assert data["support"] == "CONTRADICTED"
        assert data["score"] == 0.2


# ---------------------------------------------------------------------------
# HypothesisSet
# ---------------------------------------------------------------------------


class TestHypothesisSet:
    def test_create_minimal(self):
        hypothesis_set = HypothesisSet(set_id="hs1", claim="C")
        assert hypothesis_set.set_id == "hs1"
        assert hypothesis_set.claim == "C"
        assert hypothesis_set.hypotheses == ()
        assert hypothesis_set.top_hypothesis_id == ""
        assert isinstance(hypothesis_set.created_at, datetime)
        assert hypothesis_set.metadata == {}
        assert hypothesis_set.count == 0
        assert hypothesis_set.top_hypothesis is None

    def test_create_full(self):
        h1 = Hypothesis(
            hypothesis_id="h1",
            claim="C1",
            score=0.9,
        )
        h2 = Hypothesis(
            hypothesis_id="h2",
            claim="C2",
            score=0.5,
        )
        hypothesis_set = HypothesisSet(
            set_id="hs2",
            claim="C",
            hypotheses=(h1, h2),
            top_hypothesis_id="h1",
        )
        assert hypothesis_set.count == 2
        assert hypothesis_set.top_hypothesis_id == "h1"
        assert hypothesis_set.top_hypothesis == h1

    def test_immutability(self):
        hypothesis_set = HypothesisSet(set_id="hs3", claim="C")
        with pytest.raises(AttributeError):
            hypothesis_set.claim = "D"  # type: ignore[misc]

    def test_to_dict(self):
        h1 = Hypothesis(hypothesis_id="h1", claim="C1", score=0.9)
        hypothesis_set = HypothesisSet(
            set_id="hs4",
            claim="C",
            hypotheses=(h1,),
        )
        data = hypothesis_set.to_dict()
        assert data["set_id"] == "hs4"
        assert data["hypotheses"][0]["hypothesis_id"] == "h1"
        assert isinstance(data["created_at"], datetime)


# ---------------------------------------------------------------------------
# VerificationFinding
# ---------------------------------------------------------------------------


class TestVerificationFinding:
    def test_create_minimal(self):
        finding = VerificationFinding(finding_id="f1")
        assert finding.finding_id == "f1"
        assert finding.check_type == ""
        assert finding.passed is False
        assert finding.message == ""
        assert finding.severity == "error"
        assert finding.metadata == {}

    def test_create_full(self):
        finding = VerificationFinding(
            finding_id="f2",
            check_type="circularity",
            passed=True,
            message="no circular references",
            severity="warning",
            metadata={"k": "v"},
        )
        assert finding.check_type == "circularity"
        assert finding.passed is True
        assert finding.message == "no circular references"
        assert finding.severity == "warning"
        assert finding.metadata == {"k": "v"}

    def test_immutability(self):
        finding = VerificationFinding(finding_id="f3")
        with pytest.raises(AttributeError):
            finding.passed = True  # type: ignore[misc]

    def test_to_dict(self):
        finding = VerificationFinding(
            finding_id="f4",
            check_type="evidence_support",
            passed=False,
        )
        data = finding.to_dict()
        assert data["finding_id"] == "f4"
        assert data["check_type"] == "evidence_support"
        assert data["passed"] is False


# ---------------------------------------------------------------------------
# VerificationReport
# ---------------------------------------------------------------------------


class TestVerificationReport:
    def test_create_minimal(self):
        report = VerificationReport(report_id="v1", target_id="t1")
        assert report.report_id == "v1"
        assert report.target_id == "t1"
        assert report.verdict == VerificationVerdict.INCONCLUSIVE
        assert report.findings == ()
        assert report.confidence_before == 0.0
        assert report.confidence_after == 0.0
        assert isinstance(report.verified_at, datetime)
        assert report.metadata == {}
        assert report.is_passed is False

    def test_create_full(self):
        finding = VerificationFinding(
            finding_id="f1",
            check_type="circularity",
            passed=True,
        )
        report = VerificationReport(
            report_id="v2",
            target_id="t1",
            verdict=VerificationVerdict.PASSED,
            findings=(finding,),
            confidence_before=0.7,
            confidence_after=0.9,
        )
        assert report.verdict == VerificationVerdict.PASSED
        assert report.finding_count == 1
        assert report.passed_count == 1
        assert report.failed_count == 0
        assert report.confidence_before == 0.7
        assert report.confidence_after == 0.9
        assert report.is_passed is True

    def test_failed_count(self):
        finding = VerificationFinding(
            finding_id="f1",
            check_type="contradiction",
            passed=False,
        )
        report = VerificationReport(
            report_id="v3",
            target_id="t1",
            verdict=VerificationVerdict.FAILED,
            findings=(finding,),
        )
        assert report.failed_count == 1
        assert report.passed_count == 0
        assert report.is_passed is False

    def test_immutability(self):
        report = VerificationReport(report_id="v4", target_id="t1")
        with pytest.raises(AttributeError):
            report.verdict = VerificationVerdict.PASSED  # type: ignore[misc]

    def test_to_dict(self):
        finding = VerificationFinding(
            finding_id="f1",
            check_type="calibration",
            passed=True,
        )
        report = VerificationReport(
            report_id="v5",
            target_id="t1",
            verdict=VerificationVerdict.PASSED,
            findings=(finding,),
        )
        data = report.to_dict()
        assert data["report_id"] == "v5"
        assert data["verdict"] == "PASSED"
        assert data["findings"][0]["finding_id"] == "f1"
        assert isinstance(data["verified_at"], datetime)


# ---------------------------------------------------------------------------
# StrategyScore
# ---------------------------------------------------------------------------


class TestStrategyScore:
    def test_create_minimal(self):
        score = StrategyScore(strategy=ReasoningStrategy.DECOMPOSE)
        assert score.strategy == ReasoningStrategy.DECOMPOSE
        assert score.success_count == 0
        assert score.failure_count == 0
        assert score.total_count == 0
        assert score.success_rate == 0.0
        assert score.avg_verification_pass_rate == 0.0
        assert score.avg_steps == 0.0
        assert score.score == 0.0
        assert score.metadata == {}

    def test_create_full(self):
        score = StrategyScore(
            strategy=ReasoningStrategy.CAUSAL,
            success_count=8,
            failure_count=2,
            total_count=10,
            success_rate=0.8,
            avg_verification_pass_rate=0.9,
            avg_steps=4.0,
            score=0.85,
        )
        assert score.success_count == 8
        assert score.failure_count == 2
        assert score.total_count == 10
        assert score.success_rate == 0.8
        assert score.avg_verification_pass_rate == 0.9
        assert score.avg_steps == 4.0
        assert score.score == 0.85

    def test_immutability(self):
        score = StrategyScore(strategy=ReasoningStrategy.DECOMPOSE)
        with pytest.raises(AttributeError):
            score.score = 1.0  # type: ignore[misc]

    def test_to_dict(self):
        score = StrategyScore(
            strategy=ReasoningStrategy.HYPOTHESIS,
            score=0.6,
        )
        data = score.to_dict()
        assert data["strategy"] == "HYPOTHESIS"
        assert data["score"] == 0.6


# ---------------------------------------------------------------------------
# MetaAssessment
# ---------------------------------------------------------------------------


class TestMetaAssessment:
    def test_create_minimal(self):
        assessment = MetaAssessment(assessment_id="m1")
        assert assessment.assessment_id == "m1"
        assert assessment.strategy_scores == ()
        assert assessment.recommended_strategy == ReasoningStrategy.DECOMPOSE
        assert assessment.recommendation_reason == ""
        assert isinstance(assessment.assessed_at, datetime)
        assert assessment.metadata == {}
        assert assessment.best_strategy_score is None

    def test_create_full(self):
        s1 = StrategyScore(
            strategy=ReasoningStrategy.DECOMPOSE,
            score=0.9,
            success_rate=0.9,
        )
        s2 = StrategyScore(
            strategy=ReasoningStrategy.CAUSAL,
            score=0.4,
            success_rate=0.5,
        )
        assessment = MetaAssessment(
            assessment_id="m2",
            strategy_scores=(s1, s2),
            recommended_strategy=ReasoningStrategy.DECOMPOSE,
            recommendation_reason="highest score",
        )
        assert assessment.recommended_strategy == ReasoningStrategy.DECOMPOSE
        assert assessment.recommendation_reason == "highest score"
        assert assessment.best_strategy_score == s1

    def test_immutability(self):
        assessment = MetaAssessment(assessment_id="m3")
        with pytest.raises(AttributeError):
            assessment.recommendation_reason = "x"  # type: ignore[misc]

    def test_to_dict(self):
        s1 = StrategyScore(
            strategy=ReasoningStrategy.DECOMPOSE,
            score=0.9,
        )
        assessment = MetaAssessment(
            assessment_id="m4",
            strategy_scores=(s1,),
            recommended_strategy=ReasoningStrategy.DECOMPOSE,
        )
        data = assessment.to_dict()
        assert data["assessment_id"] == "m4"
        assert data["strategy_scores"][0]["strategy"] == "DECOMPOSE"
        assert data["recommended_strategy"] == "DECOMPOSE"
        assert isinstance(data["assessed_at"], datetime)


# ---------------------------------------------------------------------------
# ReasoningConfig
# ---------------------------------------------------------------------------


class TestReasoningConfig:
    def test_defaults(self):
        config = ReasoningConfig()
        assert config.max_steps == 20
        assert config.max_depth == 5
        assert config.max_hypotheses == 5
        assert config.confidence_threshold == 0.6
        assert config.verification_enabled is True
        assert config.verification_check_types == (
            "premise_usage",
            "circularity",
            "contradiction",
            "evidence_support",
            "calibration",
        )
        assert config.meta_window_size == 100
        assert config.evidence_limit == 10
        assert config.enabled is True

    def test_create_custom(self):
        config = ReasoningConfig(
            max_steps=10,
            max_depth=3,
            max_hypotheses=2,
            confidence_threshold=0.8,
            verification_enabled=False,
            verification_check_types=("circularity",),
            meta_window_size=50,
            evidence_limit=5,
            enabled=False,
        )
        assert config.max_steps == 10
        assert config.max_depth == 3
        assert config.max_hypotheses == 2
        assert config.confidence_threshold == 0.8
        assert config.verification_enabled is False
        assert config.verification_check_types == ("circularity",)
        assert config.meta_window_size == 50
        assert config.evidence_limit == 5
        assert config.enabled is False

    def test_immutability(self):
        config = ReasoningConfig()
        with pytest.raises(AttributeError):
            config.max_steps = 1  # type: ignore[misc]

    def test_to_dict(self):
        config = ReasoningConfig(max_steps=10, enabled=False)
        data = config.to_dict()
        assert data["max_steps"] == 10
        assert data["enabled"] is False
        assert data["confidence_threshold"] == 0.6
        assert data["verification_check_types"] == (
            "premise_usage",
            "circularity",
            "contradiction",
            "evidence_support",
            "calibration",
        )


# ---------------------------------------------------------------------------
# Serialization compatibility
# ---------------------------------------------------------------------------


class TestSerializationCompatibility:
    def test_nested_trace_serializes_to_json(self):
        step = ReasoningTraceStep(
            step_id="s1",
            description="d",
            evidence_refs=("ev1",),
        )
        trace = ReasoningTrace(
            trace_id="t1",
            question="Q",
            strategy=ReasoningStrategy.DECOMPOSE,
            steps=(step,),
            status=TraceStatus.COMPLETED,
        )
        data = trace.to_dict()

        def drop_datetimes(value):
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, dict):
                return {k: drop_datetimes(v) for k, v in value.items()}
            if isinstance(value, (tuple, list)):
                return [drop_datetimes(v) for v in value]
            return value

        payload = json.dumps(drop_datetimes(data))
        parsed = json.loads(payload)
        assert parsed["trace_id"] == "t1"
        assert parsed["strategy"] == "DECOMPOSE"
        assert parsed["status"] == "COMPLETED"
        assert parsed["steps"][0]["evidence_refs"] == ["ev1"]

    def test_nested_hypothesis_set_serializes_to_json(self):
        h1 = Hypothesis(hypothesis_id="h1", claim="C1", score=0.9)
        hypothesis_set = HypothesisSet(
            set_id="hs1",
            claim="C",
            hypotheses=(h1,),
            top_hypothesis_id="h1",
        )
        data = hypothesis_set.to_dict()

        def drop_datetimes(value):
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, dict):
                return {k: drop_datetimes(v) for k, v in value.items()}
            if isinstance(value, (tuple, list)):
                return [drop_datetimes(v) for v in value]
            return value

        payload = json.dumps(drop_datetimes(data))
        parsed = json.loads(payload)
        assert parsed["set_id"] == "hs1"
        assert parsed["top_hypothesis_id"] == "h1"
        assert parsed["hypotheses"][0]["score"] == 0.9

    def test_enum_names_are_stable_strings(self):
        trace = ReasoningTrace(
            trace_id="t1",
            question="Q",
            strategy=ReasoningStrategy.CAUSAL,
            status=TraceStatus.COMPLETED,
        )
        assert trace.to_dict()["strategy"] == "CAUSAL"
        assert trace.to_dict()["status"] == "COMPLETED"

        hypothesis = Hypothesis(
            hypothesis_id="h1",
            claim="C",
            support=HypothesisSupport.SUPPORTED,
        )
        assert hypothesis.to_dict()["support"] == "SUPPORTED"

        report = VerificationReport(
            report_id="v1",
            target_id="t1",
            verdict=VerificationVerdict.PASSED,
        )
        assert report.to_dict()["verdict"] == "PASSED"
