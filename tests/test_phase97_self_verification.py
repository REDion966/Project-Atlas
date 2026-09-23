"""Phase 9.7 — Self-verification: evidence contract.

Investigation result: Atlas already verifies its own changes via
``DevelopmentVerification`` (evidence-based: VERIFIED / UNVERIFIED / PARTIAL /
UNVERIFIABLE). "Code was applied" is never equated with "development succeeded".
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


def _result(status, outcomes):
    return SimpleNamespace(
        status=status, outcomes=list(outcomes), iterations_used=len(outcomes), message=""
    )


def _outcome(passed: bool):
    return DevelopmentOutcome(
        outcome=DevelopmentOutcomeStatus.SUCCESS,
        proposal_id="P",
        plan_id="PL",
        iteration=1,
        verification_passed=passed,
        test_outcome="passed" if passed else "failed",
    )


class TestPhase97SelfVerification:
    def test_code_applied_alone_is_not_success(self):
        # A FAILED run with no iteration evidence is UNVERIFIABLE, not VERIFIED.
        report = DevelopmentVerification().verify(
            _result(DevelopmentOutcomeStatus.FAILED, [])
        )
        assert report.status is VerificationStatus.UNVERIFIABLE
        assert report.all_tests_passed is None

    def test_passing_evidence_is_verified(self):
        report = DevelopmentVerification().verify(
            _result(DevelopmentOutcomeStatus.SUCCESS, [_outcome(True)])
        )
        assert report.status is VerificationStatus.VERIFIED
        assert report.all_tests_passed is True

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
