"""
Tests for the Planning Engine pure logic component.

Phase 6.8 — Planning Engine.
"""

import unittest

from atlas.reasoning.models import ReasoningPlan, ReasoningStep
from atlas.reasoning.planning import PlanningEngine, PlanningPlan, PlanningStep


class TestPlanningEngine(unittest.TestCase):
    """Unit tests for PlanningEngine."""

    def setUp(self):
        self.engine = PlanningEngine()

    # --- decompose() tests ---

    def test_decompose_empty_plan(self):
        """Decomposing a plan with no steps returns a completed plan."""
        plan = ReasoningPlan(goal="do nothing", steps=[])
        result = self.engine.decompose(plan)

        self.assertIsInstance(result, PlanningPlan)
        self.assertEqual(result.goal, "do nothing")
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.steps), 0)

    def test_decompose_single_step_plan(self):
        """Decomposing a single-step plan preserves the step."""
        step = ReasoningStep(
            description="say hello",
            action="respond",
            parameters={"message": "hello"},
        )
        plan = ReasoningPlan(goal="greet user", steps=[step])
        result = self.engine.decompose(plan)

        self.assertEqual(result.goal, "greet user")
        self.assertEqual(result.status, "pending")
        self.assertEqual(len(result.steps), 1)
        self.assertEqual(result.steps[0].id, "step-1")
        self.assertEqual(result.steps[0].action, "respond")
        self.assertEqual(result.steps[0].description, "say hello")
        self.assertEqual(result.steps[0].parameters, {"message": "hello"})
        self.assertEqual(result.steps[0].status, "pending")
        self.assertEqual(result.sub_goals, ["greet user"])

    def test_decompose_multi_step_plan(self):
        """Decomposing a multi-step plan creates steps with dependencies."""
        step1 = ReasoningStep(description="research topic", action="research")
        step2 = ReasoningStep(description="write summary", action="write")
        plan = ReasoningPlan(goal="create report", steps=[step1, step2])
        result = self.engine.decompose(plan)

        self.assertEqual(result.goal, "create report")
        self.assertEqual(len(result.steps), 2)
        self.assertEqual(result.steps[0].id, "step-1")
        self.assertEqual(result.steps[1].id, "step-2")
        # Step 2 should depend on step 1 (sequential)
        self.assertIn("step-1", result.dependencies.get("step-2", []))

    def test_decompose_preserves_metadata(self):
        """Decomposing preserves metadata from the original plan."""
        plan = ReasoningPlan(
            goal="test",
            steps=[ReasoningStep(description="do", action="do")],
            metadata={"source": "test", "version": 1},
        )
        result = self.engine.decompose(plan)
        self.assertEqual(result.metadata.get("source"), "test")
        self.assertEqual(result.metadata.get("version"), 1)

    # --- validate() tests ---

    def test_validate_valid_plan(self):
        """A well-formed plan returns no validation errors."""
        step1 = PlanningStep(id="step-1", description="first", action="do")
        step2 = PlanningStep(
            id="step-2", description="second", action="do", depends_on=["step-1"]
        )
        plan = PlanningPlan(
            goal="test",
            steps=[step1, step2],
            dependencies={"step-2": ["step-1"]},
        )
        errors = self.engine.validate(plan)
        self.assertEqual(errors, [])

    def test_validate_empty_plan(self):
        """An empty plan (no steps) is valid."""
        plan = PlanningPlan(goal="empty")
        errors = self.engine.validate(plan)
        self.assertEqual(errors, [])

    def test_validate_empty_action(self):
        """A step with an empty action produces a validation error."""
        step = PlanningStep(id="step-1", description="bad", action="")
        plan = PlanningPlan(goal="test", steps=[step])
        errors = self.engine.validate(plan)
        self.assertIn("empty action", errors[0].lower())

    def test_validate_unknown_dependency(self):
        """A step referencing a non-existent step ID produces an error."""
        step = PlanningStep(
            id="step-1", description="bad", action="do", depends_on=["step-99"]
        )
        plan = PlanningPlan(goal="test", steps=[step])
        errors = self.engine.validate(plan)
        self.assertIn("unknown step", errors[0].lower())

    def test_validate_circular_dependency(self):
        """A circular dependency produces a validation error."""
        step1 = PlanningStep(
            id="step-1", description="first", action="do", depends_on=["step-2"]
        )
        step2 = PlanningStep(
            id="step-2", description="second", action="do", depends_on=["step-1"]
        )
        plan = PlanningPlan(goal="test", steps=[step1, step2])
        errors = self.engine.validate(plan)
        self.assertTrue(any("circular" in e.lower() for e in errors))

    def test_validate_self_reference_dependency(self):
        """A step depending on itself produces a circular dependency error."""
        step = PlanningStep(
            id="step-1", description="self", action="do", depends_on=["step-1"]
        )
        plan = PlanningPlan(goal="test", steps=[step])
        errors = self.engine.validate(plan)
        self.assertTrue(any("circular" in e.lower() for e in errors))

    def test_validate_empty_sub_goals(self):
        """Empty sub-goal entries produce a validation error."""
        step = PlanningStep(id="step-1", description="do", action="do")
        plan = PlanningPlan(
            goal="test",
            steps=[step],
            sub_goals=["valid", ""],
        )
        errors = self.engine.validate(plan)
        self.assertIn("empty sub-goal", errors[0].lower())

    # --- next_steps() tests ---

    def test_next_steps_all_pending_no_deps(self):
        """All pending steps with no dependencies are ready."""
        step1 = PlanningStep(id="step-1", description="a", action="do")
        step2 = PlanningStep(id="step-2", description="b", action="do")
        plan = PlanningPlan(goal="test", steps=[step1, step2])
        ready = self.engine.next_steps(plan)
        self.assertEqual(len(ready), 2)

    def test_next_steps_with_dependencies(self):
        """Only steps whose dependencies are completed are ready."""
        step1 = PlanningStep(
            id="step-1", description="first", action="do", status="completed"
        )
        step2 = PlanningStep(
            id="step-2",
            description="second",
            action="do",
            depends_on=["step-1"],
            status="pending",
        )
        step3 = PlanningStep(
            id="step-3",
            description="third",
            action="do",
            depends_on=["step-2"],
            status="pending",
        )
        plan = PlanningPlan(
            goal="test",
            steps=[step1, step2, step3],
            dependencies={"step-2": ["step-1"], "step-3": ["step-2"]},
        )
        ready = self.engine.next_steps(plan)
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].id, "step-2")

    def test_next_steps_blocked_by_dependency(self):
        """A step with an uncompleted dependency is not ready."""
        step1 = PlanningStep(
            id="step-1", description="first", action="do", status="pending"
        )
        step2 = PlanningStep(
            id="step-2",
            description="second",
            action="do",
            depends_on=["step-1"],
            status="pending",
        )
        plan = PlanningPlan(
            goal="test",
            steps=[step1, step2],
            dependencies={"step-2": ["step-1"]},
        )
        ready = self.engine.next_steps(plan)
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].id, "step-1")

    def test_next_steps_completed_plan(self):
        """A completed plan returns no next steps."""
        step = PlanningStep(id="step-1", description="done", action="do")
        plan = PlanningPlan(goal="test", steps=[step], status="completed")
        ready = self.engine.next_steps(plan)
        self.assertEqual(ready, [])

    def test_next_steps_failed_plan(self):
        """A failed plan returns no next steps."""
        step = PlanningStep(id="step-1", description="fail", action="do")
        plan = PlanningPlan(goal="test", steps=[step], status="failed")
        ready = self.engine.next_steps(plan)
        self.assertEqual(ready, [])

    def test_next_steps_non_pending_skipped(self):
        """Steps that are not pending are not returned as next steps."""
        step1 = PlanningStep(
            id="step-1", description="a", action="do", status="in_progress"
        )
        step2 = PlanningStep(
            id="step-2", description="b", action="do", status="completed"
        )
        step3 = PlanningStep(
            id="step-3", description="c", action="do", status="failed"
        )
        step4 = PlanningStep(
            id="step-4", description="d", action="do", status="blocked"
        )
        plan = PlanningPlan(goal="test", steps=[step1, step2, step3, step4])
        ready = self.engine.next_steps(plan)
        self.assertEqual(len(ready), 0)

    def test_next_steps_empty_plan(self):
        """An empty plan returns no next steps."""
        plan = PlanningPlan(goal="empty")
        ready = self.engine.next_steps(plan)
        self.assertEqual(ready, [])


