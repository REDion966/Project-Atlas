"""
Phase 20 Batch 6 — Activate the existing ModelRouter.

Tests proving the RuntimeCoordinator constructs a RoutingRequest and
passes it through AIService.chat(routing_context=...), that the
ModelRouter is consulted, and that direct ConversationService chat
receives routing context.

Uses spies/fakes only — no external provider calls.
"""

from unittest.mock import MagicMock

from atlas.ai.routing.models import ModelProfile, RoutingDecision, RoutingRequest
from atlas.ai.routing.registry import ModelProfileRegistry
from atlas.ai.routing.router import ModelRouter
from atlas.cognition.models import StageType
from atlas.services.ai_service import AIService


def _tracking_handler(calls: list):
    """Return a handler that records every invocation."""
    from atlas.reasoning.execution.models import ExecutionResult

    def handler(params: dict) -> ExecutionResult:
        calls.append(params)
        return ExecutionResult(
            capability=params.get("action", "unknown"),
            success=True,
            output={"received": params},
        )
    return handler


_NOT_PROVIDED = object()


def _make_coordinator(ai_service, planning_engine=_NOT_PROVIDED):
    """Build a RuntimeCoordinator with the given AI service.

    planning_engine defaults to a real PlanningEngine; pass None
    explicitly to disable planning.
    """
    from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
    from atlas.reasoning.controller import ReasoningController
    from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
    from atlas.reasoning.execution.registry import CapabilityRegistry
    from atlas.reasoning.execution.routing import CapabilityRouter
    from atlas.reasoning.models import ReasoningPlan, ReasoningStep
    from atlas.reasoning.planning import PlanningEngine
    from atlas.runtime.runtime_coordinator import RuntimeCoordinator

    if planning_engine is _NOT_PROVIDED:
        planning_engine = PlanningEngine()

    registry = CapabilityRegistry()
    registry.register("conversation", _tracking_handler([]))

    plan = ReasoningPlan(
        goal="respond: test",
        steps=[ReasoningStep(
            description="Step for respond",
            action="respond",
            parameters={"action": "respond"},
        )],
    )
    return RuntimeCoordinator(
        reasoning_controller=ReasoningController(),
        capability_analyzer=CapabilityAnalyzer(),
        capability_registry=registry,
        capability_router=CapabilityRouter(registry),
        capability_dispatcher=CapabilityDispatcher(registry),
        planning_engine=planning_engine,
        ai_service=ai_service,
    )


class RecordingAIService:
    """Fake AIService recording whether routing_context was passed."""

    def __init__(self):
        self.routing_contexts: list = []

    def chat(self, messages, routing_context=None):
        self.routing_contexts.append(routing_context)
        response = MagicMock()
        response.text = "routed reply"
        return response

    def stream_chat(self, messages, routing_context=None):
        self.routing_contexts.append(routing_context)
        yield "chunk"


class TestRuntimeCoordinatorRouting:
    """A/B: RoutingRequest built and passed as routing_context to AIService."""

    def test_routing_request_reaches_ai_service(self):
        ai = RecordingAIService()
        coordinator = _make_coordinator(ai)

        result = coordinator.process("Hello routing")

        ai_stage = [s for s in result.stages if s.stage == StageType.AI_RESPONSE]
        assert len(ai_stage) == 1
        assert ai_stage[0].status.name == "SUCCESS"

        # Exactly one chat call, and it carried a RoutingRequest.
        assert len(ai.routing_contexts) == 1
        context = ai.routing_contexts[0]
        assert isinstance(context, RoutingRequest)
        # Planning ran (1 step) → complexity floored at >= 0.5.
        assert context.complexity >= 0.5
        assert context.complexity <= 1.0
        assert context.task_type
        assert context.metadata["source"] == "runtime_coordinator"

    def test_no_planning_produces_no_routing_context(self):
        """When planning never runs, no routing request is built (fail-soft)."""
        ai = RecordingAIService()
        coordinator = _make_coordinator(ai, planning_engine=None)

        coordinator.process("no planning")

        assert len(ai.routing_contexts) == 1
        assert ai.routing_contexts[0] is None


