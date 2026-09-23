"""Phase 13.2 — Persistent evolution state: evidence contract.

Validation result: the EXISTING ``EvolutionMemory`` + ``SQLiteEvolutionStorage``
already persist everything a later cycle needs (outcomes, insights, proposals,
approval requests). Phase 13 adds no second store: the continuity projection
reads the existing one.
"""

from __future__ import annotations

import ast
from pathlib import Path

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.evolution_continuity import (
    EvolutionOpportunityState,
    continuation_view,
    subject_history,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.models import (
    EvolutionInsight,
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
)
from tests.phase13_support import candidate, record_outcome, sqlite_memory

_MODULE = Path(__file__).resolve().parents[1] / "atlas/evolution/evolution_continuity.py"


class TestPhase132PersistentEvolutionState:
    def test_outcomes_survive_a_new_memory_instance(self, tmp_path):
        memory, storage = sqlite_memory(tmp_path)
        record_outcome(
            memory,
            cycle_id="SEV-000001",
            subject="cap.persisted",
            terminal="verification_failed",
            outcome_kind="verification_failure",
            proposal_id="DEV-1",
        )
        memory.store_insight(
            EvolutionInsight(
                insight_id="INS-1",
                proposal_id="DEV-1",
                execution_record_id="EVO-1",
                tracked_goal_id="",
                outcome="verification_failure",
                confidence=1.0,
                effectiveness_score=0.0,
                evidence_summary="verification did not pass",
                evidence_count=1,
                evidence_quality=1.0,
                regression_risk=0.0,
                proposal_title="cap.persisted",
                proposal_summary="verification_failure",
            )
        )
        storage.close()

        # A brand-new process boundary: fresh memory, same database.
        reopened, storage2 = sqlite_memory(tmp_path)
        try:
            reopened.restore()
            view = continuation_view(reopened)
            opportunity = view.for_subject("cap.persisted")
            assert opportunity is not None
            assert (
                opportunity.state is EvolutionOpportunityState.EVIDENCE_REQUIRED
            )
            assert opportunity.last_terminal == "verification_failed"
            assert reopened.get_insights(), "insight evidence was not restored"
            assert subject_history(reopened, "cap.persisted")
        finally:
            storage2.close()

    def test_proposals_and_approval_requests_are_durable(self, tmp_path):
        memory, storage = sqlite_memory(tmp_path)
        manager = ApprovalManager()
        proposal = EvolutionProposal(
            proposal_id="DEV-P13",
            title="t",
            summary="s",
            rationale="r",
            expected_benefit="b",
            risks="x",
            impact_analysis="i",
            implementation_approach="a",
            plan=ImprovementPlan(
                plan_id="PL-1",
                title="t",
                description="d",
                priority=ImprovementPriority.MEDIUM,
            ),
            status=ProposalStatus.DRAFT,
        )
        request = manager.create_approval_request(proposal)
        memory.store_proposal(proposal)
        memory.store_approval_request(request)
        storage.close()

        reopened, storage2 = sqlite_memory(tmp_path)
        try:
            reopened.restore()
            assert reopened.get_proposal("DEV-P13") is not None
            assert reopened.get_approval_request(request.request_id) is not None
            assert reopened.get_pending_approval_requests()
        finally:
            storage2.close()

    def test_continuity_reads_existing_storage_and_creates_no_new_one(self):
        tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for banned in ("sqlite3", "atlas.storage", "json", "pathlib"):
            assert banned not in imported, banned

    def test_unavailable_storage_degrades_to_memory_only(self):
        # The existing adapter's contract: an unusable backend must not break
        # the in-memory path the continuity view reads.
        memory = EvolutionMemory(storage=None)
        record_outcome(
            memory,
            cycle_id="SEV-000009",
            subject="cap.memory_only",
            terminal="preparation_failed",
            outcome_kind="unsuccessful_attempt",
        )
        assert (
            continuation_view(memory).for_subject("cap.memory_only").state
            is EvolutionOpportunityState.EVIDENCE_REQUIRED
        )

    def test_missing_memory_yields_no_fabricated_history(self):
        view = continuation_view(None)
        assert view.opportunities == ()
        assert view.may_attempt("cap.anything")[0] is True
        assert candidate("cap.anything")[0] is not None
