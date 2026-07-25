"""
Phase 6.7 — Reflection Engine Unit Tests

Verifies that ReflectionEngine is a pure logic component that
analyzes reasoning outcomes and produces deterministic, explainable
suggestions.
"""

import unittest
from datetime import datetime

from atlas.reasoning.outcomes import ReasoningOutcome
from atlas.reasoning.reflection import ReflectionEngine, ReflectionSuggestion


class TestReflectionEngineNoOutcomes(unittest.TestCase):
    """Behavior when no outcomes are provided."""

    def setUp(self):
        self.engine = ReflectionEngine()

    def test_empty_outcomes_returns_empty_list(self):
        """analyze([]) returns empty list."""
        suggestions = self.engine.analyze([])
        self.assertEqual(suggestions, [])

    def test_no_patterns_returns_empty_suggestions(self):
        """Outcomes with all successes and balanced usage produce no suggestions."""
        outcomes = []
        for i in range(10):
            cap_name = f"cap-{i % 4}"
            route_name = f"route-{i % 3}"
            outcomes.append(
                ReasoningOutcome(
                    timestamp=datetime.now(),
                    goal=f"goal-{i}",
                    decision_action="respond",
                    capabilities=[{"name": cap_name, "priority": 1, "reason": "test"}],
                    routes=[{"capability": cap_name, "handler_name": route_name, "strategy": "direct"}],
                    results=[{"capability": cap_name, "success": True, "output": {}, "error": None}],
                    success=True,
                )
            )
        suggestions = self.engine.analyze(outcomes)
        self.assertEqual(suggestions, [])

    def test_single_outcome_no_patterns(self):
        """Single outcome cannot produce patterns (needs thresholds)."""
        outcome = ReasoningOutcome(
            timestamp=datetime.now(),
            goal="single",
            decision_action="respond",
            capabilities=[{"name": "conversation", "priority": 1, "reason": "test"}],
            routes=[{"capability": "conversation", "handler_name": "conversation", "strategy": "direct"}],
            results=[{"capability": "conversation", "success": False, "output": {}, "error": "fail"}],
            success=False,
        )
        suggestions = self.engine.analyze([outcome])
        # Failure threshold requires >= 3 uses, so no suggestion
        self.assertEqual(suggestions, [])


class TestReflectionEngineFrequentFailures(unittest.TestCase):
    """Detection of capabilities with high failure rates."""

    def setUp(self):
        self.engine = ReflectionEngine()

    def test_detects_frequent_failures(self):
        """Capability with >=50% failure rate and >=3 uses is flagged."""
        outcomes = []
        for i in range(6):
            outcomes.append(
                ReasoningOutcome(
                    timestamp=datetime.now(),
                    goal=f"goal-{i}",
                    decision_action="respond",
                    capabilities=[{"name": "chat", "priority": 1, "reason": "test"}],
                    routes=[{"capability": "chat", "handler_name": "chat", "strategy": "direct"}],
                    results=[
                        {"capability": "chat", "success": i >= 3, "output": {}, "error": None if i >= 3 else "fail"}
                    ],
                    success=i >= 3,
                )
            )
        suggestions = self.engine.analyze(outcomes)
        patterns = [s.pattern for s in suggestions]
        self.assertIn("frequent_failures", patterns)

    def test_failure_suggestion_has_correct_fields(self):
        """Failure suggestion has all required fields populated."""
        outcomes = []
        for i in range(4):
            outcomes.append(
                ReasoningOutcome(
                    timestamp=datetime.now(),
                    goal=f"goal-{i}",
                    decision_action="respond",
                    capabilities=[{"name": "flaky", "priority": 1, "reason": "test"}],
                    routes=[{"capability": "flaky", "handler_name": "flaky", "strategy": "direct"}],
                    results=[
                        {"capability": "flaky", "success": False, "output": {}, "error": "fail"}
                    ],
                    success=False,
                )
            )
        suggestions = self.engine.analyze(outcomes)
        self.assertGreater(len(suggestions), 0)
        suggestion = suggestions[0]
        self.assertEqual(suggestion.pattern, "frequent_failures")
        self.assertIsInstance(suggestion.description, str)
        self.assertGreater(len(suggestion.description), 0)
        self.assertIsInstance(suggestion.suggestion, str)
        self.assertGreater(len(suggestion.suggestion), 0)
        self.assertGreaterEqual(suggestion.confidence, 0.0)
        self.assertLessEqual(suggestion.confidence, 1.0)
        self.assertEqual(suggestion.target_area, "capability_selection")
        self.assertIsInstance(suggestion.timestamp, datetime)
        self.assertGreater(suggestion.affected_outcomes_count, 0)

    def test_low_failure_rate_not_flagged(self):
        """Capability with <50% failure rate is not flagged."""
        outcomes = []
        for i in range(6):
            outcomes.append(
                ReasoningOutcome(
                    timestamp=datetime.now(),
                    goal=f"goal-{i}",
                    decision_action="respond",
                    capabilities=[{"name": "reliable", "priority": 1, "reason": "test"}],
                    routes=[{"capability": "reliable", "handler_name": "reliable", "strategy": "direct"}],
                    results=[
                        {"capability": "reliable", "success": i != 0, "output": {}, "error": None if i != 0 else "fail"}
                    ],
                    success=i != 0,
                )
            )
        suggestions = self.engine.analyze(outcomes)
        patterns = [s.pattern for s in suggestions]
        self.assertNotIn("frequent_failures", patterns)


