"""
Phase 20 Batch 3 — Plan-Controlled Capability Selection.

Integration tests proving that in the RuntimeCoordinator:
  a. PLANNING runs before capability dispatch.
  b. no capability execution occurs during REASONING.
  c. a capability execution result appears during/after PLANNING.
  d. the dispatched capability is derived from a PlanningPlan step.
  e. a plan step action can reach a registered Track capability
     (e.g. ``research.query``) when that capability exists in the
     registry (via the plan-action direct-capability fallback).
  f. the CapabilityAnalyzer maps planning steps to capabilities.
"""

import unittest

from atlas.cognition.decision import CognitionDecision
from atlas.cognition.models import StageStatus, StageType
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.planning import PlanningEngine
from atlas.reasoning.planning.models import PlanningStep
from atlas.runtime.runtime_coordinator import RuntimeCoordinator


def _tracking_handler(calls: list):
    """Return a handler that records every invocation."""
    def handler(params: dict) -> ExecutionResult:
        calls.append(params)
        return ExecutionResult(
            capability=params.get("action", "unknown"),
            success=True,
            output={"received": params},
        )
    return handler


def _recording_plan_controller(plan):
    """Return a ReasoningController substitute that returns a fixed plan."""
    class _RecordingController(ReasoningController):
        def create_plan(self, decision: CognitionDecision):
            return plan
    return _RecordingController()


def _simple_handler(params: dict) -> ExecutionResult:
    """A default-handler style handler used for the baseline mapping."""
    return ExecutionResult(
        capability=params.get("action", "unknown"),
        success=True,
        output={"received": params},
    )


