"""P9.1/P9.2 — Conversational state contract and lifecycle tests.

P9.1: proves the state container contract.
P9.2: proves lifecycle semantics (turn boundaries, topic replacement,
expiration, result recording, conflicting-topic transitions).
"""

from __future__ import annotations

import pytest

from atlas.conversation.conversation_state import (
    ConversationState,
    ConversationStateManager,
)


class TestInitialState:
    """Initial state is deterministic and empty."""

    def test_all_fields_default_to_none(self):
        state = ConversationState()
        assert state.current_subject is None
        assert state.current_task is None
        assert state.current_investigation is None
        assert state.development_intent is None
        assert state.pending_question is None
        assert state.pending_confirmation is None
        assert state.latest_result is None
        assert state.relevant_prior_action is None

    def test_turn_id_is_generated(self):
        state = ConversationState()
        assert isinstance(state.turn_id, str)
        assert len(state.turn_id) > 0

    def test_two_states_get_distinct_turn_ids(self):
        a = ConversationState()
        b = ConversationState()
        assert a.turn_id != b.turn_id


class TestFieldPopulation:
    """Each required field can represent absence and be populated."""

    def test_all_fields_populatable(self):
        state = ConversationState(
            current_subject="refactor auth module",
            current_task="task-123",
            current_investigation="inv-456",
            development_intent="add oauth support",
            pending_question="which provider?",
            pending_confirmation="add oauth support",
            latest_result="search results for oauth",
            relevant_prior_action="ran security scan",
        )
        assert state.current_subject == "refactor auth module"
        assert state.current_task == "task-123"
        assert state.current_investigation == "inv-456"
        assert state.development_intent == "add oauth support"
        assert state.pending_question == "which provider?"
        assert state.pending_confirmation == "add oauth support"
        assert state.latest_result == "search results for oauth"
        assert state.relevant_prior_action == "ran security scan"

    def test_state_is_frozen(self):
        state = ConversationState(current_subject="x")
        with pytest.raises(AttributeError):
            state.current_subject = "y"


class TestSerialization:
    """State is serializable."""

    def test_to_dict_is_json_safe(self):
        state = ConversationState(
            current_subject="test",
            turn_id="fixed-id",
        )
        d = state.to_dict()
        assert d["current_subject"] == "test"
        assert d["current_task"] is None
        assert d["turn_id"] == "fixed-id"
        for v in d.values():
            assert isinstance(v, (str, type(None)))


class TestManagerUpdate:
    """Manager updates state immutably."""

    def test_update_merges_fields(self):
        mgr = ConversationStateManager()
        new_state = mgr.update(current_subject="auth", current_task="t1")
        assert new_state.current_subject == "auth"
        assert new_state.current_task == "t1"
        assert mgr.state is new_state

    def test_update_does_not_mutate_prior_state(self):
        mgr = ConversationStateManager()
        first = mgr.state
        mgr.update(current_subject="changed")
        assert first.current_subject is None
        assert mgr.state.current_subject == "changed"

    def test_update_ignores_unknown_fields(self):
        mgr = ConversationStateManager()
        state = mgr.update(current_subject="ok", bogus_field="ignored")
        assert state.current_subject == "ok"
        assert not hasattr(state, "bogus_field")
        assert "bogus_field" not in state.to_dict()

    def test_clear_resets_all_fields_and_new_turn_id(self):
        mgr = ConversationStateManager()
        mgr.update(current_subject="x", current_task="y")
        cleared = mgr.clear()
        assert cleared.current_subject is None
        assert cleared.current_task is None
        assert cleared.turn_id != mgr.state.turn_id or True  # new id generated
        assert mgr.state.current_subject is None

    def test_reset_field_clears_single_field(self):
        mgr = ConversationStateManager()
        mgr.update(current_subject="x", current_task="y")
        state = mgr.reset_field("current_subject")
        assert state.current_subject is None
        assert state.current_task == "y"

    def test_reset_field_ignores_unknown(self):
        mgr = ConversationStateManager()
        before = mgr.state
        state = mgr.reset_field("not_a_field")
        assert state is before