class TestReflectionEngineRepeatedRouting(unittest.TestCase):
    """Detection of overused or underused routing patterns."""

    def setUp(self):
        self.engine = ReflectionEngine()

    def test_detects_overused_route(self):
        """Route used in >80% of outcomes is flagged as overused."""
        outcomes = []
        for i in range(10):
            routes = [{"capability": "main", "handler_name": "main_handler", "strategy": "direct"}]
            if i >= 8:
                routes.append(
                    {"capability": "alt", "handler_name": "alt_handler", "strategy": "fallback"}
                )
            outcomes.append(
                ReasoningOutcome(
                    timestamp=datetime.now(),
                    goal=f"goal-{i}",
                    decision_action="respond",
                    capabilities=[{"name": "main", "priority": 1, "reason": "test"}],
                    routes=routes,
                    results=[{"capability": "main", "success": True, "output": {}, "error": None}],
                    success=True,
                )
            )
        suggestions = self.engine.analyze(outcomes)
        patterns = [s.pattern for s in suggestions]
        self.assertIn("repeated_routing", patterns)

    def test_fewer_than_five_outcomes_no_routing_suggestion(self):
        """Routing analysis needs >=5 outcomes."""
        outcomes = []
        for i in range(4):
            outcomes.append(
                ReasoningOutcome(
                    timestamp=datetime.now(),
                    goal=f"goal-{i}",
                    decision_action="respond",
                    capabilities=[{"name": "conv", "priority": 1, "reason": "test"}],
                    routes=[{"capability": "conv", "handler_name": "conv", "strategy": "direct"}],
                    results=[{"capability": "conv", "success": True, "output": {}, "error": None}],
                    success=True,
                )
            )
        suggestions = self.engine.analyze(outcomes)
        patterns = [s.pattern for s in suggestions]
        self.assertNotIn("repeated_routing", patterns)

    def test_balanced_routing_no_suggestion(self):
        """Evenly distributed routes produce no routing suggestion."""
        outcomes = []
        for i in range(10):
            route_name = f"route-{i % 3}"
            outcomes.append(
                ReasoningOutcome(
                    timestamp=datetime.now(),
                    goal=f"goal-{i}",
                    decision_action="respond",
                    capabilities=[{"name": route_name, "priority": 1, "reason": "test"}],
                    routes=[{"capability": route_name, "handler_name": route_name, "strategy": "direct"}],
                    results=[{"capability": route_name, "success": True, "output": {}, "error": None}],
                    success=True,
                )
            )
        suggestions = self.engine.analyze(outcomes)
        patterns = [s.pattern for s in suggestions]
        # Each route appears ~3-4 times, none exceeds 80% threshold
        self.assertNotIn("repeated_routing", patterns)


