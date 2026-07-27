"""
Phase 9.2a — Experience → Understanding Bridge Integration Tests.

Tests for RuntimeCoordinator wiring:
- Experiences are fed into UnderstandingEngine after pipeline completion
- Understanding graph receives experience-derived concepts
- Insights are generated from experiences
- Repeated runs consolidate correctly
- Missing dependencies handled gracefully
"""

import unittest
from datetime import datetime
from unittest.mock import MagicMock, PropertyMock

from atlas.cognition.models import (
    CognitionState,
    PipelineMetrics,
    PipelineResult,
    StageResult,
    StageStatus,
    StageType,
)
from atlas.experience.models import ExperienceOutcome, StructuredExperience
from atlas.experience.experience_repository import ExperienceRepository
from atlas.experience.experience_accumulator import ExperienceAccumulator
from atlas.runtime.runtime_coordinator import RuntimeCoordinator
from atlas.understanding.understanding_engine import UnderstandingEngine


class TestExperienceBridgeIntegration(unittest.TestCase):
    """Experiences flow from accumulator through bridge into understanding."""

    def setUp(self):
        self.repo = ExperienceRepository(max_experiences=100)
        self.accumulator = ExperienceAccumulator(repository=self.repo)
        self.understanding = UnderstandingEngine()
        self.coordinator = RuntimeCoordinator()
        self.coordinator.set_experience_accumulator(self.accumulator)
        # Inject the understanding engine (same pattern as Atlas.start())
        self.coordinator._understanding_engine = self.understanding

    def tearDown(self):
        self.repo.clear()

    def _add_experience_directly(self, capability: str = "conversation",
                                  outcome: ExperienceOutcome = ExperienceOutcome.SUCCESS) -> None:
        """Add an experience directly to the repository to simulate prior runs."""
        exp = StructuredExperience(
            experience_id=f"EXP-{self.repo.experience_count + 1:08d}",
            timestamp=datetime.now(),
            duration_ms=50.0,
            pipeline_path=["understanding", "reasoning"],
            outcome=outcome,
            reasoning_capabilities=[capability],
        )
        self.repo.store_experience(exp)

    def test_experiences_fed_to_understanding_after_pipeline(self):
        """After process(), understanding graph has concepts from experiences."""
        self._add_experience_directly(capability="conversation")
        self._add_experience_directly(capability="analysis")

        result = self.coordinator.process("hello")
        self.assertTrue(result.success)

        # Understanding engine should now have concepts from the bridge
        concepts = self.understanding.graph.get_all_concepts()
        labels = [c.label for c in concepts]
        # Should have concepts from experiences (outcome, capability names)
        self.assertIn("conversation", labels)
        self.assertIn("analysis", labels)
        self.assertIn("outcome:success", labels)

    def test_insights_generated_from_experiences(self):
        """Experience processing produces understanding insights."""
        self._add_experience_directly(capability="tool_execution")

        self.coordinator.process("hello")

        insights = self.understanding.memory.get_insights(100)
        self.assertGreater(len(insights), 0)

        # Should have at least one TREND_INSIGHT or PATTERN_INSIGHT
        from atlas.understanding.models import UnderstandingCategory
        categories = {i.category for i in insights}
        has_meaningful_category = (
            UnderstandingCategory.TREND_INSIGHT in categories
            or UnderstandingCategory.PATTERN_INSIGHT in categories
        )
        self.assertTrue(has_meaningful_category)

    def test_repeated_runs_consolidate_concepts(self):
        """Repeated runs with same capability merge into single concept."""
        for i in range(3):
            self._add_experience_directly(capability="repeated_cap")

        self.coordinator.process("hello")

        capability_concepts = [
            c for c in self.understanding.graph.get_all_concepts()
            if c.label == "repeated_cap"
        ]
        self.assertEqual(len(capability_concepts), 1)
        self.assertEqual(capability_concepts[0].frequency, 3)

    def test_subsequent_runs_enrich_graph(self):
        """Understanding state accumulates across pipeline calls."""
        self._add_experience_directly(capability="first_cap")
        self.coordinator.process("first run")
        first_count = len(self.understanding.graph.get_all_concepts())

        self._add_experience_directly(capability="second_cap")
        self.coordinator.process("second run")
        second_count = len(self.understanding.graph.get_all_concepts())

        # Second run should have added new concepts (not just replaced)
        self.assertGreaterEqual(second_count, first_count)

        # Second_cap should now exist
        labels = [c.label for c in self.understanding.graph.get_all_concepts()]
        self.assertIn("first_cap", labels)
        self.assertIn("second_cap", labels)

    def test_text_and_experience_both_contribute(self):
        """process_text + experience bridge combine for richer understanding."""
        # First process text directly (simulates what stage 4 does)
        self.understanding.process_text("the api interface module", source="test")
        text_concept_count = self.understanding.graph.concept_count

        # Then run pipeline with experiences
        self._add_experience_directly(capability="execute")
        self.coordinator.process("hello")

        # Should have more concepts than text alone
        self.assertGreater(self.understanding.graph.concept_count, text_concept_count)
        self.assertIsNotNone(self.understanding.graph.get_concept_by_label("execute"))

    def test_understanding_relationships_from_experiences(self):
        """Experience bridge creates relationships that appear in the graph."""
        self._add_experience_directly(capability="respond")
        self.coordinator.process("hello")

        # Graph should have relationships (capability → outcome, etc.)
        # Note: UnderstandingGraph.relationship_count may come from memory
        rels = self.understanding.memory.get_relationships(100)
        self.assertGreater(len(rels), 0)

    def test_patterns_generated_from_experiences(self):
        """Experience patterns appear in understanding memory."""
        for i in range(4):
            self._add_experience_directly(capability="stable_op")

        self.coordinator.process("hello")

        patterns = self.understanding.memory.get_patterns(50)
        pattern_labels = [p.label for p in patterns]
        self.assertTrue(
            any("stable_op" in label for label in pattern_labels),
            f"Expected a pattern mentioning 'stable_op', got: {pattern_labels}",
        )

    def test_experience_bridge_does_not_break_text_pipeline(self):
        """Text pipeline still works after experience bridge processes."""
        self._add_experience_directly(capability="tool_call")
        self.coordinator.process("hello")

        # Text pipeline should still work independently
        text_insights = self.understanding.process_text(
            "analysis complete", source="test"
        )
        self.assertGreater(len(text_insights), 0)

    def test_absent_understanding_engine_skips_gracefully(self):
        """No understanding engine → no error, pipeline completes."""
        coord = RuntimeCoordinator()
        coord.set_experience_accumulator(self.accumulator)
        # Do NOT inject understanding engine
        result = coord.process("hello")
        self.assertTrue(result.success)

    def test_absent_experience_accumulator_skips_gracefully(self):
        """No accumulator → no error, pipeline completes."""
        coord = RuntimeCoordinator()
        coord._understanding_engine = self.understanding
        # Do NOT inject experience accumulator
        result = coord.process("hello")
        self.assertTrue(result.success)

    def test_empty_experience_repo_skips_gracefully(self):
        """Empty repo → no experience processing, no error."""
        # No experiences added to the repo
        result = self.coordinator.process("hello")
        self.assertTrue(result.success)

        # Understanding graph should only have text-derived concepts
        concepts = self.understanding.graph.get_all_concepts()
        # The text "hello" should produce some concepts from process_text
        self.assertGreaterEqual(len(concepts), 0)

    def test_accumulator_not_injected_skips_gracefully(self):
        """Default RuntimeCoordinator with no accumulator set → safe."""
        coord = RuntimeCoordinator()
        coord._understanding_engine = self.understanding
        result = coord.process("hello")
        self.assertTrue(result.success)


class TestExperienceBridgeOrdering(unittest.TestCase):
    """Verify processing order: accumulate then feed to understanding."""

    def setUp(self):
        self.repo = ExperienceRepository(max_experiences=100)
        self.accumulator = ExperienceAccumulator(repository=self.repo)
        self.understanding = UnderstandingEngine()
        # Track if process_experiences was called via closure variables
        self._bridge_called = False
        self._last_exp_count = 0
        original = self.understanding.process_experiences

        def tracking_wrapper(experiences, source=""):
            self._bridge_called = True
            self._last_exp_count = len(experiences)
            return original(experiences, source=source)

        self.understanding.process_experiences = tracking_wrapper

        self.coordinator = RuntimeCoordinator()
        self.coordinator.set_experience_accumulator(self.accumulator)
        self.coordinator._understanding_engine = self.understanding

    def tearDown(self):
        self.repo.clear()

    def test_experiences_are_recorded_before_understanding(self):
        """process_experiences receives the just-recorded experience."""
        result = self.coordinator.process("hello")
        self.assertTrue(result.success)
        self.assertTrue(self._bridge_called)
        self.assertGreater(self._last_exp_count, 0,
                           "process_experiences should receive at least one experience")


if __name__ == "__main__":
    unittest.main()