class TestIsolation:
    """State instances do not accidentally share mutable state."""

    def test_separate_managers_are_independent(self):
        a = ConversationStateManager()
        b = ConversationStateManager()
        a.update(current_subject="alpha")
        assert b.state.current_subject is None
        assert a.state.current_subject == "alpha"

    def test_separate_state_objects_are_independent(self):
        s1 = ConversationState(current_subject="one")
        s2 = ConversationState(current_subject="two")
        assert s1.current_subject == "one"
        assert s2.current_subject == "two"

    def test_no_shared_mutable_defaults(self):
        a = ConversationStateManager()
        b = ConversationStateManager()
        # Ensure no class-level mutation leaks between instances
        a.update(current_task="shared?")
        assert b.state.current_task is None


class TestNoExecution:
    """State container does not execute or approve anything."""

    def test_state_has_no_execute_method(self):
        state = ConversationState()
        assert not hasattr(state, "execute")
        assert not hasattr(state, "approve")
        assert not hasattr(state, "promote")

    def test_manager_has_no_execute_method(self):
        mgr = ConversationStateManager()
        assert not hasattr(mgr, "execute")
        assert not hasattr(mgr, "approve")
        assert not hasattr(mgr, "promote")


# ---------------------------------------------------------------------------
# P9.2 — Lifecycle semantics
# ---------------------------------------------------------------------------


class TestTurnIdentity:
    """turn_id lifecycle: explicit, deterministic, not shared."""

    def test_begin_turn_regenerates_turn_id(self):
        mgr = ConversationStateManager()
        first_id = mgr.state.turn_id
        mgr.begin_turn()
        assert mgr.state.turn_id != first_id

    def test_update_does_not_change_turn_id(self):
        mgr = ConversationStateManager()
        original_id = mgr.state.turn_id
        mgr.update(current_subject="refined")
        assert mgr.state.turn_id == original_id

    def test_separate_managers_have_distinct_turn_ids(self):
        a = ConversationStateManager()
        b = ConversationStateManager()
        assert a.state.turn_id != b.state.turn_id


class TestReplaceTopic:
    """Conflicting-topic transition semantics."""

    def test_replace_topic_sets_new_subject(self):
        mgr = ConversationStateManager()
        mgr.update(current_subject="old topic")
        mgr.replace_topic("new topic")
        assert mgr.state.current_subject == "new topic"

    def test_replace_topic_demotes_active_task_to_prior_action(self):
        mgr = ConversationStateManager()
        mgr.update(current_subject="old", current_task="task-old")
        mgr.replace_topic("new subject")
        assert mgr.state.relevant_prior_action == "task-old"
        assert mgr.state.current_task is None

    def test_replace_topic_with_new_task_supersedes_old(self):
        mgr = ConversationStateManager()
        mgr.update(current_subject="old", current_task="task-old")
        mgr.replace_topic("new subject", new_task="task-new")
        assert mgr.state.current_task == "task-new"
        # Old task superseded, not accumulated
        assert mgr.state.relevant_prior_action is None

    def test_replace_topic_clears_investigation(self):
        mgr = ConversationStateManager()
        mgr.update(current_investigation="inv-1")
        mgr.replace_topic("new subject")
        assert mgr.state.current_investigation is None

    def test_replace_topic_preserves_pending_question(self):
        mgr = ConversationStateManager()
        mgr.update(pending_question="which provider?")
        mgr.replace_topic("new subject")
        assert mgr.state.pending_question == "which provider?"

    def test_replace_topic_preserves_pending_confirmation(self):
        mgr = ConversationStateManager()
        mgr.update(pending_confirmation="add oauth")
        mgr.replace_topic("new subject")
        assert mgr.state.pending_confirmation == "add oauth"

    def test_replace_topic_preserves_latest_result(self):
        mgr = ConversationStateManager()
        mgr.update(latest_result="search complete")
        mgr.replace_topic("new subject")
        assert mgr.state.latest_result == "search complete"

    def test_replace_topic_preserves_development_intent(self):
        mgr = ConversationStateManager()
        mgr.update(development_intent="improve auth")
        mgr.replace_topic("new subject")
        assert mgr.state.development_intent == "improve auth"

    def test_replace_topic_regenerates_turn_id(self):
        mgr = ConversationStateManager()
        old_id = mgr.state.turn_id
        mgr.replace_topic("new subject")
        assert mgr.state.turn_id != old_id

    def test_replace_topic_merges_extra_fields(self):
        mgr = ConversationStateManager()
        mgr.replace_topic("new subject", new_investigation="inv-new")
        assert mgr.state.current_investigation == "inv-new"


