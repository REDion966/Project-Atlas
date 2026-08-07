"""Track D — SelfVerifier tests (Batch 2).

Covers contradiction detection, unsupported conclusions, premise coverage,
circular reasoning detection, confidence calibration, report generation,
optional VerificationModel enhancement (fail-soft), and edge cases.
"""

from atlas.advanced_reasoning.models import (
    ReasoningTrace,
    ReasoningTraceStep,
    TraceStatus,
    VerificationFinding,
    VerificationVerdict,
)
from atlas.advanced_reasoning.verify import SelfVerifier
from tests._advanced_reasoning_fakes import (
    FakeVerificationModel,
)


def _trace(steps: tuple[ReasoningTraceStep, ...], conclusion: str = "") -> ReasoningTrace:
    """Build a completed trace with the given steps and conclusion."""
    return ReasoningTrace(
        trace_id="t1",
        question="Is X true?",
        steps=steps,
        status=TraceStatus.COMPLETED,
        conclusion=conclusion,
        confidence=0.8,
    )


class TestCircularity:
    def test_self_reference_cycle_is_detected(self):
        steps = (
            ReasoningTraceStep(step_id="s1", premise_step_ids=("s1",), conclusion="c"),
        )
        report = SelfVerifier().verify(_trace(steps, conclusion="c"))
        assert report.verdict == VerificationVerdict.FAILED
        circularity = next(f for f in report.findings if f.check_type == "circularity")
        assert circularity.passed is False

    def test_no_cycle_passes(self):
        steps = (
            ReasoningTraceStep(step_id="s1", conclusion="c"),
        )
        report = SelfVerifier().verify(_trace(steps, conclusion="c"))
        circularity = next(f for f in report.findings if f.check_type == "circularity")
        assert circularity.passed is True


class TestPremiseCoverage:
    def test_missing_premise_is_detected(self):
        steps = (
            ReasoningTraceStep(step_id="s1", premise_step_ids=("ghost",), conclusion="c"),
        )
        report = SelfVerifier().verify(_trace(steps, conclusion="c"))
        assert report.verdict == VerificationVerdict.FAILED
        coverage = next(f for f in report.findings if f.check_type == "premise_coverage")
        assert coverage.passed is False

    def test_all_premises_exist(self):
        steps = (
            ReasoningTraceStep(step_id="s1", conclusion="a"),
            ReasoningTraceStep(step_id="s2", premise_step_ids=("s1",), conclusion="b"),
        )
        report = SelfVerifier().verify(_trace(steps, conclusion="b"))
        coverage = next(f for f in report.findings if f.check_type == "premise_coverage")
        assert coverage.passed is True


class TestContradiction:
    def test_contradictory_statements_detected(self):
        steps = (
            ReasoningTraceStep(step_id="s1", conclusion="the sky is blue"),
            ReasoningTraceStep(step_id="s2", conclusion="not the sky is blue"),
        )
        report = SelfVerifier().verify(_trace(steps, conclusion="the sky is blue"))
        assert report.verdict == VerificationVerdict.FAILED
        contradiction = next(f for f in report.findings if f.check_type == "contradiction")
        assert contradiction.passed is False

    def test_no_contradiction(self):
        steps = (
            ReasoningTraceStep(step_id="s1", conclusion="the sky is blue"),
        )
        report = SelfVerifier().verify(_trace(steps, conclusion="the sky is blue"))
        contradiction = next(f for f in report.findings if f.check_type == "contradiction")
        assert contradiction.passed is True


class TestUnsupportedConclusion:
    def test_unsupported_conclusion_detected(self):
        steps = (
            ReasoningTraceStep(step_id="s1", conclusion="something else"),
        )
        report = SelfVerifier().verify(_trace(steps, conclusion="the sky is blue"))
        unsupported = next(
            f for f in report.findings if f.check_type == "unsupported_conclusion"
        )
        assert unsupported.passed is False
        # warning severity -> inconclusive, not failed
        assert report.verdict == VerificationVerdict.INCONCLUSIVE

    def test_supported_conclusion(self):
        steps = (
            ReasoningTraceStep(step_id="s1", conclusion="the sky is blue"),
        )
        report = SelfVerifier().verify(_trace(steps, conclusion="the sky is blue"))
        unsupported = next(
            f for f in report.findings if f.check_type == "unsupported_conclusion"
        )
        assert unsupported.passed is True


