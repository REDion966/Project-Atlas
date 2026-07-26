"""
Phase 7.0 — Self-Evolution Foundation: EvolutionMemory Tests.
"""

import pytest

from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.models import (
    ApprovalDecision,
    ApprovalRequest,
    EvolutionProposal,
    EvolutionRecord,
    ImprovementPlan,
    ImprovementPriority,
    Observation,
    ObservationCategory,
    ProposalStatus,
)


class TestEvolutionMemoryInit:

    def test_default_limits(self):
        mem = EvolutionMemory()
        assert mem.observation_count == 0
        assert mem.proposal_count == 0
        assert mem.approval_request_count == 0
        assert mem.record_count == 0

    def test_custom_limits(self):
        mem = EvolutionMemory(max_observations=10, max_proposals=5, max_records=20)
        assert mem.observation_count == 0

    def test_invalid_limits(self):
        with pytest.raises(ValueError, match="positive integer"):
            EvolutionMemory(max_observations=0)
        with pytest.raises(ValueError, match="positive integer"):
            EvolutionMemory(max_proposals=0)
        with pytest.raises(ValueError, match="positive integer"):
            EvolutionMemory(max_records=0)


class TestEvolutionMemoryObservations:

    def test_store_and_retrieve(self):
        mem = EvolutionMemory()
        obs = Observation(
            category=ObservationCategory.RUNTIME_METRICS,
            metric_name="test",
            value=42,
        )
        mem.store_observation(obs)
        assert mem.observation_count == 1
        retrieved = mem.get_observations()
        assert len(retrieved) == 1
        assert retrieved[0].value == 42

    def test_get_observations_limit(self):
        mem = EvolutionMemory()
        for i in range(10):
            mem.store_observation(Observation(
                category=ObservationCategory.RUNTIME_METRICS,
                metric_name=f"test_{i}",
                value=i,
            ))
        assert len(mem.get_observations(3)) == 3
        assert len(mem.get_observations(100)) == 10

    def test_get_observations_invalid_n(self):
        mem = EvolutionMemory()
        assert mem.get_observations(0) == []
        assert mem.get_observations(-1) == []


class TestEvolutionMemoryProposals:

    def test_store_and_retrieve(self):
        mem = EvolutionMemory()
        plan = ImprovementPlan(
            plan_id="IMP-001", title="Test", description="Test",
            priority=ImprovementPriority.LOW,
        )
        proposal = EvolutionProposal(
            proposal_id="PROP-001", title="Test", summary="Test",
            rationale="Test", expected_benefit="Test", risks="Test",
            impact_analysis="Test", implementation_approach="Test",
            plan=plan,
        )
        mem.store_proposal(proposal)
        assert mem.proposal_count == 1

        retrieved = mem.get_proposal("PROP-001")
        assert retrieved is not None
        assert retrieved.proposal_id == "PROP-001"

        assert mem.get_proposal("NONEXISTENT") is None

    def test_get_proposals_by_status(self):
        mem = EvolutionMemory()
        plan = ImprovementPlan(
            plan_id="IMP-001", title="Test", description="Test",
            priority=ImprovementPriority.LOW,
        )
        p1 = EvolutionProposal(
            proposal_id="PROP-001", title="A", summary="", rationale="",
            expected_benefit="", risks="", impact_analysis="",
            implementation_approach="", plan=plan,
            status=ProposalStatus.DRAFT,
        )
        p2 = EvolutionProposal(
            proposal_id="PROP-002", title="B", summary="", rationale="",
            expected_benefit="", risks="", impact_analysis="",
            implementation_approach="", plan=plan,
            status=ProposalStatus.APPROVED,
        )
        mem.store_proposal(p1)
        mem.store_proposal(p2)

        drafts = mem.get_proposals_by_status(ProposalStatus.DRAFT)
        assert len(drafts) == 1
        assert drafts[0].proposal_id == "PROP-001"

        approved = mem.get_proposals_by_status(ProposalStatus.APPROVED)
        assert len(approved) == 1

    def test_update_proposal_status(self):
        mem = EvolutionMemory()
        plan = ImprovementPlan(
            plan_id="IMP-001", title="Test", description="Test",
            priority=ImprovementPriority.LOW,
        )
        proposal = EvolutionProposal(
            proposal_id="PROP-001", title="Test", summary="", rationale="",
            expected_benefit="", risks="", impact_analysis="",
            implementation_approach="", plan=plan,
        )
        mem.store_proposal(proposal)

        assert mem.update_proposal_status("PROP-001", ProposalStatus.APPROVED) is True
        assert proposal.status == ProposalStatus.APPROVED
        assert proposal.approved_at is not None

        assert mem.update_proposal_status("NONEXISTENT", ProposalStatus.APPROVED) is False

    def test_update_proposal_rejected(self):
        mem = EvolutionMemory()
        plan = ImprovementPlan(
            plan_id="IMP-001", title="Test", description="Test",
            priority=ImprovementPriority.LOW,
        )
        proposal = EvolutionProposal(
            proposal_id="PROP-001", title="Test", summary="", rationale="",
            expected_benefit="", risks="", impact_analysis="",
            implementation_approach="", plan=plan,
        )
        mem.store_proposal(proposal)
        mem.update_proposal_status("PROP-001", ProposalStatus.REJECTED, "Not needed")
        assert proposal.status == ProposalStatus.REJECTED
        assert proposal.rejection_reason == "Not needed"

    def test_get_all_proposals(self):
        mem = EvolutionMemory()
        plan = ImprovementPlan(
            plan_id="IMP-001", title="Test", description="Test",
            priority=ImprovementPriority.LOW,
        )
        for i in range(3):
            mem.store_proposal(EvolutionProposal(
                proposal_id=f"PROP-{i:03d}", title=f"Test {i}", summary="",
                rationale="", expected_benefit="", risks="", impact_analysis="",
                implementation_approach="", plan=plan,
            ))
        all_proposals = mem.get_all_proposals()
        assert len(all_proposals) == 3


