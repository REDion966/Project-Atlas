"""Post-Core F8 — Evolution Audit & Proposal Visibility.

Verifies the operator-inspectable audit surface added on top of the
existing evolution architecture:

  - EvolutionExecutionEngine.get_proposal_audit(): deterministic,
    read-only audit projection combining the proposal's own lifecycle
    fields, the current approval decision, and the F7 execution outcome
    (EvolutionRecord metadata).
  - cmd_proposals_audit(): stable, human-readable CLI output.
  - CLI `proposals list|show|audit` wiring (read-only).

No new persistence, no new models, no governance changes. Inspection is
read-only and must never imply execution authority.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

from atlas.cli.evolution_commands import (
    cmd_proposals_audit,
    cmd_proposals_list,
    cmd_proposals_show,
)
from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.execution_engine import EvolutionExecutionEngine
from atlas.evolution.models import (
    ApprovalDecision,
    ApprovalRequest,
    EvolutionProposal,
    EvolutionRecord,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def make_plan() -> ImprovementPlan:
    return ImprovementPlan(
        plan_id="IMP-001",
        title="Test Plan",
        description="A test improvement plan",
        priority=ImprovementPriority.LOW,
    )


def make_proposal(
    proposal_id: str = "PROP-001",
    status: ProposalStatus = ProposalStatus.PENDING_APPROVAL,
) -> EvolutionProposal:
    return EvolutionProposal(
        proposal_id=proposal_id,
        title="Test Proposal",
        summary="A test proposal for testing",
        rationale="Testing rationale.",
        expected_benefit="Better testability.",
        risks="Low risk.",
        impact_analysis="Affects test components.",
        implementation_approach="1. Test. 2. Verify.",
        plan=make_plan(),
        status=status,
    )


def make_request(
    proposal_id: str = "PROP-001",
    decision: ApprovalDecision = ApprovalDecision.PENDING,
) -> ApprovalRequest:
    return ApprovalRequest(
        request_id=f"APPR-{proposal_id}",
        proposal_id=proposal_id,
        title="Test Approval",
        description="Test description",
        rationale="Test rationale",
        risks="Test risks",
        expected_benefit="Test benefit",
        decision=decision,
    )


def make_execution_record(
    proposal_id: str,
    success: bool = True,
    error: str = "",
    tracked_goal_id: str = "",
) -> EvolutionRecord:
    return EvolutionRecord(
        record_id=f"EVR-{proposal_id}",
        event_type="execution",
        description="execution",
        related_ids=[proposal_id],
        metadata={
            "success": success,
            "error": error,
            "status": ProposalStatus.IMPLEMENTED.name if success else ProposalStatus.DRAFT.name,
            "tracked_goal_id": tracked_goal_id,
        },
    )


def make_engine(
    proposal: EvolutionProposal | None = None,
    request: ApprovalRequest | None = None,
    record: EvolutionRecord | None = None,
) -> EvolutionExecutionEngine:
    memory = EvolutionMemory()
    engine = EvolutionExecutionEngine(
        approval_manager=ApprovalManager(),
        evolution_memory=memory,
    )
    if proposal is not None:
        memory.store_proposal(proposal)
    if request is not None:
        memory.store_approval_request(request)
    if record is not None:
        memory.store_record(record)
    return engine


class Args:
    """Simulate CLI argument namespace."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# 1-2. Unknown / empty
# ---------------------------------------------------------------------------


class TestAuditUnknown:
    def test_unknown_proposal_returns_none(self):
        engine = make_engine()
        assert engine.get_proposal_audit("NONEXISTENT") is None

    def test_audit_requires_proposal_id(self):
        assert "proposal_id is required" in cmd_proposals_audit(make_engine(), Args(proposal_id=""))

    def test_audit_unknown_proposal(self):
        assert "not found" in cmd_proposals_audit(make_engine(), Args(proposal_id="NOPE"))


# ---------------------------------------------------------------------------
# 3-6. list: empty / multiple / ordering / status visibility
# ---------------------------------------------------------------------------