class TestPlanningPlanModel(unittest.TestCase):
    """Unit tests for the PlanningPlan dataclass."""

    def test_default_values(self):
        """PlanningPlan has sensible defaults."""
        plan = PlanningPlan()
        self.assertEqual(plan.goal, "")
        self.assertEqual(plan.sub_goals, [])
        self.assertEqual(plan.steps, [])
        self.assertEqual(plan.dependencies, {})
        self.assertEqual(plan.status, "pending")
        self.assertEqual(plan.metadata, {})
        self.assertEqual(plan.validation_errors, [])

    def test_custom_values(self):
        """PlanningPlan accepts custom values."""
        step = PlanningStep(id="s1", description="test", action="do")
        plan = PlanningPlan(
            goal="custom goal",
            sub_goals=["sub1"],
            steps=[step],
            dependencies={"s1": []},
            status="active",
            metadata={"key": "val"},
            validation_errors=["err"],
        )
        self.assertEqual(plan.goal, "custom goal")
        self.assertEqual(plan.sub_goals, ["sub1"])
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.dependencies, {"s1": []})
        self.assertEqual(plan.status, "active")
        self.assertEqual(plan.metadata, {"key": "val"})
        self.assertEqual(plan.validation_errors, ["err"])


class TestPlanningStepModel(unittest.TestCase):
    """Unit tests for the PlanningStep dataclass."""

    def test_default_values(self):
        """PlanningStep has sensible defaults."""
        step = PlanningStep(id="s1")
        self.assertEqual(step.id, "s1")
        self.assertEqual(step.description, "")
        self.assertEqual(step.action, "")
        self.assertEqual(step.parameters, {})
        self.assertEqual(step.depends_on, [])
        self.assertEqual(step.status, "pending")
        self.assertEqual(step.validation_errors, [])

    def test_custom_values(self):
        """PlanningStep accepts custom values."""
        step = PlanningStep(
            id="s1",
            description="do something",
            action="execute",
            parameters={"key": "val"},
            depends_on=["s0"],
            status="in_progress",
            validation_errors=["err"],
        )
        self.assertEqual(step.id, "s1")
        self.assertEqual(step.description, "do something")
        self.assertEqual(step.action, "execute")
        self.assertEqual(step.parameters, {"key": "val"})
        self.assertEqual(step.depends_on, ["s0"])
        self.assertEqual(step.status, "in_progress")
        self.assertEqual(step.validation_errors, ["err"])


if __name__ == "__main__":
    unittest.main()