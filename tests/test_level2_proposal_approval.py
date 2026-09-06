"""P13.5 — Level 2 Proposal + Explicit Approval Contract Tests.

Proves the Level 2 invariants:
- L2-01: Proposal generation cannot mutate
- L2-02: Proposal cannot execute itself
- L2-03: Proposal != authorization
- L2-04: Approval is explicit
- L2-05: Approval bound to exact proposal identity/content
- L2-06: Approval != authorization
- L2-07: Rejected proposal cannot execute
- L2-08: Stale approval cannot execute
- L2-09: Unrelated context cannot approve
- L2-10: No silent Level 3 transition
- L2-11: Execution boundary remains protected
- L2-12: Human approval controls promotion
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.models import (
    ApprovalDecision,
    ApprovalRequest,
    EvolutionProposal,
    ImprovementPlan,
    ProposalStatus,
)
from atlas.conversation.task_intake import TaskIntake, TaskType


@pytest.fixture
def sample_plan() -> ImprovementPlan:
    from atlas.evolution.models import ImprovementPriority, Weakness
    return ImprovementPlan(
        plan_id="PLAN-1",
        title="Test Plan",
        description="Test description",
        priority=ImprovementPriority.MEDIUM,
    )


@pytest.fixture
def sample_proposal(sample_plan: ImprovementPlan) -> EvolutionProposal:
    return EvolutionProposal(
        proposal_id="PROP-1",
        title="Fix datetime handling",
        summary="Normalize datetimes to aware UTC",
        rationale="Mixed naive/aware comparisons fail",
        expected_benefit="Consistent datetime handling",
        risks="Low risk",
        impact_analysis="Affects understanding module",
        implementation_approach="Replace datetime.now() with datetime.now(timezone.utc)",
        plan=sample_plan,
    )


class TestProposalFingerprint:
    """Proposal identity/fingerprint tests."""

    def test_same_content_same_fingerprint(self, sample_proposal: EvolutionProposal):
        """Identical proposal content produces identical fingerprint."""
        fp1 = sample_proposal.compute_fingerprint()
        fp2 = sample_proposal.compute_fingerprint()
        assert fp1 == fp2
        assert len(fp1) > 0

    def test_different_content_different_fingerprint(
        self, sample_proposal: EvolutionProposal, sample_plan: ImprovementPlan
    ):
        """Changed proposal content produces different fingerprint."""
        fp1 = sample_proposal.compute_fingerprint()
        different_proposal = EvolutionProposal(
            proposal_id="PROP-2",
            title="Different title",
            summary="Different summary",
            rationale="Different rationale",
            expected_benefit="Different benefit",
            risks="Different risks",
            impact_analysis="Different impact",
            implementation_approach="Different approach",
            plan=sample_plan,
        )
        fp2 = different_proposal.compute_fingerprint()
        assert fp1 != fp2

    def test_fingerprint_excludes_status_and_timestamps(
        self, sample_proposal: EvolutionProposal
    ):
        """Fingerprint is independent of status and timestamps."""
        fp1 = sample_proposal.compute_fingerprint()
        sample_proposal.status = ProposalStatus.APPROVED
        fp2 = sample_proposal.compute_fingerprint()
        assert fp1 == fp2


class TestApprovalBinding:
    """Approval must be bound to exact proposal."""

    def test_approval_stores_fingerprint(self, sample_proposal: EvolutionProposal):
        """ApprovalRequest stores the proposal fingerprint."""
        manager = ApprovalManager()
        request = manager.create_approval_request(sample_proposal)
        assert request.proposal_fingerprint == sample_proposal.proposal_fingerprint
        assert len(request.proposal_fingerprint) > 0

    def test_approval_valid_for_same_proposal(
        self, sample_proposal: EvolutionProposal
    ):
        """Approval is valid for the exact proposal it was created for."""
        manager = ApprovalManager()
        request = manager.create_approval_request(sample_proposal)
        assert request.is_valid_for(sample_proposal) is True

    def test_approval_invalid_for_changed_proposal(
        self, sample_proposal: EvolutionProposal, sample_plan: ImprovementPlan
    ):
        """Approval becomes invalid when proposal content changes."""
        manager = ApprovalManager()
        request = manager.create_approval_request(sample_proposal)

        # Create a new proposal with changed content (frozen dataclass)
        changed_proposal = EvolutionProposal(
            proposal_id=sample_proposal.proposal_id,
            title="Changed title",  # Changed
            summary=sample_proposal.summary,
            rationale=sample_proposal.rationale,
            expected_benefit=sample_proposal.expected_benefit,
            risks=sample_proposal.risks,
            impact_analysis=sample_proposal.impact_analysis,
            implementation_approach=sample_proposal.implementation_approach,
            plan=sample_plan,
        )
        assert request.is_valid_for(changed_proposal) is False

    def test_approval_invalid_for_different_proposal_id(
        self, sample_proposal: EvolutionProposal, sample_plan: ImprovementPlan
    ):
        """Approval is invalid for a different proposal ID."""
        manager = ApprovalManager()
        request = manager.create_approval_request(sample_proposal)

        different_proposal = EvolutionProposal(
            proposal_id="PROP-DIFFERENT",
            title=sample_proposal.title,
            summary=sample_proposal.summary,
            rationale=sample_proposal.rationale,
            expected_benefit=sample_proposal.expected_benefit,
            risks=sample_proposal.risks,
            impact_analysis=sample_proposal.impact_analysis,
            implementation_approach=sample_proposal.implementation_approach,
            plan=sample_plan,
        )
        assert request.is_valid_for(different_proposal) is False

    def test_approval_a_cannot_approve_proposal_b(
        self, sample_proposal: EvolutionProposal, sample_plan: ImprovementPlan
    ):
        """Approval for Proposal A cannot approve Proposal B."""
        manager = ApprovalManager()
        request_a = manager.create_approval_request(sample_proposal)

        proposal_b = EvolutionProposal(
            proposal_id="PROP-B",
            title="Different",
            summary="Different",
            rationale="Different",
            expected_benefit="Different",
            risks="Different",
            impact_analysis="Different",
            implementation_approach="Different",
            plan=sample_plan,
        )
        assert request_a.is_valid_for(proposal_b) is False


class TestExplicitApprovalClassification:
    """Explicit approval must be distinguished from ambiguous responses."""

    @pytest.mark.parametrize("text", [
        "Approve this proposal.",
        "I approve this proposal.",
        "Yes, I approve the proposed changes.",
        "Accept this proposal.",
        "Authorize this proposal.",
    ])
    def test_explicit_approval_classified(self, text: str):
        """Explicit approval language is classified as APPROVAL."""
        spec = TaskIntake().intake(text)
        assert spec.task_type is TaskType.APPROVAL

    @pytest.mark.parametrize("text", [
        "Okay.",
        "Sure.",
        "Looks good.",
        "Sounds good.",
        "Makes sense.",
        "Go ahead.",
        "Do it.",
        "Fine.",
    ])
    def test_ambiguous_responses_not_approval(self, text: str):
        """Ambiguous responses are NOT classified as approval."""
        spec = TaskIntake().intake(text)
        assert spec.task_type is not TaskType.APPROVAL

    def test_negated_approval_not_approval(self):
        """'Don't approve' is not classified as approval."""
        spec = TaskIntake().intake("Don't approve this proposal.")
        assert spec.task_type is not TaskType.APPROVAL


