"""Phase 4 integration — goal → reasoning → decomposition → planning → governed action.

Demonstrates the Phase 4 completion criterion with one bounded, deterministic,
model-free path:

    request goal
      → structured interpretation (TaskIntake → TaskSpec)
      → structured meaning (L7 TurnMeaning → reasoning projection)
      → context/self-knowledge
      → reasoning (RuntimeCoordinator REASONING)
      → decomposition + planning (PLANNING stage / PlanningEngine)
      → capability inspection (CapabilityAnalyzer)
      → governed action boundary (OrchestrationExecutor, SessionContext authority)
      → structured result + recorded evidence/history

  ... with no external AI model.

An ambiguous goal is shown not to reach the action boundary (fail-closed).
"""

from __future__ import annotations

from datetime import datetime

from atlas.authority.service import AuthorityService
from atlas.cognition.models import StageStatus, StageType
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.conversation.turn_meaning import build_turn_meaning
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.models import EvolutionRecord
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.orchestration.execution_models import (
    ExecutionRequest,
    ExecutionStatus,
    ExecutionStep,
)
from atlas.orchestration.executor import OrchestrationExecutor
from atlas.orchestration.models import NodeKind
from atlas.orchestration.target_resolution import task_spec_to_execution_steps
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.models import ReasoningPlan, ReasoningStep
from atlas.reasoning.planning.engine import PlanningEngine
from atlas.runtime.runtime_coordinator import RuntimeCoordinator
from atlas.self_knowledge.architecture_model import build_architecture_model
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager

_GOAL = "add a new capability to Atlas for exporting notes"


def _registry() -> ComponentRegistry:
    registry = ComponentRegistry()
    registry.register(
        ComponentMetadata(
            name="memory_service",
            package="atlas.memory.service",
            module_path="atlas.memory.service.memory_manager_service.MemoryManagerService",
            status=ComponentStatus.HEALTHY,
            provided_capabilities=["memory_search"],
        )
    )
    return registry


def _coordinator() -> RuntimeCoordinator:
    registry = CapabilityRegistry()
    for name in ("conversation", "knowledge_retrieval", "task_execution"):
        registry.register(
            name,
            lambda params, _n=name: ExecutionResult(capability=_n, success=True, output={}),
        )
    return RuntimeCoordinator(
        reasoning_controller=ReasoningController(),
        capability_analyzer=CapabilityAnalyzer(),
        capability_registry=registry,
        capability_router=CapabilityRouter(registry),
        capability_dispatcher=CapabilityDispatcher(registry),
        planning_engine=PlanningEngine(),
    )


def _cap_executor(*names):
    registry = CapabilityRegistry()
    for name in names:
        registry.register(
            name,
            lambda params, _n=name: ExecutionResult(
                capability=_n, success=True, output={"done": _n}
            ),
        )
    return registry, CapabilityDispatcher(registry)


def _make_authority():
    authority = AuthorityService("Owner")
    manager = SessionManager(authority)
    return authority, SessionContext.from_session(manager.create_session("owner"))


class TestPhase4EndToEnd:
    def test_goal_to_plan_without_external_model(self):
        # 1-3. Request-level goal → structured interpretation + structured goal.
        spec = TaskIntake(now=datetime(2026, 9, 23, 12, 0, 0)).intake(_GOAL)
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST

        # 2. Structured meaning crosses into reasoning.
        meaning = build_turn_meaning(spec, _GOAL)
        projected = meaning.to_reasoning_meaning()
        assert projected["goal"]
        assert projected["task_type"] == TaskType.DEVELOPMENT_REQUEST.value

        # 4. Relevant context / self-knowledge.
        model = build_architecture_model(_registry())
        assert model.locate("memory_service").found

        # 5-7. Reason, decompose, plan — deterministically, no external model.
        result = _coordinator().process(_GOAL, turn_meaning=meaning)
        by_stage = {stage.stage: stage for stage in result.stages}
        assert by_stage[StageType.REASONING].status is StageStatus.SUCCESS
        assert by_stage[StageType.PLANNING].status is StageStatus.SUCCESS
        assert by_stage[StageType.REASONING].data["capabilities"]
        assert by_stage[StageType.PLANNING].data["steps"]

    def test_plan_reaches_governed_action_boundary_and_records_evidence(self):
        # 11. Reasoning capabilities → plan toward the governed action boundary.
        capabilities = CapabilityAnalyzer().analyze(
            ReasoningPlan(goal="respond", steps=[ReasoningStep(action="respond")])
        )
        steps = tuple(
            ExecutionStep(
                step_id=f"step-{i:04d}", kind=NodeKind.CAPABILITY, target=c.name
            )
            for i, c in enumerate(capabilities)
        )

        # 12-13. Authorized/governed execution → execution-ready structured result.
        registry, dispatcher = _cap_executor("conversation")
        authority, ctx = _make_authority()
        result = OrchestrationExecutor(
            capability_registry=registry,
            capability_dispatcher=dispatcher,
            authority_service=authority,
        ).execute(ExecutionRequest(steps=steps, session_context=ctx))

        assert result.status is ExecutionStatus.COMPLETED
        assert result.steps[0].allowed is True
        assert result.steps[0].principal_id  # attributed to the session

        # 14. Record evidence/history for the action.
        memory = EvolutionMemory()
        memory.store_record(
            EvolutionRecord(
                record_id="REASON-P4-INT",
                event_type="reasoning.plan",
                description="Phase 4 integration run.",
                related_ids=[s.step_id for s in result.steps],
                metadata={"status": result.status.value},
            )
        )
        records = memory.get_records_by_type("reasoning.plan")
        assert records and records[0].related_ids
        assert records[0].metadata["status"] == "completed"

    def test_ambiguous_goal_does_not_reach_the_action_boundary(self):
        spec = TaskIntake().intake("improve this module")
        assert spec.needs_clarification is True
        # Fail-closed: no executable action is fabricated from an unclear goal.
        assert task_spec_to_execution_steps(spec) is None
