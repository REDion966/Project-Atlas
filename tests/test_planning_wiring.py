"""
Phase 6.8 — Planning Engine Wiring Integration Tests

Validates that CognitionService optionally runs planning decomposition
when a PlanningEngine is injected alongside the reasoning pipeline,
while preserving backward compatibility when it is not.
"""

import unittest

from atlas.cognition.decision import CognitionDecision
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.planning import PlanningEngine, PlanningPlan, PlanningStep
from atlas.services.cognition_service import CognitionService


def _simple_handler(params: dict) -> ExecutionResult:
    """A simple handler that returns a successful execution result."""
    return ExecutionResult(
        capability=params.get("action", "unknown"),
        success=True,
        output={"received": params},
    )


class TestCognitionServiceWithoutPlanning(unittest.TestCase):
    """Backward compatibility when no PlanningEngine is injected."""

    def setUp(self):
        self.registry = CapabilityRegistry()
        self.registry.register("conversation", _simple_handler)

        self.service = CognitionService(
            reasoning_controller=ReasoningController(),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=self.registry,
            capability_router=CapabilityRouter(self.registry),
            capability_dispatcher=CapabilityDispatcher(self.registry),
        )
        self.service.start()

    def tearDown(self):
        self.service.stop()

    def test_planning_engine_property_is_none_by_default(self):
        """planning_engine property returns None when not injected."""
        self.assertIsNone(self.service.planning_engine)

    def test_process_runs_without_planning(self):
        """Pipeline runs normally without planning engine."""
        decision = self.service.process("Hello")
        self.assertIn("reasoning", decision.data)
        self.assertNotIn("planning", decision.data)

    def test_status_reports_no_planning(self):
        """Status correctly reports has_planning=False."""
        status = self.service.status
        self.assertFalse(status["has_planning"])

    def test_existing_behavior_preserved(self):
        """Existing reasoning and recording still work without planning."""
        decision = self.service.process("Hello world")
        self.assertIn("reasoning", decision.data)
        self.assertIsInstance(decision, CognitionDecision)
        self.assertEqual(decision.action, "respond")


class TestCognitionServiceWithPlanning(unittest.TestCase):
    """CognitionService works correctly with PlanningEngine injected."""

    def setUp(self):
        self.registry = CapabilityRegistry()
        self.registry.register("conversation", _simple_handler)

        self.planning_engine = PlanningEngine()

        self.service = CognitionService(
            reasoning_controller=ReasoningController(),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=self.registry,
            capability_router=CapabilityRouter(self.registry),
            capability_dispatcher=CapabilityDispatcher(self.registry),
            planning_engine=self.planning_engine,
        )
        self.service.start()

    def tearDown(self):
        self.service.stop()

    def test_planning_engine_property_is_injected(self):
        """planning_engine property returns the injected engine."""
        self.assertIs(self.service.planning_engine, self.planning_engine)

    def test_status_reports_has_planning(self):
        """Status correctly reports has_planning=True."""
        status = self.service.status
        self.assertTrue(status["has_planning"])

    def test_planning_data_in_decision(self):
        """Planning data appears in decision.data when engine is injected."""
        decision = self.service.process("Hello")
        self.assertIn("planning", decision.data)

    def test_planning_data_has_expected_structure(self):
        """Planning data in decision.data has correct fields."""
        decision = self.service.process("Analyze and report")
        self.assertIn("planning", decision.data)

        planning = decision.data["planning"]
        self.assertIn("goal", planning)
        self.assertIn("sub_goals", planning)
        self.assertIn("steps", planning)
        self.assertIn("status", planning)
        self.assertIn("validation_errors", planning)

    def test_planning_steps_have_expected_structure(self):
        """Each planning step in decision.data has correct fields."""
        decision = self.service.process("Do something")
        planning = decision.data["planning"]

        for step in planning["steps"]:
            self.assertIn("id", step)
            self.assertIn("description", step)
            self.assertIn("action", step)
            self.assertIn("depends_on", step)
            self.assertIn("status", step)

    def test_planning_does_not_break_existing_behavior(self):
        """Existing reasoning and recording still work with planning."""
        decision = self.service.process("Hello world")

        self.assertIn("reasoning", decision.data)
        self.assertIn("planning", decision.data)
        self.assertIsInstance(decision, CognitionDecision)
        self.assertEqual(decision.action, "respond")

    def test_planning_goal_matches_reasoning_goal(self):
        """Planning goal should match the reasoning plan goal."""
        decision = self.service.process("Test input")
        planning = decision.data["planning"]
        reasoning = decision.data["reasoning"]

        self.assertEqual(planning["goal"], reasoning["goal"])


class TestCognitionServicePlanningWithoutPipeline(unittest.TestCase):
    """Planning is skipped when no reasoning pipeline is available."""

    def setUp(self):
        self.service = CognitionService(
            planning_engine=PlanningEngine(),
        )
        self.service.start()

    def tearDown(self):
        self.service.stop()

    def test_no_planning_without_pipeline(self):
        """No planning data when reasoning pipeline didn't run."""
        decision = self.service.process("Hello")
        self.assertNotIn("planning", decision.data)

    def test_status_still_reports_has_planning(self):
        """Status still reports has_planning=True even without pipeline."""
        status = self.service.status
        self.assertTrue(status["has_planning"])


class TestAtlasKernelPlanningWiring(unittest.TestCase):
    """Integration test verifying PlanningEngine is wired in Atlas.start()."""

    def test_planning_engine_created_in_atlas_start(self):
        """Atlas.start() creates and injects a PlanningEngine."""
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            cognition_service = atlas.container.get("cognition_service")
            self.assertIsNotNone(cognition_service.planning_engine)
            self.assertIsInstance(
                cognition_service.planning_engine,
                PlanningEngine,
            )
        finally:
            atlas.shutdown()

    def test_planning_engine_cleaned_up_on_shutdown(self):
        """Atlas.shutdown() nullifies the planning engine."""
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        atlas.start()
        atlas.shutdown()

        # After shutdown, the service is removed from the container
        # so we verify the engine reference is cleaned up
        self.assertIsNone(atlas._planning_engine)

    def test_planning_engine_not_in_service_container(self):
        """PlanningEngine is a private dependency, not in ServiceContainer."""
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            expected_keys = {
                "component_registry",
                "ai", "conversation", "memory", "knowledge",
                "cognition", "cognitive", "cognition_service",
                "cognition_api", "tasks",
                "runtime_coordinator", "understanding",
                "world_model", "evolution_observer", "learning_engine",
                "identity", "authority", "feedback_coordinator",
                "goal_repository", "goal_intelligence",
                "experience_repository", "experience_accumulator", "self_model_engine",
                "intelligence_engine",
                "execution_gateway",
                "evolution_knowledge",
                "goal_execution",
            }
            self.assertEqual(
                set(atlas.container.names()),
                expected_keys,
            )
        finally:
            atlas.shutdown()

    def test_planning_engine_available_via_cognition_service(self):
        """PlanningEngine is accessible through cognition_service."""
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            cognition_service = atlas.container.get("cognition_service")
            self.assertTrue(cognition_service.status["has_planning"])
        finally:
            atlas.shutdown()


if __name__ == "__main__":
    unittest.main()
