"""P9.3 — Conversational reference resolution tests.

Proves the deterministic reference resolver contract:
RESOLVED / UNRESOLVED / AMBIGUOUS, with the core safety invariant:
AMBIGUITY -> CLARIFICATION. NEVER GUESS.
"""

from __future__ import annotations

import pytest

from atlas.conversation.conversation_state import (
    ConversationState,
    ConversationStateManager,
)
from atlas.conversation.reference_resolution import (
    ConversationReferenceResolver,
    ReferenceResolutionStatus,
    ReferenceResolutionResult,
)


@pytest.fixture
def resolver() -> ConversationReferenceResolver:
    return ConversationReferenceResolver()


class TestEmptyState:
    """Empty state yields UNRESOLVED for all reference categories."""

    @pytest.mark.parametrize("query", [
        "that problem",
        "this task",
        "run it again",
        "what did you find?",
        "continue",
        "that investigation",
    ])
    def test_empty_state_unresolved(self, resolver, query):
        result = resolver.resolve(query, ConversationState())
        assert result.status == ReferenceResolutionStatus.UNRESOLVED
        assert result.resolved_field is None
        assert result.resolved_value is None


class TestSubjectReferences:
    """Subject reference resolution."""

    def test_that_topic_resolved(self, resolver):
        state = ConversationState(current_subject="auth module")
        result = resolver.resolve("that topic", state)
        assert result.status == ReferenceResolutionStatus.RESOLVED
        assert result.resolved_field == "current_subject"
        assert result.resolved_value == "auth module"

    def test_this_issue_resolved(self, resolver):
        state = ConversationState(current_subject="logging bug")
        result = resolver.resolve("this issue", state)
        assert result.status == ReferenceResolutionStatus.RESOLVED
        assert result.resolved_value == "logging bug"


class TestTaskReferences:
    """Task reference resolution."""

    def test_run_it_again_with_task_resolved(self, resolver):
        state = ConversationState(current_task="task-123")
        result = resolver.resolve("run it again", state)
        assert result.status == ReferenceResolutionStatus.RESOLVED
        assert result.resolved_field == "current_task"
        assert result.resolved_value == "task-123"

    def test_run_it_again_without_task_unresolved(self, resolver):
        state = ConversationState()  # no task
        result = resolver.resolve("run it again", state)
        assert result.status == ReferenceResolutionStatus.UNRESOLVED

    def test_it_resolves_to_current_task(self, resolver):
        state = ConversationState(current_task="task-456")
        result = resolver.resolve("it", state)
        assert result.status == ReferenceResolutionStatus.RESOLVED
        assert result.resolved_field == "current_task"


class TestInvestigationReferences:
    """Investigation reference resolution."""

    def test_what_did_you_find_with_investigation(self, resolver):
        state = ConversationState(current_investigation="inv-789")
        result = resolver.resolve("what did you find?", state)
        assert result.status == ReferenceResolutionStatus.RESOLVED
        assert result.resolved_field == "current_investigation"
        assert result.resolved_value == "inv-789"

    def test_that_investigation_resolved(self, resolver):
        state = ConversationState(current_investigation="inv-001")
        result = resolver.resolve("that investigation", state)
        assert result.status == ReferenceResolutionStatus.RESOLVED
        assert result.resolved_value == "inv-001"


class TestResultReferences:
    """Result reference resolution."""

    def test_that_result_resolved(self, resolver):
        state = ConversationState(latest_result="search complete")
        result = resolver.resolve("that result", state)
        assert result.status == ReferenceResolutionStatus.RESOLVED
        assert result.resolved_field == "latest_result"
        assert result.resolved_value == "search complete"


class TestActionReferences:
    """Action reference resolution with ambiguity handling."""

    def test_do_that_again_with_only_prior_action(self, resolver):
        state = ConversationState(relevant_prior_action="ran scan")
        result = resolver.resolve("do that again", state)
        assert result.status == ReferenceResolutionStatus.RESOLVED
        assert result.resolved_field == "relevant_prior_action"
        assert result.resolved_value == "ran scan"

    def test_run_it_again_with_both_task_and_action_ambiguous(self, resolver):
        state = ConversationState(
            current_task="task-1",
            relevant_prior_action="ran scan",
        )
        result = resolver.resolve("run it again", state)
        assert result.status == ReferenceResolutionStatus.AMBIGUOUS
        assert "current_task" in result.candidates
        assert "relevant_prior_action" in result.candidates


class TestAmbiguityNeverGuessed:
    """Multiple plausible referents must never be silently resolved."""

    def test_ambiguous_returns_candidates(self, resolver):
        state = ConversationState(
            current_task="task-1",
            relevant_prior_action="action-a",
        )
        result = resolver.resolve("do that again", state)
        assert result.status == ReferenceResolutionStatus.AMBIGUOUS
        assert result.resolved_field is None
        assert result.resolved_value is None
        assert len(result.candidates) >= 2

    def test_ambiguous_reason_mentions_candidates(self, resolver):
        state = ConversationState(
            current_task="task-1",
            relevant_prior_action="action-a",
        )
        result = resolver.resolve("do that again", state)
        assert "current_task" in result.reason
        assert "relevant_prior_action" in result.reason


