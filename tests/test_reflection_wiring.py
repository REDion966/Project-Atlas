"""
Phase 6.7 — Reflection Wiring Integration Tests

Validates that CognitionService optionally runs reflection analysis
when a ReflectionEngine is injected alongside the reasoning pipeline
and recorder, while preserving backward compatibility when it is not.
"""

import unittest
from datetime import datetime

from atlas.cognition.decision import CognitionDecision
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.outcomes import ReasoningOutcome, ReasoningRecorder
from atlas.reasoning.reflection import ReflectionEngine, ReflectionSuggestion
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


class TestCognitionServiceWithoutReflection(unittest.TestCase):
    """Backward compatibility when no ReflectionEngine is injected."""

    def setUp(self):
        self.registry = CapabilityRegistry()
        self.registry.register("conversation", _simple_handler)

        self.service = CognitionService(
            reasoning_controller=ReasoningController(),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=self.registry,
            capability_router=CapabilityRouter(self.registry),
            capability_dispatcher=CapabilityDispatcher(self.registry),
            reasoning_recorder=ReasoningRecorder(),
        )
        self.service.start()

    def tearDown(self):
        self.service.stop()

    def test_reflection_engine_property_is_none_by_default(self):
        """reflection_engine property returns None when not injected."""
        self.assertIsNone(self.service.reflection_engine)

    def test_process_runs_without_reflection(self):
        """Pipeline runs and records outcomes without reflection."""
        decision = self.service.process("Hello")
        self.assertIn("reasoning", decision.data)
        self.assertNotIn("reflection", decision.data)

    def test_status_reports_no_reflection(self):
        """Status correctly reports has_reflection=False."""
        status = self.service.status
        self.assertFalse(status["has_reflection"])


class TestCognitionServiceWithReflection(unittest.TestCase):
    """CognitionService works correctly with ReflectionEngine injected."""

    def setUp(self):
        self.registry = CapabilityRegistry()
        self.registry.register("conversation", _simple_handler)

        self.recorder = ReasoningRecorder()
        self.reflection_engine = ReflectionEngine()

        self.service = CognitionService(
            reasoning_controller=ReasoningController(),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=self.registry,
            capability_router=CapabilityRouter(self.registry),
            capability_dispatcher=CapabilityDispatcher(self.registry),
            reasoning_recorder=self.recorder,
            reflection_engine=self.reflection_engine,
        )
        self.service.start()

    def tearDown(self):
        self.service.stop()

    def test_reflection_engine_property_is_injected(self):
        """reflection_engine property returns the injected engine."""
        self.assertIs(self.service.reflection_engine, self.reflection_engine)

    def test_status_reports_has_reflection(self):
        """Status correctly reports has_reflection=True."""
        status = self.service.status
        self.assertTrue(status["has_reflection"])

    def test_no_reflection_key_without_enough_outcomes(self):
        """No reflection data when fewer than 5 outcomes recorded."""
        self.service.process("Hello 1")
        self.service.process("Hello 2")
        self.service.process("Hello 3")
        # 3 outcomes, all successes, below routing/imbalance threshold of 5
        decision = self.service.process("Hello 4")
        self.assertNotIn("reflection", decision.data)

    def test_reflection_key_present_with_failures(self):
        """Reflection data appears when failures trigger suggestions."""
        # Register a failing handler
        self.registry.unregister("conversation")
        self.registry.register("conversation", _failing_handler)

        # Run enough processes to accumulate failures
        for i in range(6):
            self.service.process(f"Hello {i}")

        # Switch back to success handler for the final call
        self.registry.unregister("conversation")
        self.registry.register("conversation", _simple_handler)

        decision = self.service.process("Final")
        # The recorder has 7 outcomes, 6 failures — should trigger frequent_failures
        self.assertIn("reflection", decision.data)

    def test_reflection_suggestions_have_expected_structure(self):
        """Reflection suggestions in decision.data have correct fields."""
        self.registry.unregister("conversation")
        self.registry.register("conversation", _failing_handler)

        for i in range(6):
            self.service.process(f"Hello {i}")

        self.registry.unregister("conversation")
        self.registry.register("conversation", _simple_handler)

        decision = self.service.process("Final")
        self.assertIn("reflection", decision.data)

        suggestions = decision.data["reflection"]
        self.assertIsInstance(suggestions, list)
        self.assertGreater(len(suggestions), 0)

        suggestion = suggestions[0]
        self.assertIn("pattern", suggestion)
        self.assertIn("description", suggestion)
        self.assertIn("suggestion", suggestion)
        self.assertIn("confidence", suggestion)
        self.assertIn("target_area", suggestion)
        self.assertIn("timestamp", suggestion)
        self.assertIn("affected_outcomes_count", suggestion)

    def test_reflection_does_not_break_existing_behavior(self):
        """Existing reasoning and recording still work with reflection."""
        decision = self.service.process("Hello world")

        self.assertIn("reasoning", decision.data)
        self.assertEqual(self.recorder.count, 1)
        self.assertIsInstance(decision, CognitionDecision)
        self.assertEqual(decision.action, "respond")


class TestCognitionServiceReflectionWithoutRecorder(unittest.TestCase):
    """Reflection is skipped when no recorder is available."""

    def setUp(self):
        self.service = CognitionService(
            reflection_engine=ReflectionEngine(),
        )
        self.service.start()

    def tearDown(self):
        self.service.stop()

    def test_no_reflection_without_recorder(self):
        """No reflection data when recorder is missing."""
        decision = self.service.process("Hello")
        self.assertNotIn("reflection", decision.data)


class TestCognitionServiceReflectionWithoutPipeline(unittest.TestCase):
    """Reflection is skipped when no reasoning pipeline produced outcomes."""

    def setUp(self):
        self.recorder = ReasoningRecorder()
        self.service = CognitionService(
            reasoning_recorder=self.recorder,
            reflection_engine=ReflectionEngine(),
        )
        self.service.start()

    def tearDown(self):
        self.service.stop()

    def test_no_reflection_without_pipeline(self):
        """No reflection data when reasoning pipeline didn't run."""
        decision = self.service.process("Hello")
        # No reasoning pipeline means no outcomes recorded
        self.assertEqual(self.recorder.count, 0)
        self.assertNotIn("reflection", decision.data)


if __name__ == "__main__":
    unittest.main()