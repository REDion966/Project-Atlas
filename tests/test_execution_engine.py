"""
Phase 11.0 — EvolutionExecutionEngine Tests.

Tests that the EvolutionExecutionEngine correctly orchestrates the
proposal approval lifecycle at ADMINISTRATIVE level (record-keeping only).

Pure logic tests — no infrastructure dependencies.
"""

from unittest.mock import MagicMock

import pytest

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.execution_engine import EvolutionExecutionEngine
from atlas.evolution.models import (
    ApprovalDecision,
    ApprovalRequest,
    EvolutionProposal,
    ExecutionLevel,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_proposal(
    proposal_id="PROP-001",
    status=ProposalStatus.PENDING_APPROVAL,
):
    """Create a test EvolutionProposal."""
    plan = ImprovementPlan(
        plan_id="IMP-001",
        title="Test Plan",
        description="A test improvement plan",
        priority=ImprovementPriority.LOW,
    )
    return EvolutionProposal(
        proposal_id=proposal_id,
        title="Test Proposal",
        summary="A test proposal for testing",
        rationale="This change is needed for testing.",
        expected_benefit="Better testability.",
        risks="Low risk.",
        impact_analysis="Affects test components.",
        implementation_approach="1. Test. 2. Verify.",
        plan=plan,
        status=status,
    )


def make_approval_request(proposal_id="PROP-001"):
    """Create a test ApprovalRequest linked to a proposal."""
    return ApprovalRequest(
        request_id="APPR-001",
        proposal_id=proposal_id,
        title="Test Approval",
        description="Test description",
        rationale="Test rationale",
        risks="Test risks",
        expected_benefit="Test benefit",
    )


def make_engine(
    approval_manager=None,
    evolution_memory=None,
    outcome_tracker=None,
    execution_level=ExecutionLevel.ADMINISTRATIVE,
):
    """Create an EvolutionExecutionEngine with test defaults."""
    return EvolutionExecutionEngine(
        approval_manager=approval_manager or ApprovalManager(),
        evolution_memory=evolution_memory or EvolutionMemory(),
        outcome_tracker=outcome_tracker,
        execution_level=execution_level,
    )


# ---------------------------------------------------------------------------
# Test: Engine construction and defaults
# ---------------------------------------------------------------------------

class TestEngineConstruction:

    def test_default_execution_level(self):
        """Engine defaults to ADMINISTRATIVE level."""
        engine = EvolutionExecutionEngine()
        assert engine.execution_level == ExecutionLevel.ADMINISTRATIVE

    def test_custom_execution_level(self):
        """Engine accepts custom execution level."""
        engine = EvolutionExecutionEngine(
            execution_level=ExecutionLevel.SELF_CONFIG,
        )
        assert engine.execution_level == ExecutionLevel.SELF_CONFIG

    def test_properties_reflect_injected_deps(self):
        """Properties return the injected dependencies."""
        am = ApprovalManager()
        mem = EvolutionMemory()
        tracker = MagicMock()
        engine = EvolutionExecutionEngine(
            approval_manager=am,
            evolution_memory=mem,
            outcome_tracker=tracker,
        )
        assert engine.approval_manager is am
        assert engine.evolution_memory is mem
        assert engine.outcome_tracker is tracker


# ---------------------------------------------------------------------------
# Test: Approve proposal
# ---------------------------------------------------------------------------

class TestApproveProposal:

    def test_approve_proposal_success(self):
        """
        Approving a pending proposal updates its status to APPROVED
        and returns a successful ExecutionResult with a record_id.
        """
        proposal = make_proposal()
        request = make_approval_request()
        memory = EvolutionMemory()
        engine = make_engine(evolution_memory=memory)

        result = engine.approve_proposal(proposal, request)

        assert result.success is True
        assert result.proposal_id == "PROP-001"
        assert result.status == ProposalStatus.IMPLEMENTED.name
        assert result.record_id.startswith("EVR-")
        assert proposal.status == ProposalStatus.IMPLEMENTED
        assert request.decision == ApprovalDecision.APPROVED

    def test_approve_proposal_stores_execution_record(self):
        """Approving a proposal stores an EvolutionRecord in memory."""
        proposal = make_proposal()
        request = make_approval_request()
        memory = EvolutionMemory()
        engine = make_engine(evolution_memory=memory)

        engine.approve_proposal(proposal, request)

        assert memory.record_count == 1
        record = memory.get_records(1)[0]
        assert record.event_type == "execution"
        assert record.related_ids == ["PROP-001"]

    def test_approve_proposal_without_approval_manager(self):
        """Missing ApprovalManager returns error ExecutionResult."""
        engine = EvolutionExecutionEngine()
        proposal = make_proposal()
        request = make_approval_request()

        result = engine.approve_proposal(proposal, request)

        assert result.success is False
        assert "ApprovalManager" in result.error

    def test_approve_proposal_tracks_outcome(self):
        """
        When outcome_tracker is provided, approve_proposal creates a
        TrackedGoal via track_recommendation.
        """
        proposal = make_proposal()
        request = make_approval_request()
        tracker = MagicMock()
        tracker.track_recommendation.return_value.goal_id = "TRK-001"
        engine = make_engine(outcome_tracker=tracker)

        result = engine.approve_proposal(proposal, request)

        assert result.success is True
        assert result.tracked_goal_id == "TRK-001"
        tracker.track_recommendation.assert_called_once()

    def test_approve_twice_fails(self):
        """Approving an already-approved proposal returns failure."""
        proposal = make_proposal()
        request = make_approval_request()
        engine = make_engine()

        engine.approve_proposal(proposal, request)
        result2 = engine.approve_proposal(proposal, request)

        assert result2.success is False
        assert result2.error != ""


# ---------------------------------------------------------------------------
# Test: Execute proposal (direct)
# ---------------------------------------------------------------------------

class TestExecute:

    def test_execute_approved_proposal(self):
        """Executing an APPROVED proposal succeeds."""
        proposal = make_proposal(status=ProposalStatus.APPROVED)
        memory = EvolutionMemory()
        engine = make_engine(evolution_memory=memory)

        result = engine.execute(proposal)

        assert result.success is True
        assert result.status == ProposalStatus.IMPLEMENTED.name
        assert result.record_id.startswith("EVR-")
        assert proposal.status == ProposalStatus.IMPLEMENTED

    def test_execute_non_approved_fails(self):
        """Executing a non-APPROVED proposal returns error."""
        proposal = make_proposal(status=ProposalStatus.PENDING_APPROVAL)
        engine = make_engine()

        result = engine.execute(proposal)

        assert result.success is False
        assert "must be APPROVED" in result.error

    def test_execute_draft_fails(self):
        """Executing a DRAFT proposal returns error."""
        proposal = make_proposal(status=ProposalStatus.DRAFT)
        engine = make_engine()

        result = engine.execute(proposal)

        assert result.success is False

    def test_execute_stores_record(self):
        """Execute stores an EvolutionRecord with correct metadata."""
        proposal = make_proposal(status=ProposalStatus.APPROVED)
        memory = EvolutionMemory()
        engine = make_engine(evolution_memory=memory)

        engine.execute(proposal)

        assert memory.record_count == 1
        record = memory.get_records(1)[0]
        assert record.event_type == "execution"
        assert record.related_ids == [proposal.proposal_id]
        assert "execution_level" in record.metadata
        assert record.metadata["execution_level"] == "ADMINISTRATIVE"

    def test_execute_without_memory_succeeds(self):
        """Execute works without EvolutionMemory (no record stored)."""
        proposal = make_proposal(status=ProposalStatus.APPROVED)
        engine = EvolutionExecutionEngine(
            approval_manager=ApprovalManager(),
        )

        result = engine.execute(proposal)

        assert result.success is True
        assert result.record_id.startswith("EVR-")

    def test_execute_tracks_outcome(self):
        """Execute creates a TrackedGoal via outcome tracker."""
        proposal = make_proposal(status=ProposalStatus.APPROVED)
        tracker = MagicMock()
        tracker.track_recommendation.return_value.goal_id = "TRK-001"
        engine = make_engine(outcome_tracker=tracker)

        result = engine.execute(proposal)

        assert result.success is True
        assert result.tracked_goal_id == "TRK-001"

    def test_execute_proposal_metadata_updated(self):
        """Execute adds executed_at timestamp to proposal metadata."""
        proposal = make_proposal(status=ProposalStatus.APPROVED)
        engine = make_engine()

        engine.execute(proposal)

        assert "executed_at" in proposal.metadata
        assert isinstance(proposal.metadata["executed_at"], str)


# ---------------------------------------------------------------------------
# Test: Reject proposal
# ---------------------------------------------------------------------------

class TestRejectProposal:

    def test_reject_proposal_success(self):
        """Rejecting a pending proposal sets status to REJECTED."""
        proposal = make_proposal()
        request = make_approval_request()
        engine = make_engine()

        result = engine.reject_proposal(proposal, request, reason="Not needed")

        assert result.success is True
        assert result.status == ProposalStatus.REJECTED.name
        assert proposal.status == ProposalStatus.REJECTED
        assert request.decision == ApprovalDecision.REJECTED

    def test_reject_proposal_stores_record(self):
        """Rejecting stores a rejection record in EvolutionMemory."""
        proposal = make_proposal()
        request = make_approval_request()
        memory = EvolutionMemory()
        engine = make_engine(evolution_memory=memory)

        engine.reject_proposal(proposal, request, reason="Not needed")

        assert memory.record_count == 1
        record = memory.get_records(1)[0]
        assert record.event_type == "rejection"

    def test_reject_without_reason_fails(self):
        """Rejecting without a reason returns error."""
        proposal = make_proposal()
        request = make_approval_request()
        engine = make_engine()

        result = engine.reject_proposal(proposal, request, reason="")

        assert result.success is False
        assert result.error != ""

    def test_reject_without_approval_manager(self):
        """Missing ApprovalManager returns error."""
        engine = EvolutionExecutionEngine()
        proposal = make_proposal()
        request = make_approval_request()

        result = engine.reject_proposal(proposal, request, reason="Reason")

        assert result.success is False


# ---------------------------------------------------------------------------
# Test: Defer proposal
# ---------------------------------------------------------------------------

class TestDeferProposal:

    def test_defer_proposal_success(self):
        """Deferring a pending proposal sets status to DEFERRED."""
        proposal = make_proposal()
        request = make_approval_request()
        engine = make_engine()

        result = engine.defer_proposal(proposal, request)

        assert result.success is True
        assert result.status == ProposalStatus.DEFERRED.name
        assert proposal.status == ProposalStatus.DEFERRED
        assert request.decision == ApprovalDecision.DEFERRED

    def test_defer_with_reason(self):
        """Deferring with a reason works."""
        proposal = make_proposal()
        request = make_approval_request()
        engine = make_engine()

        result = engine.defer_proposal(proposal, request, reason="Later")

        assert result.success is True
        assert request.decision_comment == "Later"

    def test_defer_without_approval_manager(self):
        """Missing ApprovalManager returns error."""
        engine = EvolutionExecutionEngine()
        proposal = make_proposal()
        request = make_approval_request()

        result = engine.defer_proposal(proposal, request)

        assert result.success is False


# ---------------------------------------------------------------------------
# Test: Graceful degradation
# ---------------------------------------------------------------------------

class TestGracefulDegradation:

    def test_execute_proposal_updates_status_without_memory(self):
        """Execute updates proposal status even without EvolutionMemory."""
        proposal = make_proposal(status=ProposalStatus.APPROVED)
        engine = EvolutionExecutionEngine(
            approval_manager=ApprovalManager(),
        )

        result = engine.execute(proposal)

        assert result.success is True
        assert proposal.status == ProposalStatus.IMPLEMENTED

    def test_execute_tracker_failure_does_not_block(self):
        """If OutcomeTracker raises, execution still succeeds."""
        proposal = make_proposal(status=ProposalStatus.APPROVED)
        tracker = MagicMock()
        tracker.track_recommendation.side_effect = RuntimeError("DB error")
        engine = make_engine(outcome_tracker=tracker)

        result = engine.execute(proposal)

        assert result.success is True
        assert result.tracked_goal_id == ""

    def test_approve_with_latest_experience_id(self):
        """approve_proposal passes latest_experience_id to tracker."""
        proposal = make_proposal()
        request = make_approval_request()
        tracker = MagicMock()
        tracker.track_recommendation.return_value.goal_id = "TRK-001"
        engine = make_engine(outcome_tracker=tracker)

        engine.approve_proposal(
            proposal, request,
            comment="Looks good",
            latest_experience_id="EXP-00000042",
        )

        tracker.track_recommendation.assert_called_once()
        kwargs = tracker.track_recommendation.call_args[1]
        assert kwargs.get("related_experience_id") == "EXP-00000042"
