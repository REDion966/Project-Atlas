"""
Atlas Evolution — Development Verification — Phase P17 (Verify).

Read-only, deterministic, evidence-based post-execution verification of an
already-produced :class:`DevelopmentRunResult`.

Responsibilities
----------------
* Consume an existing :class:`DevelopmentRunResult` (from execution or
  recovery) and its contained :class:`DevelopmentOutcome` evidence.
* Determine verification status: VERIFIED / UNVERIFIED / PARTIAL /
  UNVERIFIABLE.
* Cite the specific evidence supporting the conclusion.
* Produce an immutable :class:`VerificationReport`.

This component is pure analysis:
* it never mutates the repository, the proposal, or the approval;
* it never invokes execution, tests, subprocesses, or AI;
* it never authorizes, approves, recovers, or promotes.

It verifies ONLY the evidence already present in the supplied result. It does
not infer success from human-readable messages, does not claim filesystem or
repository state was verified unless the evidence explicitly shows it, and
preserves the distinction between execution success, test success, verification
evidence, and acceptance/promotion.

Pure logic. No infrastructure. No AI. No mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


# ---------------------------------------------------------------------------
# Verification status
# ---------------------------------------------------------------------------


class VerificationStatus(str, Enum):
    """Post-execution verification conclusion."""

    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    PARTIAL = "partial"
    UNVERIFIABLE = "unverifiable"


# ---------------------------------------------------------------------------
# Verification report
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """Structured, evidence-backed verification of a development result.

    Attributes:
        status: The verification conclusion.
        evidence: Specific evidence supporting the conclusion.
        iterations_examined: Number of development iterations examined.
        all_tests_passed: True when every examined iteration passed
            verification; False when at least one failed; None when no
            test/verification evidence exists.
        any_rollback: True when any iteration recorded a rollback.
        changed_files: Union of changed_files across all examined iterations.
        message: Human-readable summary.
    """

    status: VerificationStatus
    evidence: str
    iterations_examined: int = 0
    all_tests_passed: bool | None = None
    any_rollback: bool = False
    changed_files: tuple[str, ...] = ()
    message: str = ""


# ---------------------------------------------------------------------------
# Verification engine
# ---------------------------------------------------------------------------


class DevelopmentVerification:
    """Read-only, deterministic post-execution evidence verifier.

    Consumes an existing DevelopmentRunResult and produces a
    VerificationReport. Never mutates anything. Fail-closed: absent or
    ambiguous evidence yields UNVERIFIABLE, never a false VERIFIED.
    """

    def verify(self, result: Any) -> VerificationReport:
        """Produce a structured verification report from a development result.

        Args:
            result: The DevelopmentRunResult to verify.

        Returns:
            A VerificationReport. When evidence is insufficient, returns
            UNVERIFIABLE with an explicit rationale.
        """
        if result is None:
            return VerificationReport(
                status=VerificationStatus.UNVERIFIABLE,
                evidence="No development result was supplied.",
                message="Cannot verify: no development result available.",
            )

        status = getattr(result, "status", None)
        status_name = getattr(status, "name", str(status)) if status is not None else "NONE"

        outcomes = list(getattr(result, "outcomes", None) or [])
        iterations_used = int(getattr(result, "iterations_used", 0) or 0)

        # Definitive non-success terminal statuses are UNVERIFIED regardless
        # of whether iteration outcomes were recorded — the status itself is
        # authoritative evidence that verification did not succeed.
        if status_name in (
            "GOVERNANCE_DENIED",
            "INVALID_OBJECTIVE",
            "ITERATIONS_EXHAUSTED",
            "UNAVAILABLE_CAPABILITY",
        ):
            return VerificationReport(
                status=VerificationStatus.UNVERIFIED,
                evidence=f"status={status_name}",
                iterations_examined=iterations_used,
                message=f"Development NOT verified: result status is {status_name}.",
            )

        # No iteration outcomes for FAILED: insufficient evidence to verify.
        if not outcomes:
            return VerificationReport(
                status=VerificationStatus.UNVERIFIABLE,
                evidence=f"status={status_name}; no iteration outcomes recorded.",
                iterations_examined=0,
                message=(
                    "Cannot verify: the development result contains no "
                    "iteration outcomes to examine."
                ),
            )

        # Aggregate evidence across all iterations.
        all_tests_passed: bool | None = True
        any_rollback = False
        changed_files: list[str] = []
        verified_count = 0
        failed_count = 0

        for outcome in outcomes:
            verification_passed = bool(getattr(outcome, "verification_passed", False))
            rollback = bool(getattr(outcome, "rollback_occurred", False))
            changed_files.extend(getattr(outcome, "changed_files", None) or [])

            if rollback:
                any_rollback = True

            if verification_passed:
                verified_count += 1
            else:
                failed_count += 1
                all_tests_passed = False

        iterations_examined = len(outcomes)
        unique_changed = tuple(dict.fromkeys(changed_files))  # dedup, order-preserving

        # Build evidence string.
        evidence_parts = [
            f"status={status_name}",
            f"iterations_examined={iterations_examined}",
            f"verified_iterations={verified_count}",
            f"failed_iterations={failed_count}",
        ]
        if any_rollback:
            evidence_parts.append("rollback_occurred=True")
        evidence = "; ".join(evidence_parts)

        # --- Determine verification status -----------------------------------

        # Terminal SUCCESS status with all iterations passing verification.
        if status_name == "SUCCESS" and verified_count == iterations_examined:
            return VerificationReport(
                status=VerificationStatus.VERIFIED,
                evidence=evidence,
                iterations_examined=iterations_examined,
                all_tests_passed=all_tests_passed,
                any_rollback=any_rollback,
                changed_files=unique_changed,
                message=(
                    "Development verified: result status is SUCCESS and all "
                    f"{iterations_examined} iteration(s) passed verification."
                ),
            )

        # Some iterations passed but not all: partial verification.
        if verified_count > 0 and failed_count > 0:
            return VerificationReport(
                status=VerificationStatus.PARTIAL,
                evidence=evidence,
                iterations_examined=iterations_examined,
                all_tests_passed=False,
                any_rollback=any_rollback,
                changed_files=unique_changed,
                message=(
                    "Partial verification: "
                    f"{verified_count}/{iterations_examined} iteration(s) passed "
                    f"verification, {failed_count} did not."
                ),
            )

        # All iterations failed verification.
        if failed_count == iterations_examined:
            return VerificationReport(
                status=VerificationStatus.UNVERIFIED,
                evidence=evidence,
                iterations_examined=iterations_examined,
                all_tests_passed=False,
                any_rollback=any_rollback,
                changed_files=unique_changed,
                message=(
                    "Development NOT verified: all "
                    f"{iterations_examined} iteration(s) failed verification."
                ),
            )

        # Status is SUCCESS but verification evidence is missing/ambiguous.
        if status_name == "SUCCESS":
            return VerificationReport(
                status=VerificationStatus.PARTIAL,
                evidence=evidence,
                iterations_examined=iterations_examined,
                all_tests_passed=all_tests_passed,
                any_rollback=any_rollback,
                changed_files=unique_changed,
                message=(
                    "Result status is SUCCESS but verification evidence is "
                    "incomplete across iterations."
                ),
            )

        # Anything else: insufficient evidence to verify.
        return VerificationReport(
            status=VerificationStatus.UNVERIFIABLE,
            evidence=evidence,
            iterations_examined=iterations_examined,
            all_tests_passed=all_tests_passed,
            any_rollback=any_rollback,
            changed_files=unique_changed,
            message=(
                f"Verification status undetermined: result status is "
                f"{status_name} with incomplete verification evidence."
            ),
        )
