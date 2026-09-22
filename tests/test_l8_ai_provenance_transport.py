"""L8-b-i — per-response AI provenance transport.

The AI layer already attaches ``provider``/``model`` to every ``AIResponse``;
the runtime's AI_RESPONSE stage now records that identity in its stage data and
CognitionService exposes it as a bounded ``ai_provenance`` mapping. Behaviour is
unchanged: nothing consumes the value, routing/provider selection is untouched,
and missing identity is represented conservatively.
"""

from __future__ import annotations

import inspect
import json

from atlas.cognition.api import CognitionAPI
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.task_intake import TaskIntake
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.planning import PlanningEngine
from atlas.runtime.runtime_coordinator import (
    _MAX_PROVIDER_ID_CHARS,
    RuntimeCoordinator,
)
from atlas.services.cognition_service import CognitionService

TEXT = "What should I work on next?"
AMBIGUOUS = "Build it."


class _Response:
    def __init__(self, text: str, provider=None, model=None) -> None:
        self.text = text
        if provider is not None:
            self.provider = provider
        if model is not None:
            self.model = model


class _StubAI:
    """Duck-typed ai_service recording the call shape and identity."""

    def __init__(self, text="STUB PIPELINE ANSWER", provider="Stub Provider",
                 model="stub-1", with_identity=True) -> None:
        self._text = text
        self._provider = provider
        self._model = model
        self._with_identity = with_identity
        self.routing_contexts: list[object] = []

    def chat(self, messages, routing_context=None):
        self.routing_contexts.append(routing_context)
        if self._with_identity:
            return _Response(self._text, self._provider, self._model)
        return _Response(self._text)


def _coordinator(ai_service=None) -> RuntimeCoordinator:
    registry = CapabilityRegistry()
    registry.register(
        "conversation",
        lambda p: ExecutionResult(capability="conversation", success=True, output={}),
    )
    return RuntimeCoordinator(
        reasoning_controller=ReasoningController(),
        capability_analyzer=CapabilityAnalyzer(),
        capability_registry=registry,
        capability_router=CapabilityRouter(registry),
        capability_dispatcher=CapabilityDispatcher(registry),
        planning_engine=PlanningEngine(),
        ai_service=ai_service,
    )


def _api(ai_service=None) -> CognitionAPI:
    service = CognitionService(
        runtime_coordinator=_coordinator(ai_service=ai_service)
    )
    service.start()
    return CognitionAPI(cognition_service=service)


def _run(text: str = TEXT, ai_service=None):
    from atlas.conversation.turn_meaning import build_turn_meaning

    spec = TaskIntake().intake(text)
    tm = build_turn_meaning(spec, text)
    coordinator = _coordinator(ai_service=ai_service)
    result = coordinator.process(
        user_input=text, goal=spec.goal_string(), turn_meaning=tm
    )
    service = CognitionService(runtime_coordinator=coordinator)
    service.start()
    decision = CognitionAPI(cognition_service=service).process(
        user_input=text, goal=spec.goal_string(), turn_meaning=tm
    )
    return result, decision


def _stage(result, name):
    return next(s for s in result.stages if s.stage.name == name)


class TestStageDataCarriesIdentity:
    def test_ai_stage_data_carries_length_provider_and_model(self):
        stub = _StubAI("STUB PIPELINE ANSWER")
        result, _decision = _run(ai_service=stub)
        assert _stage(result, "AI_RESPONSE").data == {
            "response_length": len("STUB PIPELINE ANSWER"),
            "provider": "Stub Provider",
            "model": "stub-1",
        }

    def test_existing_response_text_behaviour_is_unchanged(self):
        result, decision = _run(ai_service=_StubAI("STUB PIPELINE ANSWER"))
        assert result.final_response == "STUB PIPELINE ANSWER"
        assert decision.data["final_response"] == "STUB PIPELINE ANSWER"

    def test_routing_call_shape_is_unchanged(self):
        # The provider-selection path is untouched: every call still receives a
        # routing context, exactly as before this transport. ``_run`` executes
        # the pipeline twice (once directly for stage data, once via the API).
        stub = _StubAI()
        _run(ai_service=stub)
        assert stub.routing_contexts
        assert all(ctx is not None for ctx in stub.routing_contexts)
        assert stub.routing_contexts[0].complexity == 0.3


