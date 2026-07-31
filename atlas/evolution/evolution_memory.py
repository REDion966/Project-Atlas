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
    ApprovalDecision,
    ApprovalRequest,
    ImprovementPlan,
    ImprovementPriority,
    EvolutionProposal,
    EvolutionRecord,
    Observation,
    ProposalStatus,
    Weakness,
)


# ---------------------------------------------------------------------------
# Module-level helpers: dict → domain model (for restore from storage)
# ---------------------------------------------------------------------------


def _proposal_from_dict(data: dict) -> EvolutionProposal:
    """Reconstruct an EvolutionProposal from a dictionary."""
    plan_data = data.get("plan", {})
    weaknesses_data = plan_data.get("weaknesses", [])
    weaknesses = [
        Weakness(
            area=w.get("area", ""),
            description=w.get("description", ""),
            severity=getattr(ImprovementPriority, w.get("severity", "LOW"), ImprovementPriority.LOW),
            supporting_observations=w.get("supporting_observations", []),
            detected_at=datetime.fromisoformat(w["detected_at"])
            if isinstance(w.get("detected_at"), str) else w.get("detected_at", datetime.now()),
        )
        for w in weaknesses_data
    ]

    plan = ImprovementPlan(
        plan_id=plan_data.get("plan_id", ""),
        title=plan_data.get("title", ""),
        description=plan_data.get("description", ""),
        priority=getattr(ImprovementPriority, plan_data.get("priority", "LOW"), ImprovementPriority.LOW),
        weaknesses=weaknesses,
        expected_benefit=plan_data.get("expected_benefit", ""),
        complexity_estimate=plan_data.get("complexity_estimate", "medium"),
        target_components=plan_data.get("target_components", []),
        created_at=datetime.fromisoformat(plan_data["created_at"])
        if isinstance(plan_data.get("created_at"), str) else plan_data.get("created_at", datetime.now()),
    )

    return EvolutionProposal(
        proposal_id=data.get("proposal_id", ""),
        title=data.get("title", ""),
        summary=data.get("summary", ""),
        rationale=data.get("rationale", ""),
        expected_benefit=data.get("expected_benefit", ""),
        risks=data.get("risks", ""),
        impact_analysis=data.get("impact_analysis", ""),
        implementation_approach=data.get("implementation_approach", ""),
        plan=plan,
        status=getattr(ProposalStatus, data.get("status", "DRAFT"), ProposalStatus.DRAFT),
        rejection_reason=data.get("rejection_reason", ""),
        created_at=datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("created_at"), str) else data.get("created_at", datetime.now()),
        approved_at=datetime.fromisoformat(data["approved_at"])
        if isinstance(data.get("approved_at"), str) else data.get("approved_at"),
        metadata=data.get("metadata", {}),
    )


def _approval_request_from_dict(data: dict) -> ApprovalRequest:
    """Reconstruct an ApprovalRequest from a dictionary."""
    from atlas.evolution.models import ApprovalDecision

    return ApprovalRequest(
        request_id=data.get("request_id", ""),
        proposal_id=data.get("proposal_id", ""),
        title=data.get("title", ""),
        description=data.get("description", ""),
        rationale=data.get("rationale", ""),
        risks=data.get("risks", ""),
        expected_benefit=data.get("expected_benefit", ""),
        decision=getattr(ApprovalDecision, data.get("decision", "PENDING"), ApprovalDecision.PENDING),
        decision_comment=data.get("decision_comment", ""),
        created_at=datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("created_at"), str) else data.get("created_at", datetime.now()),
        decided_at=datetime.fromisoformat(data["decided_at"])
        if isinstance(data.get("decided_at"), str) else data.get("decided_at"),
    )


def _proposal_to_dict(proposal: EvolutionProposal) -> dict:
    """Serialize an EvolutionProposal to a JSON-safe dictionary."""
    return {
        "proposal_id": proposal.proposal_id,
        "title": proposal.title,
        "summary": proposal.summary,
        "rationale": proposal.rationale,
        "expected_benefit": proposal.expected_benefit,
        "risks": proposal.risks,
        "impact_analysis": proposal.impact_analysis,
        "implementation_approach": proposal.implementation_approach,
        "plan": {
            "plan_id": proposal.plan.plan_id,
            "title": proposal.plan.title,
            "description": proposal.plan.description,
            "priority": proposal.plan.priority.name,
            "weaknesses": [
                {
                    "area": w.area,
                    "description": w.description,
                    "severity": w.severity.name,
                    "supporting_observations": w.supporting_observations,
                    "detected_at": w.detected_at.isoformat() if hasattr(w.detected_at, "isoformat") else str(w.detected_at),
                }
                for w in proposal.plan.weaknesses
            ],
            "expected_benefit": proposal.plan.expected_benefit,
            "complexity_estimate": proposal.plan.complexity_estimate,
            "target_components": list(proposal.plan.target_components),
            "created_at": proposal.plan.created_at.isoformat() if hasattr(proposal.plan.created_at, "isoformat") else str(proposal.plan.created_at),
        },
        "status": proposal.status.name,
        "rejection_reason": proposal.rejection_reason,
        "created_at": proposal.created_at.isoformat() if hasattr(proposal.created_at, "isoformat") else str(proposal.created_at),
        "approved_at": proposal.approved_at.isoformat() if proposal.approved_at and hasattr(proposal.approved_at, "isoformat") else (proposal.approved_at or None),
        "metadata": dict(proposal.metadata),
    }


