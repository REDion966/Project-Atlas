"""Phase 6.7 — Verification: evidence contract.

Investigation result: the Development Engine already determines whether a result
satisfies its acceptance criteria from concrete evidence, so no new verification
system was introduced.

* ``atlas/evolution/development_verification.py::DevelopmentVerification`` —
  read-only, deterministic, evidence-based post-execution verification producing
  a ``VerificationReport`` (VERIFIED / UNVERIFIED / PARTIAL / UNVERIFIABLE).
  Absent evidence can never become success.
"""

from __future__ import annotations

from types import SimpleNamespace

from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
)
from atlas.evolution.development_verification import (
    DevelopmentVerification,
    VerificationStatus,
)


def _result(status, outcomes, iterations=None):
    return SimpleNamespace(
        status=status,
        outcomes=list(outcomes),
        iterations_used=len(outcomes) if iterations is None else iterations,
        message="",
    )


def _outcome(passed: bool, changed=()):
    return DevelopmentOutcome(
        outcome=DevelopmentOutcomeStatus.SUCCESS,
        proposal_id="P",
        plan_id="PL",
        iteration=1,
        verification_passed=passed,
        test_outcome="passed" if passed else "failed",
        changed_files=list(changed),
    )


class TestPhase67Verification:
    def test_success_with_passing_evidence_is_verified(self):
        report = DevelopmentVerification().verify(
            _result(
                DevelopmentOutcomeStatus.SUCCESS,
                [_outcome(True, changed=["atlas/x.py"])],
            )
        )
        assert report.status is VerificationStatus.VERIFIED
        assert report.all_tests_passed is True
        assert report.changed_files == ("atlas/x.py",)
        assert "status=SUCCESS" in report.evidence

    def test_absent_evidence_is_unverifiable_never_success(self):
        report = DevelopmentVerification().verify(
            _result(DevelopmentOutcomeStatus.FAILED, [])
        )
        assert report.status is VerificationStatus.UNVERIFIABLE
        assert report.all_tests_passed is None

    def test_failed_evidence_is_unverified(self):
        report = DevelopmentVerification().verify(
            _result(DevelopmentOutcomeStatus.SUCCESS, [_outcome(False)])
        )
        assert report.status is VerificationStatus.UNVERIFIED
        assert report.all_tests_passed is False

    def test_mixed_evidence_is_partial(self):
        report = DevelopmentVerification().verify(
            _result(DevelopmentOutcomeStatus.SUCCESS, [_outcome(True), _outcome(False)])
        )
        assert report.status is VerificationStatus.PARTIAL

    def test_no_result_is_unverifiable(self):
        assert (
            DevelopmentVerification().verify(None).status
            is VerificationStatus.UNVERIFIABLE
        )
