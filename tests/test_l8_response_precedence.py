"""L8-b-ii + L8-c — deterministic response precedence and bounded delegation.

Final L8 contract:

  * the deterministic floor keeps first opportunity (unchanged cascade);
  * L6 is an absolute fail-closed veto;
  * a turn the floor could not answer is delegated to cognition only when the
    existing L7 ``reasoning_eligibility`` signal permits it and cognition is
    wired;
  * a trustworthy (non-local-provider, non-blocked, non-empty) pipeline answer
    becomes the single user-facing response and the conversation-level AI call
    is skipped;
  * anything else (empty, L6-blocked, local Mock tier) is never surfaced and the
    existing deterministic fallback chain stays terminal — with no second AI
    invocation.
"""

from __future__ import annotations

import json

from atlas.cognition.api import CognitionAPI
from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import (
    ConversationService,
    _usable_pipeline_response,
)
from atlas.conversation.investigation import InvestigationService
from atlas.conversation.message import Message
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.planning import PlanningEngine
from atlas.runtime.runtime_coordinator import RuntimeCoordinator
from atlas.services.cognition_service import CognitionService

ELIGIBLE = "What should I work on next?"
GREETING = "Hello Atlas."
AMBIGUOUS = "Build it."

NON_LOCAL = ("Stub Provider", "stub-1")
LOCAL_TIER = ("Mock Provider", "atlas-mock-v1")


class _Response:
    def __init__(self, text, provider=None, model=None) -> None:
        self.text = text
        if provider is not None:
            self.provider = provider
        if model is not None:
            self.model = model


class _AI:
    """Duck-typed ai_service counting invocations."""

    def __init__(self, text="CHAT ANSWER", identity=None) -> None:
        self._text = text
        self._identity = identity
        self.calls = 0

    def chat(self, messages, routing_context=None):
        self.calls += 1
        prov, model = self._identity or (None, None)
        return _Response(self._text, prov, model)

    def stream_chat(self, messages, routing_context=None):
        self.calls += 1
        yield self._text


class _RecordingAPI:
    def __init__(self, inner) -> None:
        self._inner = inner
        self.calls: list[str] = []

    def process(self, user_input, memory=None, metadata=None, goal=None,
                turn_meaning=None):
        self.calls.append(user_input)
        return self._inner.process(
            user_input=user_input, memory=memory, metadata=metadata,
            goal=goal, turn_meaning=turn_meaning,
        )


def _pipeline(ai_service=None) -> CognitionAPI:
    registry = CapabilityRegistry()
    registry.register("conversation", lambda p: ExecutionResult(
        capability="conversation", success=True, output={}))
    coordinator = RuntimeCoordinator(
        reasoning_controller=ReasoningController(),
        capability_analyzer=CapabilityAnalyzer(),
        capability_registry=registry,
        capability_router=CapabilityRouter(registry),
        capability_dispatcher=CapabilityDispatcher(registry),
        planning_engine=PlanningEngine(),
        ai_service=ai_service,
    )
    service = CognitionService(runtime_coordinator=coordinator)
    service.start()
    return CognitionAPI(cognition_service=service)


def _service(pipeline_answer="PIPELINE ANSWER", identity=NON_LOCAL,
             cognition=True, chat_ai=None):
    api = _pipeline(ai_service=_AI(pipeline_answer, identity))
    recording = _RecordingAPI(api) if cognition else None
    service = ConversationService(
        chat_ai or _AI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        cognition_api=recording,
        # Mirrors the kernel wiring: an ACTION/INFORMATION request whose target
        # cannot be resolved yields the orchestration clarification (and, for an
        # L6-blocked turn, the clarification gate) before cognition.
        orchestration_resolver=lambda spec, session_context: None,
        development_bridge=lambda spec: Message(
            role="assistant", content="DEVELOPMENT BRIDGE"
        ),
        investigation_service=InvestigationService(),
    )
    return service, recording