class TestVerdicts:
    def test_clean_trace_passes(self):
        steps = (
            ReasoningTraceStep(step_id="s1", conclusion="the sky is blue"),
        )
        report = SelfVerifier().verify(_trace(steps, conclusion="the sky is blue"))
        assert report.verdict == VerificationVerdict.PASSED
        assert report.is_passed is True

    def test_claim_string_verification_inconclusive(self):
        # claim-only verification: no steps -> INCONCLUSIVE.
        report = SelfVerifier().verify("the sky is blue")
        assert report.verdict == VerificationVerdict.INCONCLUSIVE

    def test_empty_target_fails_with_error_finding(self):
        report = SelfVerifier().verify("   ")
        assert report.verdict == VerificationVerdict.FAILED
        target = next(f for f in report.findings if f.check_type == "target")
        assert target.passed is False


class TestConfidenceCalibration:
    def test_failed_error_penalty(self):
        steps = (
            ReasoningTraceStep(step_id="s1", premise_step_ids=("ghost",), conclusion="c"),
        )
        report = SelfVerifier().verify(_trace(steps, conclusion="c"))
        # 0.8 confidence - 0.1 penalty (premise_coverage error)
        assert report.confidence_before == 0.8
        assert report.confidence_after <= 0.7

    def test_clean_trace_uncertain(self):
        steps = (
            ReasoningTraceStep(step_id="s1", conclusion="the sky is blue"),
        )
        report = SelfVerifier().verify(_trace(steps, conclusion="the sky is blue"))
        assert report.confidence_after == report.confidence_before


class TestReportMetadata:
    def test_aggregate_quality_and_support_score(self):
        steps = (
            ReasoningTraceStep(
                step_id="s1",
                conclusion="the sky is blue",
                evidence_refs=("ev1", "ev2"),
            ),
        )
        report = SelfVerifier().verify(_trace(steps, conclusion="the sky is blue"))
        assert 0.0 < report.metadata["aggregate_quality"] <= 1.0
        assert report.metadata["support_score"] == 1.0
        assert report.metadata["is_trace"] is True
        assert report.metadata["trace_id"] == "t1"

    def test_claim_only_support_score_zero(self):
        report = SelfVerifier().verify("the sky is blue")
        assert report.metadata["support_score"] == 0.0
        assert report.metadata["is_trace"] is False

    def test_report_id_override(self):
        report = SelfVerifier().verify("the sky is blue", report_id="custom")
        assert report.report_id == "custom"


class TestModelEnhancement:
    def test_model_finding_merged(self):
        model_finding = VerificationFinding(
            finding_id="finding:semantic",
            check_type="contradiction",
            passed=True,
            message="semantic check ok",
            severity="warning",
        )
        verifier = SelfVerifier(verification_model=FakeVerificationModel(finding=model_finding))
        report = verifier.verify("the sky is blue")
        assert any(f.finding_id == "finding:semantic" for f in report.findings)

    def test_raising_model_is_ignored(self):
        verifier = SelfVerifier(verification_model=FakeVerificationModel(failure=True))
        report = verifier.verify("the sky is blue")
        assert all(f.finding_id != "finding:semantic" for f in report.findings)

    def test_none_model_finding_ignored(self):
        verifier = SelfVerifier(verification_model=FakeVerificationModel(finding=None))
        report = verifier.verify("the sky is blue")
        assert report.finding_count == len([f for f in report.findings])


class TestDeterminism:
    def test_same_input_same_findings(self):
        steps = (
            ReasoningTraceStep(step_id="s1", conclusion="the sky is blue"),
        )
        first = SelfVerifier().verify(_trace(steps, conclusion="the sky is blue"))
        second = SelfVerifier().verify(_trace(steps, conclusion="the sky is blue"))
        assert first.findings == second.findings
        assert first.verdict == second.verdict
        assert first.confidence_after == second.confidence_after
