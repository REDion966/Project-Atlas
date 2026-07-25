"""
Phase 6.5.2 — Reasoning Outcome Unit Tests

Unit tests for ReasoningOutcome and ReasoningRecorder.
Verifies that the recorder is a pure logic component with no
infrastructure dependencies.
"""

import unittest
from datetime import datetime

from atlas.reasoning.outcomes import ReasoningOutcome, ReasoningRecorder


class TestReasoningOutcome(unittest.TestCase):
    """Tests for the ReasoningOutcome data model."""

    def test_reasoning_outcome_creation(self):
        """ReasoningOutcome can be created with all fields."""
        now = datetime.now()
        outcome = ReasoningOutcome(
            timestamp=now,
            goal="test goal",
            decision_action="respond",
            capabilities=[{"name": "conversation"}],
            routes=[{"capability": "conversation"}],
            results=[{"capability": "conversation", "success": True}],
            success=True,
            metadata={"source": "test"},
        )

        self.assertEqual(outcome.timestamp, now)
        self.assertEqual(outcome.goal, "test goal")
        self.assertEqual(outcome.decision_action, "respond")
        self.assertEqual(outcome.capabilities, [{"name": "conversation"}])
        self.assertEqual(outcome.routes, [{"capability": "conversation"}])
        self.assertEqual(
            outcome.results, [{"capability": "conversation", "success": True}]
        )
        self.assertTrue(outcome.success)
        self.assertEqual(outcome.metadata, {"source": "test"})

    def test_reasoning_outcome_defaults(self):
        """ReasoningOutcome uses sensible defaults."""
        now = datetime.now()
        outcome = ReasoningOutcome(timestamp=now)

        self.assertEqual(outcome.timestamp, now)
        self.assertEqual(outcome.goal, "")
        self.assertEqual(outcome.decision_action, "")
        self.assertEqual(outcome.capabilities, [])
        self.assertEqual(outcome.routes, [])
        self.assertEqual(outcome.results, [])
        self.assertFalse(outcome.success)
        self.assertEqual(outcome.metadata, {})


class TestReasoningRecorder(unittest.TestCase):
    """Tests for the ReasoningRecorder ring buffer."""

    def test_recorder_starts_empty(self):
        """New recorder has no outcomes."""
        recorder = ReasoningRecorder()

        self.assertEqual(recorder.count, 0)
        self.assertIsNone(recorder.latest())
        self.assertEqual(recorder.recent(), [])

    def test_recorder_records_outcome(self):
        """Recording increases count and stores latest outcome."""
        recorder = ReasoningRecorder()
        outcome = ReasoningOutcome(timestamp=datetime.now(), goal="goal")

        recorder.record(outcome)

        self.assertEqual(recorder.count, 1)
        self.assertIs(recorder.latest(), outcome)

    def test_recorder_recent_returns_newest_first(self):
        """recent() returns outcomes ordered newest to oldest."""
        recorder = ReasoningRecorder()
        first = ReasoningOutcome(timestamp=datetime.now(), goal="first")
        second = ReasoningOutcome(timestamp=datetime.now(), goal="second")

        recorder.record(first)
        recorder.record(second)

        recent = recorder.recent()
        self.assertEqual(len(recent), 2)
        self.assertIs(recent[0], second)
        self.assertIs(recent[1], first)

    def test_recorder_recent_limits_count(self):
        """recent(n) returns at most n outcomes."""
        recorder = ReasoningRecorder()
        for i in range(5):
            recorder.record(
                ReasoningOutcome(timestamp=datetime.now(), goal=f"goal-{i}")
            )

        recent = recorder.recent(3)
        self.assertEqual(len(recent), 3)
        self.assertEqual(recent[0].goal, "goal-4")
        self.assertEqual(recent[1].goal, "goal-3")
        self.assertEqual(recent[2].goal, "goal-2")

    def test_recorder_recent_zero_or_negative_returns_empty(self):
        """recent(0) and recent(-1) return empty lists."""
        recorder = ReasoningRecorder()
        recorder.record(ReasoningOutcome(timestamp=datetime.now()))

        self.assertEqual(recorder.recent(0), [])
        self.assertEqual(recorder.recent(-5), [])

    def test_recorder_ring_buffer_discards_oldest(self):
        """Recorder enforces max_size by discarding oldest outcomes."""
        recorder = ReasoningRecorder(max_size=3)
        outcomes = [
            ReasoningOutcome(timestamp=datetime.now(), goal=f"goal-{i}")
            for i in range(5)
        ]

        for outcome in outcomes:
            recorder.record(outcome)

        self.assertEqual(recorder.count, 3)
        recent = recorder.recent(10)
        self.assertEqual(len(recent), 3)
        self.assertIs(recent[0], outcomes[4])
        self.assertIs(recent[1], outcomes[3])
        self.assertIs(recent[2], outcomes[2])

    def test_recorder_max_size_default(self):
        """Default max_size is 100."""
        recorder = ReasoningRecorder()

        self.assertEqual(recorder.max_size, 100)

    def test_recorder_custom_max_size(self):
        """max_size can be configured at construction."""
        recorder = ReasoningRecorder(max_size=10)

        self.assertEqual(recorder.max_size, 10)

    def test_recorder_invalid_max_size_raises(self):
        """Non-positive max_size raises ValueError."""
        with self.assertRaises(ValueError):
            ReasoningRecorder(max_size=0)

        with self.assertRaises(ValueError):
            ReasoningRecorder(max_size=-1)

    def test_recorder_summary_empty(self):
        """summary() on empty recorder returns None rates."""
        recorder = ReasoningRecorder()

        summary = recorder.summary()

        self.assertEqual(summary["count"], 0)
        self.assertEqual(summary["success_count"], 0)
        self.assertEqual(summary["failure_count"], 0)
        self.assertIsNone(summary["success_rate"])
        self.assertIsNone(summary["latest_timestamp"])

    def test_recorder_summary_with_outcomes(self):
        """summary() computes success/failure counts and rate."""
        recorder = ReasoningRecorder()
        now = datetime.now()
        recorder.record(
            ReasoningOutcome(timestamp=now, success=True)
        )
        recorder.record(
            ReasoningOutcome(timestamp=now, success=True)
        )
        recorder.record(
            ReasoningOutcome(timestamp=now, success=False)
        )

        summary = recorder.summary()

        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["success_count"], 2)
        self.assertEqual(summary["failure_count"], 1)
        self.assertAlmostEqual(summary["success_rate"], 2 / 3)
        self.assertEqual(summary["latest_timestamp"], now.isoformat())

    def test_recorder_clear(self):
        """clear() removes all recorded outcomes."""
        recorder = ReasoningRecorder()
        recorder.record(ReasoningOutcome(timestamp=datetime.now()))

        recorder.clear()

        self.assertEqual(recorder.count, 0)
        self.assertIsNone(recorder.latest())

    def test_recorder_has_no_infrastructure_dependencies(self):
        """ReasoningRecorder imports no infrastructure modules."""
        import inspect

        source = inspect.getsource(ReasoningRecorder)
        self.assertNotIn("EventBus", source)
        self.assertNotIn("MemoryManagerService", source)
        self.assertNotIn("KnowledgeManager", source)
        self.assertNotIn("AIProvider", source)


if __name__ == "__main__":
    unittest.main()
