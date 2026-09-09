"""
Atlas Evolution — Development Diagnostic — Phase P17 (Diagnose).

Read-only, deterministic, evidence-based diagnosis of governed development
execution failures.

Responsibilities
----------------
* Analyze already-produced :class:`DevelopmentRunResult` /
  :class:`DevelopmentOutcome` evidence.
* Classify WHAT failed (implementation / verification / governance / objective /
  / capability / infrastructure / unknown).
* Assign cause confidence (known / probable / unknown).
* Cite the specific evidence supporting the conclusion.
* Assess recoverability conservatively.

This component is pure logic:
* it never mutates the repository, the proposal, or the approval;
* it never invokes execution, tests, subprocesses, or AI;
* it never authorizes, approves, or promotes.

If the available evidence is insufficient to determine a cause, it returns an
explicit UNKNOWN diagnosis rather than inventing a root cause.

Pure logic. No infrastructure. No AI. No mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


# ---------------------------------------------------------------------------
# Diagnostic classifications
# ---------------------------------------------------------------------------


class DiagnosticConfidence(str, Enum):
    """How strongly the evidence supports the diagnosed cause."""

    KNOWN = "known"
    PROBABLE = "probable"
    UNKNOWN = "unknown"


class DiagnosticFailureClass(str, Enum):
    """WHAT failed, based on the strongest available evidence."""

    IMPLEMENTATION = "implementation"
    VERIFICATION = "verification"
    GOVERNANCE = "governance"
    OBJECTIVE = "objective"
    CAPABILITY = "capability"
    INFRASTRUCTURE = "infrastructure"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Diagnostic result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    """Structured, evidence-backed diagnosis of a development failure.

    Attributes:
        failure_class: WHAT failed.
        confidence: How strongly the evidence supports the conclusion.
        cause: Human-readable cause description.
        evidence: Specific evidence supporting the conclusion.
        recoverable: True/False when recoverability can be established from
            evidence; None when it cannot.
    """

    failure_class: DiagnosticFailureClass
    confidence: DiagnosticConfidence
    cause: str
    evidence: str
    recoverable: bool | None = None


# ---------------------------------------------------------------------------
# Diagnostic analyzer
# ---------------------------------------------------------------------------


class DevelopmentDiagnostic:
    """Read-only analyzer of governed development failure evidence.

    Deterministic and evidence-based. Never invents a root cause.
    """

    # Test-outcome tokens that indicate a verification failure.
    _FAILED_VERIFICATION_OUTCOMES: frozenset[str] = frozenset(
        {"failed", "error", "timeout"}
    )

    def diagnose(self, result: Any) -> DiagnosticResult:
        """Produce a structured diagnosis from a DevelopmentRunResult.

        Args:
            result: The authoritative development run result.

        Returns:
            A DiagnosticResult. When evidence is insufficient, returns an
            UNKNOWN diagnosis with UNKNOWN confidence.
        """
        status = getattr(result, "status", None)
        status_name = getattr(status, "name", str(status)) if status is not None else "NONE"

        # Success is not a failure; leave it to the existing success path.
        if status_name == "SUCCESS":
            return DiagnosticResult(
                failure_class=DiagnosticFailureClass.UNKNOWN,
                confidence=DiagnosticConfidence.UNKNOWN,
                cause="Development succeeded; no failure to diagnose.",
                evidence=f"status={status_name}",
                recoverable=None,
            )

        outcomes = list(getattr(result, "outcomes", None) or [])
        last = outcomes[-1] if outcomes else None
        result_message = (getattr(result, "message", "") or "").strip()

        # ---- Status-direct classifications (KNOWN confidence) ------------

        if status_name == "GOVERNANCE_DENIED":
            return DiagnosticResult(
                failure_class=DiagnosticFailureClass.GOVERNANCE,
                confidence=DiagnosticConfidence.KNOWN,
                cause="Development was denied by governance/authority.",
                evidence=result_message or f"status={status_name}",
                recoverable=False,
            )

        if status_name == "INVALID_OBJECTIVE":
            return DiagnosticResult(
                failure_class=DiagnosticFailureClass.OBJECTIVE,
                confidence=DiagnosticConfidence.KNOWN,
                cause="The development objective or workload was invalid.",
                evidence=result_message or f"status={status_name}",
                recoverable=False,
            )

        if status_name == "UNAVAILABLE_CAPABILITY":
            return DiagnosticResult(
                failure_class=DiagnosticFailureClass.CAPABILITY,
                confidence=DiagnosticConfidence.KNOWN,
                cause="A required development capability was unavailable.",
                evidence=result_message or f"status={status_name}",
                recoverable=False,
            )

        # ---- Iteration exhaustion: classify from the last outcome ---------

        if status_name == "ITERATIONS_EXHAUSTED":
            return self._diagnose_exhausted(result, last, result_message)

        # ---- Generic FAILED: classify from the last outcome ----------------

        if status_name == "FAILED":
            return self._diagnose_failed(last, result_message)

        # ---- Unknown / unhandled status -----------------------------------

        return DiagnosticResult(
            failure_class=DiagnosticFailureClass.UNKNOWN,
            confidence=DiagnosticConfidence.UNKNOWN,
            cause=f"Failure status '{status_name}' is not specifically classified.",
            evidence=result_message or f"status={status_name}",
            recoverable=None,
        )

    def _diagnose_exhausted(
        self, result: Any, last: Any, result_message: str
    ) -> DiagnosticResult:
        """Diagnose ITERATIONS_EXHAUSTED from the last iteration outcome."""
        if last is None:
            return DiagnosticResult(
                failure_class=DiagnosticFailureClass.UNKNOWN,
                confidence=DiagnosticConfidence.UNKNOWN,
                cause="Iteration budget was exhausted without a recorded outcome.",
                evidence=result_message or "status=ITERATIONS_EXHAUSTED",
                recoverable=None,
            )

        if self._is_verification_failure(last):
            return DiagnosticResult(
                failure_class=DiagnosticFailureClass.VERIFICATION,
                confidence=DiagnosticConfidence.PROBABLE,
                cause=(
                    "The bounded iteration budget was exhausted because "
                    "verification did not pass."
                ),
                evidence=(
                    f"status=ITERATIONS_EXHAUSTED; "
                    f"last.test_outcome={getattr(last, 'test_outcome', '')!r}; "
                    f"last.verification_passed={getattr(last, 'verification_passed', False)!r}"
                ),
                recoverable=None,
            )

        if self._is_implementation_failure(last):
            return DiagnosticResult(
                failure_class=DiagnosticFailureClass.IMPLEMENTATION,
                confidence=DiagnosticConfidence.PROBABLE,
                cause=(
                    "The bounded iteration budget was exhausted because "
                    "implementation did not succeed."
                ),
                evidence=(
                    f"status=ITERATIONS_EXHAUSTED; "
                    f"last.rollback_occurred={getattr(last, 'rollback_occurred', False)!r}; "
                    f"last.message={getattr(last, 'message', '')!r}"
                ),
                recoverable=None,
            )

        return DiagnosticResult(
            failure_class=DiagnosticFailureClass.UNKNOWN,
            confidence=DiagnosticConfidence.UNKNOWN,
            cause="Iteration budget was exhausted; the specific failure cause is unclear.",
            evidence=result_message or "status=ITERATIONS_EXHAUSTED",
            recoverable=None,
        )

    def _diagnose_failed(self, last: Any, result_message: str) -> DiagnosticResult:
        """Diagnose a generic FAILED from the last iteration outcome."""
        if last is None:
            return DiagnosticResult(
                failure_class=DiagnosticFailureClass.UNKNOWN,
                confidence=DiagnosticConfidence.UNKNOWN,
                cause="Development failed without a recorded iteration outcome.",
                evidence=result_message or "status=FAILED",
                recoverable=None,
            )

        if self._is_verification_failure(last):
            return DiagnosticResult(
                failure_class=DiagnosticFailureClass.VERIFICATION,
                confidence=DiagnosticConfidence.KNOWN,
                cause="Verification did not pass.",
                evidence=(
                    f"last.test_outcome={getattr(last, 'test_outcome', '')!r}; "
                    f"last.verification_passed={getattr(last, 'verification_passed', False)!r}; "
                    f"last.message={getattr(last, 'message', '')!r}"
                ),
                recoverable=None,
            )

        if self._is_implementation_failure(last):
            return DiagnosticResult(
                failure_class=DiagnosticFailureClass.IMPLEMENTATION,
                confidence=DiagnosticConfidence.KNOWN,
                cause="Implementation did not succeed.",
                evidence=(
                    f"last.rollback_occurred={getattr(last, 'rollback_occurred', False)!r}; "
                    f"last.message={getattr(last, 'message', '')!r}"
                ),
                recoverable=None,
            )

        return DiagnosticResult(
            failure_class=DiagnosticFailureClass.UNKNOWN,
            confidence=DiagnosticConfidence.UNKNOWN,
            cause="Development failed; the specific failure cause is unclear from available evidence.",
            evidence=(
                result_message
                or f"last.message={getattr(last, 'message', '')!r}"
                or "status=FAILED"
            ),
            recoverable=None,
        )

    @classmethod
    def _is_verification_failure(cls, outcome: Any) -> bool:
        """True when outcome evidence indicates a verification failure."""
        if bool(getattr(outcome, "verification_passed", False)):
            return False
        test_outcome = (getattr(outcome, "test_outcome", "") or "").strip().lower()
        return test_outcome in cls._FAILED_VERIFICATION_OUTCOMES

    @classmethod
    def _is_implementation_failure(cls, outcome: Any) -> bool:
        """True when outcome evidence indicates an implementation failure."""
        return bool(getattr(outcome, "rollback_occurred", False))
