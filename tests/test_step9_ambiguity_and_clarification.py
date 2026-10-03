"""Step 9 — ambiguity & clarification.

The baseline (real Atlas/kernel, multi-turn) showed that Steps 5-8 already
detect a great deal of ambiguity (the semantic frame's needs-clarification
contract, reference-resolution AMBIGUOUS, the Step 8 world state, and the
existing captured-entity product clarification) but three concrete gaps
remained:

  * a GENERAL contextual reference ambiguity (e.g. two distinct established
    facts) was detected by the resolver and then SILENTLY DROPPED — the turn
    fell to the generic "cannot answer" floor instead of asking;
  * an UNDERSPECIFIED investigation request whose whole object was a bare
    reference with no antecedent ("Investigate it.") was treated as a
    determined objective and Atlas investigated the literal pronoun;
  * a clarification was NOT resolvable: the competing candidates were not
    preserved, so the user's follow-up ("the handling one", "the second one",
    "auth module") fell to the floor and the intended route never resumed.

The smallest coherent model that closes those gaps is a bounded
``PendingClarification`` record on the EXISTING ``ConversationState``: what was
ambiguous, the bounded candidate interpretations an existing deterministic
surface actually produced, and the originating turn. It is representation only:
it never routes, approves, executes, promotes, or contacts a model, and it is
not a second store. No existing interpretation/reference/world-state system was
rebuilt.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.clarification import (
    KIND_REFERENCE,
    KIND_SUBJECT,
    KIND_TOPIC,
    PendingClarification,
    build_question,
    candidate_matches,
)
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import ConversationStateManager
from atlas.conversation.investigation import InvestigationService
from atlas.conversation.task_intake import TaskIntake
from atlas.conversation.world_state import ConversationWorld, complete_topic

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
    _FailingAI.calls = 0
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        investigation_service=InvestigationService(),
    )


def _two_fact_service() -> ConversationService:
    """A service whose conversation carries two distinct established facts."""
    service = _service()
    service.state_manager.update(current_subject="auth module")
    service.state_manager.update(development_intent="add oauth support")
    return service


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
# 1. Clarification model: matching, bounds, serialization
# ---------------------------------------------------------------------------


class TestCandidateMatching:
    def test_exact_and_containment(self):
        candidates = ("auth module", "add oauth support")
        assert candidate_matches("auth module", candidates) == ("auth module",)
        assert candidate_matches("the add oauth support one", candidates) == (
            "add oauth support",
        )

    def test_distinctive_token_selection(self):
        candidates = ("Investigate the conversation state handling", "Investigate the conversation state manager")
        assert candidate_matches("the handling one", candidates) == (
            "Investigate the conversation state handling",
        )

    def test_ordinal_selection(self):
        candidates = ("alpha topic", "beta topic", "gamma topic")
        assert candidate_matches("the second one", candidates) == ("beta topic",)
        assert candidate_matches("the last one", candidates) == ("gamma topic",)
        assert candidate_matches("the first one", candidates) == ("alpha topic",)

    def test_generic_reply_selects_nothing(self):
        candidates = ("alpha topic", "beta topic")
        assert candidate_matches("the one", candidates) == ()
        assert candidate_matches("that", candidates) == ()

    def test_multi_match_is_reported(self):
        candidates = ("conversation state handling", "conversation state manager")
        assert set(candidate_matches("the conversation state one", candidates)) == set(
            candidates
        )

    def test_no_match_and_no_candidates(self):
        assert candidate_matches("something unrelated", ("alpha topic",)) == ()
        assert candidate_matches("alpha topic", ()) == ()

    def test_deterministic(self):
        candidates = ("auth module", "add oauth support")
        for _ in range(10):
            assert candidate_matches("auth module", candidates) == ("auth module",)


class TestPendingClarificationModel:
    def test_round_trip(self):
        pending = PendingClarification(
            kind=KIND_REFERENCE,
            question="Which one?",
            candidates=("a", "b"),
            original_text="Tell me more about it.",
        )
        assert PendingClarification.from_dict(pending.to_dict()) == pending

    def test_malformed_rejected(self):
        assert PendingClarification.from_dict("nope") is None
        assert PendingClarification.from_dict({"kind": "reference"}) is None
        rebuilt = PendingClarification.from_dict({"kind": "bogus", "question": "Which?"})
        assert rebuilt is not None and rebuilt.kind == KIND_SUBJECT

    def test_candidates_bounded_and_deduplicated(self):
        pending = PendingClarification.from_dict(
            {
                "kind": "topic",
                "question": "Which?",
                "candidates": ["a", "a", "b", "c", "d", "e", "f", "g", "h"],
            }
        )
        assert pending is not None
        assert len(pending.candidates) == 6
        assert pending.candidates[0] == "a"

    def test_build_question_lists_candidates_or_falls_back(self):
        assert "a" in build_question(KIND_TOPIC, ("a", "b"), "Which?")
        assert build_question(KIND_SUBJECT, (), "Which subject?") == "Which subject?"


class TestStateManagerClarification:
    def test_record_and_read(self):
        manager = ConversationStateManager()
        manager.record_pending_clarification(
            KIND_TOPIC, "Which?", ["a", "b"], original_text="go back"
        )
        pending = manager.state.pending_clarification
        assert pending is not None
        assert pending.kind == KIND_TOPIC
        assert pending.candidates == ("a", "b")

    def test_clear(self):
        manager = ConversationStateManager()
        manager.record_pending_clarification(KIND_REFERENCE, "Which?", ["a"])
        assert manager.clear_pending_clarification().pending_clarification is None

    def test_blank_question_is_not_recorded(self):
        manager = ConversationStateManager()
        before = manager.state
        manager.record_pending_clarification(KIND_SUBJECT, "", ())
        assert manager.state.pending_clarification is None
        assert manager.state is before  # fail closed: nothing recorded

    def test_to_dict_round_trip_through_update(self):
        manager = ConversationStateManager()
        manager.record_pending_clarification(KIND_REFERENCE, "Which?", ["a", "b"])
        payload = manager.state.to_dict()
        assert payload["pending_clarification"]["candidates"] == ["a", "b"]
        assert manager.update(**payload).pending_clarification == (
            manager.state.pending_clarification
        )

    def test_isolation(self):
        a = ConversationStateManager()
        b = ConversationStateManager()
        a.record_pending_clarification(KIND_TOPIC, "Which?", ["a"])
        assert b.state.pending_clarification is None


# ---------------------------------------------------------------------------
# 2. Detection through the service
# ---------------------------------------------------------------------------


class TestGenuineAmbiguityDetected:
    def test_general_contextual_ambiguity_asks(self):
        service = _two_fact_service()
        message = service.send("Tell me more about it.")
        assert message.metadata.get("clarification", {}).get("kind") == KIND_REFERENCE
        assert "auth module" in message.content
        assert "add oauth support" in message.content
        assert "cannot answer" not in message.content
        pending = service.state_manager.state.pending_clarification
        assert pending is not None and set(pending.candidates) == {
            "auth module",
            "add oauth support",
        }

    def test_underspecified_investigation_asks_instead_of_inventing(self):
        service = _service()
        message = service.send("Investigate it.")
        assert message.metadata.get("frame_clarification") is not None
        assert "Which subject should I use?" in message.content
        pending = service.state_manager.state.pending_clarification
        assert pending is not None and pending.kind == KIND_SUBJECT
        # Nothing was investigated.
        assert service.state_manager.state.current_investigation is None

    def test_captured_entity_ambiguity_is_preserved(self):
        service = _service()
        service.send(
            "I am comparing the Samsung Galaxy S26 Ultra and the Samsung Galaxy Z Fold."
        )
        message = service.send("Research the Samsung phone.")
        # The existing captured-entity clarification keeps its pinned wording.
        assert "which of the products" in message.content.lower()
        pending = service.state_manager.state.pending_clarification
        assert pending is not None and pending.kind == KIND_REFERENCE
        assert "Samsung Galaxy S26 Ultra" in pending.candidates

    def test_ambiguous_topic_return_asks(self):
        service = _service()
        service.send("Investigate the conversation state handling.")
        service.send("Investigate the conversation state manager.")
        message = service.send("Go back to the conversation state.")
        assert message.metadata.get("world_state", {}).get("status") == "ambiguous"
        pending = service.state_manager.state.pending_clarification
        assert pending is not None and pending.kind == KIND_TOPIC


# ---------------------------------------------------------------------------
# 3. Clarification resolution + route resumption
# ---------------------------------------------------------------------------


class TestClarificationResolution:
    def test_reference_clarification_resolves_by_name(self):
        service = _two_fact_service()
        service.send("Tell me more about it.")
        message = service.send("auth module")
        assert message.metadata.get("clarification_resolved", {}).get("resolved") == (
            "auth module"
        )
        assert "auth module" in message.content
        assert service.state_manager.state.pending_clarification is None

    def test_reference_clarification_resolves_by_ordinal(self):
        service = _two_fact_service()
        service.send("Tell me more about it.")
        message = service.send("the second one")
        resolved = message.metadata.get("clarification_resolved", {}).get("resolved")
        assert resolved in ("auth module", "add oauth support")
        assert service.state_manager.state.pending_clarification is None

    def test_topic_clarification_resumes_the_topic_return(self):
        service = _service()
        service.send("Investigate the conversation state handling.")
        service.send("Investigate the conversation state manager.")
        service.send("Go back to the conversation state.")
        message = service.send("the handling one")
        assert "conversation state handling" in message.content
        assert service.state_manager.state.world.active_topic.endswith(
            "conversation state handling"
        )
        assert service.state_manager.state.pending_clarification is None

    def test_still_ambiguous_reply_keeps_the_question_open(self):
        service = _service()
        service.send("Investigate the conversation state handling.")
        service.send("Investigate the conversation state manager.")
        service.send("Go back to the conversation state.")
        message = service.send("the conversation state one")
        assert message.metadata.get("clarification", {}).get("status") == (
            "still_ambiguous"
        )
        assert service.state_manager.state.pending_clarification is not None

    def test_a_new_objective_supersedes_the_clarification(self):
        service = _two_fact_service()
        service.send("Tell me more about it.")
        message = service.send("Investigate the storage layer.")
        assert (message.metadata or {}).get("investigation") is not None
        assert service.state_manager.state.pending_clarification is None

    def test_resolution_grants_no_authority(self):
        service = _two_fact_service()
        service.send("Tell me more about it.")
        message = service.send("auth module")
        for key in ("execution", "approval", "promotion"):
            assert key not in message.metadata, key
        assert service.state_manager.state.pending_approval_id is None
        assert service._active_approval_requests == {}
        assert _FailingAI.calls == 0

    def test_stream_parity_for_clarification(self):
        sent = _two_fact_service()
        streamed = _two_fact_service()
        assert sent.send("Tell me more about it.").content == "".join(
            streamed.stream("Tell me more about it.")
        )
        assert sent.send("auth module").content == "".join(
            streamed.stream("auth module")
        )


# ---------------------------------------------------------------------------
# 4. No over-clarification / Steps 5-8 preserved
# ---------------------------------------------------------------------------

class TestNoOverClarification:
    def test_clear_request_is_not_clarified(self):
        service = _service()
        message = service.send("Investigate the storage layer.")
        assert (message.metadata or {}).get("clarification") is None
        assert (message.metadata or {}).get("frame_clarification") is None
        assert (message.metadata or {}).get("investigation") is not None

    def test_single_investigation_pronoun_still_resolves(self):
        service = _service()
        service.send("Investigate the memory architecture.")
        message = service.send("What does it do?")
        assert message.metadata.get("reference_field") == "current_investigation"
        assert service.state_manager.state.pending_clarification is None

    def test_ordinary_continuation_is_not_clarified(self):
        service = _service()
        service.send("Investigate the memory architecture.")
        message = service.send("continue")
        assert (message.metadata or {}).get("clarification") is None

    def test_unsupported_request_stays_unsupported(self):
        message = _service().send("Order me a new laptop.")
        assert message.metadata.get("builtin_intent") == "unsupported"
        assert "out-of-scope request" in message.content

    def test_step7_ordinal_without_candidates_stays_represented(self):
        service = _service()
        service.send("Investigate the memory architecture.")
        message = service.send("What about the previous one?")
        assert (message.metadata or {}).get("reference_clarification") is not None

    def test_step5_multi_intent_and_step6_are_preserved(self):
        message = _service().send("What can you do and also book me a table for two.")
        assert message.metadata.get("multi_intent") is not None

    def test_casual_turn_clears_a_stale_clarification(self):
        service = _two_fact_service()
        service.send("Tell me more about it.")
        message = service.send("thanks")
        assert (message.metadata or {}).get("builtin_intent") is not None
        assert service.state_manager.state.pending_clarification is None


class TestPendingClarificationLifecycle:
    """P1-1 — an outstanding clarification must not trap unrelated turns."""

    @staticmethod
    def _pending() -> ConversationService:
        service = _two_fact_service()
        service.send("Tell me more about it.")
        assert service.state_manager.state.pending_clarification is not None
        return service

    def test_casual_follow_up_releases_the_stale_clarification(self):
        service = self._pending()
        message = service.send("Okay, use that approach.")
        assert service.state_manager.state.pending_clarification is None
        assert (
            (message.metadata or {}).get("clarification", {}).get("status")
            != "unresolved"
        )

    def test_unrelated_question_releases_the_stale_clarification(self):
        service = self._pending()
        message = service.send("How's it going?")
        assert service.state_manager.state.pending_clarification is None
        assert (
            (message.metadata or {}).get("clarification", {}).get("status")
            != "unresolved"
        )

    def test_genuine_candidate_reply_still_resolves(self):
        service = self._pending()
        message = service.send("auth module")
        assert message.metadata.get("clarification_resolved", {}).get("resolved") == (
            "auth module"
        )
        assert service.state_manager.state.pending_clarification is None

    def test_bare_reference_pointer_keeps_the_clarification_open(self):
        service = self._pending()
        message = service.send("it")
        assert service.state_manager.state.pending_clarification is not None
        assert (
            (message.metadata or {}).get("clarification", {}).get("status")
            == "unresolved"
        )

    def test_new_objective_supersedes_and_proceeds(self):
        service = self._pending()
        message = service.send("Investigate the storage layer.")
        assert (message.metadata or {}).get("investigation") is not None
        assert service.state_manager.state.pending_clarification is None


# ---------------------------------------------------------------------------
# 5. Real Atlas/kernel multi-turn validation
# ---------------------------------------------------------------------------


class TestRealKernel:
    def test_ambiguous_topic_return_is_resolved_and_route_resumes(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            atlas.chat("Investigate the conversation state handling.")
            atlas.chat("Investigate the conversation state manager.")
            asked = atlas.chat("Go back to the conversation state.")
            assert asked.metadata.get("world_state", {}).get("status") == "ambiguous"
            state = atlas._conversation.state_manager.state  # noqa: SLF001
            assert state.pending_clarification is not None

            resolved = atlas.chat("the handling one")
            assert (resolved.metadata or {}).get("clarification_resolved", {}).get(
                "resolved"
            ) == "Investigate the conversation state handling"
            state = atlas._conversation.state_manager.state  # noqa: SLF001
            assert state.pending_clarification is None
            assert state.world.active_topic.endswith("conversation state handling")

            # The resumed route answers the follow-up against the chosen topic.
            follow = atlas.chat("What does it do?")
            assert "conversation state handling" in follow.content
            assert atlas.pending_promotion_reviews() == []
        finally:
            atlas.shutdown()

    def test_ambiguous_follow_up_asks_then_resolves(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            atlas.chat("Research the Europa Clipper mission.")
            state = atlas._conversation.state_manager  # noqa: SLF001
            state.update(current_subject="the Europa Clipper mission")
            state.update(development_intent="add a guidance module")
            asked = atlas.chat("Tell me more about it.")
            assert "cannot answer" not in asked.content
            assert "guidance module" in asked.content
            resolved = atlas.chat("add a guidance module")
            assert (resolved.metadata or {}).get("clarification_resolved") is not None
        finally:
            atlas.shutdown()

    def test_clear_requests_are_not_clarified(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat("Investigate the storage layer.")
            assert (message.metadata or {}).get("clarification") is None
            assert (message.metadata or {}).get("investigation") is not None
            unsupported = atlas.chat("Order me a new laptop.")
            assert unsupported.metadata.get("builtin_intent") == "unsupported"
        finally:
            atlas.shutdown()

    def test_live_repository_untouched(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            atlas.chat("Investigate it.")
            atlas.chat("auth module")
            assert not (
                _REPO_ROOT / "tests" / "test_goal_commands_evidence_gap.py"
            ).exists()
        finally:
            atlas.shutdown()


# Reference the world helpers in a lightweight way so the import surface above
# stays honest about what this suite touches.
def test_world_state_still_available():
    assert ConversationWorld().active_topic == ""
    assert complete_topic(ConversationWorld(), "x").active_topic == ""
