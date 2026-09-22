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
    has_bounded_reference,
)
from atlas.conversation.conversation_context import (
    MAX_CONTEXT_TURNS,
    build_conversation_context,
)
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationService
from atlas.conversation.message import Message
from atlas.conversation.task_intake import TaskIntake


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


class TestResultQualifierAliases:
    """Bounded aliases for the single retained result (no result history).

    Atlas keeps exactly one result in ``ConversationState``. These qualifier
    forms add reference *coverage* to that single value; they do not express
    genuine historical ordering and must fail closed when no result exists.
    """

    _STATE = ConversationState(latest_result="result-1")

    @pytest.mark.parametrize(
        "text",
        [
            "the previous result",
            "the last result",
            "the prior result",
            "What about the previous result?",
            "What about the last result?",
            "What about the prior result?",
        ],
    )
    def test_qualifier_forms_resolve_to_latest_result(self, resolver, text):
        result = resolver.resolve(text, self._STATE)
        assert result.status == ReferenceResolutionStatus.RESOLVED
        assert result.resolved_field == "latest_result"
        assert result.resolved_value == "result-1"

    @pytest.mark.parametrize(
        "text",
        ["the previous result", "the last result", "the prior result"],
    )
    def test_qualifier_forms_fail_closed_without_result(self, resolver, text):
        result = resolver.resolve(text, ConversationState())
        assert result.status == ReferenceResolutionStatus.UNRESOLVED
        assert result.resolved_field is None
        assert result.resolved_value is None

    @pytest.mark.parametrize(
        "text",
        ["the previous result", "the last result", "the prior result"],
    )
    def test_qualifier_forms_are_bounded_multi_word(self, text):
        assert has_bounded_reference(text) is True

    @pytest.mark.parametrize(
        "text", ["the last results", "the previous results", "prior results"]
    )
    def test_plural_forms_are_not_captured(self, resolver, text):
        result = resolver.resolve(text, self._STATE)
        assert result.status == ReferenceResolutionStatus.UNRESOLVED

    def test_alias_selects_the_only_retained_result(self, resolver):
        # There is no result history: the qualifier is not a history claim and
        # must bind the one retained value.
        result = resolver.resolve("the previous result", self._STATE)
        assert result.resolved_value == "result-1"


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


# ---------------------------------------------------------------------------
# C7 GAP-C31-02 — word-boundary matching (substring false positives removed)
# ---------------------------------------------------------------------------


class TestWordBoundaryMatching:
    """Triggers must match as whole words, never as ordinary-word substrings."""

    _STATE = ConversationState(
        current_subject="auth",
        current_task="task-1",
        current_investigation="inv-1",
        relevant_prior_action="action-a",
        latest_result="result-1",
    )

    @pytest.mark.parametrize(
        "text",
        [
            "What is the priority of the release?",      # "priority" contains "it"
            "Is the architecture documented?",           # "architecture" contains "it"
            "How is the quality of the output?",         # "quality" contains "it"
            "Please summarise the repository structure.",  # "repository" contains "it"
            "We voted against the rule.",                # "against" contains "again"
        ],
    )
    def test_substring_false_positives_eliminated(self, resolver, text):
        result = resolver.resolve(text, self._STATE)
        assert result.status == ReferenceResolutionStatus.UNRESOLVED

    @pytest.mark.parametrize(
        "text,field,value",
        [
            ("that investigation", "current_investigation", "inv-1"),
            ("the investigation", "current_investigation", "inv-1"),
            ("that result", "latest_result", "result-1"),
            ("the result", "latest_result", "result-1"),
            ("the findings", "latest_result", "result-1"),
        ],
    )
    def test_bounded_multi_word_references_still_resolve(
        self, resolver, text, field, value
    ):
        result = resolver.resolve(text, self._STATE)
        assert result.status == ReferenceResolutionStatus.RESOLVED
        assert result.resolved_field == field
        assert result.resolved_value == value

    def test_ambiguous_reference_unchanged(self, resolver):
        result = resolver.resolve("what did you find?", self._STATE)
        assert result.status == ReferenceResolutionStatus.AMBIGUOUS

    def test_repeated_matching_is_deterministic(self, resolver):
        a = resolver.resolve("that investigation", self._STATE)
        b = resolver.resolve("that investigation", self._STATE)
        assert (a.status, a.resolved_field, a.resolved_value) == (
            b.status, b.resolved_field, b.resolved_value
        )


