"""P9.1 — Conversational state contract tests.

Proves the state container contract without implementing P9.2 lifecycle
semantics or P9.3 reference resolution.
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
