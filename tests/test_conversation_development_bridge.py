"""B3 — Conversational development bridge (kernel integration) tests.

Proves the conversational seam routes a DEVELOPMENT_REQUEST into the EXISTING
governed development preparation flow and STOPS at PENDING_APPROVAL:

  * ``Atlas.chat()`` reaches the development preparation flow.
  * Successful preparation (with an injected concrete change supplier) stops
    at PENDING_APPROVAL and never approves/executes/promotes.
  * The deterministic default supplier fails closed when no concrete
    ``code_changes`` exist (no fabricated code).
  * An under-specified request is stopped by clarification before any
    development work.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest

from tests.test_durable_guided_improvement import _storage_class


class _FakeAcquisition:
    """Duck-typed F8 acquisition result (no network)."""

    status = "ok"

    def to_dict(self):
        return {
            "acquisition_id": "ACQ-B3-000001",
            "status": "ok",
            "report_id": "report:b3",
            "sources": ("https://example.test/a",),
            "confidence": 0.8,
            "claim_count": 1,
        }


class _ConcreteSupplier:
    """Injected change supplier producing one concrete sandbox change.

    Mirrors the existing ``ChangeSupplier`` protocol; used only to prove the
    full conversational -> PENDING_APPROVAL path. Never wired by the kernel.
    """

    def supply_changes(self, need):
        from atlas.evolution.development_cycle import SuppliedChanges

        return SuppliedChanges(
            code_changes=(("docs/b3_bridge_note.md", "# b3\n"),),
            origin="deterministic",
        )


def _started_atlas(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage",
        _storage_class(tmp_path),
    )
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    return atlas


def _stub_research(atlas):
    """Replace the controller's F8 researcher to avoid any network access."""
    controller = atlas.development_controller
    controller._researcher = lambda **kwargs: _FakeAcquisition()  # noqa: SLF001


class TestConversationalDevelopmentRouting:
    def test_chat_fails_closed_without_concrete_changes(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _stub_research(atlas)
            message = atlas.chat("add a new capability to Atlas for scheduling")
        finally:
            atlas.shutdown()

        assert message.role == "assistant"
        # Deterministic supplier found no code_changes -> honest refusal.
        assert "FAILED" in message.content
        assert "supplier" in message.content
        assert "approved" not in message.content.lower()
        assert "executed" not in message.content.lower()
        assert "promoted" not in message.content.lower()

    def test_chat_successful_preparation_stops_at_pending_approval(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _stub_research(atlas)
            atlas.development_controller._change_supplier = _ConcreteSupplier()  # noqa: SLF001
            message = atlas.chat(
                "add a new capability to Atlas for scheduling so that tasks run on time"
            )
        finally:
            atlas.shutdown()

        assert "PENDING_APPROVAL" in message.content
        assert "Proposal ID:" in message.content
        assert "Approval Request:" in message.content
        # The report must explicitly deny, never claim, those terminal states.
        assert "Nothing is approved, executed, or promoted" in message.content
        assert "approved by" not in message.content.lower()
        assert "Run status:" not in message.content
        assert "Governed development execution complete" not in message.content

    def test_chat_under_specified_request_clarified(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            # The bridge is wired; but clarification must short-circuit it.
            message = atlas.chat("improve this module")
        finally:
            atlas.shutdown()

        assert message.role == "assistant"
        assert "more detail" in message.content
        assert "Proposal ID:" not in message.content

    def test_no_approval_execution_or_promotion_calls(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _stub_research(atlas)
            atlas.development_controller._change_supplier = _ConcreteSupplier()  # noqa: SLF001

            approval_manager = atlas._approval_manager  # noqa: SLF001
            original_approve = approval_manager.approve
            approval_manager.approve = MagicMock(wraps=original_approve)

            atlas.chat("add a new capability to Atlas for scheduling")

            approval_manager.approve.assert_not_called()
        finally:
            atlas.shutdown()


class TestArchitectureGuards:
    def test_conversation_service_has_no_evolution_import(self):
        import ast
        from pathlib import Path

        source = (
            Path("atlas/conversation/conversation_service.py")
            .read_text(encoding="utf-8")
        )
        tree = ast.parse(source)
        # P17 approved the governed conversational approval + execution +
        # recovery paths, which intentionally bind the conversation layer to
        # the EXISTING ApprovalManager, the EXISTING proposal/request status
        # enums, and the EXISTING development outcome enums (for read-only
        # recovery analysis). Every other atlas.evolution import remains
        # forbidden (execution engine, autonomy, planner, ...).
        allowed_modules = {
            "atlas.evolution.approval_manager",
            "atlas.evolution.models",
            "atlas.evolution.development_models",
            "atlas.evolution.development_diagnostic",
            "atlas.evolution.development_recovery",
            "atlas.evolution.development_verification",
            "atlas.evolution.development_report",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert (
                    node.module in allowed_modules
                    or not node.module.startswith("atlas.evolution")
                ), "ConversationService imports evolution"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert (
                        alias.name in allowed_modules
                        or not alias.name.startswith("atlas.evolution")
                    ), "ConversationService imports evolution"

    def test_task_intake_has_no_evolution_import(self):
        import ast
        from pathlib import Path

        source = (
            Path("atlas/conversation/task_intake.py").read_text(encoding="utf-8")
        )
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(
                    "atlas.evolution"
                ), "task_intake imports evolution"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(
                        "atlas.evolution"
                    ), "task_intake imports evolution"

    def test_tick_untouched(self):
        from atlas.kernel.atlas import Atlas

        tick_src = inspect.getsource(Atlas.tick)
        assert "_development_bridge" not in tick_src
        assert "run_development_cycle" not in tick_src