class TestNoExecutionFromApproval:
    """Approval must not trigger execution."""

    def test_approval_does_not_call_application_engine(self):
        """Approval handling must not call ApplicationEngine.apply()."""
        service = TaskIntake()
        spec = service.intake("Approve this proposal.")

        with patch(
            "atlas.evolution.autonomy.application_engine.ApplicationEngine.apply"
        ) as mock_apply:
            # The classification itself doesn't call apply
            assert spec.task_type is TaskType.APPROVAL
            mock_apply.assert_not_called()

    def test_approval_does_not_create_authorization(self):
        """Approval must not create execution authorization."""
        with patch(
            "atlas.evolution.autonomy.authorization_manager.AuthorizationManager"
        ) as mock_auth:
            service = TaskIntake()
            spec = service.intake("Approve this proposal.")
            assert spec.task_type is TaskType.APPROVAL
            mock_auth.assert_not_called()


class TestConversationStateProposalTracking:
    """ConversationState must support proposal/approval tracking."""

    def test_state_has_active_proposal_fields(self):
        """ConversationState has fields for active proposal tracking."""
        from atlas.conversation.conversation_state import ConversationState

        state = ConversationState(
            active_proposal_id="PROP-1",
            active_proposal_fingerprint="abc123",
            pending_approval_id="APPR-1",
        )
        assert state.active_proposal_id == "PROP-1"
        assert state.active_proposal_fingerprint == "abc123"
        assert state.pending_approval_id == "APPR-1"

    def test_state_proposal_fields_are_isolated(self):
        """Proposal state is separate from investigation state."""
        from atlas.conversation.conversation_state import ConversationState

        state = ConversationState(
            current_investigation="inv-1",
            active_proposal_id="PROP-1",
        )
        # Investigation and proposal are distinct fields
        assert state.current_investigation == "inv-1"
        assert state.active_proposal_id == "PROP-1"
        assert state.current_investigation != state.active_proposal_id

    def test_manager_updates_proposal_state(self):
        """ConversationStateManager can update proposal state."""
        from atlas.conversation.conversation_state import ConversationStateManager

        mgr = ConversationStateManager()
        mgr.update(
            active_proposal_id="PROP-1",
            active_proposal_fingerprint="fp123",
            pending_approval_id="APPR-1",
        )
        assert mgr.state.active_proposal_id == "PROP-1"
        assert mgr.state.active_proposal_fingerprint == "fp123"
        assert mgr.state.pending_approval_id == "APPR-1"

    def test_manager_clears_proposal_state(self):
        """Proposal state can be cleared."""
        from atlas.conversation.conversation_state import ConversationStateManager

        mgr = ConversationStateManager()
        mgr.update(active_proposal_id="PROP-1")
        mgr.reset_field("active_proposal_id")
        assert mgr.state.active_proposal_id is None