class TestUnrecognizedReference:
    """Unrecognized references are UNRESOLVED, not guessed."""

    def test_random_text_unresolved(self, resolver):
        state = ConversationState(current_subject="auth")
        result = resolver.resolve("the weather is nice today", state)
        assert result.status == ReferenceResolutionStatus.UNRESOLVED

    def test_empty_query_unresolved(self, resolver):
        state = ConversationState(current_subject="auth")
        result = resolver.resolve("", state)
        assert result.status == ReferenceResolutionStatus.UNRESOLVED


class TestLifecycleCompatibility:
    """Resolver correctly observes P9.2 lifecycle transitions."""

    def test_stale_reference_after_complete_task(self, resolver):
        mgr = ConversationStateManager()
        mgr.update(current_task="task-1", current_subject="auth")
        mgr.complete_task(result="done")
        # current_task now None; "run it again" should not resolve to stale task
        result = resolver.resolve("run it again", mgr.state)
        # relevant_prior_action now holds the completed task
        assert result.status == ReferenceResolutionStatus.RESOLVED
        assert result.resolved_field == "relevant_prior_action"
        assert result.resolved_value == "task-1"

    def test_replace_topic_clears_old_subject(self, resolver):
        mgr = ConversationStateManager()
        mgr.update(current_subject="old topic", current_task="old-task")
        mgr.replace_topic("new topic", new_task="new-task")
        result = resolver.resolve("that topic", mgr.state)
        assert result.resolved_value == "new topic"
        # old task should not be resolvable as current
        old_ref = resolver.resolve("the task", mgr.state)
        assert old_ref.resolved_value == "new-task"

    def test_expire_field_removes_referent(self, resolver):
        mgr = ConversationStateManager()
        mgr.update(current_subject="auth")
        mgr.expire_field("current_subject")
        result = resolver.resolve("that topic", mgr.state)
        assert result.status == ReferenceResolutionStatus.UNRESOLVED

    def test_begin_turn_preserves_state(self, resolver):
        mgr = ConversationStateManager()
        mgr.update(current_subject="auth", current_task="t1")
        mgr.begin_turn()
        result = resolver.resolve("that topic", mgr.state)
        assert result.status == ReferenceResolutionStatus.RESOLVED
        assert result.resolved_value == "auth"


class TestDeterminism:
    """Repeated resolution is deterministic."""

    def test_repeated_resolution_same_result(self, resolver):
        state = ConversationState(current_subject="auth", current_task="t1")
        r1 = resolver.resolve("that topic", state)
        r2 = resolver.resolve("that topic", state)
        assert r1.status == r2.status
        assert r1.resolved_value == r2.resolved_value

    def test_resolver_does_not_mutate_state(self, resolver):
        state = ConversationState(current_subject="auth")
        original_turn = state.turn_id
        resolver.resolve("that topic", state)
        assert state.turn_id == original_turn
        assert state.current_subject == "auth"


class TestIsolation:
    """Separate state managers do not leak references."""

    def test_separate_managers_independent(self, resolver):
        a = ConversationStateManager()
        b = ConversationStateManager()
        a.update(current_subject="alpha")
        b.update(current_subject="beta")
        assert resolver.resolve("that topic", a.state).resolved_value == "alpha"
        assert resolver.resolve("that topic", b.state).resolved_value == "beta"


class TestNoExecution:
    """Resolver does not execute or approve anything."""

    def test_resolver_has_no_execute(self, resolver):
        assert not hasattr(resolver, "execute")
        assert not hasattr(resolver, "approve")
        assert not hasattr(resolver, "promote")

    def test_result_has_no_execute(self, resolver):
        result = resolver.resolve("that topic", ConversationState())
        assert not hasattr(result, "execute")


class TestSerialization:
    """Result is serializable."""

    def test_to_dict_json_safe(self, resolver):
        state = ConversationState(current_subject="auth")
        result = resolver.resolve("that topic", state)
        d = result.to_dict()
        assert d["status"] == "resolved"
        assert d["query"] == "that topic"
        assert d["resolved_field"] == "current_subject"
        assert d["resolved_value"] == "auth"
        for v in d.values():
            assert isinstance(v, (str, list, type(None)))


class TestAdversarialWording:
    """Adversarial/ambiguous wording never silently selects a candidate."""

    def test_mixed_yes_no_ambiguous(self, resolver):
        state = ConversationState(
            current_task="task-1",
            relevant_prior_action="action-a",
        )
        result = resolver.resolve("do that again", state)
        assert result.status == ReferenceResolutionStatus.AMBIGUOUS
        assert result.resolved_value is None

    def test_generic_reference_with_multiple_state(self, resolver):
        state = ConversationState(
            current_subject="auth",
            current_task="task-1",
            current_investigation="inv-1",
        )
        # "continue" maps to task/investigation/development_intent
        result = resolver.resolve("continue", state)
        assert result.status == ReferenceResolutionStatus.AMBIGUOUS
        assert len(result.candidates) >= 2