class TestProposalList:
    def test_empty_list(self):
        engine = make_engine()
        assert engine.list_proposals() == []
        assert "No proposals found." in cmd_proposals_list(engine, Args(pending=False))

    def test_multiple_proposals_ordered(self):
        memory = EvolutionMemory()
        engine = EvolutionExecutionEngine(
            approval_manager=ApprovalManager(),
            evolution_memory=memory,
        )
        for pid in ("PROP-B", "PROP-A", "PROP-C"):
            memory.store_proposal(make_proposal(proposal_id=pid))

        assert [p.proposal_id for p in engine.list_proposals()] == ["PROP-C", "PROP-A", "PROP-B"]

        output = cmd_proposals_list(engine, Args(pending=False))
        assert "Found 3 proposal(s)" in output
        assert "PROP-A" in output
        assert "Status: PENDING_APPROVAL" in output


# ---------------------------------------------------------------------------
# 7. show
# ---------------------------------------------------------------------------


class TestProposalShow:
    def test_show_proposal(self):
        engine = make_engine(proposal=make_proposal())
        output = cmd_proposals_show(engine, Args(proposal_id="PROP-001"))
        assert "Proposal: PROP-001" in output
        assert "Title: Test Proposal" in output

    def test_show_unknown(self):
        assert "not found" in cmd_proposals_show(make_engine(), Args(proposal_id="NOPE"))


# ---------------------------------------------------------------------------
# 8-12. audit: lifecycle / approval / execution / failure / linkage
# ---------------------------------------------------------------------------


class TestAuditLifecycle:
    def test_audit_approval_visibility(self):
        engine = make_engine(
            proposal=make_proposal(),
            request=make_request(decision=ApprovalDecision.APPROVED),
        )
        audit = engine.get_proposal_audit("PROP-001")
        assert audit is not None
        assert audit["status"] == "PENDING_APPROVAL"
        assert audit["approval"]["decision"] == "APPROVED"

    def test_audit_execution_visibility(self):
        engine = make_engine(
            proposal=make_proposal(),
            record=make_execution_record("PROP-001", tracked_goal_id="TRK-001"),
        )
        audit = engine.get_proposal_audit("PROP-001")
        assert audit["execution"]["success"] is True
        assert audit["execution"]["record_id"] == "EVR-PROP-001"
        assert audit["execution"]["tracked_goal_id"] == "TRK-001"

    def test_audit_no_approval_no_execution(self):
        audit = make_engine(proposal=make_proposal()).get_proposal_audit("PROP-001")
        assert audit["approval"] is None
        assert audit["execution"] is None

    def test_failed_execution_visible_in_audit(self):
        engine = make_engine(
            proposal=make_proposal(status=ProposalStatus.DRAFT),
            record=make_execution_record("PROP-001", success=False, error="must be APPROVED"),
        )
        audit = engine.get_proposal_audit("PROP-001")
        assert audit["execution"]["success"] is False
        assert "must be APPROVED" in audit["execution"]["error"]

    def test_audit_output_shows_failure(self):
        engine = make_engine(
            proposal=make_proposal(status=ProposalStatus.DRAFT),
            record=make_execution_record("PROP-001", success=False, error="refused by governance"),
        )
        output = cmd_proposals_audit(engine, Args(proposal_id="PROP-001"))
        assert "Execution: Failure" in output
        assert "Execution Error: refused by governance" in output

    def test_audit_output_shows_success_linkage(self):
        engine = make_engine(
            proposal=make_proposal(),
            request=make_request(decision=ApprovalDecision.APPROVED),
            record=make_execution_record("PROP-001", tracked_goal_id="TRK-001"),
        )
        output = cmd_proposals_audit(engine, Args(proposal_id="PROP-001"))
        assert "Execution: Success" in output
        assert "Tracked Goal: TRK-001" in output
        assert "Approval Decision: APPROVED" in output

    def test_audit_output_not_executed(self):
        output = cmd_proposals_audit(
            make_engine(proposal=make_proposal()),
            Args(proposal_id="PROP-001"),
        )
        assert "Execution: (not yet executed)" in output


# ---------------------------------------------------------------------------
# 14. determinism
# ---------------------------------------------------------------------------


class TestAuditDeterminism:
    def test_audit_deterministic(self):
        engine = make_engine(
            proposal=make_proposal(),
            request=make_request(decision=ApprovalDecision.APPROVED),
            record=make_execution_record("PROP-001", success=True, tracked_goal_id="TRK-001"),
        )
        assert engine.get_proposal_audit("PROP-001") == engine.get_proposal_audit("PROP-001")

    def test_timestamps_formatted_stably(self):
        assert EvolutionExecutionEngine._format_timestamp(None) == ""
        assert (
            EvolutionExecutionEngine._format_timestamp(datetime(2026, 8, 1, 12, 0, 0))
            == "2026-08-01T12:00:00"
        )


