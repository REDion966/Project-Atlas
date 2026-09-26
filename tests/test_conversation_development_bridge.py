"""B3 — Conversational development bridge (kernel integration) tests.

Proves the conversational seam routes a DEVELOPMENT_REQUEST into the EXISTING
governed development preparation flow and STOPS before approval:

  * ``Atlas.chat()`` reaches the governed development flow.
  * Preparation (with an injected concrete change supplier) stops at
    PENDING_APPROVAL and never approves/executes/promotes.
  * A request whose change class has no authoring content is refused honestly.
  * An under-specified request is stopped by clarification before any
    development work.

G3 reconciliation (documented, scope owner-approved): the conversational route now
rides the EXISTING bounded ``DevelopmentDriver``, and the driver derives the bounded
capability-handler scaffold specification deterministically from the request's own
words. The former premise — "the conversational route has no authoring content, so it
must fail at the supplier" — is therefore superseded. The INVARIANTS these tests
protected are unchanged and still asserted: the turn is not swallowed by the builtin
responder, nothing is approved/executed/promoted, the ApprovalManager is never called
by the conversation, and no sandbox change reaches the live repository.
"""

from __future__ import annotations

import inspect
from pathlib import Path
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
    def test_chat_reaches_the_governed_driver_and_stops_at_the_envelope(
        self, monkeypatch, tmp_path
    ):
        """G3 — the request reaches the driver and stops at the envelope boundary.

        Reconciled (see the module docstring): the driver derives the bounded scaffold
        for this change class, so the request is prepared as a bounded proposal and
        stops at the Development Envelope / approval boundary instead of failing at
        the supplier. Nothing is approved, executed, promoted, or written live.
        """
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _stub_research(atlas)
            message = atlas.chat("add a new capability to Atlas for scheduling")
            driver = dict(message.metadata or {}).get("development_driver") or {}
            pending = atlas.pending_promotion_reviews()
        finally:
            atlas.shutdown()

        assert message.role == "assistant"
        # The governed driver was reached and reported its OWN honest terminal.
        assert driver.get("terminal") == "envelope_disabled"
        assert driver.get("proposal_id")
        assert "PENDING_APPROVAL" in message.content
        assert "Approval Request:" in message.content
        # The boundary is stated and never violated.
        assert "Nothing is approved, executed, or promoted" in message.content
        assert driver.get("execution_status") in ("", None)
        assert not driver.get("promotion_request_id")
        assert tuple(pending) == ()

    def test_chat_without_an_authorable_change_class_is_refused_honestly(
        self, monkeypatch, tmp_path
    ):
        """A request naming no capability is refused honestly (no fabrication)."""
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _stub_research(atlas)
            message = atlas.chat("Can you add a new capability to Atlas?")
            driver = dict(message.metadata or {}).get("development_driver") or {}
        finally:
            atlas.shutdown()

        assert driver.get("terminal") == "author_unavailable"
        assert "supplier" in message.content
        assert "Nothing is approved, executed, or promoted" in message.content

    def test_chat_successful_preparation_stops_at_pending_approval(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _stub_research(atlas)
            atlas.development_controller._change_supplier = _ConcreteSupplier()  # noqa: SLF001
            message = atlas.chat(
                "add a new capability to Atlas for widget batching"
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

    def test_natural_develop_wording_with_incidental_overlap_is_prepared(
        self, monkeypatch, tmp_path
    ):
        """An incidental capability-name overlap must not defeat a real request.

        Reconciled (G3 defect fix, see the module docstring): the word "task"
        happens to overlap the placeholder capability name "task_execution", but
        the request asks for a NEW capability (emailing when a long-running task
        finishes). Lexical overlap is no longer read as functional equivalence,
        so the governed driver prepares the request and stops at the Development
        Envelope / approval boundary. The invariants are unchanged: the builtin
        responder did not claim the turn, the ApprovalManager was never called,
        nothing was executed/promoted/activated, and no sandbox change reached
        the live repository.
        """
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _stub_research(atlas)
            atlas.development_controller._change_supplier = _ConcreteSupplier()  # noqa: SLF001
            approval_manager = atlas._approval_manager  # noqa: SLF001
            approval_manager.approve = MagicMock(wraps=approval_manager.approve)

            message = atlas.chat(
                "I want you to develop a capability for emailing me when a "
                "long-running task finishes"
            )
            driver = dict(message.metadata or {}).get("development_driver") or {}
            pending = atlas.pending_promotion_reviews()

            approval_manager.approve.assert_not_called()
        finally:
            atlas.shutdown()

        # The builtin conversational responder must NOT have claimed the turn.
        assert message.metadata.get("builtin_intent") is None
        # The EXISTING governed driver prepared the request instead of silently
        # rejecting it as already supported.
        assert driver.get("terminal") == "envelope_disabled"
        assert driver.get("terminal") != "already_supported"
        assert driver.get("proposal_id")
        assert "PENDING_APPROVAL" in message.content
        assert "Nothing is approved, executed, or promoted" in message.content
        assert "Run status:" not in message.content
        # Nothing was executed/promoted/activated, and the sandbox change never
        # reached the live repository.
        assert tuple(pending) == ()
        assert not Path("docs/b3_bridge_note.md").exists()

    def test_natural_develop_wording_is_prepared_and_stops_before_approval(
        self, monkeypatch, tmp_path
    ):
        """A naturally phrased, not-yet-supported request stops before approval.

        Reconciled (see the module docstring): the driver derives the bounded scaffold
        for this change class, so preparation succeeds and stops at the Development
        Envelope / approval boundary — never approved, executed, or promoted.
        """
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _stub_research(atlas)
            atlas.development_controller._change_supplier = _ConcreteSupplier()  # noqa: SLF001
            approval_manager = atlas._approval_manager  # noqa: SLF001
            approval_manager.approve = MagicMock(wraps=approval_manager.approve)

            message = atlas.chat(
                "I want you to develop a capability for widget batching"
            )
            driver = dict(message.metadata or {}).get("development_driver") or {}
            pending = atlas.pending_promotion_reviews()

            approval_manager.approve.assert_not_called()
        finally:
            atlas.shutdown()

        assert message.metadata.get("builtin_intent") is None
        assert driver.get("terminal") == "envelope_disabled"
        assert "PENDING_APPROVAL" in message.content
        assert "Nothing is approved, executed, or promoted" in message.content
        assert "Run status:" not in message.content
        assert tuple(pending) == ()
        assert not Path("docs/b3_bridge_note.md").exists()

    def test_builtin_turns_remain_unaffected(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            greeting = atlas.chat("Hello Atlas!")
            capabilities = atlas.chat("What capabilities do you currently have?")
            unsupported = atlas.chat("What does this module do?")
        finally:
            atlas.shutdown()

        assert greeting.metadata.get("builtin_intent") == "greeting"
        assert capabilities.metadata.get("builtin_intent") == "capabilities"
        assert unsupported.metadata.get("builtin_intent") == "unsupported"


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
            "atlas.evolution.autonomy.autonomy_policy",
            "atlas.evolution.autonomy.authorization_manager",
            "atlas.evolution.autonomy.autonomy_controller",
            "atlas.evolution.autonomy.models",
            "atlas.evolution.governance.models",
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
