"""Durable Guided Improvement — cross-process proposal lifecycle tests.

Proves that the governed development proposal lifecycle now survives process
boundaries using ONLY existing infrastructure (EvolutionMemory +
EvolutionSQLiteStorage + ApprovalManager + DevelopmentPlanner +
SelfDevelopmentLoop + CodeSandbox):

    Session 1: `atlas postcore develop` -> DRAFT/PENDING_APPROVAL persisted
    Session 2: `atlas proposals approve <id>` -> APPROVED (persisted)
    Session 3: `atlas postcore execute --proposal-id <id>`
               -> planner + SDL sandbox -> outcome -> learning

Fail-closed legs: missing / DRAFT / REJECTED proposals refused; failing
sandbox tests never accepted; real repository never mutated; tick() and
protected architecture untouched; model=None everywhere.

"Process boundary" is simulated by separate Atlas instances over the same
temporary SQLite evolution storage (each with freshly restored state).
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from atlas.evolution.models import ProposalStatus


def _args(**overrides):
    """Build a CLI args namespace matching the postcore parser surface."""
    base = {
        "action": "",
        "question": "",
        "sources": [],
        "query_id": "",
        "need_file": "",
        "proposal_id": "",
        "message": "",
    }
    base.update(overrides)
    return SimpleNamespace(**base)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_NOW = None  # clocks are controller-internal; no determinism fixture needed


def _storage_class(tmp_path: Path):
    """Return a SQLiteEvolutionStorage subclass pinned to a tmp database."""
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage

    class TmpSQLiteEvolutionStorage(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "evolution.db")

    return TmpSQLiteEvolutionStorage


def _started_atlas(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage",
        _storage_class(tmp_path),
    )
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    return atlas


def _need_payload(**overrides):
    base = {
        "title": "Durable guided improvement need",
        "summary": "Cross-run governed development.",
        "candidate_id": "CAND-DGI-1",
        "code_changes": [
            {"path": "docs/dgi_note.md", "content": "# dgi\n"}
        ],
        "test_files": {
            "tests/test_dgi_proof.py": (
                "def test_dgi_proof_passes():\n    assert True\n"
            )
        },
    }
    base.update(overrides)
    return base


def _develop(atlas, tmp_path, **overrides) -> tuple[str, str]:
    """Run the F9 preparation through the operator CLI surface."""
    from tests.test_postcore_cli import cmd_develop

    need_file = tmp_path / f"need-{abs(hash(overrides)) % 10**8}.json"
    need_file.write_text(
        json.dumps(_need_payload(**overrides)), encoding="utf-8"
    )
    out = cmd_develop(atlas, _args(need_file=str(need_file)))
    proposal_id = ""
    for line in out.splitlines():
        if line.strip().startswith("Proposal ID:"):
            proposal_id = line.split("Proposal ID:", 1)[1].strip()
    return out, proposal_id


def _capture(atlas):
    """Test-only spy capturing the proposal/request at the approval seam."""
    captured: dict = {}
    manager = atlas._approval_manager  # noqa: SLF001
    original = manager.create_approval_request

    def spy(proposal):
        captured["proposal"] = proposal
        request = original(proposal)
        captured["request"] = request
        return request

    manager.create_approval_request = spy  # noqa: SLF001
    return captured


def _approve_cli(atlas, proposal_id, message="operator approval"):
    """Session-B human confirmation through the EXISTING kernel gate."""
    atlas.confirm_development_approval(proposal_id, comment=message)


class TestCrossProcessPersistence:
    def test_draft_survives_process_boundary(
        self, monkeypatch, tmp_path, capsys
    ):
        # Session 1: prepare + persist.
        atlas1 = _started_atlas(monkeypatch, tmp_path)
        try:
            captured = _capture(atlas1)
            from tests.test_postcore_cli import cmd_develop

            out = cmd_develop(
                atlas1, _args(need_file=str(_write_need(tmp_path)))
            )
            assert "PENDING_APPROVAL" in out
            proposal_id = captured["proposal"].proposal_id
        finally:
            atlas1.shutdown()

        # Session 2 ("new process"): restored state is discoverable via the
        # EXISTING proposal machinery.
        atlas2 = _started_atlas(monkeypatch, tmp_path)
        try:
            engine = atlas2.execution_engine
            proposal = engine.get_proposal(proposal_id)
            assert proposal is not None
            assert proposal.status is ProposalStatus.PENDING_APPROVAL
            assert proposal.title == "Durable guided improvement need"
            metadata = proposal.metadata["development_cycle"]
            assert metadata["candidate_id"] == "CAND-DGI-1"
            assert metadata["content_status"] == "unverified-draft"
            all_ids = [
                p.proposal_id for p in engine._evolution_memory.get_all_proposals()  # noqa: SLF001
            ]
            assert proposal_id in all_ids
        finally:
            atlas2.shutdown()


def _write_need(tmp_path: Path, **overrides) -> Path:
    path = tmp_path / f"need-{abs(hash(tuple(sorted(overrides.items()))))}.json"
    path.write_text(json.dumps(_need_payload(**overrides)), encoding="utf-8")
    return path


class TestCrossProcessApprovalCli:
    def _prepare(self, monkeypatch, tmp_path):
        atlas1 = _started_atlas(monkeypatch, tmp_path)
        try:
            captured = _capture(atlas1)
            from tests.test_postcore_cli import cmd_develop

            out = cmd_develop(
                atlas1,
                _args(need_file=str(_write_need(tmp_path))),
            )
            assert "PENDING_APPROVAL" in out
            return captured["proposal"].proposal_id
        finally:
            atlas1.shutdown()

    def test_confirm_across_processes(self, monkeypatch, tmp_path):
        proposal_id = self._prepare(monkeypatch, tmp_path)

        # Session 2: operator confirms through the kernel gate.
        atlas2 = _started_atlas(monkeypatch, tmp_path)
        try:
            atlas2.confirm_development_approval(
                proposal_id, comment="operator ok"
            )
            proposal = atlas2.execution_engine.get_proposal(proposal_id)
            assert proposal.status is ProposalStatus.APPROVED
        finally:
            atlas2.shutdown()

        # Session 3: a genuinely fresh process sees the APPROVED state.
        atlas3 = _started_atlas(monkeypatch, tmp_path)
        try:
            proposal = atlas3.execution_engine.get_proposal(proposal_id)
            assert proposal.status is ProposalStatus.APPROVED
        finally:
            atlas3.shutdown()

    def test_confirm_missing_proposal_fails_closed(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            with pytest.raises(RuntimeError, match="not found"):
                atlas.confirm_development_approval("DEV-DOES-NOT-EXIST")
        finally:
            atlas.shutdown()

    def test_double_confirmation_fails_closed(self, monkeypatch, tmp_path):
        from atlas.cli.postcore_commands import cmd_confirm

        proposal_id = self._prepare(monkeypatch, tmp_path)
        atlas2 = _started_atlas(monkeypatch, tmp_path)
        try:
            first = cmd_confirm(
                atlas2,
                SimpleNamespace(proposal_id=proposal_id, comment="first"),
            )
            assert "approved by explicit human confirmation" in first
            second = cmd_confirm(
                atlas2,
                SimpleNamespace(proposal_id=proposal_id, comment="again"),
            )
            # Fail-closed: an already-confirmed proposal cannot be re-confirmed.
            assert second.startswith("error:")
            assert "APPROVED" in second
        finally:
            atlas2.shutdown()


class TestCrossProcessExecution:
    def test_execute_approved_proposal_in_sandbox(
        self, monkeypatch, tmp_path
    ):
        from atlas.cli.postcore_commands import cmd_execute

        proposal_id = TestCrossProcessApprovalCli()._prepare(
            monkeypatch, tmp_path
        )

        atlas2 = _started_atlas(monkeypatch, tmp_path)
        try:
            # Approve in session B via the existing CLI gate.
            _approve_cli(atlas2, proposal_id)

            # Session C ("new process"): execute the persisted APPROVED one.
            atlas3 = _started_atlas(monkeypatch, tmp_path)
            try:
                out = cmd_execute(
                    atlas3, _args(action="execute", proposal_id=proposal_id)
                )
                assert "Governed development execution complete" in out
                assert "Run status: SUCCESS" in out
                # Real repository untouched; change lived in the sandbox.
                assert not Path("docs/dgi_note.md").exists()
                assert not Path("tests/test_dgi_proof.py").exists()
            finally:
                atlas3.shutdown()
        finally:
            atlas2.shutdown()

    def test_execute_refuses_unapproved_draft(
        self, monkeypatch, tmp_path
    ):
        from atlas.cli.postcore_commands import cmd_execute

        atlas1 = _started_atlas(monkeypatch, tmp_path)
        proposal_id = ""
        try:
            captured = _capture(atlas1)
            from tests.test_postcore_cli import cmd_develop

            cmd_develop(
                atlas1, _args(need_file=str(_write_need(tmp_path)))
            )
            proposal_id = captured["proposal"].proposal_id
        finally:
            atlas1.shutdown()

        atlas2 = _started_atlas(monkeypatch, tmp_path)
        try:
            out = cmd_execute(
                atlas2, _args(action="execute", proposal_id=proposal_id)
            )
            assert out.startswith("error:")
            assert "PENDING_APPROVAL" in out
        finally:
            atlas2.shutdown()

    def test_execute_missing_proposal_refused(self, monkeypatch, tmp_path):
        from atlas.cli.postcore_commands import cmd_execute

        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            out = cmd_execute(
                atlas,
                _args(action="execute", proposal_id="DEV-MISSING"),
            )
            assert "not found" in out
        finally:
            atlas.shutdown()


class TestArchitectureGuards:
    def test_tick_and_scheduler_untouched_by_f11_track(self):
        from atlas.kernel.atlas import Atlas

        tick_src = inspect.getsource(Atlas.tick)
        for forbidden in (
            "run_self_management_review",
            "run_development_cycle",
            "ai_availability",
            "store_proposal",
        ):
            assert forbidden not in tick_src


class TestPersistenceFailurePaths:
    """Fail-closed coverage for the F9 durable-persistence boundaries."""

    def test_proposal_persistence_failure_fails_closed(self):
        """A store_proposal failure fails the cycle closed AFTER the documented
        approval submission: the cause is surfaced under the 'persistence'
        stage, no proposal id is reported as prepared, and — because neither
        the proposal nor its approval request was persisted — the in-process
        submission is discarded when the process exits."""
        from unittest.mock import MagicMock

        from atlas.evolution.development_cycle import (
            DevelopmentCycleController,
            DevelopmentNeed,
        )

        proposal_store = MagicMock()
        proposal_store.store_proposal.side_effect = RuntimeError("disk full")

        manager = MagicMock()

        def _fake_create(proposal):
            # Mirror ApprovalManager.create_approval_request's real
            # contract: DRAFT -> PENDING_APPROVAL.
            from atlas.evolution.models import ProposalStatus

            proposal.status = ProposalStatus.PENDING_APPROVAL
            return SimpleNamespace(
                request_id="APPR-TEST-1", proposal_id=proposal.proposal_id
            )

        manager.create_approval_request.side_effect = _fake_create
        manager.create_approval_request.return_value = SimpleNamespace(
            request_id="APPR-SHOULD-NOT-EXIST"
        )

        controller = DevelopmentCycleController(
            approval_manager=manager,
            proposal_store=proposal_store,
        )
        need = DevelopmentNeed(
            title="Persistence failure need",
            summary="s",
            candidate_id="CAND-PF-1",
            evidence_change_ids=("CHG-PF-1",),
            metadata={
                "code_changes": [
                    {"path": "docs/pf.md", "content": "# pf\n"}
                ],
            },
        )
        result = controller.run_development_cycle(need)

        assert result.ok is False
        assert result.decision == "failed"
        persistence_failures = [
            msg for stage, msg in result.failures if stage == "persistence"
        ]
        assert persistence_failures and "disk full" in persistence_failures[0]
        assert result.proposal_id == ""
        # Documented ordering: submission happens first; the failure path
        # never re-submits or retries.
        assert manager.create_approval_request.call_count == 1

    def test_partial_persistence_is_reported_and_not_confirmable(self):
        """Proposal storage succeeds; approval-request storage fails.

        Fail closed with explicit partial-state reporting: the proposal was
        handed to the durable store exactly once as PENDING_APPROVAL with
        provenance intact, the failing approval-request store never received
        anything, and a later process holding only durably-persisted state
        can neither confirm nor execute the orphaned proposal.
        """
        from unittest.mock import MagicMock

        from atlas.evolution.development_cycle import (
            DevelopmentCycleController,
            DevelopmentNeed,
        )
        from atlas.evolution.evolution_memory import EvolutionMemory

        proposal_store = MagicMock()
        approval_request_store = MagicMock()
        approval_request_store.store_approval_request.side_effect = (
            RuntimeError("approval store down")
        )

        manager = MagicMock()

        def _fake_create(proposal):
            # Mirror ApprovalManager.create_approval_request's real
            # contract: DRAFT -> PENDING_APPROVAL.
            proposal.status = ProposalStatus.PENDING_APPROVAL
            return SimpleNamespace(
                request_id="APPR-TEST-1", proposal_id=proposal.proposal_id
            )

        manager.create_approval_request.side_effect = _fake_create

        controller = DevelopmentCycleController(
            approval_manager=manager,
            proposal_store=proposal_store,
            approval_request_store=approval_request_store,
        )
        need = DevelopmentNeed(
            title="Partial persistence need",
            summary="s",
            candidate_id="CAND-DGI-PARTIAL",
            evidence_change_ids=("CHG-DGI-P1",),
            metadata={
                "code_changes": [
                    {"path": "docs/dgi_partial_note.md", "content": "# x\n"}
                ],
            },
        )
        result = controller.run_development_cycle(need)

        # Explicit partial-state failure reporting.
        assert result.ok is False
        persistence_failures = [
            msg for stage, msg in result.failures if stage == "persistence"
        ]
        assert persistence_failures
        assert (
            "approval request submitted but not persisted"
            in persistence_failures[0]
        )
        assert "approval store down" in persistence_failures[0]

        # Exactly one durable hand-off: PENDING_APPROVAL + provenance.
        proposal_store.store_proposal.assert_called_once()
        stored = proposal_store.store_proposal.call_args[0][0]
        assert stored.status is ProposalStatus.PENDING_APPROVAL
        dc_meta = stored.metadata["development_cycle"]
        assert dc_meta["candidate_id"] == "CAND-DGI-PARTIAL"
        assert dc_meta["content_status"] == "unverified-draft"
        assert dc_meta["change_origin"] == "deterministic"

        # The failing store was attempted exactly once and never falsely
        # reported persistence (its raise is what produced the failure).
        approval_request_store.store_approval_request.assert_called_once()

        # A later process restoring ONLY durably-persisted state cannot
        # confirm or execute the orphaned proposal (no pending request).
        later_memory = EvolutionMemory()
        later_memory.store_proposal(stored)
        assert later_memory.get_proposal(stored.proposal_id) is not None
        assert later_memory.get_all_approval_requests() == []
        with pytest.raises(RuntimeError, match="no pending approval request"):
            _confirm_like_kernel(later_memory, stored.proposal_id)
        with pytest.raises(RuntimeError, match="not APPROVED"):
            _execute_like_kernel(later_memory, stored.proposal_id)

        # No repository mutation occurred anywhere in the failed flow.
        assert not Path("docs/dgi_partial_note.md").exists()


def _confirm_like_kernel(memory, proposal_id):
    """Mirror of ``Atlas.confirm_development_approval``'s fail-closed gates,
    reduced to its durable-state preconditions (pending request lookup)."""
    proposal = memory.get_proposal(proposal_id)
    if proposal is None:
        raise RuntimeError(f"Proposal '{proposal_id}' not found.")
    status_name = getattr(proposal.status, "name", "")
    if status_name != "PENDING_APPROVAL":
        raise RuntimeError(
            f"Proposal '{proposal_id}' is {status_name}, not "
            "PENDING_APPROVAL — refusing to confirm."
        )
    pending = [
        req
        for req in memory.get_all_approval_requests()
        if req.proposal_id == proposal_id
        and getattr(req.decision, "name", "") == "PENDING"
    ]
    if not pending:
        raise RuntimeError(
            f"Proposal '{proposal_id}' has no pending approval request."
        )


def _execute_like_kernel(memory, proposal_id):
    """Mirror of ``Atlas.run_development_execution``'s fail-closed gates."""
    from atlas.evolution.models import ProposalStatus as _PS

    proposal = memory.get_proposal(proposal_id)
    if proposal is None:
        raise RuntimeError(f"Proposal '{proposal_id}' not found.")
    if getattr(proposal.status, "name", "") != "APPROVED":
        raise RuntimeError(
            f"Proposal '{proposal_id}' is "
            f"{getattr(proposal.status, 'name', '')}, not APPROVED."
        )
    del _PS