# ---------------------------------------------------------------------------
# 15. read-only: never mutates / never executes / never touches governance
# ---------------------------------------------------------------------------


class TestAuditReadOnly:
    def test_audit_does_not_mutate_proposal(self):
        proposal = make_proposal()
        engine = make_engine(
            proposal=proposal,
            request=make_request(),
            record=make_execution_record("PROP-001"),
        )
        before_status = proposal.status
        before_metadata = dict(proposal.metadata)

        engine.get_proposal_audit("PROP-001")

        assert proposal.status == before_status
        assert proposal.metadata == before_metadata
        assert "executed_at" not in proposal.metadata

    def test_audit_does_not_execute(self):
        engine = make_engine(proposal=make_proposal(status=ProposalStatus.DRAFT))
        spy = MagicMock(wraps=engine.approve_proposal_by_id)
        engine.approve_proposal_by_id = spy  # type: ignore[method-assign]

        engine.get_proposal_audit("PROP-001")

        spy.assert_not_called()

    def test_audit_does_not_touch_governance(self):
        engine = make_engine(
            proposal=make_proposal(),
            request=make_request(),
            record=make_execution_record("PROP-001"),
        )
        with patch.object(
            engine, "_find_approval_request", wraps=engine._find_approval_request
        ) as spy:
            engine.get_proposal_audit("PROP-001")
            spy.assert_called_once()


# ---------------------------------------------------------------------------
# 16. persistence/reload using existing storage
# ---------------------------------------------------------------------------


class TestAuditPersistence:
    def test_audit_survives_restore(self):
        import os
        import tempfile

        from atlas.storage.evolution_storage import SQLiteEvolutionStorage

        db_path = os.path.join(tempfile.gettempdir(), "test_evol_f8_audit.db")
        storage = SQLiteEvolutionStorage(db_path=db_path)
        storage.initialize()
        try:
            memory = EvolutionMemory(storage=storage)
            memory.restore()
            engine = EvolutionExecutionEngine(
                approval_manager=ApprovalManager(),
                evolution_memory=memory,
            )
            memory.store_proposal(make_proposal())
            memory.store_approval_request(make_request(decision=ApprovalDecision.APPROVED))
            memory.store_record(make_execution_record("PROP-001", tracked_goal_id="TRK-001"))

            memory2 = EvolutionMemory(storage=storage)
            memory2.restore()
            engine2 = EvolutionExecutionEngine(
                approval_manager=ApprovalManager(),
                evolution_memory=memory2,
            )
            audit = engine2.get_proposal_audit("PROP-001")
            assert audit is not None
            assert audit["approval"]["decision"] == "APPROVED"
            assert audit["execution"]["tracked_goal_id"] == "TRK-001"
        finally:
            storage.clear_all()
            storage.close()
            try:
                os.remove(db_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# 17. CLI parser + dispatch integration
# ---------------------------------------------------------------------------


class TestCLIDispatch:
    def test_proposals_subcommand_registered(self):
        import atlas.cli.main as cli_main

        source = open(cli_main.__file__).read()
        assert '"proposals"' in source
        assert '"audit"' in source
        assert "_run_proposals(args)" in source

    def test_dispatch_routes_audit_to_cmd(self):
        """_run_proposals('audit') calls cmd_proposals_audit with the engine."""
        import atlas.cli.evolution_commands as ev_cmds
        import atlas.cli.main as cli_main

        with patch.object(ev_cmds, "cmd_proposals_audit", return_value="audit-output") as mock_audit, patch(
            "atlas.kernel.atlas.Atlas"
        ) as mock_atlas:
            engine = make_engine(proposal=make_proposal())
            mock_atlas.return_value.execution_engine = engine

            args = Args(action="audit", proposal_id="PROP-001", pending=False)
            cli_main._run_proposals(args)

            mock_audit.assert_called_once()
            passed_engine, passed_args = mock_audit.call_args[0]
            assert passed_engine is engine
            assert passed_args.proposal_id == "PROP-001"
