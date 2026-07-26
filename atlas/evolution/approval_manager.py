"""
Atlas Approval Manager

Represents the approval workflow for evolution proposals.
Every proposal requires explicit user approval before execution.
No execution capability in this phase.

Phase 7.0 — Self-Evolution Foundation.
"""

from datetime import datetime

from atlas.evolution.models import (
    ApprovalDecision,
    ApprovalRequest,
    EvolutionProposal,
    ProposalStatus,
)


class ApprovalManager:
    """
    Manages the approval workflow for evolution proposals.

    This is a pure logic component with no infrastructure dependencies.
    It manages approval state and generates approval requests.
    It never executes proposals or modifies the system.

    The approval workflow is:
        1. Proposal is generated (DRAFT).
        2. Proposal is submitted for approval (PENDING_APPROVAL).
        3. Approval request is created and presented to the user.
        4. User approves, rejects, or defers the request.
        5. Proposal status is updated accordingly.
    """

    def __init__(self) -> None:
        self._request_counter = 0

    def _next_request_id(self) -> str:
        """Generate a unique approval request identifier."""
        self._request_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"APPR-{timestamp}-{self._request_counter:04d}"

    def create_approval_request(
        self,
        proposal: EvolutionProposal,
    ) -> ApprovalRequest:
        """
        Create an approval request for a proposal.

        This transitions the proposal from DRAFT to PENDING_APPROVAL.

        Args:
            proposal: The EvolutionProposal requiring approval.

        Returns:
            An ApprovalRequest ready for user review.

        Raises:
            ValueError: If the proposal is already approved, rejected,
                or has been implemented.
        """
        if proposal.status in (
            ProposalStatus.APPROVED,
            ProposalStatus.REJECTED,
            ProposalStatus.IMPLEMENTED,
        ):
            raise ValueError(
                f"Cannot create approval request for proposal "
                f"'{proposal.proposal_id}' with status "
                f"'{proposal.status.name}'."
            )

        proposal.status = ProposalStatus.PENDING_APPROVAL

        return ApprovalRequest(
            request_id=self._next_request_id(),
            proposal_id=proposal.proposal_id,
            title=proposal.title,
            description=proposal.summary,
            rationale=proposal.rationale,
            risks=proposal.risks,
            expected_benefit=proposal.expected_benefit,
        )

    def approve(
        self,
        request: ApprovalRequest,
        comment: str = "",
    ) -> None:
        """
        Approve a pending approval request.

        Args:
            request: The ApprovalRequest to approve.
            comment: Optional user comment on the decision.

        Raises:
            ValueError: If the request is not in PENDING state.
        """
        if request.decision != ApprovalDecision.PENDING:
            raise ValueError(
                f"Cannot approve request '{request.request_id}' "
                f"with decision '{request.decision.name}'."
            )

        request.decision = ApprovalDecision.APPROVED
        request.decision_comment = comment
        request.decided_at = datetime.now()

    def reject(
        self,
        request: ApprovalRequest,
        reason: str,
    ) -> None:
        """
        Reject a pending approval request.

        Args:
            request: The ApprovalRequest to reject.
            reason: The reason for rejection.

        Raises:
            ValueError: If the request is not in PENDING state.
            ValueError: If no rejection reason is provided.
        """
        if request.decision != ApprovalDecision.PENDING:
            raise ValueError(
                f"Cannot reject request '{request.request_id}' "
                f"with decision '{request.decision.name}'."
            )

        if not reason.strip():
            raise ValueError(
                "Rejection reason is required."
            )

        request.decision = ApprovalDecision.REJECTED
        request.decision_comment = reason
        request.decided_at = datetime.now()

    def defer(
        self,
        request: ApprovalRequest,
        reason: str = "",
    ) -> None:
        """
        Defer a pending approval request for later consideration.

        Args:
            request: The ApprovalRequest to defer.
            reason: Optional reason for deferring.

        Raises:
            ValueError: If the request is not in PENDING state.
        """
        if request.decision != ApprovalDecision.PENDING:
            raise ValueError(
                f"Cannot defer request '{request.request_id}' "
                f"with decision '{request.decision.name}'."
            )

        request.decision = ApprovalDecision.DEFERRED
        request.decision_comment = reason
        request.decided_at = datetime.now()

    def update_proposal_from_decision(
        self,
        proposal: EvolutionProposal,
        request: ApprovalRequest,
    ) -> None:
        """
        Update a proposal's status based on an approval decision.

        Args:
            proposal: The EvolutionProposal to update.
            request: The ApprovalRequest with the decision.

        Raises:
            ValueError: If the request is still PENDING.
            ValueError: If the request's proposal_id does not match
                the proposal's proposal_id.
        """
        if request.decision == ApprovalDecision.PENDING:
            raise ValueError(
                "Cannot update proposal from a pending approval request."
            )

        if request.proposal_id != proposal.proposal_id:
            raise ValueError(
                f"Approval request '{request.request_id}' is for proposal "
                f"'{request.proposal_id}', not '{proposal.proposal_id}'."
            )

        if request.decision == ApprovalDecision.APPROVED:
            proposal.status = ProposalStatus.APPROVED
            proposal.approved_at = datetime.now()
        elif request.decision == ApprovalDecision.REJECTED:
            proposal.status = ProposalStatus.REJECTED
            proposal.rejection_reason = request.decision_comment
        elif request.decision == ApprovalDecision.DEFERRED:
            proposal.status = ProposalStatus.DEFERRED