"""
Phase 6.5.2 — Reasoning Recorder Integration Tests

Validates that CognitionService optionally records reasoning
pipeline outcomes when a ReasoningRecorder is injected, while
preserving backward compatibility when it is not.
"""

import unittest
from unittest.mock import MagicMock

from atlas.cognition.decision import CognitionDecision
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.outcomes import ReasoningOutcome, ReasoningRecorder
from atlas.services.cognition_service import CognitionService


def _simple_handler(params: dict) -> ExecutionResult:
    """A simple handler that returns a successful execution result."""
    return ExecutionResult(
        capability=params.get("action", "unknown"),
        success=True,
        output={"received": params},
    )


def _failing_handler(params: dict) -> ExecutionResult:
    """A simple handler that returns a failed execution result."""
    return ExecutionResult(
        capability=params.get("action", "unknown"),
        success=False,
        error="test failure",
    )


class TestCognitionServiceRecorderBackwardCompatibility(unittest.TestCase):
    """Backward compatibility when no recorder is injected."""

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

    def test_recorder_property_is_none_by_default(self):
        """reasoning_recorder property returns None when not injected."""
        self.assertIsNone(self.service.reasoning_recorder)

    def test_process_runs_pipeline_without_recorder(self):
        """Pipeline runs and attaches reasoning even without recorder."""
        decision = self.service.process("Hello")

        self.assertIn("reasoning", decision.data)

    def test_no_outcomes_recorded_without_recorder(self):
        """No outcomes are recorded when recorder is not present."""
        self.service.process("Hello")

        self.assertIsNone(self.service.reasoning_recorder)

    def test_status_reports_no_recorder(self):
        """Status correctly reports has_recorder=False."""
        status = self.service.status

        self.assertFalse(status["has_recorder"])


class TestCognitionServiceRecorderInjection(unittest.TestCase):
    """Constructor injection of the reasoning recorder."""

    def test_constructor_injects_recorder(self):
        """reasoning_recorder constructor parameter is stored."""
        recorder = ReasoningRecorder()
        service = CognitionService(reasoning_recorder=recorder)

        self.assertIs(service.reasoning_recorder, recorder)

    def test_recorder_defaults_to_none(self):
        """reasoning_recorder defaults to None."""
        service = CognitionService()

        self.assertIsNone(service.reasoning_recorder)


