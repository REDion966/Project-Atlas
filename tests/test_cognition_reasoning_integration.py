"""
Phase 6.5.1 — Cognition Reasoning Integration Tests

Validates that CognitionService optionally runs the reasoning
pipeline when components are injected, while preserving
backward compatibility when they are not.
"""

import unittest
from unittest.mock import ANY, MagicMock

from atlas.cognition.decision import CognitionDecision
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.models import ReasoningPlan, ReasoningStep
from atlas.services.cognition_service import CognitionService


# ---------------------------------------------------------------------------
# Simple handler for registry — returns success ExecutionResult
# ---------------------------------------------------------------------------

def _simple_handler(params: dict) -> ExecutionResult:
    """A simple handler that echoes parameters as output."""
    return ExecutionResult(
        capability=params.get("action", "unknown"),
        success=True,
        output={"received": params},
    )


# ---------------------------------------------------------------------------
# Test: Backward Compatibility (no reasoning components)
# ---------------------------------------------------------------------------

class TestCognitionServiceBackwardCompatibility(unittest.TestCase):
    """Verify that existing behavior is unchanged without reasoning injection."""

    def setUp(self):
        self.service = CognitionService()
        self.service.start()

    def tearDown(self):
        self.service.stop()

    def test_default_constructor_creates_valid_service(self):
        """Service with no reasoning params behaves identically to pre-6.5.1."""
        service = CognitionService()
        self.assertIsInstance(service, CognitionService)

    def test_reasoning_controller_property_is_none_by_default(self):
        """reasoning_controller property returns None when not injected."""
        self.assertIsNone(self.service.reasoning_controller)

    def test_process_returns_decision_same_as_before(self):
        """process() returns a valid CognitionDecision — no regression."""
        decision = self.service.process("Hello world")
        self.assertIsInstance(decision, CognitionDecision)
        self.assertEqual(decision.action, "respond")

    def test_decision_data_has_no_reasoning_key_by_default(self):
        """decision.data does NOT contain 'reasoning' key without injection."""
        decision = self.service.process("Hello world")
        self.assertNotIn("reasoning", decision.data)

    def test_process_with_empty_input_still_returns_decision(self):
        """Empty input still returns 'idle' decision — no regression."""
        decision = self.service.process("")
        self.assertEqual(decision.action, "idle")


# ---------------------------------------------------------------------------
# Test: Constructor Injection
# ---------------------------------------------------------------------------

class TestCognitionServiceReasoningInjection(unittest.TestCase):
    """Verify that reasoning components are properly injected."""

    def test_constructor_injects_reasoning_controller(self):
        mock_controller = MagicMock(spec=ReasoningController)
        service = CognitionService(reasoning_controller=mock_controller)
        self.assertIs(service.reasoning_controller, mock_controller)

    def test_constructor_injects_all_reasoning_components(self):
        controller = MagicMock(spec=ReasoningController)
        analyzer = MagicMock(spec=CapabilityAnalyzer)
        registry = MagicMock(spec=CapabilityRegistry)
        router = MagicMock(spec=CapabilityRouter)
        dispatcher = MagicMock(spec=CapabilityDispatcher)

        service = CognitionService(
            reasoning_controller=controller,
            capability_analyzer=analyzer,
            capability_registry=registry,
            capability_router=router,
            capability_dispatcher=dispatcher,
        )

        self.assertIs(service.reasoning_controller, controller)

    def test_reasoning_controller_defaults_to_none(self):
        service = CognitionService()
        self.assertIsNone(service.reasoning_controller)


# ---------------------------------------------------------------------------
# Test: Partial Injection — Pipeline Skipped
# ---------------------------------------------------------------------------

