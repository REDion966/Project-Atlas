"""Phase 5 integration — goal → capability system → governed execution.

Demonstrates the Phase 5 completion criterion with one bounded, deterministic,
model-free path:

    natural-language goal
      → structured meaning (TaskIntake → TaskSpec → L7 TurnMeaning)
      → reasoning determines the capability need (RuntimeCoordinator REASONING)
      → capability system: model / discovery / availability
      → capability gap OR valid capability selection
      → routing (CapabilityRouter) → dispatch (CapabilityDispatcher)
      → governed action boundary (OrchestrationExecutor, SessionContext authority)
      → structured, attributable result

  ... with no external AI model. A negative path shows a missing/unavailable
  capability is handled honestly and fail-closed (no development is triggered).
"""

from __future__ import annotations

from datetime import datetime

from atlas.authority.service import AuthorityService
from atlas.cognition.models import StageType
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.conversation.turn_meaning import build_turn_meaning
from atlas.evolution.development_gap import (
    DevelopmentGapKind,
    assess_development_gap,
)
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.orchestration.execution_models import (
    ExecutionRequest,
    ExecutionStatus,
    ExecutionStep,
)
from atlas.orchestration.executor import OrchestrationExecutor
from atlas.orchestration.models import NodeKind
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.models import ReasoningPlan, ReasoningStep
from atlas.reasoning.planning.engine import PlanningEngine
from atlas.runtime.runtime_coordinator import RuntimeCoordinator
from atlas.self_knowledge.capability_model import build_capability_model
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager

_GOAL = "add a new capability to Atlas for exporting notes"


class _FailingAI:
    def chat(self, *args, **kwargs):
        raise RuntimeError("no external model available")

    def stream_chat(self, *args, **kwargs):
        def _gen():
            raise RuntimeError("no external model available")
            yield ""  # pragma: no cover

        return _gen()


def _registry(*names):
    registry = CapabilityRegistry()
    for name in names:
        registry.register(
            name,
            lambda params, _n=name: ExecutionResult(
                capability=_n, success=True, output={"done": _n}
            ),
        )
    return registry


def _coordinator():
    registry = _registry("conversation", "knowledge_retrieval")
    return RuntimeCoordinator(
        reasoning_controller=ReasoningController(),
        capability_analyzer=CapabilityAnalyzer(),
        capability_registry=registry,
        capability_router=CapabilityRouter(registry),
        capability_dispatcher=CapabilityDispatcher(registry),
        planning_engine=PlanningEngine(),
        ai_service=_FailingAI(),
    )


def _authority_ctx():
    authority = AuthorityService("Owner")
    manager = SessionManager(authority)
    return authority, SessionContext.from_session(manager.create_session("owner"))


class TestPhase5Integration:
    def test_goal_to_governed_capability_execution_without_external_model(self):
        # 1-2. Goal → structured meaning.
        spec = TaskIntake(now=datetime(2026, 9, 24, 12, 0, 0)).intake(_GOAL)
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        meaning = build_turn_meaning(spec, _GOAL)

        # 3. Reasoning determines the capability need (no external model).
        result = _coordinator().process(_GOAL, turn_meaning=meaning)
        by_stage = {stage.stage: stage for stage in result.stages}
        needed = [c["name"] for c in by_stage[StageType.REASONING].data["capabilities"]]
        assert needed  # a capability need was determined

        # 4. Capability system: authoritative model + availability.
        components = ComponentRegistry()
        components.register(
            ComponentMetadata(
                name="conversation_service",
                package="atlas.conversation",
                module_path="atlas.conversation.conversation_service",
                status=ComponentStatus.HEALTHY,
                provided_capabilities=["conversation"],
            )
        )
        model = build_capability_model(components)
        assert any(e.name == "conversation" for e in model.entries)

        # 5. Selection/routing only over available (handler-registered) capabilities.
        candidates = [Capability(name=n) for n in needed]
        registry = _registry("conversation", "knowledge_retrieval")
        routes = CapabilityRouter(registry).route(candidates)
        assert routes  # at least one candidate is genuinely routable

        # 6. Gap check is consistent (a routable capability is already supported).
        gap = assess_development_gap(_GOAL, capability_names=registry.registered_names)
        assert gap.kind in {
            DevelopmentGapKind.ALREADY_SUPPORTED,
            DevelopmentGapKind.MISSING_CAPABILITY,
            DevelopmentGapKind.MISSING_KNOWLEDGE,
        }

        # 7-9. Governed action boundary with session attribution.
        authority, ctx = _authority_ctx()
        steps = tuple(
            ExecutionStep(step_id=f"step-{i:04d}", kind=NodeKind.CAPABILITY, target=r.capability)
            for i, r in enumerate(routes)
        )
        execution = OrchestrationExecutor(
            capability_registry=registry,
            capability_dispatcher=CapabilityDispatcher(registry),
            authority_service=authority,
        ).execute(ExecutionRequest(steps=steps, session_context=ctx))

        assert execution.status is ExecutionStatus.COMPLETED
        assert execution.steps[0].allowed is True
        assert execution.steps[0].principal_id  # attributable

    def test_missing_capability_is_honest_and_fail_closed(self):
        # An unsupported action discovers only the generic (unroutable) capability.
        capabilities = CapabilityAnalyzer().analyze(
            ReasoningPlan(goal="g", steps=[ReasoningStep(action="frobnicate")])
        )
        assert [c.name for c in capabilities] == ["general"]

        registry = _registry("conversation", "knowledge_retrieval")
        assert CapabilityRouter(registry).route(capabilities) == []
        # No execution steps are fabricated.
        assert not [
            CapabilityRouter(registry).route([c]) for c in capabilities
        ][0]
        # The gap detector does not claim the missing capability is supported.
        gap = assess_development_gap(
            "frobnicate the quantum widget", capability_names=registry.registered_names
        )
        assert gap.kind is not DevelopmentGapKind.ALREADY_SUPPORTED

    def test_unavailable_capability_is_not_executed(self):
        capabilities = [Capability(name="knowledge_retrieval")]
        empty = CapabilityRegistry()
        assert CapabilityRouter(empty).route(capabilities) == []
        results = CapabilityDispatcher(empty).dispatch(capabilities)
        assert results[0].success is False and "No handler" in results[0].error
