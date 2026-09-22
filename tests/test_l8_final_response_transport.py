"""L8-a — pipeline ``final_response`` transport to the conversation layer.

The RuntimeCoordinator already produces ``PipelineResult.final_response``.
``CognitionService`` now transports it into the existing ``CognitionDecision.data``
payload. These tests pin that transport, its behaviour-neutrality, and the
*absence* of trustworthy provider/mock provenance at this boundary.
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
from atlas.runtime.runtime_coordinator import RuntimeCoordinator
from atlas.services.cognition_service import CognitionService

TEXT = "What should I work on next?"
AMBIGUOUS = "Build it."

#: Keys that would indicate a trustworthy "where did final_response come from"
#: signal. None of them exists at this boundary today (see the provenance test).
_PROVENANCE_KEYS = (
    "provider",
    "provider_name",
    "model_name",
    "is_mock",
    "final_response_source",
    "provenance",
)


class _Response:
    def __init__(self, text: str) -> None:
        self.text = text


class _StubAI:
    """Duck-typed ai_service returning a fixed answer."""

    def __init__(self, text: str = "STUB PIPELINE ANSWER") -> None:
        self._text = text
        self.calls = 0

    def chat(self, messages, routing_context=None):
        self.calls += 1
        return _Response(self._text)


def _coordinator(ai_service=None) -> RuntimeCoordinator:
    registry = CapabilityRegistry()

    def handler(params):
        return ExecutionResult(
            capability="conversation", success=True, output={"ok": True}
        )

    registry.register("conversation", handler)
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


def _decision(text: str = TEXT, ai_service=None):
    from atlas.conversation.turn_meaning import build_turn_meaning

    spec = TaskIntake().intake(text)
    decision = _api(ai_service).process(
        user_input=text,
        goal=spec.goal_string(),
        turn_meaning=build_turn_meaning(spec, text),
    )
    return spec, decision


class TestFinalResponseTransport:
    def test_final_response_is_transported_when_the_pipeline_answers(self):
        stub = _StubAI("STUB PIPELINE ANSWER")
        _spec, decision = _decision(ai_service=stub)
        assert decision.data["final_response"] == "STUB PIPELINE ANSWER"
        assert stub.calls == 1

    def test_empty_final_response_is_transported_as_an_empty_string(self):
        # Provider-free pipeline: AI_RESPONSE is skipped, so the transport must
        # still be present and empty rather than missing.
        _spec, decision = _decision(ai_service=None)
        assert "final_response" in decision.data
        assert decision.data["final_response"] == ""

    def test_transport_is_a_string_and_json_safe(self):
        _spec, decision = _decision(ai_service=_StubAI())
        assert isinstance(decision.data["final_response"], str)
        json.dumps(decision.data)

    def test_transport_is_deterministic(self):
        first = _decision(ai_service=_StubAI())[1].data
        second = _decision(ai_service=_StubAI())[1].data
        assert first["final_response"] == second["final_response"]
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


class TestProvenanceIsNotInvented:
    def test_no_validity_judgement_key_is_transported(self):
        # L8-b-i transports the RAW answering provider identity under
        # ``ai_provenance``; no key here may encode a validity judgement
        # (is_mock / final_response_source / …). The decision of what is usable
        # is still not made anywhere.
        _spec, decision = _decision(ai_service=_StubAI())
        for key in _PROVENANCE_KEYS:
            assert key not in decision.data, key

    def test_ai_stage_still_records_the_response_length(self):
        # L8-b-i added the answering provider/model identity to this same stage
        # data (see tests/test_l8_ai_provenance_transport.py). The pre-existing
        # ``response_length`` field is unchanged by that addition.
        coordinator = _coordinator(ai_service=_StubAI())
        result = coordinator.process(user_input=TEXT)
        ai_stage = next(
            s for s in result.stages if s.stage.name == "AI_RESPONSE"
        )
        assert ai_stage.data["response_length"] == len("STUB PIPELINE ANSWER")
        assert result.final_response == "STUB PIPELINE ANSWER"

    def test_non_string_final_response_is_coerced_to_an_empty_string(self):
        class _Metrics:
            stage_count = 0
            success_count = 0

        class _Broken:
            final_response = 42
            intermediate_data: dict = {}
            stages: list = []
            metrics = _Metrics()

        class _StubCoordinator:
            def process(self, *args, **kwargs):
                return _Broken()

        service = CognitionService(runtime_coordinator=_StubCoordinator())
        service.start()
        decision = CognitionAPI(cognition_service=service).process(user_input="x")
        assert decision.data["final_response"] == ""


class TestExistingPayloadsUnchanged:
    def test_planning_and_reasoning_payloads_are_still_exposed(self):
        from atlas.conversation.turn_meaning import build_turn_meaning

        spec = TaskIntake().intake(TEXT)
        turn_meaning = build_turn_meaning(spec, TEXT)
        coordinator = _coordinator(ai_service=_StubAI())
        result = coordinator.process(
            user_input=TEXT, goal=spec.goal_string(), turn_meaning=turn_meaning
        )
        stage = {s.stage.name: s.data for s in result.stages if s.data}
        service = CognitionService(runtime_coordinator=coordinator)
        service.start()
        data = CognitionAPI(cognition_service=service).process(
            user_input=TEXT, goal=spec.goal_string(), turn_meaning=turn_meaning
        ).data

        assert data["planning"] == stage["PLANNING"]
        assert set(data["reasoning"]) == {
            "goal", "capabilities", "routes", "results", "meaning",
        }
        expected_base = {
            "input", "memory_count", "knowledge_count",
            "understanding_insights_count", "reasoning", "planning",
        }
        assert expected_base <= set(data)
        # L8-a adds ``final_response``; L8-b-i adds ``ai_provenance`` (the raw
        # provider identity, not a validity judgement). ``tool_results`` is
        # unrelated: it appears only when a TOOL_EXECUTION stage produced data,
        # and this coordinator wires no tool engine.
        assert set(data) - {
            "final_response", "ai_provenance", "tool_results",
        } == expected_base

    def test_l6_clarification_gate_is_unchanged(self):
        _spec, decision = _decision(AMBIGUOUS, ai_service=_StubAI())
        planning = decision.data["planning"]
        assert planning["status"] == "blocked"
        assert planning["steps"] == []
        assert planning["results"] == []
        assert planning["requires_clarification"] is True
        assert decision.data["reasoning"]["requires_clarification"] is True
        # The transport itself does not gate: it carries whatever the pipeline
        # produced, including on a clarification-blocked turn.
        assert decision.data["final_response"] == "STUB PIPELINE ANSWER"


class TestBehaviourNeutral:
    def test_provider_classification_is_not_inlined_in_the_service(self):
        # L8-b-ii consumes the transported payload, but the classification is
        # delegated to the module-level precedence helper and the existing
        # LOCAL_PROVIDER_NAMES contract: no provider literal and no duplicate
        # provenance source is inlined in the conversation service class.
        source = inspect.getsource(ConversationService)
        assert "Mock Provider" not in source
        assert "LOCAL_PROVIDER_NAMES" not in source
        assert "ai_provenance" not in source

    def test_task_intake_and_routing_are_untouched_by_the_transport(self):
        Intake = TaskIntake()
        assert Intake.intake(TEXT).task_type.value == "question"
        assert Intake.intake(AMBIGUOUS).needs_clarification is True