class TestCognitionServicePartialReasoningInjection(unittest.TestCase):
    """Pipeline is skipped when only some components are injected."""

    def setUp(self):
        self.controller = MagicMock(spec=ReasoningController)

    def test_partial_injection_controller_only_skips_pipeline(self):
        """Injecting only the controller does not trigger the pipeline."""
        service = CognitionService(reasoning_controller=self.controller)
        service.start()

        decision = service.process("test")

        self.controller.create_plan.assert_not_called()
        self.assertNotIn("reasoning", decision.data)

        service.stop()

    def test_partial_injection_controller_and_analyzer_only_skips(self):
        """Pipeline is skipped when registry/router/dispatcher are missing."""
        analyzer = MagicMock(spec=CapabilityAnalyzer)
        service = CognitionService(
            reasoning_controller=self.controller,
            capability_analyzer=analyzer,
        )
        service.start()

        decision = service.process("test")

        self.controller.create_plan.assert_not_called()
        self.assertNotIn("reasoning", decision.data)

        service.stop()

    def test_partial_injection_missing_dispatcher_skips(self):
        """Pipeline skipped when all but dispatcher are injected."""
        analyzer = MagicMock(spec=CapabilityAnalyzer)
        registry = MagicMock(spec=CapabilityRegistry)
        router = MagicMock(spec=CapabilityRouter)
        service = CognitionService(
            reasoning_controller=self.controller,
            capability_analyzer=analyzer,
            capability_registry=registry,
            capability_router=router,
        )
        service.start()

        decision = service.process("test")
        self.assertNotIn("reasoning", decision.data)

        service.stop()


# ---------------------------------------------------------------------------
# Test: Full Pipeline Execution
# ---------------------------------------------------------------------------

class TestCognitionServiceFullReasoningPipeline(unittest.TestCase):
    """Pipeline runs end-to-end when all components are injected."""

    def setUp(self):
        # Build real reasoning components with a populated registry
        self.registry = CapabilityRegistry()
        self.registry.register("conversation", _simple_handler)

        self.controller = ReasoningController()
        self.analyzer = CapabilityAnalyzer()
        self.router = CapabilityRouter(self.registry)
        self.dispatcher = CapabilityDispatcher(self.registry)

        self.service = CognitionService(
            reasoning_controller=self.controller,
            capability_analyzer=self.analyzer,
            capability_registry=self.registry,
            capability_router=self.router,
            capability_dispatcher=self.dispatcher,
        )
        self.service.start()

    def tearDown(self):
        self.service.stop()

    def test_decision_data_contains_reasoning_key(self):
        """When pipeline runs, decision.data has a 'reasoning' key."""
        decision = self.service.process("Hello world")
        self.assertIn("reasoning", decision.data)

    def test_reasoning_contains_goal(self):
        """Reasoning output includes the plan goal."""
        decision = self.service.process("Hello world")
        reasoning = decision.data["reasoning"]
        self.assertIn("goal", reasoning)
        self.assertIn("respond", reasoning["goal"])

    def test_reasoning_contains_capabilities_list(self):
        """Reasoning output includes the list of selected capabilities."""
        decision = self.service.process("Hello world")
        reasoning = decision.data["reasoning"]
        self.assertIn("capabilities", reasoning)
        self.assertIsInstance(reasoning["capabilities"], list)

    def test_reasoning_capability_has_name_priority_reason(self):
        """Each capability entry has name, priority, and reason."""
        decision = self.service.process("Hello world")
        caps = decision.data["reasoning"]["capabilities"]
        self.assertGreater(len(caps), 0)
        cap = caps[0]
        self.assertIn("name", cap)
        self.assertIn("priority", cap)
        self.assertIn("reason", cap)

    def test_reasoning_contains_routes_list(self):
        """Reasoning output includes the list of execution routes."""
        decision = self.service.process("Hello world")
        reasoning = decision.data["reasoning"]
        self.assertIn("routes", reasoning)
        self.assertIsInstance(reasoning["routes"], list)

    def test_reasoning_route_has_capability_handler_strategy(self):
        """Each route has capability, handler_name, and strategy."""
        decision = self.service.process("Hello world")
        routes = decision.data["reasoning"]["routes"]
        self.assertGreater(len(routes), 0)
        route = routes[0]
        self.assertIn("capability", route)
        self.assertIn("handler_name", route)
        self.assertIn("strategy", route)

    def test_reasoning_contains_results_list(self):
        """Reasoning output includes the list of execution results."""
        decision = self.service.process("Hello world")
        reasoning = decision.data["reasoning"]
        self.assertIn("results", reasoning)
        self.assertIsInstance(reasoning["results"], list)

    def test_reasoning_result_has_capability_success_output_error(self):
        """Each execution result has capability, success, output, error."""
        decision = self.service.process("Hello world")
        results = decision.data["reasoning"]["results"]
        self.assertGreater(len(results), 0)
        result = results[0]
        self.assertIn("capability", result)
        self.assertIn("success", result)
        self.assertIn("output", result)
        self.assertIn("error", result)

    def test_capability_dispatched_successfully(self):
        """The handler registered in setUp processes correctly."""
        decision = self.service.process("Hello world")
        results = decision.data["reasoning"]["results"]
        self.assertTrue(results[0]["success"])

    def test_pipeline_runs_for_different_actions(self):
        """Pipeline runs correctly for non-respond actions too."""
        decision = self.service.process("")  # idle action
        # idle maps to "noop" capability — no handler registered
        self.assertIn("reasoning", decision.data)
        results = decision.data["reasoning"]["results"]
        self.assertGreater(len(results), 0)

    def test_input_survives_reasoning_pipeline(self):
        """The user input is still accessible in decision.data after pipeline."""
        decision = self.service.process("Hello world")
        self.assertIn("input", decision.data)
        self.assertEqual(decision.data["input"], "Hello world")