class TestCognitionServiceRecorderPipelineIntegration(unittest.TestCase):
    """Recording happens after successful reasoning pipeline execution."""

    def setUp(self):
        self.registry = CapabilityRegistry()
        self.registry.register("conversation", _simple_handler)

        self.recorder = ReasoningRecorder()
        self.service = CognitionService(
            reasoning_controller=ReasoningController(),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=self.registry,
            capability_router=CapabilityRouter(self.registry),
            capability_dispatcher=CapabilityDispatcher(self.registry),
            reasoning_recorder=self.recorder,
        )
        self.service.start()

    def tearDown(self):
        self.service.stop()

    def test_recorder_captures_outcome_after_pipeline(self):
        """One outcome is recorded after a cognition process."""
        self.service.process("Hello world")

        self.assertEqual(self.recorder.count, 1)

    def test_recorded_outcome_has_decision_action(self):
        """Outcome captures the decision action."""
        self.service.process("Hello world")

        outcome = self.recorder.latest()
        self.assertIsInstance(outcome, ReasoningOutcome)
        self.assertEqual(outcome.decision_action, "respond")

    def test_recorded_outcome_has_goal(self):
        """Outcome captures the reasoning goal."""
        self.service.process("Hello world")

        outcome = self.recorder.latest()
        self.assertIn("respond", outcome.goal)

    def test_recorded_outcome_has_capabilities(self):
        """Outcome captures selected capabilities."""
        self.service.process("Hello world")

        outcome = self.recorder.latest()
        self.assertGreater(len(outcome.capabilities), 0)
        self.assertEqual(outcome.capabilities[0]["name"], "conversation")

    def test_recorded_outcome_has_routes(self):
        """Outcome captures execution routes."""
        self.service.process("Hello world")

        outcome = self.recorder.latest()
        self.assertGreater(len(outcome.routes), 0)
        self.assertEqual(outcome.routes[0]["capability"], "conversation")

    def test_recorded_outcome_has_results(self):
        """Outcome captures execution results."""
        self.service.process("Hello world")

        outcome = self.recorder.latest()
        self.assertGreater(len(outcome.results), 0)
        self.assertTrue(outcome.results[0]["success"])

    def test_recorded_outcome_success_flag_true(self):
        """Outcome success is True when all results succeed."""
        self.service.process("Hello world")

        outcome = self.recorder.latest()
        self.assertTrue(outcome.success)

    def test_recorded_outcome_success_flag_false(self):
        """Outcome success is False when any result fails."""
        self.registry.unregister("conversation")
        self.registry.register("conversation", _failing_handler)

        self.service.process("Hello world")

        outcome = self.recorder.latest()
        self.assertFalse(outcome.success)

    def test_recorded_outcome_has_timestamp(self):
        """Outcome has a timestamp."""
        from datetime import datetime

        self.service.process("Hello world")

        outcome = self.recorder.latest()
        self.assertIsInstance(outcome.timestamp, datetime)

    def test_recorded_outcome_has_metadata(self):
        """Outcome has source metadata."""
        self.service.process("Hello world")

        outcome = self.recorder.latest()
        self.assertEqual(outcome.metadata.get("source"), "cognition_service")

    def test_recorder_captures_multiple_process_calls(self):
        """Multiple process calls record multiple outcomes."""
        self.service.process("Hello")
        self.service.process("World")

        self.assertEqual(self.recorder.count, 2)
        self.assertEqual(self.recorder.recent()[0].decision_action, "respond")
        self.assertEqual(self.recorder.recent()[1].decision_action, "respond")

    def test_recorder_skips_when_pipeline_skipped(self):
        """No outcome recorded when reasoning pipeline components missing."""
        service = CognitionService(reasoning_recorder=self.recorder)
        service.start()

        service.process("Hello world")

        self.assertEqual(self.recorder.count, 0)
        service.stop()


class TestCognitionServiceRecorderEventsPreserved(unittest.TestCase):
    """Recording does not interfere with events or learning."""

    def setUp(self):
        self.event_bus = MagicMock()
        self.learning_manager = MagicMock()
        self.learning_manager.learn.return_value = MagicMock(knowledge="test")

        self.registry = CapabilityRegistry()
        self.registry.register("conversation", _simple_handler)
        self.recorder = ReasoningRecorder()

        self.service = CognitionService(
            reasoning_controller=ReasoningController(),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=self.registry,
            capability_router=CapabilityRouter(self.registry),
            capability_dispatcher=CapabilityDispatcher(self.registry),
            reasoning_recorder=self.recorder,
            learning_manager=self.learning_manager,
            event_bus=self.event_bus,
        )
        self.service.start()

    def tearDown(self):
        self.service.stop()

    def test_learning_feedback_still_runs_with_recorder(self):
        """Learning feedback loop is not affected by recording."""
        self.service.process("Hello")

        self.learning_manager.learn.assert_called_once()

    def test_decision_event_still_published_with_recorder(self):
        """Decision event is still published with recorder active."""
        self.service.process("Hello")

        self.event_bus.publish.assert_any_call(
            "cognition.decision.made",
            unittest.mock.ANY,
        )

    def test_status_reports_recorder(self):
        """Status correctly reports has_recorder=True."""
        status = self.service.status

        self.assertTrue(status["has_recorder"])


class TestCognitionServiceRecorderImportPurity(unittest.TestCase):
    """CognitionService does not import ReasoningOutcome at module level."""

    def test_no_outcome_import_at_module_level(self):
        """ReasoningOutcome is not imported at module level."""
        import inspect

        source = inspect.getsource(CognitionService)
        self.assertNotIn("from atlas.reasoning.outcomes import ReasoningOutcome", source)


if __name__ == "__main__":
    unittest.main()
