"""
Phase 7.0 — Self-Evolution Foundation: ApprovalManager Tests.
"""

import pytest

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.models import (
    ApprovalDecision,
    ImprovementPlan,
    ImprovementPriority,
    EvolutionProposal,
    ProposalStatus,
)


def make_proposal(proposal_id="PROP-001", status=ProposalStatus.DRAFT):
    plan = ImprovementPlan(
        plan_id="IMP-001",
        title="Test Plan",
        description="A test plan",
        priority=ImprovementPriority.LOW,
    )
    return EvolutionProposal(
        proposal_id=proposal_id,
        title="Test Proposal",
        summary="Summary of the proposal",
        rationale="This change is needed to improve system reliability.",
        expected_benefit="Better reliability and performance.",
        risks="Low complexity, isolated changes.",
        impact_analysis="Affects runtime components only.",
        implementation_approach="1. Analyze. 2. Fix. 3. Verify.",
        plan=plan,
        status=status,
    )


class TestApprovalManagerCreateRequest:

    def test_create_approval_request(self):
        manager = ApprovalManager()
        proposal = make_proposal()

        request = manager.create_approval_request(proposal)

        assert request.request_id.startswith("APPR-")
        assert request.proposal_id == "PROP-001"
        assert request.title == "Test Proposal"
        assert request.decision == ApprovalDecision.PENDING
        assert proposal.status == ProposalStatus.PENDING_APPROVAL

    def test_create_approval_request_already_approved(self):
        manager = ApprovalManager()
        proposal = make_proposal(status=ProposalStatus.APPROVED)

        with pytest.raises(ValueError, match="Cannot create approval request"):
            manager.create_approval_request(proposal)

    def test_create_approval_request_already_rejected(self):
        manager = ApprovalManager()
        proposal = make_proposal(status=ProposalStatus.REJECTED)

        with pytest.raises(ValueError, match="Cannot create approval request"):
            manager.create_approval_request(proposal)

    def test_create_approval_request_already_implemented(self):
        manager = ApprovalManager()
        proposal = make_proposal(status=ProposalStatus.IMPLEMENTED)

        with pytest.raises(ValueError, match="Cannot create approval request"):
            manager.create_approval_request(proposal)

    def test_create_request_contains_all_fields(self):
        manager = ApprovalManager()
        proposal = make_proposal()

        request = manager.create_approval_request(proposal)

        assert request.rationale == proposal.rationale
        assert request.risks == proposal.risks
        assert request.expected_benefit == proposal.expected_benefit
        assert request.description == proposal.summary


class TestApprovalManagerApprove:

    def test_approve_request(self):
        manager = ApprovalManager()
        proposal = make_proposal()
        request = manager.create_approval_request(proposal)

        manager.approve(request, comment="Looks good")

        assert request.decision == ApprovalDecision.APPROVED
        assert request.decision_comment == "Looks good"
        assert request.decided_at is not None

    def test_approve_request_no_comment(self):
        manager = ApprovalManager()
        proposal = make_proposal()
        request = manager.create_approval_request(proposal)

        manager.approve(request)

        assert request.decision == ApprovalDecision.APPROVED
        assert request.decision_comment == ""

    def test_approve_non_pending_request(self):
        manager = ApprovalManager()
        proposal = make_proposal()
        request = manager.create_approval_request(proposal)
        manager.approve(request)

        with pytest.raises(ValueError, match="Cannot approve"):
            manager.approve(request)

    def test_approve_updates_proposal(self):
        manager = ApprovalManager()
        proposal = make_proposal()
        request = manager.create_approval_request(proposal)

        manager.approve(request)
        manager.update_proposal_from_decision(proposal, request)

        assert proposal.status == ProposalStatus.APPROVED
        assert proposal.approved_at is not None


class TestApprovalManagerReject:

    def test_reject_request(self):
        manager = ApprovalManager()
        proposal = make_proposal()
        request = manager.create_approval_request(proposal)

        manager.reject(request, reason="Not needed at this time")

        assert request.decision == ApprovalDecision.REJECTED
        assert request.decision_comment == "Not needed at this time"
        assert request.decided_at is not None

    def test_reject_without_reason(self):
        manager = ApprovalManager()
        proposal = make_proposal()
        request = manager.create_approval_request(proposal)

        with pytest.raises(ValueError, match="Rejection reason is required"):
            manager.reject(request, reason="")

    def test_reject_non_pending(self):
        manager = ApprovalManager()
        proposal = make_proposal()
        request = manager.create_approval_request(proposal)
        manager.reject(request, reason="Not needed")

        with pytest.raises(ValueError, match="Cannot reject"):
            manager.reject(request, reason="Again")

    def test_reject_updates_proposal(self):
        manager = ApprovalManager()
        proposal = make_proposal()
        request = manager.create_approval_request(proposal)

        manager.reject(request, reason="Out of scope")
        manager.update_proposal_from_decision(proposal, request)

        assert proposal.status == ProposalStatus.REJECTED
        assert proposal.rejection_reason == "Out of scope"


class TestApprovalManagerDefer:

    def test_defer_request(self):
        manager = ApprovalManager()
        proposal = make_proposal()
        request = manager.create_approval_request(proposal)

        manager.defer(request, reason="Need more information")

        assert request.decision == ApprovalDecision.DEFERRED
        assert request.decision_comment == "Need more information"
        assert request.decided_at is not None

    def test_defer_without_reason(self):
        manager = ApprovalManager()
        proposal = make_proposal()
        request = manager.create_approval_request(proposal)

        manager.defer(request)

        assert request.decision == ApprovalDecision.DEFERRED
        assert request.decision_comment == ""

    def test_defer_non_pending(self):
        manager = ApprovalManager()
        proposal = make_proposal()
        request = manager.create_approval_request(proposal)
        manager.approve(request)

        with pytest.raises(ValueError, match="Cannot defer"):
            manager.defer(request)


class TestApprovalManagerUpdateProposal:

    def test_update_proposal_mismatched_ids(self):
        manager = ApprovalManager()
        proposal = make_proposal(proposal_id="PROP-001")
        other_proposal = make_proposal(proposal_id="PROP-002")
        request = manager.create_approval_request(proposal)
        manager.approve(request)

        with pytest.raises(ValueError, match="not 'PROP-002'"):
            manager.update_proposal_from_decision(other_proposal, request)

    def test_update_proposal_pending_request(self):
        manager = ApprovalManager()
        proposal = make_proposal()
        request = manager.create_approval_request(proposal)

        with pytest.raises(ValueError, match="pending"):
            manager.update_proposal_from_decision(proposal, request)

    def test_update_proposal_deferred(self):
        manager = ApprovalManager()
        proposal = make_proposal()
        request = manager.create_approval_request(proposal)
        manager.defer(request)

        manager.update_proposal_from_decision(proposal, request)

        assert proposal.status == ProposalStatus.DEFERRED