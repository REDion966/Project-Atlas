"""Atlas Advanced Reasoning — SelfVerifier (Track D, Batch 2).

Deterministic self-verification of reasoning traces and conclusions. Checks
contradiction, unsupported conclusions, premise coverage, circular reasoning,
and confidence calibration; then produces an immutable
:class:`~atlas.advanced_reasoning.models.VerificationReport`.

Optional :class:`VerificationModel` enhancement is protocol-injected and
fail-soft: a raising or malformed model contributes no findings.

Pure logic. No storage. No kernel. No AI SDKs. No atlas.reasoning imports.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime
from typing import Any

from atlas.advanced_reasoning.catalog import (
    FINDING_ID_PREFIX,
    VERIFICATION_ID_PREFIX,
)
from atlas.advanced_reasoning.models import (
    ReasoningTrace,
    ReasoningTraceStep,
    VerificationFinding,
    VerificationReport,
    VerificationVerdict,
)
from atlas.advanced_reasoning.protocols import VerificationModel

#: Finding severity for failed "error" checks.
_SEVERITY_ERROR: str = "error"
#: Finding severity for failed "warning" checks.
_SEVERITY_WARNING: str = "warning"

#: Confidence error margin tolerated during calibration evaluation.
_CALIBRATION_TOLERANCE: float = 0.15
#: Decimal precision for confidence calibration.
_CALIBRATION_PRECISION: int = 4


class SelfVerifier:
    """Deterministic self-verification engine.

    Args:
        verification_model: Optional semantic-verification enhancer. When
            absent (or failing), only the deterministic checks run.
    """

    def __init__(self, verification_model: VerificationModel | None = None) -> None:
        self._verification_model = verification_model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verify(
        self,
        target: ReasoningTrace | str,
        report_id: str | None = None,
    ) -> VerificationReport:
        """Verify a reasoning trace or a raw claim string.

        Returns:
            A VerificationReport. Verification never raises: malformed or
            empty targets yield an INCONCLUSIVE report with a failure
            finding explaining why.
        """
        if isinstance(target, ReasoningTrace):
            trace = target
            claim = trace.conclusion or trace.question
            steps = trace.steps
            confidence_before = trace.confidence
        else:
            claim = str(target).strip()
            steps = ()
            confidence_before = 0.0

        base_findings: list[VerificationFinding] = []
        if not claim:
            base_findings.append(
                self._finding(
                    check_type="target",
                    passed=False,
                    message="Empty verification target.",
                    severity=_SEVERITY_ERROR,
                )
            )
        elif isinstance(target, ReasoningTrace) and not steps:
            base_findings.append(
                self._finding(
                    check_type="premise_coverage",
                    passed=False,
                    message="Trace has no steps to verify.",
                    severity=_SEVERITY_WARNING,
                )
            )

        findings = self._run_checks(claim, steps, isinstance(target, ReasoningTrace))
        all_findings = tuple(base_findings + findings + self._model_findings(claim, steps))

        verdict = self._verdict(all_findings, steps)
        confidence_after = self._calibrated_confidence(confidence_before, all_findings)
        aggregate, support_score = self._aggregate_quality(all_findings, steps)

        metadata: dict[str, Any] = {
            "aggregate_quality": aggregate,
            "support_score": support_score,
            "is_trace": isinstance(target, ReasoningTrace),
            "checks_run": [f.check_type for f in all_findings],
        }
        if isinstance(target, ReasoningTrace):
            metadata["trace_id"] = target.trace_id

        return VerificationReport(
            report_id=report_id or self._default_report_id(claim),
            target_id=target.trace_id if isinstance(target, ReasoningTrace) else "",
            verdict=verdict,
            findings=all_findings,
            confidence_before=round(confidence_before, _CALIBRATION_PRECISION),
            confidence_after=round(confidence_after, _CALIBRATION_PRECISION),
            verified_at=datetime.now(),
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Deterministic checks
    # ------------------------------------------------------------------

    def _run_checks(
        self,
        claim: str,
        steps: tuple[ReasoningTraceStep, ...],
        is_trace: bool,
    ) -> list[VerificationFinding]:
        """Run every deterministic check and collect findings."""
        findings: list[VerificationFinding] = []
        findings.append(self._check_circularity(steps))
        findings.append(self._check_premise_coverage(steps, is_trace))
        contradiction = self._check_contradiction(claim, steps)
        findings.extend(contradiction)
        findings.append(self._check_unsupported_conclusion(claim, steps, is_trace))
        return findings

    def _check_circularity(
        self,
        steps: tuple[ReasoningTraceStep, ...],
    ) -> VerificationFinding:
        """Detect a step that (transitively) depends on itself."""
        ids = {step.step_id for step in steps}
        adjacency = {
            step.step_id: [p for p in step.premise_step_ids if p in ids]
            for step in steps
        }

        status: dict[str, int] = {}

        def has_cycle(node: str) -> bool:
            status[node] = 1
            for target in adjacency.get(node, ()):
                if target not in status:
                    if has_cycle(target):
                        return True
                elif status[target] == 1:
                    return True
            status[node] = 2
            return False

        cyclic = any(
            node not in status and has_cycle(node)
            for node in sorted(ids)
        )
        return self._finding(
            check_type="circularity",
            passed=not cyclic,
            message=(
                "No circular dependencies detected."
                if not cyclic
                else "Circular dependency detected in step graph."
            ),
            severity=_SEVERITY_ERROR,
        )

    def _check_premise_coverage(
        self,
        steps: tuple[ReasoningTraceStep, ...],
        is_trace: bool,
    ) -> VerificationFinding:
        """Verify every referenced premise step actually exists."""
        if not steps:
            if is_trace:
                return self._finding(
                    check_type="premise_coverage",
                    passed=False,
                    message="Trace has no steps to cover premises.",
                    severity=_SEVERITY_WARNING,
                )
            return self._finding(
                check_type="premise_coverage",
                passed=True,
                message="Claim-only verification has no premise graph.",
                severity=_SEVERITY_WARNING,
            )
        ids = {step.step_id for step in steps}
        missing = sorted(
            {
                premise
                for step in steps
                for premise in step.premise_step_ids
                if premise not in ids
            }
        )
        return self._finding(
            check_type="premise_coverage",
            passed=not missing,
            message=(
                "All referenced premises exist."
                if not missing
                else f"Missing premise step(s): {', '.join(missing)}."
            ),
            severity=_SEVERITY_ERROR,
        )

    def _check_contradiction(
        self,
        claim: str,
        steps: tuple[ReasoningTraceStep, ...],
    ) -> list[VerificationFinding]:
        """Detect mutually exclusive conclusions among trace steps/claim.

        Deterministic token-level negation heuristic: a statement and its
        negated form are treated as contradictory.
        """
        if not steps:
            return []
        statements = [step.conclusion for step in steps if step.conclusion.strip()]
        if claim.strip():
            statements.append(claim)

        negation_pairs = [
            (statement, negation)
            for statement in statements
            for negation in statements
            if statement != negation and self._is_negation(statement, negation)
        ]
        if not negation_pairs:
            return [
                self._finding(
                    check_type="contradiction",
                    passed=True,
                    message="No step-level contradictions detected.",
                    severity=_SEVERITY_WARNING,
                )
            ]
        first_statement, first_negation = negation_pairs[0]
        return [
            self._finding(
                check_type="contradiction",
                passed=False,
                message=(
                    f"Contradictory statements: {first_statement!r} vs "
                    f"{first_negation!r}."
                ),
                severity=_SEVERITY_ERROR,
            )
        ]

    def _check_unsupported_conclusion(
        self,
        claim: str,
        steps: tuple[ReasoningTraceStep, ...],
        is_trace: bool,
    ) -> VerificationFinding:
        """Verify the conclusion is supported by at least one step."""
        if not is_trace or not claim:
            return self._finding(
                check_type="unsupported_conclusion",
                passed=True,
                message="No conclusion to evaluate.",
                severity=_SEVERITY_WARNING,
            )
        supported = any(
            step.conclusion.strip() and claim == step.conclusion.strip()
            for step in steps
        )
        return self._finding(
            check_type="unsupported_conclusion",
            passed=supported,
            message=(
                "Conclusion is supported by a trace step."
                if supported
                else "Conclusion is not reproduced by any trace step."
            ),
            severity=_SEVERITY_WARNING,
        )

    # ------------------------------------------------------------------
    # Calibration & verdict
    # ------------------------------------------------------------------

    def _calibrated_confidence(
        self,
        confidence: float,
        findings: tuple[VerificationFinding, ...],
    ) -> float:
        """Adjust confidence down when error-severity checks fail."""
        if not findings:
            return confidence
        failed_errors = sum(
            1 for f in findings
            if not f.passed and f.severity == _SEVERITY_ERROR
        )
        penalty = 0.1 * failed_errors
        calibrated = max(0.0, confidence - penalty)
        # Clamp confidence within tolerance of the claim's plausibility band.
        if confidence <= 0.0:
            calibrated = min(calibrated, _CALIBRATION_TOLERANCE)
        return round(calibrated, _CALIBRATION_PRECISION)

    def _verdict(
        self,
        findings: tuple[VerificationFinding, ...],
        steps: tuple[ReasoningTraceStep, ...],
    ) -> VerificationVerdict:
        """Derive the report verdict from findings."""
        if any(not f.passed and f.severity == _SEVERITY_ERROR for f in findings):
            return VerificationVerdict.FAILED
        if any(not f.passed and f.severity == _SEVERITY_WARNING for f in findings):
            return VerificationVerdict.INCONCLUSIVE
        if steps:
            return VerificationVerdict.PASSED
        return VerificationVerdict.INCONCLUSIVE

    @staticmethod
    def _aggregate_quality(
        findings: tuple[VerificationFinding, ...],
        steps: tuple[ReasoningTraceStep, ...],
    ) -> tuple[float, float]:
        """Return (aggregate_quality 0..1, support_score 0..1)."""
        if not findings:
            return 1.0, 1.0
        passed = sum(1 for f in findings if f.passed)
        aggregate = round(passed / len(findings), 4)
        if not steps:
            return aggregate, 0.0
        evidence_counts = Counter(
            ref for step in steps for ref in step.evidence_refs
        )
        support_score = round(min(1.0, len(evidence_counts) / max(1, len(steps))), 4)
        return aggregate, support_score

    # ------------------------------------------------------------------
    # Model enhancement (fail-soft)
    # ------------------------------------------------------------------

    def _model_findings(
        self,
        claim: str,
        steps: tuple[ReasoningTraceStep, ...],
    ) -> list[VerificationFinding]:
        """Query the injected verification model (validated; fail-soft)."""
        model = self._verification_model
        if model is None:
            return []
        context: dict[str, Any] = {
            "steps": [
                {
                    "step_id": step.step_id,
                    "conclusion": step.conclusion,
                    "premise_step_ids": list(step.premise_step_ids),
                }
                for step in steps
            ]
        }
        try:
            finding = model.assess(claim, context)
        except Exception:
            return []
        if finding is None or not finding.finding_id:
            return []
        return [finding]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_negation(first: str, second: str) -> bool:
        """Token-level negation heuristic between two statements."""
        first_l = first.lower()
        second_l = second.lower()
        if first_l.startswith("not ") and second_l == first_l[4:].strip():
            return True
        if second_l.startswith("not ") and first_l == second_l[4:].strip():
            return True
        return False

    @staticmethod
    def _finding(
        check_type: str,
        passed: bool,
        message: str,
        severity: str,
    ) -> VerificationFinding:
        """Deterministic finding id per check."""
        return VerificationFinding(
            finding_id=f"{FINDING_ID_PREFIX}:{check_type}",
            check_type=check_type,
            passed=passed,
            message=message,
            severity=severity,
        )

    @staticmethod
    def _default_report_id(claim: str) -> str:
        """Timestamped report id with a deterministic claim digest."""
        digest = hashlib.sha256(claim.encode("utf-8")).hexdigest()[:16]
        return f"{VERIFICATION_ID_PREFIX}:{digest}:{datetime.now().isoformat()}"
