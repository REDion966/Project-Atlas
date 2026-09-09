"""
Atlas Evolution — Development Recovery — Phase P17 (Recover).

Read-only, deterministic, evidence-based recovery DECISION for governed
development execution failures.

Responsibilities
----------------
* Consume an existing :class:`DevelopmentRunResult` and its
  :class:`DiagnosticResult`.
* Decide whether a recovery attempt is appropriate.
* Select a recovery strategy (NO_RECOVERY / REVISE_AND_RETRY / ESCALATE).
* Cite the evidence and rationale for the decision.

This component is pure decision logic:
* it never mutates the repository, the proposal, or the approval;
* it never invokes execution, tests, subprocesses, or AI;
* it never authorizes, approves, or promotes.

Fail-closed invariants:
* UNKNOWN diagnosis -> NO_RECOVERY (never invent a strategy).
* Non-recoverable diagnosis -> NO_RECOVERY.
* Governance/objective/capability failures -> NO_RECOVERY/ESCALATE
  (never silently retry or modify objectives).
* Only implementation/verification failures with KNOWN/PROBABLE confidence
  may yield REVISE_AND_RETRY, and only when the evidence supports a
  corrective strategy.

Pure logic. No infrastructure. No AI. No mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


# ---------------------------------------------------------------------------
# Recovery strategy
# ---------------------------------------------------------------------------


class RecoveryStrategy(str, Enum):
    """Recovery strategies available when a failure is recoverable."""

    NO_RECOVERY = "no_recovery"
    REVISE_AND_RETRY = "revise_and_retry"
    ESCALATE = "escalate"


# ---------------------------------------------------------------------------
# Recovery decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    """Structured, evidence-backed recovery decision.

    Attributes:
        recoverable: Whether a recovery attempt is appropriate.
        strategy: The selected recovery strategy.
        rationale: Human-readable explanation of the decision.
        evidence: Specific evidence supporting the decision.
    """

    recoverable: bool
    strategy: RecoveryStrategy
    rationale: str
    evidence: str


# ---------------------------------------------------------------------------
# Recovery decision engine
# ---------------------------------------------------------------------------


class DevelopmentRecovery:
    """Read-only, deterministic recovery decision engine.

    Consumes already-produced failure evidence and diagnosis.
    Never invokes execution or mutation. Fail-closed.
    """

    def decide(
        self,
        result: Any,
        diagnostic: Any,
    ) -> RecoveryDecision:
        """Produce a structured recovery decision from failure evidence.

        Args:
            result: The authoritative DevelopmentRunResult.
            diagnostic: The DiagnosticResult produced by
                DevelopmentDiagnostic.

        Returns:
            A RecoveryDecision. Fail-closed: when evidence is insufficient,
            returns NO_RECOVERY with an explicit rationale.
        """
        # --- Fail-closed guards on diagnosis quality --------------------

        confidence = getattr(diagnostic, "confidence", None)
        failure_class = getattr(diagnostic, "failure_class", None)
        recoverable = getattr(diagnostic, "recoverable", None)

        # Unknown confidence: cannot justify any recovery strategy.
        if getattr(confidence, "value", str(confidence)).lower() == "unknown":
            return RecoveryDecision(
                recoverable=False,
                strategy=RecoveryStrategy.NO_RECOVERY,
                rationale=(
                    "Recovery requires a diagnosis with known or probable "
                    "confidence; the current diagnosis is unknown."
                ),
                evidence=_evidence(diagnostic),
            )

        # Unknown failure class: cannot determine an appropriate strategy.
        if getattr(failure_class, "value", str(failure_class)).lower() == "unknown":
            return RecoveryDecision(
                recoverable=False,
                strategy=RecoveryStrategy.NO_RECOVERY,
                rationale=(
                    "Recovery requires a specific failure classification; "
                    "the failure class is unknown."
                ),
                evidence=_evidence(diagnostic),
            )

        # --- Classification-based strategy selection ---------------------
        # Failure-class-specific rules take precedence over the generic
        # recoverable flag: e.g. objective/capability failures escalate to
        # humans even when recoverable=False, because they cannot be resolved
        # by retrying execution.

        class_value = getattr(failure_class, "value", str(failure_class)).lower()

        # Governance/authority failures must not be "recovered" by retrying.
        if class_value == "governance":
            return RecoveryDecision(
                recoverable=False,
                strategy=RecoveryStrategy.NO_RECOVERY,
                rationale=(
                    "Governance/authority denials cannot be recovered by "
                    "retrying execution. A new explicit approval is required."
                ),
                evidence=_evidence(diagnostic),
            )

        # Objective failures: cannot silently modify the objective.
        if class_value == "objective":
            return RecoveryDecision(
                recoverable=False,
                strategy=RecoveryStrategy.ESCALATE,
                rationale=(
                    "The development objective is invalid and cannot be "
                    "silently revised. Human planning is required to define "
                    "a corrected objective."
                ),
                evidence=_evidence(diagnostic),
            )

        # Capability failures: cannot retry an unavailable capability.
        if class_value == "capability":
            return RecoveryDecision(
                recoverable=False,
                strategy=RecoveryStrategy.ESCALATE,
                rationale=(
                    "A required development capability is unavailable and "
                    "cannot be recovered by retry. Human intervention is "
                    "required to restore the capability."
                ),
                evidence=_evidence(diagnostic),
            )

        # Infrastructure failures: escalate rather than blind retry.
        if class_value == "infrastructure":
            return RecoveryDecision(
                recoverable=False,
                strategy=RecoveryStrategy.ESCALATE,
                rationale=(
                    "An infrastructure/environment failure is unlikely to be "
                    "resolved by retry alone. Escalating for human diagnosis."
                ),
                evidence=_evidence(diagnostic),
            )

        # --- Potentially recoverable failures ----------------------------

        # Implementation / verification failures with known/probable
        # confidence may be candidates for revise-and-retry, but only when
        # the evidence supports a corrective strategy AND the diagnosis
        # indicates recoverability.
        if class_value in ("implementation", "verification"):
            if (
                recoverable is True
                and DevelopmentRecovery._evidence_supports_correction(diagnostic)
            ):
                return RecoveryDecision(
                    recoverable=True,
                    strategy=RecoveryStrategy.REVISE_AND_RETRY,
                    rationale=(
                        f"The {class_value} failure has "
                        f"{getattr(confidence, 'value', str(confidence)).lower()} "
                        "confidence and the evidence supports a corrective "
                        "strategy. Recovery requires explicit approval."
                    ),
                    evidence=_evidence(diagnostic),
                )

            # Recoverable but insufficient evidence for an automatic
            # corrective strategy: escalate to humans rather than inventing
            # a strategy or falsely claiming no recovery.
            if recoverable is True:
                return RecoveryDecision(
                    recoverable=False,
                    strategy=RecoveryStrategy.ESCALATE,
                    rationale=(
                        f"The {class_value} failure may be recoverable, but "
                        "the available evidence does not support an automatic "
                        "corrective strategy. Escalating for human review."
                    ),
                    evidence=_evidence(diagnostic),
                )

            return RecoveryDecision(
                recoverable=False,
                strategy=RecoveryStrategy.NO_RECOVERY,
                rationale=(
                    f"The {class_value} failure is not recoverable: "
                    "the diagnosis indicates it is not recoverable."
                ),
                evidence=_evidence(diagnostic),
            )

        # Anything else: fail closed.
        return RecoveryDecision(
            recoverable=False,
            strategy=RecoveryStrategy.NO_RECOVERY,
            rationale=(
                f"No recovery strategy is defined for failure class "
                f"'{class_value}'."
            ),
            evidence=_evidence(diagnostic),
        )

    @staticmethod
    def _evidence_supports_correction(diagnostic: Any) -> bool:
        """True when the diagnostic evidence supports a corrective strategy.

        Requires a non-empty cause and evidence string — the bare minimum
        to propose a corrective action without inventing one.
        """
        cause = (getattr(diagnostic, "cause", "") or "").strip()
        evidence = (getattr(diagnostic, "evidence", "") or "").strip()
        return bool(cause) and bool(evidence)


def _evidence(diagnostic: Any) -> str:
    """Extract a compact evidence string from a DiagnosticResult."""
    if diagnostic is None:
        return ""
    parts = []
    for attr in ("failure_class", "confidence", "cause", "evidence"):
        value = getattr(diagnostic, attr, None)
        if value is None:
            continue
        text = getattr(value, "value", str(value))
        if text:
            parts.append(f"{attr}={text}")
    return "; ".join(parts)
