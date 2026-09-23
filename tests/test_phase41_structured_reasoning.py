"""Phase 4.1 — Structured reasoning pipeline: evidence contract.

Investigation result: Atlas already has a structured reasoning pipeline, so no
new reasoning engine was introduced.

* ``atlas/runtime/runtime_coordinator.py::RuntimeCoordinator`` — the single
  orchestrator running an explicit ordered stage pipeline
  (CONVERSATION_CONTEXT → MEMORY_RETRIEVAL → KNOWLEDGE_RETRIEVAL → UNDERSTANDING
  → WORLD_MODEL → REASONING → PLANNING → TOOL_DECISION → TOOL_EXECUTION →
  AI_RESPONSE → …).
* ``atlas/cognition/models.py::CognitionState`` — the structured state exchanged
  between stages (memories, knowledge, understanding, reasoning_result,
  planning_result, meaning, …).
* REASONING: ``ReasoningController.create_plan`` → ``ReasoningPlan``;
  ``CapabilityAnalyzer.analyze`` → ranked ``Capability`` list.
* PLANNING: ``PlanningEngine.decompose`` → ``PlanningPlan`` (sub-goals, steps,
  dependencies, validation); ``CapabilityRouter``/``CapabilityDispatcher``.

These tests pin the structured pipeline and its data contracts.
"""

from __future__ import annotations

from atlas.cognition.models import StageType
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.models import ReasoningPlan
from atlas.reasoning.planning.engine import PlanningEngine
from atlas.reasoning.planning.models import PlanningPlan
from atlas.runtime.runtime_coordinator import RuntimeCoordinator


def _coordinator() -> RuntimeCoordinator:
    registry = CapabilityRegistry()
    for name in ("conversation", "knowledge_retrieval", "task_execution", "analysis"):
        registry.register(
            name,
            lambda params, _n=name: ExecutionResult(
                capability=_n, success=True, output={"done": _n}
            ),
        )
    return RuntimeCoordinator(
        reasoning_controller=ReasoningController(),
        capability_analyzer=CapabilityAnalyzer(),
        capability_registry=registry,
        capability_router=CapabilityRouter(registry),
        capability_dispatcher=CapabilityDispatcher(registry),
        planning_engine=PlanningEngine(),
    )


class TestPhase41StructuredReasoning:
    def test_runtime_runs_an_ordered_structured_pipeline(self):
        result = _coordinator().process("hello")

        order = [stage.stage for stage in result.stages]
        # The canonical stage order is preserved.
        assert order == [
            StageType.CONVERSATION_CONTEXT,
            StageType.MEMORY_RETRIEVAL,
            StageType.KNOWLEDGE_RETRIEVAL,
            StageType.UNDERSTANDING,
            StageType.WORLD_MODEL,
            StageType.REASONING,
            StageType.PLANNING,
            StageType.TOOL_DECISION,
            StageType.TOOL_EXECUTION,
            StageType.AI_RESPONSE,
            StageType.REFLECTION,
            StageType.LEARNING,
            StageType.EVOLUTION_OBSERVATION,
            StageType.GOAL_INTELLIGENCE,
            StageType.MEMORY_STORAGE,
        ]

    def test_reasoning_and_planning_stages_produce_structured_state(self):
        result = _coordinator().process("hello")

        by_stage = {stage.stage: stage for stage in result.stages}
        reasoning_data = by_stage[StageType.REASONING].data
        assert "goal" in reasoning_data
        assert "capabilities" in reasoning_data

        planning_data = by_stage[StageType.PLANNING].data
        assert "steps" in planning_data
        assert "sub_goals" in planning_data

    def test_reasoning_controller_produces_a_structured_plan(self):
        from atlas.cognition.decision import CognitionDecision

        plan = ReasoningController().create_plan(
            CognitionDecision(action="respond", reasoning="say hello", data={"goal": "g"})
        )
        assert isinstance(plan, ReasoningPlan)
        assert plan.goal == "respond: say hello"
        assert plan.steps and plan.steps[0].action == "respond"
        assert plan.steps[0].parameters == {"goal": "g"}

    def test_capability_analyzer_maps_plan_steps_to_capabilities(self):
        plan = ReasoningPlan(
            goal="respond",
            steps=[
                type("S", (), {"action": "respond", "parameters": {}})(),
                type("S", (), {"action": "query", "parameters": {}})(),
            ],
        )
        capabilities = CapabilityAnalyzer().analyze(plan)
        assert all(isinstance(c, Capability) for c in capabilities)
        assert [c.name for c in capabilities] == ["conversation", "knowledge_retrieval"]

    def test_planning_engine_decomposes_into_a_planning_plan(self):
        plan = ReasoningPlan(
            goal="respond",
            steps=[type("S", (), {"action": "respond", "description": "r", "parameters": {}})()],
        )
        planning_plan = PlanningEngine().decompose(plan)
        assert isinstance(planning_plan, PlanningPlan)
        assert planning_plan.steps and planning_plan.steps[0].id == "step-1"