class TestBoundedDelegation:
    def test_eligible_turn_reaches_cognition(self):
        service, recording = _service()
        message = service.send(ELIGIBLE)
        assert recording.calls == [ELIGIBLE]
        assert message.content == "PIPELINE ANSWER"

    def test_eligibility_signal_is_required_for_delegation(self):
        # Same unsupported floor outcome, no eligibility signal (a statement
        # rather than a question/request) -> the floor stays terminal.
        service, recording = _service()
        message = service.send("...")
        assert recording.calls == []
        assert message.metadata.get("builtin_intent") == "unsupported"

    def test_greeting_never_reaches_cognition(self):
        service, recording = _service()
        message = service.send(GREETING)
        assert recording.calls == []
        assert message.metadata.get("builtin_intent") == "greeting"

    def test_without_a_cognition_boundary_the_floor_stays_terminal(self):
        service, _recording = _service(cognition=False)
        message = service.send(ELIGIBLE)
        assert message.metadata.get("builtin_intent") == "unsupported"

    def test_governed_turns_keep_their_existing_handlers(self):
        service, recording = _service()
        expectations = (
            ("Add a capability for scheduled follow-ups.", "DEVELOPMENT BRIDGE"),
            ("Investigate why Atlas cannot answer this question.", "Investigation"),
            ("Research how Atlas currently handles references.",
             "I need a bit more detail before I can run this."),
            ("approve this proposal", "approval"),
        )
        for text, marker in expectations:
            message = service.send(text)
            assert marker.lower() in message.content.lower(), text
        # No governed turn was delegated to cognition.
        assert recording.calls == []

    def test_ambiguous_turn_stays_fail_closed(self):
        service, recording = _service()
        message = service.send(AMBIGUOUS)
        assert recording.calls == []
        assert "more detail" in message.content


class TestResponsePrecedence:
    def test_trustworthy_non_local_answer_is_surfaced(self):
        service, _recording = _service()
        message = service.send(ELIGIBLE)
        assert message.content == "PIPELINE ANSWER"
        assert message.role == "assistant"

    def test_double_ai_invocation_is_eliminated(self):
        chat_ai = _AI()
        service, _recording = _service(chat_ai=chat_ai)
        service.send(ELIGIBLE)
        assert chat_ai.calls == 0

    def test_local_mock_answer_is_never_surfaced(self):
        service, _recording = _service(identity=LOCAL_TIER)
        message = service.send(ELIGIBLE)
        assert "Mock" not in message.content
        assert "first AI provider" not in message.content
        assert message.metadata.get("builtin_intent") == "unsupported"

    def test_local_mock_case_does_not_call_the_ai_again(self):
        chat_ai = _AI()
        service, _recording = _service(identity=LOCAL_TIER, chat_ai=chat_ai)
        service.send(ELIGIBLE)
        assert chat_ai.calls == 0

    def test_empty_pipeline_answer_uses_the_deterministic_fallback(self):
        service, _recording = _service(pipeline_answer="")
        message = service.send(ELIGIBLE)
        assert message.metadata.get("builtin_intent") == "unsupported"
        assert message.metadata.get("fallback_after_provider_failure") is True

    def test_missing_identity_is_not_surfaced(self):
        service, _recording = _service(identity=None)
        message = service.send(ELIGIBLE)
        assert message.content != "PIPELINE ANSWER"
        assert message.metadata.get("builtin_intent") == "unsupported"

    def test_provider_free_pipeline_follows_the_fallback(self):
        api = _pipeline(ai_service=None)
        recording = _RecordingAPI(api)
        chat_ai = _AI()
        service = ConversationService(
            chat_ai, task_intake=TaskIntake(),
            builtin_response=BuiltinResponseService(),
            cognition_api=recording,
        )
        message = service.send(ELIGIBLE)
        assert recording.calls == [ELIGIBLE]
        assert message.metadata.get("builtin_intent") == "unsupported"
        assert chat_ai.calls == 0

    def test_exactly_one_user_visible_message_is_produced(self):
        service, _recording = _service()
        service.send(ELIGIBLE)
        messages = service.conversation.messages
        assert [m.role for m in messages] == ["user", "assistant"]
        assert messages[-1].content == "PIPELINE ANSWER"

    def test_internal_structures_are_not_exposed(self):
        service, _recording = _service()
        message = service.send(ELIGIBLE)
        assert set(message.metadata) == {"cognition"}
        assert set(message.metadata["cognition"]) == {"source"}
        text = message.content
        for internal in ("planning", "capabilities", "respond:", "final_response"):
            assert internal not in text

    def test_l6_blocked_pipeline_payload_is_not_usable(self):
        blocked = {
            "final_response": "PIPELINE ANSWER",
            "ai_provenance": {"provider": "Stub Provider"},
            "planning": {"status": "blocked", "requires_clarification": True},
        }
        assert _usable_pipeline_response(blocked) is None
        clarified = {
            "final_response": "PIPELINE ANSWER",
            "ai_provenance": {"provider": "Stub Provider"},
            "reasoning": {"requires_clarification": True},
        }
        assert _usable_pipeline_response(clarified) is None

    def test_usable_requires_all_conditions(self):
        base = {"final_response": "A", "ai_provenance": {"provider": "Stub"}}
        assert _usable_pipeline_response(base) == "A"
        assert _usable_pipeline_response({**base, "final_response": ""}) is None
        assert _usable_pipeline_response({**base, "ai_provenance": {}}) is None
        assert _usable_pipeline_response(
            {**base, "ai_provenance": {"provider": "Mock Provider"}}
        ) is None
        # NLU-0: a real provider's provenance is accepted; the deterministic
        # no-network tier's is rejected by the same existing rule. The rule
        # itself is unchanged.
        assert _usable_pipeline_response(
            {**base, "ai_provenance": {"provider": "Ollama", "model": "qwen3:8b"}}
        ) == "A"
        assert _usable_pipeline_response(
            {**base, "ai_provenance": {"provider": "Mock Provider", "model": "atlas-mock-v1"}}
        ) is None
        assert _usable_pipeline_response("not-a-dict") is None


