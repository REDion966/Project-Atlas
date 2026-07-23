"""
Tests for the Atlas Reasoning Controller (Phase 6.1).
"""

import unittest

from atlas.cognition.decision import CognitionDecision
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.models import ReasoningPlan, ReasoningStep


class TestReasoningPlan(unittest.TestCase):
    """Tests for ReasoningPlan data model."""

    def test_plan_creation(self):
        """A ReasoningPlan can be created with a goal and steps."""

        step = ReasoningStep(
            description="Test step",
            action="respond",
            parameters={"key": "value"},
        )

        plan = ReasoningPlan(
            goal="test: verify",
            steps=[step],
            metadata={"version": 1},
        )

        self.assertEqual(plan.goal, "test: verify")
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].description, "Test step")
        self.assertEqual(plan.steps[0].action, "respond")
        self.assertEqual(plan.steps[0].parameters["key"], "value")
        self.assertEqual(plan.metadata["version"], 1)

    def test_default_values(self):
        """ReasoningPlan and ReasoningStep have sensible defaults."""

        plan = ReasoningPlan()
        step = ReasoningStep()

        self.assertEqual(plan.goal, "")
        self.assertEqual(plan.steps, [])
        self.assertEqual(plan.metadata, {})

        self.assertEqual(step.description, "")
        self.assertEqual(step.action, "")
        self.assertEqual(step.parameters, {})

    def test_step_in_plan(self):
        """Multiple steps can be stored in a plan."""

        steps = [
            ReasoningStep(description="Step 1", action="analyze"),
            ReasoningStep(description="Step 2", action="execute"),
        ]

        plan = ReasoningPlan(
            goal="multi-step",
            steps=steps,
        )

        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].action, "analyze")
        self.assertEqual(plan.steps[1].action, "execute")


class TestReasoningController(unittest.TestCase):
    """Tests for ReasoningController."""

    def setUp(self):
        self.controller = ReasoningController()

    def test_create_plan_from_decision(self):
        """Controller produces a ReasoningPlan from a CognitionDecision."""

        decision = CognitionDecision(
            action="respond",
            reasoning="User asked a question",
            data={"input": "What is Atlas?"},
        )

        plan = self.controller.create_plan(decision)

        self.assertIsInstance(plan, ReasoningPlan)
        self.assertIn("respond", plan.goal)
        self.assertIn("User asked a question", plan.goal)

    def test_plan_contains_step_with_decision_data(self):
        """The plan step carries the decision's action and data."""

        decision = CognitionDecision(
            action="query",
            reasoning="Looking up information",
            data={"topic": "cognition"},
        )

        plan = self.controller.create_plan(decision)

        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].action, "query")
        self.assertEqual(plan.steps[0].parameters["topic"], "cognition")

    def test_controller_has_no_external_dependencies(self):
        """ReasoningController does not import AI, memory, or knowledge."""

        import inspect

        # Verify the controller only imports from cognition.decision and reasoning.models
        source = inspect.getsource(ReasoningController)
        self.assertNotIn("AIService", source)
        self.assertNotIn("Memory", source)
        self.assertNotIn("Knowledge", source)
        self.assertNotIn("EventBus", source)
        self.assertNotIn("Service", source)

    def test_metadata_includes_source_and_action(self):
        """Plan metadata contains source and action from the decision."""

        decision = CognitionDecision(
            action="respond",
            reasoning="Test",
        )

        plan = self.controller.create_plan(decision)

        self.assertEqual(plan.metadata["source"], "cognition")
        self.assertEqual(plan.metadata["action"], "respond")


if __name__ == "__main__":
    unittest.main()