class TestBoundedReferenceGuard:
    """`has_bounded_reference` gates production invocation to multi-word forms."""

    @pytest.mark.parametrize(
        "text",
        [
            "Based on that investigation, what should I do next?",
            "what did you find?",
            "Continue with that task.",
            "run it again",
        ],
    )
    def test_multi_word_phrases_detected(self, text):
        assert has_bounded_reference(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "What is the priority of the release?",
            "Is the architecture documented?",
            "How is the quality?",
            "Please summarise the repository structure.",
            "We voted against the rule.",
            "Can you explain it?",
            "Is this correct?",
            "Which of those components depend on it?",
            "",
            "   ",
        ],
    )
    def test_single_word_and_false_positives_not_detected(self, text):
        assert has_bounded_reference(text) is False


# ---------------------------------------------------------------------------
# Phase 4 — bounded contextual reference resolution
# ---------------------------------------------------------------------------

_INVESTIGATION = "Investigate the conversation system."


def _turn(role: str, content: str) -> Message:
    return Message(role=role, content=content)


def _context(*user_turns: str):
    messages: list[Message] = []
    for text in user_turns:
        messages.append(_turn("user", text))
        messages.append(_turn("assistant", "(response)"))
    return build_conversation_context(messages)


class _FailingAI:
    def chat(self, prompt, routing_context=None):
        raise RuntimeError("No AI available")

    def stream_chat(self, prompt, routing_context=None):
        def _g():
            raise RuntimeError("No AI available")
            yield ""  # pragma: no cover

        return _g()


class TestContextualReferenceResolution:
    def test_explicit_phrase_unique_candidate_resolved(self, resolver):
        context = _context(_INVESTIGATION)
        state = ConversationState(current_investigation=_INVESTIGATION)
        result = resolver.resolve_contextual(
            "What about the conversation system?", context, state
        )
        assert result.status == ReferenceResolutionStatus.RESOLVED
        # The candidate is the ACTUAL stored state fact, so it is reported under
        # its real ConversationState field name (consumable), not the derived
        # ``context_subject`` label used for turn-derived referents.
        assert result.resolved_field == "current_investigation"
        assert "conversation system" in result.resolved_value

    def test_explicit_phrase_multiple_candidates_ambiguous(self, resolver):
        context = _context(
            _INVESTIGATION, "Investigate the conversation system cache."
        )
        result = resolver.resolve_contextual(
            "Tell me about the conversation system.", context, ConversationState()
        )
        assert result.status == ReferenceResolutionStatus.AMBIGUOUS
        assert len(result.candidates) == 2

    def test_explicit_phrase_no_candidate_unresolved(self, resolver):
        result = resolver.resolve_contextual(
            "Tell me about the capability handler.", _context(), ConversationState()
        )
        assert result.status == ReferenceResolutionStatus.UNRESOLVED

    def test_bare_it_unique_antecedent_resolved(self, resolver):
        context = _context(_INVESTIGATION)
        state = ConversationState(current_investigation=_INVESTIGATION)
        result = resolver.resolve_contextual("Can you check it?", context, state)
        assert result.status == ReferenceResolutionStatus.RESOLVED
        assert "conversation system" in result.resolved_value

    def test_bare_it_multiple_antecedents_ambiguous(self, resolver):
        context = _context(_INVESTIGATION, "Investigate the capability handler.")
        result = resolver.resolve_contextual(
            "Can you check it?", context, ConversationState()
        )
        assert result.status == ReferenceResolutionStatus.AMBIGUOUS
        assert len(result.candidates) == 2

    def test_bare_that_without_candidate_unresolved(self, resolver):
        result = resolver.resolve_contextual(
            "What about that?", _context(), ConversationState()
        )
        assert result.status == ReferenceResolutionStatus.UNRESOLVED

    def test_bare_this_without_candidate_unresolved(self, resolver):
        result = resolver.resolve_contextual(
            "Is this ready?", _context("hello there"), ConversationState()
        )
        assert result.status == ReferenceResolutionStatus.UNRESOLVED

    def test_bare_reference_not_resolved_from_non_subject_turn(self, resolver):
        result = resolver.resolve_contextual(
            "Can you check it?", _context("hello"), ConversationState()
        )
        assert result.status == ReferenceResolutionStatus.UNRESOLVED

    def test_subject_beyond_context_bound_not_used(self, resolver):
        messages: list[Message] = [
            _turn("user", _INVESTIGATION),
            _turn("assistant", "ok"),
        ]
        messages.extend(_turn("user", f"filler {index}") for index in range(12))
        context = build_conversation_context(messages)
        assert len(context.recent_turns) == MAX_CONTEXT_TURNS
        result = resolver.resolve_contextual(
            "Look into that.", context, ConversationState()
        )
        assert result.status == ReferenceResolutionStatus.UNRESOLVED

    def test_resolver_does_not_mutate_context(self, resolver):
        context = _context(_INVESTIGATION)
        before = context.to_dict()
        resolver.resolve_contextual("Look into that.", context, ConversationState())
        assert context.to_dict() == before

    def test_resolver_does_not_mutate_state_manager(self, resolver):
        manager = ConversationStateManager()
        manager.update(current_investigation=_INVESTIGATION)
        state = manager.state
        resolver.resolve_contextual("Look into that.", _context(_INVESTIGATION), state)
        assert manager.state is state
        assert manager.state.current_investigation == _INVESTIGATION

    def test_resolver_does_not_execute_anything(self, resolver):
        assert not hasattr(resolver, "execute")
        result = resolver.resolve_contextual(
            "Look into that.",
            _context(_INVESTIGATION),
            ConversationState(current_investigation=_INVESTIGATION),
        )
        assert isinstance(result, ReferenceResolutionResult)
        assert not hasattr(result, "execute")

    @pytest.mark.parametrize("text", [
        "How is the quality of the output?",
        "We voted against the rule.",
        "Please summarise the repository structure.",
    ])
    def test_false_positives_unresolved(self, resolver, text):
        result = resolver.resolve_contextual(
            text, _context(text), ConversationState()
        )
        assert result.status == ReferenceResolutionStatus.UNRESOLVED

    def test_resolution_is_deterministic(self, resolver):
        context = _context(_INVESTIGATION)
        state = ConversationState(current_investigation=_INVESTIGATION)
        first = resolver.resolve_contextual("Can you check it?", context, state)
        second = resolver.resolve_contextual("Can you check it?", context, state)
        assert first == second


