"""
Phase 11.1 — Evolution CLI Commands Tests.

Tests that the CLI presentation layer correctly formats output and
delegates to EvolutionExecutionEngine.

CLI commands are tested with real engines.
Only input argument parsing is simulated via simple args objects.
"""

from unittest.mock import MagicMock

import pytest

from atlas.evolution.execution_engine import EvolutionExecutionEngine
from atlas.evolution.models import (
    ExecutionResult,
    ImprovementPlan,
    ImprovementPriority,
    EvolutionProposal,
    ProposalStatus,
)
from atlas.cli.evolution_commands import (
    cmd_proposals_list,
    cmd_proposals_show,
    cmd_proposals_approve,
    cmd_proposals_reject,
    cmd_proposals_defer,
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
        summary="A test proposal for testing purposes",
        rationale="This change is needed for testing.",
        expected_benefit="Better testability.",
        risks="Low risk.",
        impact_analysis="Affects test components.",
        implementation_approach="1. Test. 2. Verify.",
        plan=plan,
        status=status,
    )


class Args:
    """Simulate CLI argument namespace."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# Test: cmd_proposals_list
# ---------------------------------------------------------------------------

class TestCmdProposalsList:

    def test_list_empty(self):
        """list with no proposals returns 'No proposals found'."""
        engine = EvolutionExecutionEngine(evolution_memory=MagicMock())
        engine.list_proposals = MagicMock(return_value=[])

        output = cmd_proposals_list(engine, Args())

        assert "No proposals found" in output

    def test_list_pending_empty(self):
        """list --pending with no pending proposals returns message."""
        engine = EvolutionExecutionEngine(evolution_memory=MagicMock())
        engine.list_proposals = MagicMock(return_value=[])

        output = cmd_proposals_list(engine, Args(pending=True))

        assert "No pending proposals" in output

    def test_list_with_proposals(self):
        """list returns formatted proposal lines."""
        proposal = make_proposal()
        engine = EvolutionExecutionEngine(evolution_memory=MagicMock())
        engine.list_proposals = MagicMock(return_value=[proposal])

        output = cmd_proposals_list(engine, Args(pending=False))

        assert "PROP-001" in output
        assert "Test Proposal" in output
        assert "Found 1 proposal(s)" in output

    def test_list_pending_only(self):
        """list --pending passes pending_only=True to engine."""
        engine = EvolutionExecutionEngine(evolution_memory=MagicMock())
        engine.list_proposals = MagicMock(return_value=[])

        cmd_proposals_list(engine, Args(pending=True))

        engine.list_proposals.assert_called_with(pending_only=True)


# ---------------------------------------------------------------------------
# Test: cmd_proposals_show
# ---------------------------------------------------------------------------

class TestCmdProposalsShow:

    def test_show_no_id(self):
        """show without proposal_id returns error."""
        engine = MagicMock()
        output = cmd_proposals_show(engine, Args(proposal_id=""))
        assert "proposal_id is required" in output

    def test_show_not_found(self):
        """show with unknown proposal_id returns not found."""
        engine = EvolutionExecutionEngine(evolution_memory=MagicMock())
        engine.get_proposal = MagicMock(return_value=None)

        output = cmd_proposals_show(engine, Args(proposal_id="PROP-999"))

        assert "not found" in output

    def test_show_displays_details(self):
        """show displays full proposal details."""
        proposal = make_proposal()
        engine = EvolutionExecutionEngine(evolution_memory=MagicMock())
        engine.get_proposal = MagicMock(return_value=proposal)

        output = cmd_proposals_show(engine, Args(proposal_id="PROP-001"))

        assert "PROP-001" in output
        assert "Test Proposal" in output
        assert "Summary:" in output
        assert "Rationale:" in output
        assert "Risks:" in output
        assert "Impact Analysis:" in output
        assert "Implementation Approach:" in output

    def test_show_displays_approved_at(self):
        """show displays approved_at if present."""
        from datetime import datetime
        proposal = make_proposal(status=ProposalStatus.APPROVED)
        proposal.approved_at = datetime(2026, 7, 28, 12, 0, 0)
        engine = EvolutionExecutionEngine(evolution_memory=MagicMock())
        engine.get_proposal = MagicMock(return_value=proposal)

        output = cmd_proposals_show(engine, Args(proposal_id="PROP-001"))

        assert "Approved:" in output
        assert "2026-07-28" in output

    def test_show_displays_rejection(self):
        """show displays rejection_reason if present."""
        proposal = make_proposal(status=ProposalStatus.REJECTED)
        proposal.rejection_reason = "Out of scope"
        engine = EvolutionExecutionEngine(evolution_memory=MagicMock())
        engine.get_proposal = MagicMock(return_value=proposal)

        output = cmd_proposals_show(engine, Args(proposal_id="PROP-001"))

        assert "Rejection Reason" in output
        assert "Out of scope" in output


# ---------------------------------------------------------------------------
# Test: cmd_proposals_approve
# ---------------------------------------------------------------------------

class TestCmdProposalsApprove:

    def test_approve_no_id(self):
        """approve without proposal_id returns error."""
        engine = MagicMock()
        output = cmd_proposals_approve(engine, Args(proposal_id="", message=""))
        assert "proposal_id is required" in output

    def test_approve_success(self):
        """approve returns success message with record ID."""
        engine = EvolutionExecutionEngine(evolution_memory=MagicMock())
        engine.approve_proposal_by_id = MagicMock(return_value=ExecutionResult(
            success=True,
            proposal_id="PROP-001",
            status=ProposalStatus.IMPLEMENTED.name,
            record_id="EVR-20260728-0001",
        ))

        output = cmd_proposals_approve(engine, Args(
            proposal_id="PROP-001", message="Looks good",
        ))

        assert "PROP-001" in output
        assert "approved and executed" in output
        assert "EVR-20260728-0001" in output

    def test_approve_with_tracked_goal(self):
        """approve displays tracked goal ID when present."""
        engine = EvolutionExecutionEngine(evolution_memory=MagicMock())
        engine.approve_proposal_by_id = MagicMock(return_value=ExecutionResult(
            success=True,
            proposal_id="PROP-001",
            status=ProposalStatus.IMPLEMENTED.name,
            record_id="EVR-0001",
            tracked_goal_id="TRK-001",
        ))

        output = cmd_proposals_approve(engine, Args(
            proposal_id="PROP-001", message="",
        ))

        assert "TRK-001" in output

    def test_approve_failure(self):
        """approve failure returns error message."""
        engine = EvolutionExecutionEngine(evolution_memory=MagicMock())
        engine.approve_proposal_by_id = MagicMock(return_value=ExecutionResult(
            success=False,
            proposal_id="PROP-001",
            error="Proposal not found.",
        ))

        output = cmd_proposals_approve(engine, Args(
            proposal_id="PROP-001", message="",
        ))

        assert "Failed" in output
        assert "Proposal not found" in output

    def test_approve_passes_comment(self):
        """approve passes the message to the engine."""
        engine = EvolutionExecutionEngine(evolution_memory=MagicMock())
        engine.approve_proposal_by_id = MagicMock(return_value=ExecutionResult(
            success=True,
            proposal_id="PROP-001",
            status=ProposalStatus.IMPLEMENTED.name,
        ))

        cmd_proposals_approve(engine, Args(
            proposal_id="PROP-001", message="Well done",
        ))

        engine.approve_proposal_by_id.assert_called_with(
            proposal_id="PROP-001",
            comment="Well done",
        )


# ---------------------------------------------------------------------------
# Test: cmd_proposals_reject
# ---------------------------------------------------------------------------

class TestCmdProposalsReject:

    def test_reject_no_id(self):
        """reject without proposal_id returns error."""
        engine = MagicMock()
        output = cmd_proposals_reject(engine, Args(proposal_id="", reason=""))
        assert "proposal_id is required" in output

    def test_reject_no_reason(self):
        """reject without reason returns error."""
        engine = MagicMock()
        output = cmd_proposals_reject(engine, Args(
            proposal_id="PROP-001", reason="",
        ))
        assert "rejection reason is required" in output

    def test_reject_success(self):
        """reject returns success message."""
        engine = EvolutionExecutionEngine(evolution_memory=MagicMock())
        engine.reject_proposal_by_id = MagicMock(return_value=ExecutionResult(
            success=True,
            proposal_id="PROP-001",
            status=ProposalStatus.REJECTED.name,
        ))

        output = cmd_proposals_reject(engine, Args(
            proposal_id="PROP-001", reason="Not needed",
        ))

        assert "PROP-001" in output
        assert "rejected" in output

    def test_reject_failure(self):
        """reject failure returns error message."""
        engine = EvolutionExecutionEngine(evolution_memory=MagicMock())
        engine.reject_proposal_by_id = MagicMock(return_value=ExecutionResult(
            success=False,
            proposal_id="PROP-001",
            error="Proposal already approved.",
        ))

        output = cmd_proposals_reject(engine, Args(
            proposal_id="PROP-001", reason="Reason",
        ))

        assert "Failed" in output


# ---------------------------------------------------------------------------
# Test: cmd_proposals_defer
# ---------------------------------------------------------------------------

class TestCmdProposalsDefer:

    def test_defer_no_id(self):
        """defer without proposal_id returns error."""
        engine = MagicMock()
        output = cmd_proposals_defer(engine, Args(proposal_id="", reason=""))
        assert "proposal_id is required" in output

    def test_defer_success(self):
        """defer returns success message."""
        engine = EvolutionExecutionEngine(evolution_memory=MagicMock())
        engine.defer_proposal_by_id = MagicMock(return_value=ExecutionResult(
            success=True,
            proposal_id="PROP-001",
            status=ProposalStatus.DEFERRED.name,
        ))

        output = cmd_proposals_defer(engine, Args(
            proposal_id="PROP-001", reason="Later",
        ))

        assert "PROP-001" in output
        assert "deferred" in output

    def test_defer_failure(self):
        """defer failure returns error message."""
        engine = EvolutionExecutionEngine(evolution_memory=MagicMock())
        engine.defer_proposal_by_id = MagicMock(return_value=ExecutionResult(
            success=False,
            proposal_id="PROP-001",
            error="Proposal already approved.",
        ))

        output = cmd_proposals_defer(engine, Args(
            proposal_id="PROP-001", reason="",
        ))

        assert "Failed" in output


# ---------------------------------------------------------------------------
# Test: Architecture boundary — CLI does not call subcomponents directly
# ---------------------------------------------------------------------------

class TestArchitectureBoundary:

    def test_cli_does_not_call_approval_manager(self):
        """CLI commands never call ApprovalManager methods directly."""
        import atlas.cli.evolution_commands as commands
        source = open(commands.__file__).read()

        # Module-level docstring may mention it; function bodies must not.
        assert "approval_manager." not in source
        assert "ApprovalManager." not in source

    def test_cli_does_not_call_evolution_memory(self):
        """CLI commands never call EvolutionMemory methods directly."""
        import atlas.cli.evolution_commands as commands
        source = open(commands.__file__).read()

        assert "evolution_memory" not in source
        assert "store_" not in source
        assert "get_proposal" not in source.split("def ")[0]

    def test_cli_does_not_call_outcome_tracker(self):
        """CLI commands never call OutcomeTracker methods directly."""
        import atlas.cli.evolution_commands as commands
        source = open(commands.__file__).read()

        assert "outcome_tracker" not in source
        assert "track_recommendation" not in source
        assert "evaluate_outcomes" not in source