def _approval_request_to_dict(request: ApprovalRequest) -> dict:
    """Serialize an ApprovalRequest to a JSON-safe dictionary."""
    return {
        "request_id": request.request_id,
        "proposal_id": request.proposal_id,
        "title": request.title,
        "description": request.description,
        "rationale": request.rationale,
        "risks": request.risks,
        "expected_benefit": request.expected_benefit,
        "decision": request.decision.name,
        "decision_comment": request.decision_comment,
        "created_at": request.created_at.isoformat() if hasattr(request.created_at, "isoformat") else str(request.created_at),
        "decided_at": request.decided_at.isoformat() if request.decided_at and hasattr(request.decided_at, "isoformat") else (request.decided_at or None),
    }


def _evolution_record_to_dict(record: EvolutionRecord) -> dict:
    """Serialize an EvolutionRecord to a JSON-safe dictionary."""
    return {
        "record_id": record.record_id,
        "event_type": record.event_type,
        "description": record.description,
        "related_ids": list(record.related_ids),
        "timestamp": record.timestamp.isoformat() if hasattr(record.timestamp, "isoformat") else str(record.timestamp),
        "metadata": dict(record.metadata),
    }


def _evolution_record_from_dict(data: dict) -> EvolutionRecord:
    """Reconstruct an EvolutionRecord from a dictionary."""
    return EvolutionRecord(
        record_id=data.get("record_id", ""),
        event_type=data.get("event_type", ""),
        description=data.get("description", ""),
        related_ids=data.get("related_ids", []),
        timestamp=datetime.fromisoformat(data["timestamp"])
        if isinstance(data.get("timestamp"), str) else data.get("timestamp", datetime.now()),
        metadata=data.get("metadata", {}),
    )


class EvolutionMemory:
    """
    Bounded in-memory store for evolution-related data.

    Maintains histories of observations, proposals, approval requests,
    and evolution records. When a `storage` adapter is injected, the
    memory dual-writes to both memory and storage; storage writes are
    best-effort and never break the in-memory path.

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
        storage: Any = None,
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
        self._storage = storage

        self._observations: deque[Observation] = deque(maxlen=max_observations)
        self._proposals: deque[EvolutionProposal] = deque(maxlen=max_proposals)
        self._approval_requests: deque[ApprovalRequest] = deque()
        self._records: deque[EvolutionRecord] = deque(maxlen=max_records)

    @property
    def storage(self):
        """Return the injected storage adapter, or None."""
        return self._storage

    # ------------------------------------------------------------------
    # Persistence (Phase 11.3)
    # ------------------------------------------------------------------

    def restore(self) -> None:
        """
        Load persisted data from the injected storage adapter into memory.

        If no storage is configured or storage is unavailable, this is a
        no-op. Storage failures are logged and do not crash startup.
        """
        if self._storage is None or not self._storage.is_available():
            return

        import logging
        logger = logging.getLogger(__name__)

        try:
            for prop_dict in self._storage.load_proposals():
                proposal = _proposal_from_dict(prop_dict)
                self._proposals.append(proposal)
        except Exception:
            logger.exception("Failed to restore evolution proposals from storage")

        try:
            for req_dict in self._storage.load_approval_requests():
                request = _approval_request_from_dict(req_dict)
                self._approval_requests.append(request)
        except Exception:
            logger.exception("Failed to restore evolution approval requests from storage")

        try:
            for rec_dict in self._storage.load_records():
                record = _evolution_record_from_dict(rec_dict)
                self._records.append(record)
        except Exception:
            logger.exception("Failed to restore evolution records from storage")

    def _try_storage_write(self, method_name: str, data: dict) -> None:
        """Call a storage write method, degrading gracefully on failure."""
        if self._storage is None or not self._storage.is_available():
            return
        try:
            if method_name == "store_proposal":
                self._storage.store_proposal(data)
            elif method_name == "store_approval_request":
                self._storage.store_approval_request(data)
            elif method_name == "store_record":
                self._storage.store_record(data)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Evolution storage write failed for %s", method_name
            )

    # ------------------------------------------------------------------
    # Observations
    # ------------------------------------------------------------------

    def store_observation(self, observation: Observation) -> None:
        """Store an observation in memory only."""
        self._observations.append(observation)

    def persist_observation(self, observation: Observation) -> None:
        """
        Persist an observation to the injected storage adapter.

        The observation is stored in memory (via store_observation) and
        written to storage best-effort. Storage failures never break the
        in-memory path. No-op when no storage is configured.

        Phase 13.5 — Persistent Evolution Memory Integration.

        Args:
            observation: The Observation to persist.
        """
        self.store_observation(observation)
        if self._storage is None or not self._storage.is_available():
            return
        try:
            self._storage.store_observation(
                {
                    "observation_id": (
                        observation.metadata.get("observation_id", "")
                        if isinstance(observation.metadata, dict)
                        else ""
                    ) or (
                        f"{observation.timestamp.isoformat()}:{observation.metric_name}"
                    ),
                    "category": (
                        observation.category.name
                        if hasattr(observation.category, "name")
                        else str(observation.category)
                    ),
                    "metric_name": observation.metric_name,
                    "value": observation.value,
                    "unit": observation.unit,
                    "description": observation.description,
                    "timestamp": observation.timestamp.isoformat()
                    if hasattr(observation.timestamp, "isoformat")
                    else str(observation.timestamp),
                    "source": observation.source,
                    "metadata": dict(observation.metadata),
                }
            )
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Failed to persist observation %s",
                observation.metric_name,
            )

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
        self._try_storage_write("store_proposal", _proposal_to_dict(proposal))

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

        # Persist the updated proposal to storage (best-effort)
        self._try_storage_write("store_proposal", _proposal_to_dict(proposal))

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
        self._try_storage_write("store_approval_request", _approval_request_to_dict(request))

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
        self._try_storage_write("store_record", _evolution_record_to_dict(record))

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