class TestModelRouterInvoked:
    """C: ModelRouter.route is actually invoked with the request."""

    def test_router_invoked_with_single_profile(self):
        registry = ModelProfileRegistry()
        registry.register(ModelProfile(
            provider_name="Mock Provider",
            model_name="atlas-mock-v1",
            complexity_score=0.3,
            priority=10,
        ))
        router = ModelRouter(registry)

        decision = router.route(RoutingRequest(complexity=0.5))

        assert decision is not None
        assert decision.provider_name == "Mock Provider"

    def test_router_routes_ordinary_requests_to_ollama(self):
        """Kernel profile set: Mock(0.3, p10) + Ollama(0.8, p20).

        A request with complexity 0.5 must select Ollama (the only profile
        whose complexity_score >= 0.5), not the Mock stub.
        """
        registry = ModelProfileRegistry()
        registry.register(ModelProfile(
            provider_name="Mock Provider",
            model_name="atlas-mock-v1",
            complexity_score=0.3,
            priority=10,
        ))
        registry.register(ModelProfile(
            provider_name="Ollama",
            model_name="qwen3:8b",
            complexity_score=0.8,
            priority=20,
        ))
        router = ModelRouter(registry)

        decision = router.route(RoutingRequest(complexity=0.5))

        assert decision is not None
        assert decision.provider_name == "Ollama"


class TestRoutingDecisionReachesProvider:
    """D: a routing decision reaches the provider-resolution path."""

    def test_aiservice_propagates_routing_decision_to_provider_router(self):
        inner = MagicMock()
        inner.chat.side_effect = (
            lambda messages, routing_decision=None: MagicMock(
                text=(
                    "provider=None"
                    if routing_decision is None
                    else f"provider={routing_decision.provider_name}"
                )
            )
        )
        service = AIService(router=inner)

        # AIService without a model_router must still call the provider
        # router with routing_decision=None (existing provider resolution).
        response = service.chat(
            ["hi"],
            routing_context=RoutingRequest(complexity=0.5),
        )

        inner.chat.assert_called_once_with(["hi"], routing_decision=None)
        assert response.text == "provider=None"

    def test_aiservice_routes_via_model_router(self):
        """With a model_router injected, the RoutingRequest is routed and the
        decision reaches the provider router."""
        inner = MagicMock()
        provider_response = MagicMock(text="ollama reply")
        inner.chat.return_value = provider_response

        registry = ModelProfileRegistry()
        registry.register(ModelProfile(
            provider_name="Ollama",
            model_name="qwen3:8b",
            complexity_score=0.8,
            priority=20,
        ))
        model_router = ModelRouter(registry)

        service = AIService(router=inner, model_router=model_router)
        response = service.chat(
            ["hi"],
            routing_context=RoutingRequest(complexity=0.5),
        )

        assert response == provider_response
        called = inner.chat.call_args
        args, kwargs = called
        decision = kwargs["routing_decision"]
        assert decision is not None
        assert decision.provider_name == "Ollama"


class TestFallbackBehavior:
    """E: fallback works when routing cannot select a provider."""

    def test_missing_profiles_returns_none_decision(self):
        registry = ModelProfileRegistry()
        router = ModelRouter(registry)

        decision = router.route(RoutingRequest(complexity=0.5))

        assert decision is None

    def test_empty_router_fall_soft_in_service(self):
        """AIService with no model_router and a routing_context degrades
        to the existing default chat path (no crash)."""
        inner = MagicMock()
        inner.chat.return_value = MagicMock(text="default")

        service = AIService(router=inner)
        response = service.chat(
            ["hi"],
            routing_context=RoutingRequest(complexity=0.9),
        )

        assert response.text == "default"
        inner.chat.assert_called_once_with(["hi"], routing_decision=None)


class TestConversationServiceRouting:
    """F: ConversationService direct chat receives routing context."""

    def _service(self, ai):
        from atlas.conversation.conversation_service import ConversationService

        return ConversationService(ai_service=ai)

    def test_send_passes_routing_context(self):
        ai = RecordingAIService()
        service = self._service(ai)
        service.send("Hello world")

        assert len(ai.routing_contexts) == 1
        context = ai.routing_contexts[0]
        assert isinstance(context, RoutingRequest)
        assert context.task_type == "conversation"
        assert context.metadata["source"] == "conversation_service"

    def test_stream_passes_routing_context(self):
        ai = RecordingAIService()
        service = self._service(ai)
        chunks = list(service.stream("Hello streaming"))

        assert "".join(chunks) == "chunk"
        assert len(ai.routing_contexts) == 1
        assert isinstance(ai.routing_contexts[0], RoutingRequest)

    def test_short_message_uses_minimum_complexity(self):
        ai = RecordingAIService()
        service = self._service(ai)
        service.send("hi")

        assert ai.routing_contexts[0].complexity == 0.5

    def test_long_message_escalates_complexity(self):
        ai = RecordingAIService()
        service = self._service(ai)
        long_text = "word " * 200
        service.send(long_text)

        assert ai.routing_contexts[0].complexity == 0.7