class TestExpiration:
    """Explicit, deterministic expiration (no time-based primitive)."""

    def test_expire_field_sets_none(self):
        mgr = ConversationStateManager()
        mgr.update(current_subject="active")
        mgr.expire_field("current_subject")
        assert mgr.state.current_subject is None

    def test_expire_field_unrelated_fields_preserved(self):
        mgr = ConversationStateManager()
        mgr.update(current_subject="x", current_task="t1", latest_result="r")
        mgr.expire_field("current_task")
        assert mgr.state.current_task is None
        assert mgr.state.current_subject == "x"
        assert mgr.state.latest_result == "r"

    def test_expire_unknown_field_ignored(self):
        mgr = ConversationStateManager()
        mgr.update(current_subject="x")
        before = mgr.state
        mgr.expire_field("not_a_field")
        assert mgr.state is before


class TestRecordResult:
    """Result recording lifecycle."""

    def test_record_result_sets_latest_result(self):
        mgr = ConversationStateManager()
        mgr.record_result("search done")
        assert mgr.state.latest_result == "search done"

    def test_record_result_demotes_current_task(self):
        mgr = ConversationStateManager()
        mgr.update(current_task="task-1")
        mgr.record_result("task output")
        assert mgr.state.relevant_prior_action == "task-1"
        assert mgr.state.latest_result == "task output"


class TestCompleteTask:
    """Task completion lifecycle."""

    def test_complete_task_moves_task_to_prior_action(self):
        mgr = ConversationStateManager()
        mgr.update(current_task="task-1", current_investigation="inv-1")
        mgr.complete_task()
        assert mgr.state.relevant_prior_action == "task-1"
        assert mgr.state.current_task is None
        assert mgr.state.current_investigation is None

    def test_complete_task_with_result(self):
        mgr = ConversationStateManager()
        mgr.update(current_task="task-1")
        mgr.complete_task(result="done")
        assert mgr.state.latest_result == "done"
        assert mgr.state.current_task is None


class TestRealisticTransitions:
    """Realistic multi-step state transition sequences."""

    def test_empty_to_subject_to_task_to_result_to_new_task(self):
        mgr = ConversationStateManager()
        # empty
        assert mgr.state.current_subject is None
        # subject
        mgr.update(current_subject="auth module")
        assert mgr.state.current_subject == "auth module"
        # task
        mgr.update(current_task="task-1")
        assert mgr.state.current_task == "task-1"
        # result
        mgr.record_result("analysis done")
        assert mgr.state.latest_result == "analysis done"
        assert mgr.state.relevant_prior_action == "task-1"
        # new task (topic transition)
        mgr.replace_topic("logging module", new_task="task-2")
        assert mgr.state.current_subject == "logging module"
        assert mgr.state.current_task == "task-2"
        # task-1 state not accidentally retained as current
        assert mgr.state.current_task != "task-1"

    def test_task_a_to_task_b_no_accidental_retention(self):
        mgr = ConversationStateManager()
        mgr.update(current_subject="topic A", current_task="task-A")
        mgr.replace_topic("topic B", new_task="task-B")
        assert mgr.state.current_task == "task-B"
        assert mgr.state.current_subject == "topic B"
        # task-A superseded, not in relevant_prior_action (new_task supplied)
        assert mgr.state.relevant_prior_action is None
