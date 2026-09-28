"""Step 8 — bounded conversational world state.

The baseline (real Atlas/kernel, multi-turn) showed that Atlas retained only the
ACTIVE context plus the single most recent result. It had **no representation
that separated ACTIVE conversational state from HISTORICAL state**, and the
consequences were concrete and reproducible:

  * after a topic switch, a PRIOR topic's turn still competed as an active
    contextual candidate, so a plain pronoun reference ("What does it do?")
    became ambiguous and fell all the way to the generic floor — even though one
    topic was unambiguously current;
  * there was no representation of the topics the conversation had covered, so
    returning to an earlier topic was not recognized at all (it was mis-routed
    to the knowledge path and produced a bogus empty answer);
  * there was no record that a reference had been left UNRESOLVED.

The smallest coherent model that closes those gaps is a bounded, deterministic
world state on the EXISTING ``ConversationState``: the ACTIVE topic (and what
kind of thing it is), the bounded ordered history of PRIOR topics, and the most
recent unresolved reference. It is representation only — it never routes,
approves, executes, promotes or contacts a model, and it is not a second store.

Nothing that already worked was rebuilt: existing pronoun/demonstrative/
location/most-recent-result references, the Steps 5/6 surfaces and the Step 7
unresolved-earlier-item representation keep their behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import ConversationStateManager
from atlas.conversation.investigation import InvestigationService
from atlas.conversation.task_intake import TaskIntake
from atlas.conversation.world_state import (
    MAX_WORLD_TOPICS,
    ConversationWorld,
    WorldTopic,
    complete_topic,
    mark_unresolved_reference,
    match_topics,
    observe_topic,
    reactivate_topic,
)

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
# 1. World-state model: creation, update, transitions, bounds
# ---------------------------------------------------------------------------


class TestWorldStateModel:
    def test_empty_world_has_no_active_topic(self):
        world = ConversationWorld()
        assert world.active_topic == ""
        assert world.topics == ()
        assert world.unresolved_reference == ""
        assert world.has_active_topic is False

    def test_observe_establishes_active_topic(self):
        world = observe_topic(ConversationWorld(), "Investigate the storage layer", "investigation")
        assert world.active_topic == "Investigate the storage layer"
        assert world.active_kind == "investigation"
        assert world.has_active_topic is True
        assert [(t.label, t.status) for t in world.topics] == [
            ("Investigate the storage layer", "active")
        ]

    def test_topic_switch_demotes_prior_to_history(self):
        world = observe_topic(ConversationWorld(), "topic A", "investigation")
        world = observe_topic(world, "topic B", "investigation")
        assert world.active_topic == "topic B"
        statuses = {t.label: t.status for t in world.topics}
        assert statuses == {"topic B": "active", "topic A": "superseded"}
        assert [t.label for t in world.prior_topics] == ["topic A"]

    def test_reobserving_the_same_topic_is_a_continuation(self):
        world = observe_topic(ConversationWorld(), "topic A", "investigation")
        world = observe_topic(world, "topic A", "investigation", result_ref="result-1")
        assert world.active_topic == "topic A"
        assert len(world.topics) == 1
        assert world.topics[0].result_ref == "result-1"

    def test_topic_history_is_bounded(self):
        world = ConversationWorld()
        for index in range(MAX_WORLD_TOPICS + 4):
            world = observe_topic(world, f"topic {index}", "investigation")
        assert len(world.topics) == MAX_WORLD_TOPICS
        assert world.active_topic == f"topic {MAX_WORLD_TOPICS + 3}"

    def test_blank_topic_is_ignored(self):
        world = ConversationWorld()
        assert observe_topic(world, "", "investigation") is world
        assert observe_topic(world, "   ", "investigation") is world

    def test_complete_topic_is_distinct_from_active_and_keeps_history(self):
        world = observe_topic(ConversationWorld(), "topic A", "goal")
        world = complete_topic(world, "topic A")
        assert world.active_topic == ""
        assert world.topics[0].status == "completed"

    def test_serialization_round_trip(self):
        world = observe_topic(ConversationWorld(), "topic A", "investigation", result_ref="r")
        world = observe_topic(world, "topic B", "knowledge")
        rebuilt = ConversationWorld.from_dict(world.to_dict())
        assert rebuilt == world

    def test_malformed_world_dict_is_rejected(self):
        assert ConversationWorld.from_dict("nope") is None
        assert WorldTopic.from_dict({}) is None
        rebuilt = ConversationWorld.from_dict({"topics": [{"label": "ok"}]})
        assert rebuilt is not None and rebuilt.topics[0].label == "ok"


class TestTopicMatching:
    def _world(self):
        return observe_topic(ConversationWorld(), "Investigate the storage layer", "investigation")

    def test_match_by_name(self):
        assert len(match_topics(self._world(), "the storage layer")) == 1

    def test_short_query_matches_nothing(self):
        assert match_topics(self._world(), "it") == ()

    def test_reactivate_single_match(self):
        world = observe_topic(self._world(), "Investigate the memory architecture", "investigation")
        reactivated = reactivate_topic(world, "the storage layer")
        assert reactivated is not None
        assert reactivated.active_topic == "Investigate the storage layer"
        statuses = {t.label: t.status for t in reactivated.topics}
        assert statuses["Investigate the memory architecture"] == "superseded"

    def test_reactivate_no_match_fails_closed(self):
        assert reactivate_topic(self._world(), "the payroll system") is None

    def test_reactivate_ambiguous_fails_closed(self):
        world = observe_topic(ConversationWorld(), "the storage layer service A", "investigation")
        world = observe_topic(world, "the storage layer service B", "investigation")
        assert reactivate_topic(world, "the storage layer service") is None


class TestStateManagerWorld:
    def test_observe_and_read(self):
        manager = ConversationStateManager()
        manager.observe_world_topic("topic A", "investigation", result_ref="r1", turn_index=2)
        assert manager.state.world.active_topic == "topic A"
        assert manager.state.world.topics[0].result_ref == "r1"
        assert manager.state.world.turn_index == 2

    def test_topic_switch_preserves_history(self):
        manager = ConversationStateManager()
        manager.observe_world_topic("topic A", "investigation")
        manager.observe_world_topic("topic B", "knowledge")
        assert manager.state.world.active_topic == "topic B"
        assert {t.label for t in manager.state.world.prior_topics} == {"topic A"}

    def test_reactivate_updates_active_context(self):
        manager = ConversationStateManager()
        manager.observe_world_topic("Investigate A", "investigation")
        manager.observe_world_topic("Investigate B", "investigation")
        assert manager.reactivate_world_topic("Investigate A") == "Investigate A"
        assert manager.state.world.active_topic == "Investigate A"
        # A reactivated investigation becomes the consistent active investigation.
        assert manager.state.current_investigation == "Investigate A"

    def test_reactivate_unknown_returns_none_and_changes_nothing(self):
        manager = ConversationStateManager()
        manager.observe_world_topic("topic A", "investigation")
        before = manager.state
        assert manager.reactivate_world_topic("nothing here at all") is None
        assert manager.state is before

    def test_unresolved_reference_is_recorded_not_promoted(self):
        manager = ConversationStateManager()
        manager.observe_world_topic("topic A", "investigation")
        manager.record_unresolved_reference("What about the previous one?")
        assert manager.state.world.unresolved_reference == "What about the previous one?"
        assert manager.state.world.active_topic == "topic A"

    def test_world_dict_round_trips_through_update(self):
        manager = ConversationStateManager()
        manager.observe_world_topic("topic A", "investigation")
        payload = manager.state.to_dict()
        assert payload["world"] == manager.state.world.to_dict()
        rebuilt = manager.update(**payload)
        assert rebuilt.world == manager.state.world

    def test_world_is_json_safe(self):
        import json

        manager = ConversationStateManager()
        manager.observe_world_topic("topic A", "investigation", result_ref="r")
        json.dumps(manager.state.to_dict())

    def test_clear_resets_world(self):
        manager = ConversationStateManager()
        manager.observe_world_topic("topic A", "investigation")
        assert manager.clear().world is None

    def test_two_managers_are_isolated(self):
        a = ConversationStateManager()
        b = ConversationStateManager()
        a.observe_world_topic("topic A", "investigation")
        assert b.state.world is None


# ---------------------------------------------------------------------------
# 2. Real service path: observation, switches, return, unresolved
# ---------------------------------------------------------------------------


class TestServiceWorldIntegration:
    def test_investigation_establishes_active_topic(self):
        service = _service()
        service.send("Investigate the conversation state handling.")
        world = service.state_manager.state.world
        assert world is not None
        assert world.active_kind == "investigation"
        assert world.active_topic == service.state_manager.state.current_investigation

    def test_topic_switch_demotes_previous_topic(self):
        service = _service()
        service.send("Investigate the conversation state handling.")
        first = service.state_manager.state.world.active_topic
        service.send("Now investigate the knowledge decision service.")
        world = service.state_manager.state.world
        assert world.active_topic != first
        assert {t.label for t in world.prior_topics} == {first}

    def test_pronoun_resolves_to_active_topic_after_a_switch(self):
        service = _service()
        service.send("Investigate the conversation state handling.")
        service.send("Now investigate the knowledge decision service.")
        message = service.send("What does it do?")
        assert message.metadata.get("builtin_intent") == "reference"
        assert message.metadata.get("reference_field") == "current_investigation"
        assert "knowledge decision service" in message.content
        assert "conversation state handling" not in message.content

    def test_return_to_prior_topic_reactivates_it(self):
        service = _service()
        service.send("Investigate the conversation state handling.")
        service.send("Now investigate the knowledge decision service.")
        returned = service.send("Go back to the conversation state handling.")
        assert returned.metadata.get("world_state", {}).get("status") == "reactivated"
        world = service.state_manager.state.world
        assert "conversation state handling" in world.active_topic
        follow = service.send("What does it do?")
        assert follow.metadata.get("reference_field") == "current_investigation"
        assert "conversation state handling" in follow.content

    def test_return_to_unknown_topic_fails_closed(self):
        service = _service()
        service.send("Investigate the conversation state handling.")
        message = service.send("Go back to the payroll ledger.")
        assert (message.metadata or {}).get("world_state") is None

    def test_reference_return_target_keeps_step7_ownership(self):
        service = _service()
        service.send("Investigate the conversation state handling.")
        message = service.send("Go back to that.")
        # The pure-reference target is not claimed as a topic return.
        assert (message.metadata or {}).get("world_state") is None

    def test_unsupported_request_does_not_clobber_active_topic(self):
        service = _service()
        service.send("Investigate the conversation state handling.")
        active = service.state_manager.state.world.active_topic
        service.send("Order me a new laptop.")
        assert service.state_manager.state.world.active_topic == active

    def test_unresolved_earlier_item_is_recorded_and_not_promoted(self):
        service = _service()
        service.send("Investigate the conversation state handling.")
        active = service.state_manager.state.world.active_topic
        message = service.send("What about the previous one?")
        assert message.metadata.get("reference_clarification") is not None
        world = service.state_manager.state.world
        assert world.unresolved_reference == "What about the previous one?"
        assert world.active_topic == active

    def test_knowledge_result_establishes_a_knowledge_topic(self):
        service = _service()
        from atlas.conversation.builtin_response import (
            BUILTIN_INTENT_VALIDATED_KNOWLEDGE,
        )
        from atlas.conversation.message import Message

        service._record_knowledge_result(
            Message(
                role="assistant",
                content="A bounded answer.",
                metadata={
                    "builtin_intent": BUILTIN_INTENT_VALIDATED_KNOWLEDGE,
                    "validated_query": "Atlas Evidence Device",
                    "validated_knowledge_status": "supported",
                },
            )
        )
        world = service.state_manager.state.world
        assert world is not None
        assert world.active_topic == "Atlas Evidence Device"
        assert world.active_kind == "knowledge"

    def test_world_carries_no_authority(self):
        service = _service()
        message = service.send("Investigate the conversation state handling.")
        state = service.state_manager.state
        assert state.pending_approval_id is None
        assert service._active_approval_requests == {}
        for key in ("execution", "approval", "promotion"):
            assert key not in message.metadata, key
        assert _FailingAI.calls == 0

    def test_stream_parity_for_world_observation(self):
        sent = _service()
        streamed = _service()
        sent.send("Investigate the conversation state handling.")
        list(streamed.stream("Investigate the conversation state handling."))
        assert sent.state_manager.state.world == streamed.state_manager.state.world


# ---------------------------------------------------------------------------
# 3. Step 5 / Step 6 / Step 7 behaviour preserved
# ---------------------------------------------------------------------------


class TestPriorStepsPreserved:
    def test_step5_out_of_scope_notice_intact(self):
        message = _service().send("Order me a new laptop.")
        assert message.metadata.get("builtin_intent") == "unsupported"
        assert "out-of-scope request" in message.content

    def test_step6_multi_intent_intact(self):
        message = _service().send("What can you do and also book me a table for two.")
        assert message.metadata.get("multi_intent") is not None

    def test_step7_ordinal_representation_intact(self):
        message = _service().send("What about the previous one?")
        assert message.metadata.get("reference_clarification", {}).get("requested") == "earlier_item"

    def test_resolution_without_world_state_is_unchanged(self):
        # A state with no world has no superseded topics, so nothing is filtered:
        # the legacy investigation slot resolves exactly as before.
        from atlas.conversation.conversation_state import ConversationState
        from atlas.conversation.reference_resolution import (
            ConversationReferenceResolver,
            ReferenceResolutionStatus,
        )

        state = ConversationState(current_investigation="memory architecture")
        result = ConversationReferenceResolver().resolve_contextual("What does it do?", None, state)
        assert result.status is ReferenceResolutionStatus.RESOLVED
        assert result.resolved_field == "current_investigation"

    def test_single_investigation_still_resolves_through_the_service(self):
        service = _service()
        service.send("Investigate the memory architecture.")
        message = service.send("What does it do?")
        assert message.metadata.get("reference_field") == "current_investigation"


# ---------------------------------------------------------------------------
# 4. Real Atlas/kernel multi-turn validation
# ---------------------------------------------------------------------------


class TestRealKernel:
    def test_world_state_across_several_turns(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            atlas.chat("Investigate the conversation state handling.")
            state = atlas._conversation.state_manager.state  # noqa: SLF001
            first = state.world.active_topic
            assert first and state.world.active_kind == "investigation"

            atlas.chat("Now investigate the knowledge decision service.")
            state = atlas._conversation.state_manager.state  # noqa: SLF001
            second = state.world.active_topic
            assert second != first
            assert first in {t.label for t in state.world.prior_topics}

            # The pronoun resolves to the ACTIVE topic, not the prior one.
            follow = atlas.chat("What does it do?")
            assert follow.metadata.get("reference_field") == "current_investigation"
            assert "knowledge decision service" in follow.content

            # Return to the prior topic: it becomes active again.
            atlas.chat("Go back to the conversation state handling.")
            state = atlas._conversation.state_manager.state  # noqa: SLF001
            assert state.world.active_topic == first
            follow = atlas.chat("What does it do?")
            assert first in follow.content

            assert atlas.pending_promotion_reviews() == []
        finally:
            atlas.shutdown()

    def test_unresolved_reference_stays_unresolved(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            atlas.chat("Investigate the conversation state handling.")
            before = atlas._conversation.state_manager.state.world.active_topic  # noqa: SLF001
            message = atlas.chat("What about the previous one?")
            assert message.metadata.get("reference_clarification") is not None
            state = atlas._conversation.state_manager.state  # noqa: SLF001
            assert state.world.unresolved_reference
            assert state.world.active_topic == before
        finally:
            atlas.shutdown()

    def test_a_failed_request_does_not_become_the_active_topic(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            atlas.chat("Investigate the conversation state handling.")
            before = atlas._conversation.state_manager.state.world.active_topic  # noqa: SLF001
            atlas.chat("Order me a new laptop.")
            after = atlas._conversation.state_manager.state.world.active_topic  # noqa: SLF001
            assert after == before
        finally:
            atlas.shutdown()

    def test_live_repository_untouched(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            atlas.chat("Investigate the conversation state handling.")
            atlas.chat("Go back to the conversation state handling.")
            assert not (
                _REPO_ROOT / "tests" / "test_goal_commands_evidence_gap.py"
            ).exists()
        finally:
            atlas.shutdown()