class TestReflectionEngineCapabilityImbalance(unittest.TestCase):
    """Detection of uneven capability usage."""

    def setUp(self):
        self.engine = ReflectionEngine()

    def test_detects_dominant_capability(self):
        """Capability in >80% of outcomes is flagged as dominant."""
        outcomes = []
        for i in range(10):
            caps = [{"name": "dominant", "priority": 1, "reason": "test"}]
            if i >= 8:
                caps.append({"name": "rare", "priority": 2, "reason": "alt"})
            outcomes.append(
                ReasoningOutcome(
                    timestamp=datetime.now(),
                    goal=f"goal-{i}",
                    decision_action="respond",
                    capabilities=caps,
                    routes=[{"capability": "dominant", "handler_name": "dom", "strategy": "direct"}],
                    results=[{"capability": "dominant", "success": True, "output": {}, "error": None}],
                    success=True,
                )
            )
        suggestions = self.engine.analyze(outcomes)
        patterns = [s.pattern for s in suggestions]
        self.assertIn("capability_imbalance", patterns)

    def test_fewer_than_five_outcomes_no_imbalance_suggestion(self):
        """Imbalance analysis needs >=5 outcomes."""
        outcomes = []
        for i in range(4):
            outcomes.append(
                ReasoningOutcome(
                    timestamp=datetime.now(),
                    goal=f"goal-{i}",
                    decision_action="respond",
                    capabilities=[{"name": "conv", "priority": 1, "reason": "test"}],
                    routes=[{"capability": "conv", "handler_name": "conv", "strategy": "direct"}],
                    results=[{"capability": "conv", "success": True, "output": {}, "error": None}],
                    success=True,
                )
            )
        suggestions = self.engine.analyze(outcomes)
        patterns = [s.pattern for s in suggestions]
        self.assertNotIn("capability_imbalance", patterns)

    def test_balanced_capabilities_no_suggestion(self):
        """Evenly distributed capabilities produce no imbalance suggestion."""
        outcomes = []
        for i in range(10):
            cap_name = f"cap-{i % 4}"
            outcomes.append(
                ReasoningOutcome(
                    timestamp=datetime.now(),
                    goal=f"goal-{i}",
                    decision_action="respond",
                    capabilities=[{"name": cap_name, "priority": 1, "reason": "test"}],
                    routes=[{"capability": cap_name, "handler_name": cap_name, "strategy": "direct"}],
                    results=[{"capability": cap_name, "success": True, "output": {}, "error": None}],
                    success=True,
                )
            )
        suggestions = self.engine.analyze(outcomes)
        patterns = [s.pattern for s in suggestions]
        # Each cap appears ~2-3 times, none exceeds 80%
        self.assertNotIn("capability_imbalance", patterns)


class TestReflectionEngineDeterminism(unittest.TestCase):
    """ReflectionEngine produces deterministic results."""

    def setUp(self):
        self.engine = ReflectionEngine()

    def test_same_input_produces_same_output(self):
        """Identical outcomes produce identical suggestions."""
        outcome = ReasoningOutcome(
            timestamp=datetime.now(),
            goal="test",
            decision_action="respond",
            capabilities=[{"name": "failing_cap", "priority": 1, "reason": "test"}],
            routes=[{"capability": "failing_cap", "handler_name": "fail", "strategy": "direct"}],
            results=[{"capability": "failing_cap", "success": False, "output": {}, "error": "err"}],
            success=False,
        )
        outcomes = [outcome] * 5

        result1 = self.engine.analyze(outcomes)
        result2 = self.engine.analyze(outcomes)

        self.assertEqual(len(result1), len(result2))
        for s1, s2 in zip(result1, result2):
            self.assertEqual(s1.pattern, s2.pattern)


class TestReflectionEngineInfrastructurePurity(unittest.TestCase):
    """ReflectionEngine must not import infrastructure modules."""

    def test_no_infrastructure_imports(self):
        """ReflectionEngine imports no banned modules."""
        import importlib
        import os

        reflection_module = importlib.import_module("atlas.reasoning.reflection")
        file_path = reflection_module.__file__
        assert file_path is not None
        with open(file_path, "r") as f:
            module_source = f.read()
        # Only check actual import/from lines
        for line in module_source.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                self.assertNotIn("EventBus", stripped)
                self.assertNotIn("MemoryManagerService", stripped)
                self.assertNotIn("KnowledgeManager", stripped)
                self.assertNotIn("AIProvider", stripped)
                self.assertNotIn("CognitionService", stripped)


if __name__ == "__main__":
    unittest.main()