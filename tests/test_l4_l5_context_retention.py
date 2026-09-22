"""L4/L5 — contextual reference interface, research retention and development
antecedent projection.

Covers the three smallest fixes identified by the L4/L5 boundary investigation:

  A. a contextual referent that IS a stored ConversationState fact is reported
     under that real field name (consumable), while turn-derived referents keep
     the bounded ``context_subject`` label;
  B. a COMPLETED orchestration/research result is retained in the existing
     ``latest_result`` slot so the existing findings reference pattern resolves;
  C. a reference-only development follow-up uses the resolved antecedent as its
     operand instead of the unresolved surface phrase, without clobbering the
     antecedent.

L3, L6 ambiguity, L8 composition and governance are untouched.
"""

from __future__ import annotations

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import ConversationState
from atlas.conversation.investigation import InvestigationService
from atlas.conversation.message import Message
from atlas.conversation.reference_resolution import ReferenceResolutionStatus
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.conversation.utterance_meaning import UTTERANCE_MEANING_KEY


class _FailingAI:
    def chat(self, prompt, routing_context=None):
        raise RuntimeError("No AI available")

    def stream_chat(self, prompt, routing_context=None):
        def _gen():
            raise RuntimeError("No AI available")
            yield ""  # pragma: no cover

        return _gen()


class _RecordingBridge:
    """Records every development spec handed to the governed bridge."""

    def __init__(self) -> None:
        self.calls: list[object] = []

    def __call__(self, spec):
        self.calls.append(spec)
        return Message(role="assistant", content="BRIDGED")


def _service(**kwargs) -> ConversationService:
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        **kwargs,
    )


def _state_keys(state: ConversationState) -> set[str]:
    return set(state.to_dict())


# ---------------------------------------------------------------------------
# A — L4 contextual reference interface
# ---------------------------------------------------------------------------


class TestContextualReferenceInterface:
    def test_investigation_antecedent_is_consumable(self):
        service = _service(investigation_service=InvestigationService())

        turn1 = service.send("Investigate why Atlas cannot answer this question.")
        target = service.state_manager.state.current_investigation
        assert target  # T1 still populates the investigation slot
        assert turn1.metadata.get("investigation") is not None

        spec = service._intake("What is causing it?", 2)
        spec, response = service._apply_reference_resolution(spec, "What is causing it?")

        assert response is None
        assert spec.task_type is TaskType.QUESTION
        resolved = spec.context["resolved_reference"]
        assert resolved["field"] == "current_investigation"
        assert resolved["value"] == target
        assert resolved["field"] != "context_subject"

    def test_investigation_antecedent_reaches_the_consumer(self):
        service = _service(investigation_service=InvestigationService())
        service.send("Investigate why Atlas cannot answer this question.")
        target = service.state_manager.state.current_investigation

        message = service.send("What is causing it?")

        # The reference-restatement path recognizes the real state field and no
        # longer discards the resolution; nothing else about the turn changes.
        assert message.metadata.get("reference_field") == "current_investigation"
        assert target in message.content

    def test_turn_derived_referent_keeps_the_derived_label(self):
        from atlas.conversation.conversation_context import build_conversation_context

        service = _service()
        context = build_conversation_context(
            [
                Message(role="user", content="Investigate the memory architecture."),
                Message(role="assistant", content="ok"),
            ]
        )
        result = service._reference_resolver.resolve_contextual(
            "Tell me about that", context, ConversationState()
        )
        assert result.status is ReferenceResolutionStatus.RESOLVED
        assert result.resolved_field == "context_subject"

    def test_bare_and_explicit_forms_still_resolve(self):
        service = _service()
        service.state_manager.update(current_subject="code_inspector")
        for text in ("what about that?", "is this ready?", "can you check it?"):
            result = service._reference_resolver.resolve_contextual(
                text, None, service.state_manager.state
            )
            assert result.status is ReferenceResolutionStatus.RESOLVED, text
            assert result.resolved_field == "current_subject", text

    def test_unresolved_and_ambiguous_are_unchanged(self):
        service = _service()
        unresolved = service._reference_resolver.resolve_contextual(
            "what about that?", None, ConversationState()
        )
        assert unresolved.status is ReferenceResolutionStatus.UNRESOLVED

        ambiguous = service._reference_resolver.resolve_contextual(
            "Tell me about that",
            None,
            ConversationState(current_subject="a", development_intent="b"),
        )
        assert ambiguous.status is ReferenceResolutionStatus.AMBIGUOUS


