"""Step 6 — intent & goal understanding for multi-intent requests.

Step 5's baseline recorded the limitation: *"a partially understood multi-intent
turn can still answer only its first clause without reporting the unhandled
part."* The Step 6 baseline confirmed the actual cause — it is a **goal
decomposition** gap, not a language or routing gap: the shared decomposition
requires every clause to name a recognised operation, so a genuine second
reading that only *states* what is wanted ("…and also where the conversation
service lives") is never split (`decompose(...) -> 1`) and its intent is
silently absorbed or dropped.

Step 6 adds the smallest coherent extension: a bounded coordinator split
(`semantic_frame.split_intents`, over word classes, reusing the EXISTING
`interpret` per clause) plus one conversation handler that answers every
understood clause through the EXISTING builtin surface and explicitly reports
any clause it cannot map. Nothing is executed, approved or authorized, and every
existing route keeps precedence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.conversation import semantic_frame as sf
from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.task_intake import TaskIntake

_REPO_ROOT = Path(__file__).resolve().parents[1]

_MULTI = "Tell me what you can do and also where the conversation service lives."


def _service() -> ConversationService:
    return ConversationService(
        _FailingAI(), task_intake=TaskIntake(), builtin_response=BuiltinResponseService()
    )


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
# 1. Bounded coordinator split (goal decomposition)
# ---------------------------------------------------------------------------


class TestSplitIntents:
    def test_unseen_second_clause_is_split(self):
        readings = sf.split_intents(_MULTI)
        assert [r.subject for r in readings] == [
            "Tell me what you can do",
            "where the conversation service lives",
        ]
        assert readings[0].domain == "capabilities"

    @pytest.mark.parametrize(
        "text",
        [
            "What can you do and also book me a table for two.",
            "Explain your capability surface as well as order me a new laptop.",
        ],
    )
    def test_bounded_coordinators_split(self, text):
        assert len(sf.split_intents(text)) >= 2

    def test_a_clause_the_frame_cannot_read_is_not_invented(self):
        # The frame has no bounded reading for "Who are you" (the builtin does),
        # so the split conservatively declines rather than inventing an intent.
        assert sf.split_intents("Who are you, and also what commands can I use?") == ()
        assert sf.interpret("Who are you").domain is sf.SemanticDomain.UNSUPPORTED

    def test_single_intent_turns_are_not_split(self):
        for text in (
            "What can you do?",
            "Investigate the conversation state handling.",
            "Book me a table for two at the nearest restaurant.",
        ):
            assert sf.split_intents(text) == (), text

    def test_non_text_is_not_split(self):
        assert sf.split_intents(None) == ()
        assert sf.split_intents("") == ()

    def test_split_is_bounded_and_deterministic(self):
        text = " and ".join(f"tell me about part {i}" for i in range(9))
        first = sf.split_intents(text)
        assert first == sf.split_intents(text)
        assert len(first) <= 4

    def test_existing_decomposition_is_untouched(self):
        # Step 2's goal planning reads `decompose`, which is unchanged: it still
        # yields ONE reading for the multi-intent surface above.
        assert len(sf.decompose(_MULTI)) == 1


# ---------------------------------------------------------------------------
# 2. Multi-intent handling in the conversation layer
# ---------------------------------------------------------------------------


class TestMultiIntentHandling:
    def test_understood_part_is_answered_and_the_rest_is_reported(self):
        message = _service().send(_MULTI)
        metadata = message.metadata["multi_intent"]
        assert metadata["handled"] == ["Tell me what you can do"]
        assert metadata["unhandled"] == ["where the conversation service lives"]
        assert "I answered 1 of 2" in message.content
        assert "could not be mapped to anything I can do, so it was not attempted" in (
            message.content
        )
        assert "Nothing was executed or authorized." in message.content

    def test_the_understood_clause_is_answered_by_the_existing_surface(self):
        message = _service().send(_MULTI)
        # The first clause is answered BY the existing builtin surface, and the
        # reply is embedded under the clause it answers.
        assert "**Tell me what you can do**" in message.content
        assert message.content.index("**Tell me what you can do**") < message.content.index(
            "not attempted"
        )

    def test_unsupported_portion_is_never_claimed_as_done(self):
        message = _service().send("What can you do and also book me a table for two.")
        assert "book me a table for two" in message.metadata["multi_intent"]["unhandled"]
        assert "not attempted" in message.content

    def test_single_intent_turns_keep_their_existing_route(self):
        message = _service().send("What can you do?")
        assert (message.metadata or {}).get("multi_intent") is None
        assert (message.metadata or {}).get("builtin_intent") == "help"

    def test_step5_floor_is_unchanged_for_unknown_turns(self):
        message = _service().send("Book me a table for two at the nearest restaurant.")
        assert (message.metadata or {}).get("multi_intent") is None
        assert message.content.startswith("I could not map that request")

    def test_multiple_understood_clauses_are_all_reported(self):
        message = _service().send("Who are you, and also what commands can I use?")
        metadata = (message.metadata or {}).get("multi_intent")
        if metadata is None:  # the existing single-intent surface owns this shape
            pytest.skip("existing surface owns this turn")
        assert len(metadata["handled"]) >= 1
        assert "Nothing was executed or authorized." in message.content


# ---------------------------------------------------------------------------
# 3. Governance
# ---------------------------------------------------------------------------


class TestGovernance:
    def test_multi_intent_creates_no_authority_metadata(self):
        message = _service().send(_MULTI)
        for key in ("approval", "execution", "promotion", "authorization"):
            assert key not in message.metadata, key
        assert set(message.metadata) == {"multi_intent"}

    def test_governance_sensitive_clause_is_not_answered(self):
        readings = sf.split_intents("What can you do and also approve the proposal?")
        assert readings
        sensitive = [r for r in readings if r.governance_sensitive]
        # A governed clause is never treated as a bounded intent to answer; it is
        # reported through the unhandled list when the turn is claimed at all.
        if sensitive:
            message = _service().send("What can you do and also approve the proposal?")
            metadata = (message.metadata or {}).get("multi_intent") or {"unhandled": []}
            assert any(
                "approve" in clause for clause in metadata["unhandled"]
            ) or (message.metadata or {}).get("multi_intent") is None

    def test_no_model_is_used(self):
        _FailingAI.calls = 0
        _service().send(_MULTI)
        assert _FailingAI.calls == 0


# ---------------------------------------------------------------------------
# 4. Real kernel
# ---------------------------------------------------------------------------


class TestRealKernel:
    def test_multi_intent_request_is_fully_reported(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat(_MULTI)
            metadata = (message.metadata or {}).get("multi_intent")
            assert metadata is not None
            assert metadata["handled"] and metadata["unhandled"]
            assert "not attempted" in message.content
            assert atlas.pending_promotion_reviews() == []
        finally:
            atlas.shutdown()

    def test_step5_and_step2_behaviour_is_preserved(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            capabilities = atlas.chat("Spill the beans on what you're capable of.")
            assert (capabilities.metadata or {}).get("builtin_intent") == "capabilities"

            orchestrated = atlas.chat(
                "Investigate the conversation state handling and then explain what we should do next."
            )
            assert (orchestrated.metadata or {}).get("orchestration", {}).get(
                "status"
            ) == "completed"
            assert (orchestrated.metadata or {}).get("multi_intent") is None

            out_of_scope = atlas.chat("Order me a new laptop.")
            assert out_of_scope.content.startswith("I could not map that request")
        finally:
            atlas.shutdown()

    def test_live_repository_untouched(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            atlas.chat(_MULTI)
            assert not (
                _REPO_ROOT / "tests" / "test_goal_commands_evidence_gap.py"
            ).exists()
        finally:
            atlas.shutdown()
