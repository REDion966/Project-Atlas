"""Phase 6.8 — Failure handling: evidence contract.

Investigation result: development failures already propagate fail-closed through
existing result/diagnosis/recovery semantics, so no autonomous recovery system
was introduced.

* ``SelfDevelopmentLoop`` — bounded iterations; invalid objectives and
  unapproved proposals fail closed; non-retryable failure classes stop early.
* ``DevelopmentDiagnostic`` / ``DevelopmentRecovery`` — unclear evidence yields
  UNKNOWN diagnosis and NO_RECOVERY (never an invented strategy).
* ``DevelopmentCycleController`` — bounded payload validation fails closed with
  recorded ``failures`` (no fabricated success).
"""

from __future__ import annotations

from types import SimpleNamespace

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.development_cycle import (
    DevelopmentCycleController,
    DevelopmentNeed,
)
from atlas.evolution.development_diagnostic import (
    DevelopmentDiagnostic,
    DiagnosticFailureClass,
)
from atlas.evolution.development_models import DevelopmentOutcomeStatus
from atlas.evolution.development_recovery import (
    DevelopmentRecovery,
    RecoveryStrategy,
)
from atlas.evolution.improvement_planner import ImprovementPriority
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ProposalStatus,
)
from atlas.evolution.self_development_loop import SelfDevelopmentLoop


def _proposal(status, metadata, pid="PROP-P68"):
    plan = ImprovementPlan(
        plan_id="IMP-P68",
        title="t",
        description="d",
        priority=ImprovementPriority.MEDIUM,
        target_components=["mod"],
    )
    return EvolutionProposal(
        proposal_id=pid,
        title="t",
        summary="s",
        rationale="r",
        expected_benefit="b",
        risks="low",
        impact_analysis="x",
        implementation_approach="y",
        plan=plan,
        status=status,
        metadata=metadata,
    )


class TestPhase68FailureHandling:
    def test_invalid_objective_fails_closed(self):
        result = SelfDevelopmentLoop().run(
            _proposal(ProposalStatus.APPROVED, {}), max_iterations=1
        )
        assert result.status is DevelopmentOutcomeStatus.INVALID_OBJECTIVE

    def test_unapproved_proposal_is_governance_denied(self):
        result = SelfDevelopmentLoop().run(
            _proposal(
                ProposalStatus.DRAFT,
                {"code_changes": [{"path": "atlas/x.py", "content": "V = 1\n"}]},
            ),
            max_iterations=1,
        )
        assert result.status is DevelopmentOutcomeStatus.GOVERNANCE_DENIED

    def test_diagnostic_and_recovery_fail_closed_on_unclear_evidence(self):
        result = SimpleNamespace(
            status=DevelopmentOutcomeStatus.FAILED,
            outcomes=[],
            iterations_used=0,
            message="",
        )
        diagnostic = DevelopmentDiagnostic().diagnose(result)
        assert diagnostic.failure_class is DiagnosticFailureClass.UNKNOWN
        recovery = DevelopmentRecovery().decide(result, diagnostic)
        assert recovery.recoverable is False
        assert recovery.strategy is RecoveryStrategy.NO_RECOVERY

    def test_malformed_change_payload_fails_closed(self):
        result = DevelopmentCycleController(
            approval_manager=ApprovalManager()
        ).run_development_cycle(
            DevelopmentNeed(
                title="t",
                evidence_knowledge_ids=("k",),
                metadata={"code_changes": [{"path": "   ", "content": "x"}]},
            )
        )
        assert result.ok is False
        assert any(stage == "bounds" for stage, _ in result.failures)

    def test_cycle_failure_is_recorded_not_fabricated(self):
        result = DevelopmentCycleController(
            approval_manager=ApprovalManager()
        ).run_development_cycle(DevelopmentNeed(title="   "))
        assert result.ok is False
        assert result.failures
        assert result.proposal_id == ""