# ---------------------------------------------------------------------------
# B — L5 research/orchestration result retention
# ---------------------------------------------------------------------------


def _completed_research_resolver(spec, session_ctx):
    return Message(
        role="assistant",
        content="Done: research. Steps completed: 1/1. - step-0000: acquire ok.",
        metadata={"orchestration": {"status": "completed"}},
    )


class TestOrchestrationResultRetention:
    def test_completed_orchestration_retains_a_bounded_result(self):
        service = _service(orchestration_resolver=_completed_research_resolver)
        before = service.state_manager.state
        assert before.latest_result is None

        service.send("Research how Atlas currently handles references.")

        after = service.state_manager.state
        assert after.latest_result
        assert len(after.latest_result) <= 500
        assert "\n" not in after.latest_result

    def test_retention_adds_no_state_field(self):
        service = _service(orchestration_resolver=_completed_research_resolver)
        keys_before = _state_keys(ConversationState())
        service.send("Research how Atlas currently handles references.")
        assert _state_keys(service.state_manager.state) == keys_before

    def test_findings_reference_resolves_after_research(self):
        service = _service(orchestration_resolver=_completed_research_resolver)
        service.send("Research how Atlas currently handles references.")
        recorded = service.state_manager.state.latest_result

        spec = service._intake("What did you find?", 2)
        assert spec.task_type is TaskType.INFORMATION_REQUEST
        assert spec.context[UTTERANCE_MEANING_KEY]["illocution"] == "question"
        assert spec.context[UTTERANCE_MEANING_KEY]["operation"] == "research"

        result = service._reference_resolver.resolve("what did you find?", service.state_manager.state)
        assert result.status is ReferenceResolutionStatus.RESOLVED
        assert result.resolved_field == "latest_result"
        assert result.resolved_value == recorded

    def test_incomplete_orchestration_is_not_retained(self):
        def resolver(spec, session_ctx):
            return Message(
                role="assistant",
                content="needs clarification",
                metadata={"orchestration": {"status": "failed"}},
            )

        service = _service(orchestration_resolver=resolver)
        service.send("Research how Atlas currently handles references.")
        assert service.state_manager.state.latest_result is None


# ---------------------------------------------------------------------------
# C — L5 development antecedent projection
# ---------------------------------------------------------------------------


class TestDevelopmentAntecedentProjection:
    def test_reference_follow_up_uses_the_resolved_antecedent(self):
        bridge = _RecordingBridge()
        service = _service(development_bridge=bridge)

        first = service.send(
            "Develop an email notification capability for long-running tasks."
        )
        assert first.metadata.get("development_need_dialogue") is None
        assert len(bridge.calls) == 1
        antecedent = service.state_manager.state.development_intent
        assert antecedent
        assert antecedent == bridge.calls[0].goal

        second = service.send("Develop that capability.")

        assert len(bridge.calls) == 2
        follow_up = bridge.calls[1]
        assert follow_up.goal == antecedent
        assert follow_up.intent == antecedent
        assert "that capability" not in follow_up.goal.lower()
        # The antecedent survives the follow-up unchanged.
        assert service.state_manager.state.development_intent == antecedent
        assert service.state_manager.state.last_operation.operand == antecedent
        assert second is not None

    def test_explicit_new_intent_still_replaces_the_antecedent(self):
        bridge = _RecordingBridge()
        service = _service(development_bridge=bridge)

        service.send("Develop an email notification capability.")
        first_intent = service.state_manager.state.development_intent

        service.send("Develop a logging capability.")
        second_intent = service.state_manager.state.development_intent

        assert second_intent != first_intent
        assert second_intent == bridge.calls[1].goal
        assert len(bridge.calls) == 2

    def test_reference_only_question_does_not_mutate_the_antecedent(self):
        bridge = _RecordingBridge()
        service = _service(development_bridge=bridge)

        service.send("Develop an email notification capability.")
        antecedent = service.state_manager.state.development_intent

        message = service.send("How would that capability work?")

        assert _service_spec(service, "How would that capability work?").task_type is (
            TaskType.QUESTION
        )
        assert len(bridge.calls) == 1
        assert service.state_manager.state.development_intent == antecedent
        assert message is not None


def _service_spec(service: ConversationService, text: str):
    return service._intake(text, len(service.conversation.messages))
