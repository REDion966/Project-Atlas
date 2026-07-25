"""
Phase 6.5.2 — Reasoning Recorder Runtime Wiring Tests

Verify that Atlas.start() wires the ReasoningRecorder into
CognitionService as a private Atlas-owned dependency,
without exposing it through the public ServiceContainer.
"""

import unittest

from atlas.kernel.atlas import Atlas
from atlas.reasoning.outcomes import ReasoningOutcome, ReasoningRecorder
from atlas.services.cognition_service import CognitionService


class TestReasoningRecorderRuntimeWiring(unittest.TestCase):
    """Runtime wiring tests for Phase 6.5.2."""

    def test_atlas_starts_with_recorder_enabled(self):
        """Atlas.start() creates and injects a ReasoningRecorder."""
        atlas = Atlas()
        atlas.start()

        cognition_service = atlas.container.get("cognition_service")

        self.assertIsInstance(cognition_service, CognitionService)
        self.assertIsInstance(
            cognition_service.reasoning_recorder,
            ReasoningRecorder,
        )

        atlas.shutdown()

    def test_cognition_service_status_has_recorder(self):
        """CognitionService.status reports has_recorder=True after start."""
        atlas = Atlas()
        atlas.start()

        cognition_service = atlas.container.get("cognition_service")
        status = cognition_service.status

        self.assertTrue(status["running"])
        self.assertTrue(status["has_recorder"])

        atlas.shutdown()

    def test_recorder_is_private(self):
        """ReasoningRecorder is Atlas-owned and not in ServiceContainer."""
        atlas = Atlas()
        atlas.start()

        names = atlas.container.names()

        self.assertNotIn("reasoning_recorder", names)

        atlas.shutdown()

    def test_cognition_process_records_outcome(self):
        """Cognition process through Atlas records a reasoning outcome."""
        atlas = Atlas()
        atlas.start()

        recorder = atlas._reasoning_recorder
        self.assertIsInstance(recorder, ReasoningRecorder)

        atlas.cognition_api.process("Hello world")

        self.assertEqual(recorder.count, 1)

        outcome = recorder.latest()
        self.assertIsNotNone(outcome)
        self.assertIsInstance(outcome, ReasoningOutcome)
        self.assertEqual(outcome.decision_action, "respond")

        atlas.shutdown()

    def test_recorder_outcome_contains_reasoning_fields(self):
        """Recorded outcome contains goal, capabilities, routes, results."""
        atlas = Atlas()
        atlas.start()

        atlas.cognition_api.process("Hello world")

        outcome = atlas._reasoning_recorder.latest()
        self.assertIsNotNone(outcome)
        self.assertIn("respond", outcome.goal)
        self.assertGreater(len(outcome.capabilities), 0)
        self.assertGreater(len(outcome.routes), 0)
        self.assertGreater(len(outcome.results), 0)

        atlas.shutdown()

    def test_shutdown_clears_recorder_reference(self):
        """shutdown() resets the Atlas reasoning recorder field to None."""
        atlas = Atlas()
        atlas.start()
        atlas.shutdown()

        self.assertIsNone(atlas._reasoning_recorder)

    def test_restart_creates_fresh_recorder_instance(self):
        """shutdown() + start() creates a new recorder instance."""
        atlas = Atlas()
        atlas.start()

        first_recorder = atlas._reasoning_recorder

        atlas.shutdown()
        atlas.start()

        self.assertIsNot(atlas._reasoning_recorder, first_recorder)
        self.assertIsInstance(atlas._reasoning_recorder, ReasoningRecorder)

        atlas.shutdown()

    def test_recorder_preserves_previous_reasoning_component_privacy(self):
        """Existing reasoning components remain private when recorder added."""
        atlas = Atlas()
        atlas.start()

        names = atlas.container.names()

        self.assertNotIn("reasoning_controller", names)
        self.assertNotIn("capability_analyzer", names)
        self.assertNotIn("capability_registry", names)
        self.assertNotIn("capability_router", names)
        self.assertNotIn("capability_dispatcher", names)
        self.assertNotIn("reasoning_recorder", names)

        atlas.shutdown()

    def test_multiple_process_calls_record_multiple_outcomes(self):
        """Multiple cognition API calls record multiple outcomes."""
        atlas = Atlas()
        atlas.start()

        atlas.cognition_api.process("Hello")
        atlas.cognition_api.process("World")

        self.assertEqual(atlas._reasoning_recorder.count, 2)

        atlas.shutdown()

    def test_recorder_default_max_size_from_atlas(self):
        """Atlas creates a recorder with the default max_size."""
        atlas = Atlas()
        atlas.start()

        recorder = atlas._reasoning_recorder
        self.assertEqual(recorder.max_size, 100)

        atlas.shutdown()


if __name__ == "__main__":
    unittest.main()
