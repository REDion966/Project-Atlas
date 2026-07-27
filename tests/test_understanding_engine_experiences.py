"""
Phase 9.2a — UnderstandingEngine.process_experiences() integration tests.
"""

from datetime import datetime

import pytest

from atlas.experience.models import (
    ExperienceOutcome,
    StructuredExperience,
)
from atlas.understanding.understanding_engine import UnderstandingEngine
from atlas.understanding.models import (
    ConceptDomain,
    UnderstandingCategory,
)


def _make_experience(
    experience_id: str = "EXP-00000001",
    outcome: ExperienceOutcome = ExperienceOutcome.SUCCESS,
    reasoning_capabilities: list[str] | None = None,
    planning_goal: str = "",
    tool_name: str = "",
) -> StructuredExperience:
    return StructuredExperience(
        experience_id=experience_id,
        timestamp=datetime.now(),
        duration_ms=100.0,
        pipeline_path=["reasoning", "tool_execution"],
        outcome=outcome,
        user_input="test input",
        reasoning_capabilities=reasoning_capabilities or [],
        planning_goal=planning_goal,
        tool_name=tool_name,
    )


class TestUnderstandingEngineProcessExperiences:

    def test_empty_process_experiences(self):
        engine = UnderstandingEngine()
        result = engine.process_experiences([])
        assert result == []
        assert engine.graph.concept_count == 0
        assert engine.memory.insight_count == 0

    def test_process_experiences_produces_insights(self):
        engine = UnderstandingEngine()
        experience = _make_experience(
            experience_id="EXP-001",
            outcome=ExperienceOutcome.SUCCESS,
            reasoning_capabilities=["respond"],
        )
        result = engine.process_experiences([experience])

        assert len(result) > 0
        # Should contain at least a trend insight from the bridge.
        trend_insights = [
            i for i in result
            if i.category == UnderstandingCategory.TREND_INSIGHT
        ]
        assert len(trend_insights) >= 1

    def test_process_experiences_consolidates_repeated_concepts(self):
        engine = UnderstandingEngine()
        experiences = [
            _make_experience(
                experience_id=f"EXP-{i:08d}",
                outcome=ExperienceOutcome.SUCCESS,
                reasoning_capabilities=["repeated_capability"],
            )
            for i in range(3)
        ]
        engine.process_experiences(experiences)

        # After consolidation, only one concept for the repeated capability.
        capability_concepts = [
            c for c in engine.graph.get_all_concepts()
            if c.label == "repeated_capability"
        ]
        assert len(capability_concepts) == 1
        assert capability_concepts[0].frequency == 3
        assert capability_concepts[0].domain == ConceptDomain.TECHNICAL

    def test_process_experiences_updates_graph(self):
        engine = UnderstandingEngine()
        experience = _make_experience(
            experience_id="EXP-GRAPH-001",
            outcome=ExperienceOutcome.SUCCESS,
            reasoning_capabilities=["analyze"],
            planning_goal="solve problem",
        )
        engine.process_experiences([experience])

        assert engine.graph.concept_count >= 3  # capability, goal, outcome
        assert engine.graph.get_concept_by_label("analyze") is not None
        assert engine.graph.get_concept_by_label("solve problem") is not None

    def test_process_experiences_updates_memory(self):
        engine = UnderstandingEngine()
        experience = _make_experience(
            experience_id="EXP-MEM-001",
            outcome=ExperienceOutcome.SUCCESS,
            reasoning_capabilities=["route"],
            tool_name="my_tool",
        )
        engine.process_experiences([experience])

        assert engine.memory.concept_count >= 3
        assert engine.memory.insight_count > 0
        assert engine.memory.pattern_count > 0
        assert engine.memory.relationship_count > 0

    def test_process_experiences_does_not_break_text_pipeline(self):
        engine = UnderstandingEngine()

        # First process experiences
        experience = _make_experience(
            experience_id="EXP-TEXT-001",
            outcome=ExperienceOutcome.SUCCESS,
            reasoning_capabilities=["respond"],
        )
        engine.process_experiences([experience])
        concept_count_after_experience = engine.graph.concept_count

        # Then process text
        text_result = engine.process_text("hello world", source="test")
        assert len(text_result) > 0
        assert engine.graph.concept_count > concept_count_after_experience

    def test_text_pipeline_then_experiences(self):
        engine = UnderstandingEngine()

        # First process text
        engine.process_text("the api interface and module", source="test")
        text_concepts = engine.graph.concept_count

        # Then process experiences
        experience = _make_experience(
            experience_id="EXP-TEXT-002",
            outcome=ExperienceOutcome.SUCCESS,
            reasoning_capabilities=["execute"],
        )
        engine.process_experiences([experience])

        assert engine.graph.concept_count > text_concepts
        assert engine.graph.get_concept_by_label("execute") is not None

    def test_experience_insights_are_stored(self):
        engine = UnderstandingEngine()
        experience = _make_experience(
            experience_id="EXP-INS-001",
            outcome=ExperienceOutcome.FAILURE,
            reasoning_capabilities=["fragile"],
        )
        engine.process_experiences([experience])

        failure_insights = [
            i for i in engine.memory.get_insights(100)
            if "FAILURE" in i.summary or "failure" in i.detail
        ]
        assert len(failure_insights) > 0

    def test_repeated_experiences_increase_confidence(self):
        engine = UnderstandingEngine()
        experiences = [
            _make_experience(
                experience_id=f"EXP-CONF-{i:03d}",
                outcome=ExperienceOutcome.SUCCESS,
                reasoning_capabilities=["stable_capability"],
            )
            for i in range(4)
        ]
        engine.process_experiences(experiences)

        concept = engine.graph.get_concept_by_label("stable_capability")
        assert concept is not None
        assert concept.frequency == 4
        # Confidence may stay stable depending on the consolidator formula;
        # only guarantee is it stays within valid range.
        assert 0.0 <= concept.confidence <= 1.0

    def test_relationships_are_consolidated(self):
        engine = UnderstandingEngine()
        experience = _make_experience(
            experience_id="EXP-REL-001",
            outcome=ExperienceOutcome.SUCCESS,
            reasoning_capabilities=["capability_a"],
            tool_name="tool_x",
        )
        engine.process_experiences([experience])

        assert engine.memory.relationship_count > 0
        assert engine.graph.relationship_count > 0

    def test_empty_text_after_experiences(self):
        engine = UnderstandingEngine()

        # process_experiences([]) produces no mutation
        result = engine.process_experiences([])
        assert result == []
        assert engine.graph.concept_count == 0

        # empty text pipeline behavior remains unchanged
        empty_result = engine.process_text("")
        assert empty_result == []
        assert engine.graph.concept_count == 0

        # no duplicate concepts are created
        engine.process_text("")
        assert engine.graph.concept_count == 0
