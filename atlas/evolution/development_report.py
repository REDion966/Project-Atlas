"""
Atlas Evolution — Development Lifecycle Report — Phase P17 (Report).

Read-only, deterministic, evidence-based aggregation of the complete P17
development lifecycle into one immutable report.

Responsibilities
----------------
* Aggregate existing evidence from the full lifecycle:
  investigation → planning → approval → execution → failure → diagnosis →
  recovery → verification → final conclusion.
* Produce one immutable :class:`DevelopmentLifecycleReport`.
* Clearly distinguish SUCCESS / FAILED / RECOVERED / UNVERIFIED / PARTIAL /
  UNVERIFIABLE.

This component is pure aggregation:
* it never mutates the repository, the proposal, or the approval;
* it never invokes execution, tests, subprocesses, or AI;
* it never authorizes, approves, recovers, or promotes.

It consumes ONLY evidence already present in ConversationState, proposal
metadata, and instance-scoped registries. It does not introduce a new
persistence layer.

Pure logic. No infrastructure. No AI. No mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Final conclusion
# ---------------------------------------------------------------------------


class FinalConclusion(str, Enum):
    """Authoritative final outcome of the development lifecycle."""

    SUCCESS = "success"
    FAILED = "failed"
    RECOVERED = "recovered"
    UNVERIFIED = "unverified"
    PARTIAL = "partial"
    UNVERIFIABLE = "unverifiable"


# ---------------------------------------------------------------------------
# Lifecycle report
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DevelopmentLifecycleReport:
    """One immutable report describing the complete P17 development lifecycle.

    Attributes:
        investigation_target: What the user asked Atlas to investigate.
        original_proposal_id: The governed EvolutionProposal ID.
        original_approval_id: The approval request ID for the original proposal.
        original_execution_status: Terminal status of the original execution.
        diagnosis: DiagnosticResult if a failure was diagnosed, else None.
        recovery_decision: RecoveryDecision if recovery was attempted, else None.
        recovery_proposal_id: Distinct recovery proposal ID, else None.
        recovery_approval_id: Distinct recovery approval request ID, else None.
        recovery_execution_status: Terminal status of recovery execution.
        verification: VerificationReport if verification was performed.
        final_conclusion: Authoritative final outcome.
        evidence: Human-readable evidence summary.
    """

    final_conclusion: FinalConclusion
    evidence: str

    investigation_target: str | None = None
    original_proposal_id: str | None = None
    original_approval_id: str | None = None
    original_execution_status: str | None = None

    diagnosis: Any = None
    recovery_decision: Any = None

    recovery_proposal_id: str | None = None
    recovery_approval_id: str | None = None
    recovery_execution_status: str | None = None

    verification: Any = None

    # L1/L2 autonomy tracking
    autonomous_steps: int = 0
    last_autonomy_decision: str | None = None

    # L2 autonomy tracking
    chained_workflows: int = 0
    last_l2_decision: str | None = None

    # L3 autonomy tracking
    autonomous_recoveries: int = 0
    sub_plans_generated: int = 0
    last_l3_decision: str | None = None

    # L4 autonomy tracking
    capabilities_acquired: int = 0
    last_l4_decision: str | None = None


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


class DevelopmentReportBuilder:
    """Read-only builder of DevelopmentLifecycleReport.

    Consumes existing evidence from ConversationState, proposal metadata, and
    instance-scoped registries. Reuses DevelopmentDiagnostic,
    DevelopmentRecovery, and DevelopmentVerification for on-demand
    reconstruction. Never mutates anything.
    """

    def build(
        self,
        *,
        state: Any,
        proposal: Any,
        approval: Any,
        recovery_proposal: Any = None,
        recovery_approval: Any = None,
    ) -> DevelopmentLifecycleReport:
        """Build a complete lifecycle report from existing evidence.

        Args:
            state: The current ConversationState.
            proposal: The original EvolutionProposal (live object).
            approval: The original ApprovalRequest (live object).
            recovery_proposal: The recovery EvolutionProposal, if any.
            recovery_approval: The recovery ApprovalRequest, if any.

        Returns:
            An immutable DevelopmentLifecycleReport.
        """
        from atlas.evolution.development_diagnostic import DevelopmentDiagnostic
        from atlas.evolution.development_recovery import DevelopmentRecovery
        from atlas.evolution.development_verification import (
            DevelopmentVerification,
            VerificationStatus,
        )

        # --- Original proposal evidence -----------------------------------
        investigation_target = _investigation_target_from_proposal(proposal)
        original_proposal_id = getattr(proposal, "proposal_id", None)
        original_approval_id = getattr(approval, "request_id", None)

        # Reconstruct original execution evidence from preserved metadata.
        original_metadata = getattr(proposal, "metadata", {}) or {}
        original_execution = original_metadata.get("execution") or {}
        original_execution_status = original_execution.get("result_status")

        # --- Recovery evidence --------------------------------------------
        recovery_proposal_id = (
            getattr(recovery_proposal, "proposal_id", None)
            if recovery_proposal is not None
            else None
        )
        recovery_approval_id = (
            getattr(recovery_approval, "request_id", None)
            if recovery_approval is not None
            else None
        )
        recovery_execution_status = None
        if recovery_proposal is not None:
            recovery_metadata = getattr(recovery_proposal, "metadata", {}) or {}
            recovery_execution = recovery_metadata.get("execution") or {}
            recovery_execution_status = recovery_execution.get("result_status")

        # --- Reconstruct analysis results on-demand -----------------------
        # Build a minimal evidence stand-in for the diagnostic/recovery/verify
        # engines from the preserved proposal metadata.
        result_standin = _result_standin_from_metadata(
            original_execution, original_execution_status
        )

        diagnosis = None
        recovery_decision = None
        verification = None

        # Only diagnose if there is evidence of failure.
        if original_execution_status and original_execution_status != "SUCCESS":
            diagnosis = DevelopmentDiagnostic().diagnose(result_standin)
            recovery_decision = DevelopmentRecovery().decide(result_standin, diagnosis)

        # Verify the latest result (recovery if present, else original).
        latest_status = (
            recovery_execution_status
            if recovery_execution_status is not None
            else original_execution_status
        )
        latest_standin = (
            _result_standin_from_metadata(
                (getattr(recovery_proposal, "metadata", {}) or {}).get("execution") or {},
                recovery_execution_status,
            )
            if recovery_proposal is not None
            else result_standin
        )
        verification = DevelopmentVerification().verify(latest_standin)

        # --- Determine final conclusion -----------------------------------
        final_conclusion, evidence = self._conclude(
            original_execution_status=original_execution_status,
            recovery_execution_status=recovery_execution_status,
            verification=verification,
            has_recovery=recovery_proposal is not None,
        )

        # Extract L1/L2/L3 autonomy tracking from conversation state
        autonomous_steps = getattr(state, "autonomous_steps_executed", 0) or 0
        last_autonomy_decision = getattr(state, "last_autonomy_decision", None)

        # Extract L2-specific tracking
        chained_workflows_list = getattr(state, "chained_workflows", ()) or ()
        chained_workflows = len(chained_workflows_list)
        last_l2_decision = getattr(state, "last_l2_decision", None)

        # Extract L3-specific tracking
        autonomous_recoveries = getattr(state, "autonomous_recoveries", 0) or 0
        sub_plans_generated = getattr(state, "sub_plans_generated", 0) or 0
        last_l3_decision = getattr(state, "last_l3_decision", None)

        # Extract L4-specific tracking
        capabilities_acquired = getattr(state, "capabilities_acquired", 0) or 0
        last_l4_decision = getattr(state, "last_l4_decision", None)

        return DevelopmentLifecycleReport(
            final_conclusion=final_conclusion,
            evidence=evidence,
            investigation_target=investigation_target,
            original_proposal_id=original_proposal_id,
            original_approval_id=original_approval_id,
            original_execution_status=original_execution_status,
            diagnosis=diagnosis,
            recovery_decision=recovery_decision,
            recovery_proposal_id=recovery_proposal_id,
            recovery_approval_id=recovery_approval_id,
            recovery_execution_status=recovery_execution_status,
            verification=verification,
            autonomous_steps=autonomous_steps,
            last_autonomy_decision=last_autonomy_decision,
            chained_workflows=chained_workflows,
            last_l2_decision=last_l2_decision,
            autonomous_recoveries=autonomous_recoveries,
            sub_plans_generated=sub_plans_generated,
            last_l3_decision=last_l3_decision,
            capabilities_acquired=capabilities_acquired,
            last_l4_decision=last_l4_decision,
        )

    @staticmethod
    def _conclude(
        *,
        original_execution_status: str | None,
        recovery_execution_status: str | None,
        verification: Any,
        has_recovery: bool,
    ) -> tuple[FinalConclusion, str]:
        """Determine the final conclusion from aggregated evidence."""
        ver_status = getattr(
            getattr(verification, "status", None), "value", "unverifiable"
        )

        # Recovery path: original failed, recovery executed.
        if has_recovery and recovery_execution_status is not None:
            if recovery_execution_status == "SUCCESS" and ver_status == "verified":
                return (
                    FinalConclusion.RECOVERED,
                    (
                        "Original development failed; recovery execution "
                        "succeeded and was verified."
                    ),
                )
            if recovery_execution_status == "SUCCESS":
                return (
                    FinalConclusion.RECOVERED,
                    (
                        "Original development failed; recovery execution "
                        "succeeded but verification is incomplete."
                    ),
                )
            return (
                FinalConclusion.FAILED,
                (
                    "Original development failed; recovery execution also "
                    f"did not succeed (status: {recovery_execution_status})."
                ),
            )

        # Original execution path.
        if original_execution_status == "SUCCESS":
            if ver_status == "verified":
                return (
                    FinalConclusion.SUCCESS,
                    "Development succeeded and was verified.",
                )
            if ver_status == "partial":
                return (
                    FinalConclusion.PARTIAL,
                    "Development succeeded but verification is partial.",
                )
            return (
                FinalConclusion.UNVERIFIED,
                "Development succeeded but verification evidence is insufficient.",
            )

        if original_execution_status in ("FAILED", "GOVERNANCE_DENIED", "INVALID_OBJECTIVE"):
            return (
                FinalConclusion.FAILED,
                f"Development failed with status: {original_execution_status}.",
            )

        if original_execution_status in ("ITERATIONS_EXHAUSTED", "UNAVAILABLE_CAPABILITY"):
            return (
                FinalConclusion.FAILED,
                f"Development did not succeed: {original_execution_status}.",
            )

        if ver_status == "verified":
            return (
                FinalConclusion.SUCCESS,
                "Verification evidence indicates successful development.",
            )
        if ver_status == "partial":
            return (
                FinalConclusion.PARTIAL,
                "Verification evidence is partial.",
            )
        if ver_status == "unverified":
            return (
                FinalConclusion.UNVERIFIED,
                "Verification evidence does not confirm success.",
            )

        return (
            FinalConclusion.UNVERIFIABLE,
            "Insufficient evidence to determine final outcome.",
        )


def _investigation_target_from_proposal(proposal: Any) -> str | None:
    """Extract the investigation target from a proposal's metadata."""
    if proposal is None:
        return None
    metadata = getattr(proposal, "metadata", {}) or {}
    # InvestigationProposalConverter stores this in metadata.
    return (
        metadata.get("investigation_target")
        or metadata.get("investigation_proposal_id")
        or None
    )