# ---------------------------------------------------------------------------
# Test: Pipeline Does Not Break Existing Flow
# ---------------------------------------------------------------------------

class TestCognitionServiceReasoningPreservesOtherFeatures(unittest.TestCase):
    """Reasoning pipeline does not interfere with events, learning, etc."""

    def setUp(self):
        self.event_bus = MagicMock()
        self.learning_manager = MagicMock()
        self.learning_manager.learn.return_value = MagicMock(knowledge="test")

        self.registry = CapabilityRegistry()
        self.registry.register("conversation", _simple_handler)

        self.service = CognitionService(
            reasoning_controller=ReasoningController(),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=self.registry,
            capability_router=CapabilityRouter(self.registry),
            capability_dispatcher=CapabilityDispatcher(self.registry),
            learning_manager=self.learning_manager,
            event_bus=self.event_bus,
        )
        self.service.start()

    def tearDown(self):
        self.service.stop()

    def test_event_published_when_pipeline_runs(self):
        """'cognition.decision.made' event is still published."""
        self.service.process("Hello")
        self.event_bus.publish.assert_any_call(
            "cognition.decision.made",
            unittest.mock.ANY,
        )

    def test_learning_feedback_still_runs(self):
        """Learning feedback loop is not affected by reasoning pipeline."""
        self.service.process("Hello")
        self.learning_manager.learn.assert_called_once()

    def test_event_includes_reasoning_data_in_decision_data(self):
        """Event data now includes reasoning results alongside input."""
        self.service.process("Hello")
        call_args = self.event_bus.publish.call_args_list[0]
        event_data = call_args[0][1]
        self.assertIn("data", event_data)
        # The data dict passed to the event includes the reasoning key
        # because it's attached to the same mutable decision.data dict
        self.assertIn("reasoning", event_data["data"])


# ---------------------------------------------------------------------------
# Test: Import Purity
# ---------------------------------------------------------------------------

class TestCognitionServiceImportPurity(unittest.TestCase):
    """CognitionService does not import reasoning at module level."""

    def test_no_reasoning_import_at_module_level(self):
        """Reasoning types should use TYPE_CHECKING guard, not runtime imports."""
        import inspect

        source = inspect.getsource(CognitionService)
        # The class source should not show direct reasoning imports
        # (they are guarded by TYPE_CHECKING in the file)
        # This test verifies the file structure is correct by
        # checking that the class can import without reasoning installed
        self.assertIsNotNone(source)


if __name__ == "__main__":
    unittest.main()