class TestStreamParity:
    def test_stream_surfaces_the_same_trustworthy_answer(self):
        chat_ai = _AI()
        service, _recording = _service(chat_ai=chat_ai)
        assert "".join(service.stream(ELIGIBLE)) == "PIPELINE ANSWER"
        assert chat_ai.calls == 0

    def test_stream_rejects_the_local_tier_like_send(self):
        chat_ai = _AI()
        service, _recording = _service(identity=LOCAL_TIER, chat_ai=chat_ai)
        streamed = "".join(service.stream(ELIGIBLE))
        assert "first AI provider" not in streamed
        assert chat_ai.calls == 0
        assert streamed == service.send(ELIGIBLE).content


class TestBoundariesPreserved:
    def test_meaning_still_propagates_into_planning(self):
        captured = {}

        class _CapturingAPI(_RecordingAPI):
            def process(self, *args, **kwargs):
                decision = super().process(*args, **kwargs)
                captured["planning"] = decision.data.get("planning")
                return decision

        api = _CapturingAPI(_pipeline(ai_service=_AI("PIPELINE ANSWER", NON_LOCAL)))
        service = ConversationService(
            _AI(), task_intake=TaskIntake(),
            builtin_response=BuiltinResponseService(),
            cognition_api=api,
        )
        service.send(ELIGIBLE)
        assert captured["planning"]["meaning"]["task_type"] == "question"
        assert captured["planning"].get("requires_clarification") is not True

    def test_l4_l5_and_l6_intake_contracts_are_intact(self):
        intake = TaskIntake()
        spec = intake.intake("Build a module that tracks long-running tasks.")
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert "reference" not in spec.ambiguity.ambiguities
        assert intake.intake(AMBIGUOUS).needs_clarification is True

    def test_metadata_and_history_contracts_are_valid(self):
        service, _recording = _service()
        service.send(ELIGIBLE)
        assistant = service.conversation.messages[-1]
        assert isinstance(assistant, Message)
        json.dumps(assistant.metadata)
        assert assistant.metadata["cognition"]["source"] == "pipeline_final_response"

    def test_deterministic_across_runs(self):
        first, _r1 = _service()
        second, _r2 = _service()
        assert first.send(ELIGIBLE).content == second.send(ELIGIBLE).content
