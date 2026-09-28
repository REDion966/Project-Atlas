"""Step 7 — context & reference understanding across conversational turns.

The baseline (real Atlas/kernel, multi-turn) showed that the EXISTING reference
machinery already resolves the common cases against the retained conversation
state: "What does it do?" / "And that?" / "Tell me more about that." / "Where is
it implemented?" / "Go back to that." all resolve to the active subject, and
"What did you find?" resolves to the most recent result. Those were NOT rebuilt.

The demonstrated gap was the ORDINAL / earlier-item class: "What about the
previous one?" and "And the second one?" name an item in a LIST of earlier
things. Atlas retains the ACTIVE context and the single most recent result — not
a numbered history — and such a turn previously fell to the generic floor, which
neither resolved nor represented the unresolved reference. Step 7 makes that
explicit: the reference is reported as UNRESOLVED, the active context is restated
so the question is answerable, and nothing is invented, guessed or executed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.task_intake import TaskIntake

_REPO_ROOT = Path(__file__).resolve().parents[1]


class _FailingAI:
    calls = 0

    def chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1
        raise RuntimeError("no model may be contacted")

    def stream_chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1

        def _gen():
            raise RuntimeError("no model may be contacted")
            yield ""  # pragma: no cover

        return _gen()


def _service() -> ConversationService:
    return ConversationService(
        _FailingAI(), task_intake=TaskIntake(), builtin_response=BuiltinResponseService()
    )


def _started_atlas(monkeypatch, tmp_path):
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage

    class TmpSQLiteEvolutionStorage(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "evolution.db")

    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage", TmpSQLiteEvolutionStorage
    )
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    return atlas


# ---------------------------------------------------------------------------
# 1. Unresolved earlier-item references are represented, never guessed
# ---------------------------------------------------------------------------


class TestUnresolvedEarlierItemReferences:
    @pytest.mark.parametrize(
        "text",
        [
            "What about the previous one?",
            "And the second one?",
            "What did the last one do?",
            "Tell me about the one we discussed earlier.",
            "Scroll back to the other item.",
        ],
    )
    def test_earlier_item_reference_is_represented(self, text):
        message = _service().send(text)
        metadata = (message.metadata or {}).get("reference_clarification")
        assert metadata is not None, text
        assert metadata["requested"] == "earlier_item"
        assert "cannot tell which earlier item you mean" in message.content
        assert "Nothing was invented or executed." in message.content

    def test_no_context_yet_asks_for_the_item_by_name(self):
        message = _service().send("What about the previous one?")
        metadata = message.metadata["reference_clarification"]
        assert metadata["has_prior_context"] is False
        assert "no earlier subject or result in this conversation yet" in message.content

    def test_the_reply_carries_no_authority(self):
        metadata = _service().send("And the second one?").metadata
        assert set(metadata) == {"reference_clarification"}

    def test_ordinary_turns_are_not_claimed(self):
        service = _service()
        for text in (
            "What can you do?",
            "Explain the knowledge decision service.",
            "Investigate the conversation state handling.",
            "Book me a table for two at the nearest restaurant.",
        ):
            message = service.send(text)
            assert (message.metadata or {}).get("reference_clarification") is None, text


# ---------------------------------------------------------------------------
# 2. Existing reference resolution is preserved
# ---------------------------------------------------------------------------


class TestExistingReferencesPreserved:
    def test_demonstrative_follow_up_still_resolves(self):
        message = _service().send("Tell me more about that.")
        # The existing reference surface owns this shape (not the Step 7 handler).
        assert (message.metadata or {}).get("reference_clarification") is None

    def test_step5_and_step6_paths_are_untouched(self):
        service = _service()
        out_of_scope = service.send("Order me a new laptop.")
        assert (out_of_scope.metadata or {}).get("builtin_intent") == "unsupported"
        assert (out_of_scope.metadata or {}).get("reference_clarification") is None

        multi = service.send("What can you do and also book me a table for two.")
        assert (multi.metadata or {}).get("multi_intent") is not None


# ---------------------------------------------------------------------------
# 3. Real kernel, multi-turn
# ---------------------------------------------------------------------------


class TestRealKernel:
    def test_context_continuity_then_unresolved_earlier_item(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            atlas.chat("Investigate the conversation state handling.")

            # Continuity: the existing reference surface resolves the pronoun.
            continuity = atlas.chat("What does it do?")
            assert (continuity.metadata or {}).get("builtin_intent") == "reference"
            assert (continuity.metadata or {}).get("reference_field") == "current_investigation"

            # The most recent result is still reachable.
            result = atlas.chat("What did you find?")
            assert (result.metadata or {}).get("reference_field") == "latest_result"

            # The earlier-item reference is represented, not guessed.
            earlier = atlas.chat("What about the previous one?")
            assert (earlier.metadata or {}).get("reference_clarification") is not None
            assert "cannot tell which earlier item you mean" in earlier.content

            assert atlas.pending_promotion_reviews() == []
            assert atlas._conversation.state_manager.state.pending_approval_id is None  # noqa: SLF001
        finally:
            atlas.shutdown()

    def test_no_referent_is_invented_after_a_topic_change(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            atlas.chat("What can you do?")
            message = atlas.chat("And the second one?")
            metadata = (message.metadata or {}).get("reference_clarification")
            assert metadata is not None
            # No candidate is fabricated: the reply never claims a subject that
            # the retained context does not have.
            if not metadata["active_subject"]:
                assert "The active subject is" not in message.content
        finally:
            atlas.shutdown()

    def test_live_repository_untouched(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            atlas.chat("What about the previous one?")
            assert not (
                _REPO_ROOT / "tests" / "test_goal_commands_evidence_gap.py"
            ).exists()
        finally:
            atlas.shutdown()
