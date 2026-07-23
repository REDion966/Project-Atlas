"""
Tests for the Atlas Capability Analyzer (Phase 6.2).
"""

import unittest
import inspect

from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.models import ReasoningPlan, ReasoningStep


class TestCapability(unittest.TestCase):
    """Tests for Capability data model."""

    def test_capability_creation(self):
        """A Capability can be created with all fields."""

        cap = Capability(
            name="test_cap",
            priority=10,
            reason="Test capability",
            metadata={"key": "value"},
        )

        self.assertEqual(cap.name, "test_cap")
        self.assertEqual(cap.priority, 10)
        self.assertEqual(cap.reason, "Test capability")
        self.assertEqual(cap.metadata["key"], "value")

    def test_default_values(self):
        """Capability has sensible defaults."""

        cap = Capability()

        self.assertEqual(cap.name, "")
        self.assertEqual(cap.priority, 0)
        self.assertEqual(cap.reason, "")
        self.assertEqual(cap.metadata, {})


class TestCapabilityAnalyzer(unittest.TestCase):
    """Tests for CapabilityAnalyzer."""

    def setUp(self):
        self.analyzer = CapabilityAnalyzer()

    def test_analyzer_returns_capabilities_for_respond(self):
        """A respond action maps to the conversation capability."""

        plan = ReasoningPlan(
            goal="respond: test",
            steps=[ReasoningStep(action="respond")],
        )

        capabilities = self.analyzer.analyze(plan)

        self.assertEqual(len(capabilities), 1)
        self.assertEqual(capabilities[0].name, "conversation")
        self.assertEqual(capabilities[0].priority, 10)

    def test_analyzer_returns_capabilities_for_query(self):
        """A query action maps to the knowledge_retrieval capability."""

        plan = ReasoningPlan(
            goal="query: test",
            steps=[ReasoningStep(action="query")],
        )

        capabilities = self.analyzer.analyze(plan)

        self.assertEqual(len(capabilities), 1)
        self.assertEqual(capabilities[0].name, "knowledge_retrieval")
        self.assertEqual(capabilities[0].priority, 8)

    def test_analyzer_returns_capabilities_for_idle(self):
        """An idle action maps to the noop capability."""

        plan = ReasoningPlan(
            goal="idle: nothing",
            steps=[ReasoningStep(action="idle")],
        )

        capabilities = self.analyzer.analyze(plan)

        self.assertEqual(len(capabilities), 1)
        self.assertEqual(capabilities[0].name, "noop")
        self.assertEqual(capabilities[0].priority, 0)

    def test_analyzer_handles_unknown_action(self):
        """An unknown action maps to the general capability."""

        plan = ReasoningPlan(
            goal="unknown",
            steps=[ReasoningStep(action="unknown_action")],
        )

        capabilities = self.analyzer.analyze(plan)

        self.assertEqual(len(capabilities), 1)
        self.assertEqual(capabilities[0].name, "general")
        self.assertEqual(capabilities[0].priority, 5)

    def test_analyzer_sorts_by_priority_descending(self):
        """Capabilities are returned sorted by priority (highest first)."""

        plan = ReasoningPlan(
            goal="multi-step",
            steps=[
                ReasoningStep(action="respond"),
                ReasoningStep(action="query"),
                ReasoningStep(action="analyze"),
            ],
        )

        capabilities = self.analyzer.analyze(plan)

        # Priority order: respond(10), query(8), analyze(6)
        self.assertEqual(len(capabilities), 3)
        self.assertEqual(capabilities[0].name, "conversation")
        self.assertEqual(capabilities[1].name, "knowledge_retrieval")
        self.assertEqual(capabilities[2].name, "analysis")

    def test_analyzer_empty_plan_returns_empty_list(self):
        """An empty plan returns an empty capability list."""

        plan = ReasoningPlan()

        capabilities = self.analyzer.analyze(plan)

        self.assertEqual(capabilities, [])

    def test_analyzer_has_no_external_dependencies(self):
        """CapabilityAnalyzer does not import AI, memory, knowledge, EventBus, or services."""

        source = inspect.getsource(CapabilityAnalyzer)
        self.assertNotIn("AIService", source)
        self.assertNotIn("Memory", source)
        self.assertNotIn("Knowledge", source)
        self.assertNotIn("EventBus", source)
        self.assertNotIn("Service", source)


if __name__ == "__main__":
    unittest.main()