def _result_standin_from_metadata(
    execution: Any, status_name: str | None
) -> Any:
    """Build a minimal evidence stand-in from preserved execution metadata.

    The conversation service does not retain the full DevelopmentRunResult
    object (it is kernel-owned). This reconstructs just enough structure for
    the read-only diagnostic/recovery/verify engines to analyze the failure
    evidence preserved in proposal.metadata["execution"].
    """
    from atlas.evolution.development_models import DevelopmentOutcomeStatus

    if not isinstance(execution, dict):
        execution = {}

    if status_name:
        try:
            status = DevelopmentOutcomeStatus[status_name]
        except KeyError:
            status = DevelopmentOutcomeStatus.FAILED
    else:
        status = DevelopmentOutcomeStatus.FAILED

    last_outcome = execution.get("last_outcome") or {}

    outcome = type(
        "_O",
        (),
        {
            "outcome": status,
            "verification_passed": bool(last_outcome.get("verification_passed", False)),
            "rollback_occurred": bool(last_outcome.get("rollback_occurred", False)),
            "test_outcome": str(last_outcome.get("test_outcome", "")),
            "message": str(last_outcome.get("message", "") or execution.get("message", "")),
        },
    )()

    return type(
        "_R",
        (),
        {
            "status": status,
            "outcomes": [outcome],
            "iterations_used": int(execution.get("iterations_used", 1)),
            "message": str(execution.get("message", "")),
        },
    )()
