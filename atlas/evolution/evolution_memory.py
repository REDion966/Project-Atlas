"""
Atlas Evolution Memory

Stores observations, proposals, rejected ideas, accepted ideas, and
maintains historical evolution records.

Phase 7.0 — Self-Evolution Foundation.
"""

from collections import deque
from datetime import datetime
from typing import Any

from atlas.evolution.models import (
    ApprovalRequest,
    EvolutionProposal,
    EvolutionRecord,
    Observation,
    ProposalStatus,
)


class EvolutionMemory:
    """
    Persistent (in-memory) store for evolution-related data.

    Maintains bounded histories of observations, proposals, approval
    requests, and evolution records. This is a pure logic component
    with no infrastructure dependencies.

    Attributes:
        max_observations: Maximum number of observations to retain.
        max_proposals: Maximum number of proposals to retain.
        max_records: Maximum number of evolution records to retain.
    """

    def __init__(
        self,
        max_observations: int = 1000,
        max_proposals: int = 200,
        max_records: int = 500,
    ) -> None:
        if max_observations <= 0:
            raise ValueError("max_observations must be a positive integer")
        if max_proposals <= 0:
            raise ValueError("max_proposals must be a positive integer")
        if max_records <= 0:
            raise ValueError("max_records must be a positive integer")

        self._max_observations = max_observations
        self._max_proposals = max_proposals
        self._max_records = max_records

        self._observations: deque[Observation] = deque(maxlen=max_observations)
        self._proposals: deque[EvolutionProposal] = deque(maxlen=max_proposals)
        self._approval_requests: deque[ApprovalRequest] = deque()
        self._records: deque[EvolutionRecord] = deque(maxlen=max_records)

    # ------------------------------------------------------------------
    # Observations
    # ------------------------------------------------------------------

    def store_observation(self, observation: Observation) -> None:
        """Store an observation."""
        self._observations.append(observation)

    def get_observations(
        self,
        n: int = 50,
    ) -> list[Observation]:
        """Return the most recent n observations, newest first."""
        if n <= 0:
            return []
        return list(reversed(self._observations))[:n]

    @property
    def observation_count(self) -> int:
        """Return the number of stored observations."""
        return len(self._observations)

    # ------------------------------------------------------------------
    # Proposals
    # ------------------------------------------------------------------

    def store_proposal(self, proposal: EvolutionProposal) -> None:
        """Store an evolution proposal."""
        self._proposals.append(proposal)

    def get_proposal(self, proposal_id: str) -> EvolutionProposal | None:
        """Retrieve a proposal by its ID."""
        for proposal in self._proposals:
            if proposal.proposal_id == proposal_id:
                return proposal
        return None

    def get_proposals_by_status(
        self,
        status: ProposalStatus,
    ) -> list[EvolutionProposal]:
        """Return all proposals with a given status."""
        return [
            p for p in self._proposals
            if p.status == status
        ]

    def get_all_proposals(self) -> list[EvolutionProposal]:
        """Return all stored proposals, newest first."""
        return list(reversed(self._proposals))

    def update_proposal_status(
        self,
        proposal_id: str,
        new_status: ProposalStatus,
        rejection_reason: str = "",
    ) -> bool:
        """
        Update the status of a proposal.

        Args:
            proposal_id: The ID of the proposal to update.
            new_status: The new status to set.
            rejection_reason: If rejecting, the reason.

        Returns:
            True if the proposal was found and updated, False otherwise.
        """
        proposal = self.get_proposal(proposal_id)
        if proposal is None:
            return False

        proposal.status = new_status
        if new_status == ProposalStatus.REJECTED:
            proposal.rejection_reason = rejection_reason
        if new_status == ProposalStatus.APPROVED:
            proposal.approved_at = datetime.now()

        return True

    @property
    def proposal_count(self) -> int:
        """Return the number of stored proposals."""
        return len(self._proposals)

    # ------------------------------------------------------------------
    # Approval requests
    # ------------------------------------------------------------------

    def store_approval_request(self, request: ApprovalRequest) -> None:
        """Store an approval request."""
        self._approval_requests.append(request)

    def get_approval_request(
        self,
        request_id: str,
    ) -> ApprovalRequest | None:
        """Retrieve an approval request by its ID."""
        for req in self._approval_requests:
            if req.request_id == request_id:
                return req
        return None

    def get_pending_approval_requests(self) -> list[ApprovalRequest]:
        """Return all pending approval requests."""
        from atlas.evolution.models import ApprovalDecision

        return [
            req for req in self._approval_requests
            if req.decision == ApprovalDecision.PENDING
        ]

    def get_all_approval_requests(self) -> list[ApprovalRequest]:
        """Return all stored approval requests, newest first."""
        return list(reversed(self._approval_requests))

    @property
    def approval_request_count(self) -> int:
        """Return the number of stored approval requests."""
        return len(self._approval_requests)

    # ------------------------------------------------------------------
    # Evolution records
    # ------------------------------------------------------------------

    def store_record(self, record: EvolutionRecord) -> None:
        """Store an evolution history record."""
        self._records.append(record)

    def get_records(
        self,
        n: int = 50,
    ) -> list[EvolutionRecord]:
        """Return the most recent n evolution records, newest first."""
        if n <= 0:
            return []
        return list(reversed(self._records))[:n]

    def get_records_by_type(
        self,
        event_type: str,
        n: int = 50,
    ) -> list[EvolutionRecord]:
        """Return the most recent n records of a given event type."""
        filtered = [
            r for r in reversed(self._records)
            if r.event_type == event_type
        ]
        return filtered[:n]

    @property
    def record_count(self) -> int:
        """Return the number of stored evolution records."""
        return len(self._records)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return a summary of all stored evolution data."""
        return {
            "observation_count": self.observation_count,
            "proposal_count": self.proposal_count,
            "approval_request_count": self.approval_request_count,
            "record_count": self.record_count,
            "pending_approvals": len(self.get_pending_approval_requests()),
        }

    def clear(self) -> None:
        """Clear all stored data."""
        self._observations.clear()
        self._proposals.clear()
        self._approval_requests.clear()
        self._records.clear()