class TestContextualReferenceIntegration:
    def _service(self, investigation: bool = False) -> ConversationService:
        return ConversationService(
            _FailingAI(),
            task_intake=TaskIntake(),
            investigation_service=InvestigationService() if investigation else None,
        )

    def test_scenario_a_unique_context_reference_attaches_evidence(self):
        service = self._service()
        service.state_manager.update(current_investigation=_INVESTIGATION)
        spec = TaskIntake().intake("What about the conversation system?")
        out_spec, response = service._apply_reference_resolution(
            spec, "What about the conversation system?"
        )
        assert response is None
        assert (
            out_spec.context["resolved_reference"]["field"]
            == "current_investigation"
        )
        assert "conversation system" in out_spec.context["resolved_reference"]["value"]

    def test_scenario_b_ambiguous_context_reference_does_not_guess(self):
        service = self._service()
        service.state_manager.update(
            current_investigation="Investigate the capability handler."
        )
        service._conversation.add_message(_turn("user", _INVESTIGATION))
        service._conversation.add_message(_turn("assistant", "ok"))
        service._conversation.add_message(
            _turn("user", "Investigate the capability handler.")
        )
        service._conversation.add_message(_turn("assistant", "ok"))
        spec = TaskIntake().intake("Look into that.")
        out_spec, response = service._apply_reference_resolution(
            spec, "Look into that."
        )
        assert out_spec is spec  # unchanged: no arbitrary choice
        assert response is None

    def test_scenario_c_no_context_is_unresolved(self):
        service = self._service()
        spec = TaskIntake().intake("Look into that.")
        out_spec, response = service._apply_reference_resolution(
            spec, "Look into that."
        )
        assert out_spec is spec
        assert response is None

    def test_scenario_d_governed_investigation_still_runs(self):
        service = self._service(investigation=True)
        response = service.send(_INVESTIGATION)
        assert "Investigation" in response.content

    def test_scenario_e_builtin_capability_unchanged(self):
        from atlas.conversation.builtin_response import BuiltinResponseService

        service = ConversationService(
            _FailingAI(),
            task_intake=TaskIntake(),
            builtin_response=BuiltinResponseService(),
        )
        message = service.send("What can you currently do?")
        assert message.metadata.get("builtin_intent") == "capabilities"

    def test_resolution_does_not_invoke_handlers(self, monkeypatch):
        service = self._service()
        service.state_manager.update(current_investigation=_INVESTIGATION)
        calls: list[int] = []
        monkeypatch.setattr(
            service, "_maybe_handle_investigation_request", lambda *a, **k: calls.append(1)
        )
        spec = TaskIntake().intake("What about the conversation system?")
        service._apply_reference_resolution(
            spec, "What about the conversation system?"
        )
        assert calls == []

    def test_existing_lexicon_reference_unchanged(self):
        service = self._service()
        service.state_manager.update(current_investigation="memory architecture")
        spec = TaskIntake().intake("Based on that investigation, what next?")
        out_spec, response = service._apply_reference_resolution(
            spec, "Based on that investigation, what next?"
        )
        assert response is None
        assert out_spec.context["resolved_reference"] == {
            "field": "current_investigation",
            "value": "memory architecture",
        }

    def test_no_contextual_reference_spec_unchanged(self):
        service = self._service()
        spec = TaskIntake().intake("How is the quality of the output?")
        out_spec, response = service._apply_reference_resolution(
            spec, "How is the quality of the output?"
        )
        assert out_spec is spec
        assert response is None