class TestPlanDrivenCapabilitySelection(unittest.TestCase):
    """Timing + derivation assertions on the RuntimeCoordinator pipeline."""

    def test_planning_runs_before_dispatch_and_reasoning_does_not_execute(self):
        calls: list = []
        registry = CapabilityRegistry()
        registry.register("conversation", _tracking_handler(calls))
        registry.register("research.query", _tracking_handler(calls))

        plan = self._plan_with_step_action("respond", "step-1")
        coordinator = RuntimeCoordinator(
            reasoning_controller=_recording_plan_controller(plan),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=registry,
            capability_router=CapabilityRouter(registry),
            capability_dispatcher=CapabilityDispatcher(registry),
            planning_engine=PlanningEngine(),
        )

        result = coordinator.process("Hello Atlas")

        reasoning_stage = self._stage(result, StageType.REASONING)
        planning_stage = self._stage(result, StageType.PLANNING)

        # a. PLANNING executes before capability dispatch: the planning
        #    stage carries the dispatched execution results.
        self.assertIsNotNone(planning_stage)
        self.assertEqual(planning_stage.status, StageStatus.SUCCESS)
        self.assertTrue(planning_stage.data["results"])
        self.assertEqual(
            [c["name"] for c in planning_stage.data["dispatched_capabilities"]],
            ["conversation"],
        )

        # b. no capability execution occurs during REASONING.
        self.assertIsNotNone(reasoning_stage)
        self.assertEqual(reasoning_stage.data["results"], [])
        self.assertEqual(reasoning_stage.data["routes"], [])

        # c. a capability execution result appears during/after PLANNING
        #    (already asserted via planning stage results) and the handler
        #    was actually invoked exactly once.
        self.assertEqual(len(calls), 1)

        # d. the dispatched capability derives from a plan step: the plan
        #    step's action "respond" is carried into the handler params,
        #    and the analyzer-mapped capability "conversation" is the one
        #    dispatched (asserted via dispatched_capabilities above).
        self.assertEqual(calls[0].get("action"), "respond")

    def test_no_dispatch_when_planning_engine_missing(self):
        """Without a PlanningEngine, REASONING records no execution at all."""

        registry = CapabilityRegistry()
        registry.register("conversation", _simple_handler)

        plan = self._plan_with_step_action("respond", "step-1")
        coordinator = RuntimeCoordinator(
            reasoning_controller=_recording_plan_controller(plan),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=registry,
            capability_router=CapabilityRouter(registry),
            capability_dispatcher=CapabilityDispatcher(registry),
            planning_engine=None,
        )

        result = coordinator.process("Hello Atlas")

        reasoning_stage = self._stage(result, StageType.REASONING)
        self.assertIsNotNone(reasoning_stage)
        self.assertEqual(reasoning_stage.data["results"], [])

    def test_plan_step_action_reaches_registered_research_query(self):
        """A plan step action naming a registered Track capability
        (research.query) is dispatched directly when it exists."""

        calls: list = []
        registry = CapabilityRegistry()
        registry.register("research.query", _tracking_handler(calls))

        plan = self._plan_with_step_action("research.query", "step-rq")
        coordinator = RuntimeCoordinator(
            reasoning_controller=_recording_plan_controller(plan),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=registry,
            capability_router=CapabilityRouter(registry),
            capability_dispatcher=CapabilityDispatcher(registry),
            planning_engine=PlanningEngine(),
        )

        result = coordinator.process("Research the sky")

        planning_stage = self._stage(result, StageType.PLANNING)
        self.assertIsNotNone(planning_stage)
        self.assertEqual(planning_stage.status, StageStatus.SUCCESS)
        self.assertEqual(
            [c["name"] for c in planning_stage.data["dispatched_capabilities"]],
            ["research.query"],
        )
        self.assertEqual(len(calls), 1)
        self.assertIn("research.query", calls[0].values())

    def test_plan_step_query_maps_to_knowledge_retrieval_when_registered(self):
        """A plan step with action 'query' maps to knowledge_retrieval when
        that capability is registered in the registry."""

        calls: list = []
        registry = CapabilityRegistry()
        registry.register("knowledge_retrieval", _tracking_handler(calls))

        plan = self._plan_with_step_action("query", "step-q")
        coordinator = RuntimeCoordinator(
            reasoning_controller=_recording_plan_controller(plan),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=registry,
            capability_router=CapabilityRouter(registry),
            capability_dispatcher=CapabilityDispatcher(registry),
            planning_engine=PlanningEngine(),
        )

        result = coordinator.process("What is a sky?")

        planning_stage = self._stage(result, StageType.PLANNING)
        self.assertIsNotNone(planning_stage)
        self.assertEqual(planning_stage.status, StageStatus.SUCCESS)
        self.assertEqual(
            [c["name"] for c in planning_stage.data["dispatched_capabilities"]],
            ["knowledge_retrieval"],
        )
        self.assertEqual(len(calls), 1)

    def test_dispatcher_fail_soft_when_no_registered_capability(self):
        """A plan step that maps to no registered capability fails soft —
        the pipeline still returns success and the result records failure.
        """

        registry = CapabilityRegistry()
        plan = self._plan_with_step_action("respond", "step-1")
        coordinator = RuntimeCoordinator(
            reasoning_controller=_recording_plan_controller(plan),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=registry,
            capability_router=CapabilityRouter(registry),
            capability_dispatcher=CapabilityDispatcher(registry),
            planning_engine=PlanningEngine(),
        )

        result = coordinator.process("Hello without handlers")

        planning_stage = self._stage(result, StageType.PLANNING)
        self.assertIsNotNone(planning_stage)
        self.assertEqual(planning_stage.status, StageStatus.SUCCESS)
        # Dispatcher returns a failed result for the unroutable capability.
        self.assertEqual(len(planning_stage.data["results"]), 1)
        self.assertFalse(planning_stage.data["results"][0]["success"])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _plan_with_step_action(self, action: str, step_id: str):
        """Build a ReasoningPlan whose single step uses the given action."""
        from atlas.reasoning.models import ReasoningPlan, ReasoningStep

        return ReasoningPlan(
            goal=f"{action}: test",
            steps=[ReasoningStep(
                description=f"Step for {action}",
                action=action,
                parameters={"action": action},
            )],
        )

    def _stage(self, result, stage_type: StageType):
        for stage in result.stages:
            if stage.stage == stage_type:
                return stage
        return None


class TestCapabilityAnalyzerPlanningSteps(unittest.TestCase):
    """CapabilityAnalyzer.analyze_step maps planning steps correctly."""

    def test_analyze_step_maps_action_to_capability(self):
        analyzer = CapabilityAnalyzer()

        step = PlanningStep(
            id="step-1",
            description="Respond to user",
            action="respond",
        )
        cap = analyzer.analyze_step(step)
        self.assertEqual(cap.name, "conversation")

    def test_analyze_step_maps_query_action(self):
        analyzer = CapabilityAnalyzer()
        step = PlanningStep(
            id="step-2",
            description="Query knowledge",
            action="query",
        )
        cap = analyzer.analyze_step(step)
        self.assertEqual(cap.name, "knowledge_retrieval")


if __name__ == "__main__":
    unittest.main()
