"""Phase 6.10 — Approval boundary: evidence contract.

Investigation result: human approval is already a real, authoritative boundary
in the development lifecycle; no change was made.

* ``DevelopmentCycleController`` prepares a DRAFT proposal and stops at
  PENDING_APPROVAL (it never approves).
* ``ApprovalManager`` is the only surface that transitions the decision
  (approve/reject); the proposal only becomes APPROVED through it.
* The ``SelfDevelopmentLoop`` refuses unapproved proposals.
* ``PromotionGate`` opens a PENDING_REVIEW request for a verified run; approval
  means *ready for human promotion* — never an automatic repository change.
"""

from __future__ import annotations

from types import SimpleNamespace

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.development_cycle import (
    DevelopmentCycleController,
    DevelopmentNeed,
)
from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.improvement_planner import ImprovementPriority
from atlas.evolution.models import (
    ApprovalDecision,
    EvolutionProposal,
    ImprovementPlan,
    ProposalStatus,
)
from atlas.evolution.promotion_gate import (
    PromotionGate,
    PromotionRecommendation,
    PromotionStatus,
)
from atlas.evolution.self_development_loop import SelfDevelopmentLoop


def _draft_proposal(metadata, pid="PROP-P610"):
    plan = ImprovementPlan(
        plan_id="IMP-P610",
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
        status=ProposalStatus.DRAFT,
        metadata=metadata,
    )


class TestPhase610ApprovalBoundary:
    def test_preparation_stops_at_pending_approval(self):
        controller = DevelopmentCycleController(approval_manager=ApprovalManager())
        result = controller.run_development_cycle(
            DevelopmentNeed(
                title="add a widget capability",
                evidence_knowledge_ids=("k",),
                metadata={
                    "code_changes": [
                        {"path": "atlas/example/widget.py", "content": "V = 1\n"}
                    ]
                },
            )
        )
        assert result.ok is True
        assert result.proposal_status == ProposalStatus.PENDING_APPROVAL.name

    def test_only_the_approval_manager_grants_approval(self):
        manager = ApprovalManager()
        proposal = _draft_proposal(
            {"code_changes": [{"path": "atlas/x.py", "content": "V = 1\n"}]}
        )
        request = manager.create_approval_request(proposal)
        assert proposal.status is ProposalStatus.PENDING_APPROVAL
        assert request.decision is ApprovalDecision.PENDING

        manager.approve(request, comment="ok")
        manager.update_proposal_from_decision(proposal, request)
        assert proposal.status is ProposalStatus.APPROVED

    def test_sandbox_execution_requires_approval(self):
        proposal = _draft_proposal(
            {"code_changes": [{"path": "atlas/x.py", "content": "V = 1\n"}]}
        )
        result = SelfDevelopmentLoop().run(proposal, max_iterations=1)
        assert result.status is DevelopmentOutcomeStatus.GOVERNANCE_DENIED

    def test_verified_run_is_not_auto_promoted(self):
        gate = PromotionGate(evolution_memory=EvolutionMemory())
        outcome = DevelopmentOutcome(
            outcome=DevelopmentOutcomeStatus.SUCCESS,
            proposal_id="P",
            plan_id="PL",
            iteration=1,
            verification_passed=True,
            test_outcome="passed",
            changed_files=["atlas/example/mod.py"],
        )
        run_result = SimpleNamespace(
            status=DevelopmentOutcomeStatus.SUCCESS,
            outcomes=[outcome],
            iterations_used=1,
            message="ok",
            plan=None,
        )
        assessment = gate.assess(run_result, proposal_id="P")
        assert assessment.recommendation is PromotionRecommendation.READY_FOR_PROMOTION

        request = gate.request_review(assessment)
        # Verified success opens a review — it does NOT promote.
        assert request.status is PromotionStatus.PENDING_REVIEW
        assert request.status is not PromotionStatus.PROMOTED

        gate.approve(request, comment="ready")
        assert request.status is PromotionStatus.APPROVED
        # Approval still is not promotion.
        assert request.status is not PromotionStatus.PROMOTED