class TestDecisionProvenanceShape:
    def test_decision_exposes_bounded_ai_provenance(self):
        _result, decision = _run(ai_service=_StubAI())
        assert decision.data["ai_provenance"] == {
            "provider": "Stub Provider",
            "model": "stub-1",
        }

    def test_identity_is_whitespace_collapsed_and_bounded(self):
        _result, decision = _run(
            ai_service=_StubAI(provider="  Stub   Provider  ", model="m")
        )
        assert decision.data["ai_provenance"]["provider"] == "Stub Provider"

        _result, decision = _run(
            ai_service=_StubAI(provider="p" * (_MAX_PROVIDER_ID_CHARS + 50))
        )
        assert len(decision.data["ai_provenance"]["provider"]) == _MAX_PROVIDER_ID_CHARS

    def test_json_safe(self):
        _result, decision = _run(ai_service=_StubAI())
        json.dumps(decision.data)

    def test_deterministic(self):
        first = _run(ai_service=_StubAI())[1].data
        second = _run(ai_service=_StubAI())[1].data
        assert first["ai_provenance"] == second["ai_provenance"]
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


class TestMissingProvenanceIsConservative:
    def test_provider_free_execution_does_not_fabricate_provenance(self):
        result, decision = _run(ai_service=None)
        assert _stage(result, "AI_RESPONSE").status.name == "SKIPPED"
        assert decision.data["ai_provenance"] == {}
        assert decision.data["final_response"] == ""

    def test_response_without_identity_attributes_is_conservative(self):
        _result, decision = _run(ai_service=_StubAI(with_identity=False))
        assert decision.data["final_response"] == "STUB PIPELINE ANSWER"
        assert decision.data["ai_provenance"] == {}

    def test_blank_identity_is_conservative(self):
        for provider, model in (("", ""), ("   ", "  "), (None, None)):
            _result, decision = _run(
                ai_service=_StubAI(provider=provider, model=model)
            )
            assert decision.data["ai_provenance"] == {}, (provider, model)

    def test_model_is_never_reported_without_a_provider(self):
        _result, decision = _run(ai_service=_StubAI(provider="", model="orphan"))
        assert decision.data["ai_provenance"] == {}


class TestExistingPayloadsUnchanged:
    def test_planning_reasoning_and_key_set(self):
        result, decision = _run(ai_service=_StubAI())
        data = decision.data
        assert data["planning"] == _stage(result, "PLANNING").data
        assert set(data["reasoning"]) == {
            "goal", "capabilities", "routes", "results", "meaning",
        }
        base = {
            "input", "memory_count", "knowledge_count",
            "understanding_insights_count", "reasoning", "planning",
        }
        assert base <= set(data)
        # Exactly the two L8 keys were added by L8-a/L8-b-i.
        assert set(data) - {"final_response", "ai_provenance", "tool_results"} == base

    def test_l6_blocked_behaviour_is_unchanged(self):
        _result, decision = _run(AMBIGUOUS, ai_service=_StubAI())
        planning = decision.data["planning"]
        assert planning["status"] == "blocked"
        assert planning["steps"] == []
        assert planning["results"] == []
        assert planning["requires_clarification"] is True
        # Provenance transport does not gate or unblock anything.
        assert decision.data["ai_provenance"] == {
            "provider": "Stub Provider", "model": "stub-1",
        }

    def test_provenance_classification_is_not_inlined_in_the_service(self):
        # L8-b-ii consumes the payload through the module-level precedence
        # helper; the conversation service class inlines neither the payload key
        # nor the provider-name contract (no duplicated authority).
        source = inspect.getsource(ConversationService)
        assert "ai_provenance" not in source
        assert "LOCAL_PROVIDER_NAMES" not in source
        assert "Mock Provider" not in source

    def test_user_visible_floor_is_unchanged(self):
        from atlas.conversation.builtin_response import BuiltinResponseService

        text = "What should I work on next?"
        spec = TaskIntake().intake(text)
        baseline = BuiltinResponseService().respond(
            text, spec=spec, message_count=0, context=None
        )
        service = ConversationService(
            _StubAI(), task_intake=TaskIntake(),
            builtin_response=BuiltinResponseService(),
        )
        assert service.send(text).content == baseline.content