class TestEvolutionMemoryApprovalRequests:

    def test_store_and_retrieve(self):
        mem = EvolutionMemory()
        req = ApprovalRequest(
            request_id="APPR-001", proposal_id="PROP-001",
            title="Test", description="", rationale="",
            risks="", expected_benefit="",
        )
        mem.store_approval_request(req)
        assert mem.approval_request_count == 1

        retrieved = mem.get_approval_request("APPR-001")
        assert retrieved is not None
        assert retrieved.request_id == "APPR-001"

        assert mem.get_approval_request("NONEXISTENT") is None

    def test_get_pending_approval_requests(self):
        mem = EvolutionMemory()
        req1 = ApprovalRequest(
            request_id="APPR-001", proposal_id="PROP-001",
            title="Pending", description="", rationale="",
            risks="", expected_benefit="",
        )
        req2 = ApprovalRequest(
            request_id="APPR-002", proposal_id="PROP-002",
            title="Approved", description="", rationale="",
            risks="", expected_benefit="",
            decision=ApprovalDecision.APPROVED,
        )
        mem.store_approval_request(req1)
        mem.store_approval_request(req2)

        pending = mem.get_pending_approval_requests()
        assert len(pending) == 1
        assert pending[0].request_id == "APPR-001"


class TestEvolutionMemoryRecords:

    def test_store_and_retrieve(self):
        mem = EvolutionMemory()
        rec = EvolutionRecord(
            record_id="EV-001", event_type="test", description="Test record",
        )
        mem.store_record(rec)
        assert mem.record_count == 1

        records = mem.get_records()
        assert len(records) == 1
        assert records[0].record_id == "EV-001"

    def test_get_records_by_type(self):
        mem = EvolutionMemory()
        mem.store_record(EvolutionRecord(record_id="EV-001", event_type="proposal", description="P1"))
        mem.store_record(EvolutionRecord(record_id="EV-002", event_type="approval", description="A1"))
        mem.store_record(EvolutionRecord(record_id="EV-003", event_type="proposal", description="P2"))

        proposals = mem.get_records_by_type("proposal")
        assert len(proposals) == 2

        approvals = mem.get_records_by_type("approval")
        assert len(approvals) == 1

    def test_get_records_limit(self):
        mem = EvolutionMemory()
        for i in range(10):
            mem.store_record(EvolutionRecord(
                record_id=f"EV-{i:03d}", event_type="test", description=f"Record {i}",
            ))
        assert len(mem.get_records(3)) == 3


class TestEvolutionMemorySummary:

    def test_summary_empty(self):
        mem = EvolutionMemory()
        summary = mem.summary()
        assert summary["observation_count"] == 0
        assert summary["proposal_count"] == 0
        assert summary["approval_request_count"] == 0
        assert summary["record_count"] == 0
        assert summary["pending_approvals"] == 0

    def test_summary_with_data(self):
        mem = EvolutionMemory()
        mem.store_observation(Observation(
            category=ObservationCategory.RUNTIME_METRICS,
            metric_name="test", value=1,
        ))
        plan = ImprovementPlan(
            plan_id="IMP-001", title="Test", description="Test",
            priority=ImprovementPriority.LOW,
        )
        mem.store_proposal(EvolutionProposal(
            proposal_id="PROP-001", title="Test", summary="", rationale="",
            expected_benefit="", risks="", impact_analysis="",
            implementation_approach="", plan=plan,
        ))
        mem.store_approval_request(ApprovalRequest(
            request_id="APPR-001", proposal_id="PROP-001",
            title="Test", description="", rationale="",
            risks="", expected_benefit="",
        ))

        summary = mem.summary()
        assert summary["observation_count"] == 1
        assert summary["proposal_count"] == 1
        assert summary["approval_request_count"] == 1
        assert summary["pending_approvals"] == 1

    def test_clear(self):
        mem = EvolutionMemory()
        mem.store_observation(Observation(
            category=ObservationCategory.RUNTIME_METRICS,
            metric_name="test", value=1,
        ))
        assert mem.observation_count == 1
        mem.clear()
        assert mem.observation_count == 0
        assert mem.proposal_count == 0
        assert mem.approval_request_count == 0
        assert mem.record_count == 0