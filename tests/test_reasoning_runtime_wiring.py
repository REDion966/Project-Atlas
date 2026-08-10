"""
Phase 6.5.1 Commit 3 — Reasoning Runtime Wiring Tests

Verify that Atlas.start() wires the reasoning pipeline into
CognitionService as Atlas-owned private runtime dependencies,
without exposing them through the public ServiceContainer.
"""

import unittest

from atlas.kernel.atlas import Atlas
from atlas.services.cognition_service import CognitionService
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.handlers import DEFAULT_HANDLERS


class TestReasoningRuntimeWiring(unittest.TestCase):
    """Runtime wiring tests for Phase 6.5.1 Commit 3."""

    def test_atlas_starts_with_reasoning_enabled(self):
        """Atlas.start() creates and injects all reasoning components."""

        atlas = Atlas()
        atlas.start()

        cognition_service = atlas.container.get("cognition_service")

        self.assertIsInstance(cognition_service, CognitionService)
        self.assertIsInstance(
            cognition_service.reasoning_controller,
            ReasoningController,
        )

        atlas.shutdown()

    def test_cognition_service_status_has_reasoning(self):
        """CognitionService.status reports has_reasoning=True after Atlas.start()."""

        atlas = Atlas()
        atlas.start()

        cognition_service = atlas.container.get("cognition_service")
        status = cognition_service.status

        self.assertTrue(status["running"])
        self.assertTrue(status["has_reasoning"])

        atlas.shutdown()

    def test_reasoning_components_are_private(self):
        """Reasoning components are Atlas-owned and not in ServiceContainer."""

        atlas = Atlas()
        atlas.start()

        names = atlas.container.names()

        self.assertNotIn("reasoning_controller", names)
        self.assertNotIn("capability_analyzer", names)
        self.assertNotIn("capability_registry", names)
        self.assertNotIn("capability_router", names)
        self.assertNotIn("capability_dispatcher", names)

        atlas.shutdown()

    def test_cognition_process_returns_reasoning_data(self):
        """Cognition process through Atlas attaches reasoning results to decision."""

        atlas = Atlas()
        atlas.start()

        decision = atlas.cognition_api.process("Hello world")

        self.assertIn("reasoning", decision.data)

        reasoning = decision.data["reasoning"]
        self.assertIn("goal", reasoning)
        self.assertIn("capabilities", reasoning)
        self.assertIn("routes", reasoning)
        self.assertIn("results", reasoning)

        atlas.shutdown()

    def test_process_propagates_goal_into_reasoning_path(self):
        """RuntimeCoordinator.process(goal=...) must carry the explicit goal
        into the reasoning/plan path."""
        from atlas.runtime.runtime_coordinator import RuntimeCoordinator
        from atlas.reasoning.planning import PlanningEngine
        from atlas.reasoning.controller import ReasoningController
        from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
        from atlas.reasoning.execution.registry import CapabilityRegistry
        from atlas.reasoning.execution.routing import CapabilityRouter
        from atlas.reasoning.execution.dispatcher import CapabilityDispatcher

        registry = CapabilityRegistry()
        registry.register("conversation", lambda params: ExecutionResult(
            capability="conversation", success=True, output={"ok": True},
        ))

        coordinator = RuntimeCoordinator(
            reasoning_controller=ReasoningController(),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=registry,
            capability_router=CapabilityRouter(registry),
            capability_dispatcher=CapabilityDispatcher(registry),
            planning_engine=PlanningEngine(),
        )

        result = coordinator.process(
            user_input="is the sky blue",
            goal="verify claim X",
        )

        reasoning = next(
            s.data for s in result.stages if s.stage.name == "REASONING"
        )
        planning = next(
            s.data for s in result.stages if s.stage.name == "PLANNING"
        )

        # The explicit goal appears in the reasoning plan goal.
        self.assertIn("verify claim X", reasoning["goal"])
        # And it flows through to the planning goal via the reasoning goal.
        self.assertIn("verify claim X", planning["goal"])

    def test_reasoning_results_contain_execution_result(self):
        """Reasoning results contain the fields of an ExecutionResult."""

        atlas = Atlas()
        atlas.start()

        decision = atlas.cognition_api.process("Hello world")
        results = decision.data["reasoning"]["results"]

        self.assertGreater(len(results), 0)

        result = results[0]
        self.assertIn("capability", result)
        self.assertIn("success", result)
        self.assertIn("output", result)
        self.assertIn("error", result)
        self.assertTrue(result["success"])

        atlas.shutdown()

    def test_default_handlers_registered_in_registry(self):
        """Atlas-owned registry contains all DEFAULT_HANDLERS."""

        atlas = Atlas()
        atlas.start()

        registry = atlas._capability_registry

        self.assertIsInstance(registry, CapabilityRegistry)

        for name in DEFAULT_HANDLERS:
            self.assertTrue(registry.has(name))

        atlas.shutdown()

    def test_shutdown_clears_reasoning_references(self):
        """shutdown() resets all Atlas reasoning fields to None."""

        atlas = Atlas()
        atlas.start()
        atlas.shutdown()

        self.assertIsNone(atlas._reasoning_controller)
        self.assertIsNone(atlas._capability_analyzer)
        self.assertIsNone(atlas._capability_registry)
        self.assertIsNone(atlas._capability_router)
        self.assertIsNone(atlas._capability_dispatcher)

    def test_restart_creates_fresh_reasoning_instances(self):
        """shutdown() + start() creates new reasoning component instances."""

        atlas = Atlas()
        atlas.start()

        first_registry = atlas._capability_registry
        first_controller = atlas._reasoning_controller

        atlas.shutdown()
        atlas.start()

        self.assertIsNot(atlas._capability_registry, first_registry)
        self.assertIsNot(atlas._reasoning_controller, first_controller)
        self.assertIsInstance(atlas._capability_registry, CapabilityRegistry)
        self.assertIsInstance(atlas._reasoning_controller, ReasoningController)

        atlas.shutdown()


if __name__ == "__main__":
    unittest.main()
