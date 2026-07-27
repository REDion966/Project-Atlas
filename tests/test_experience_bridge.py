"""
Phase 9.2a — Experience → Understanding Bridge Tests.
"""

from datetime import datetime

import pytest

from atlas.experience.models import (
    ExperienceOutcome,
    StructuredExperience,
)
from atlas.understanding.experience_bridge import (
    BridgeResult,
    ExperienceBridge,
    ExperienceSource,
)
from atlas.understanding.models import (
    ConceptDomain,
    RelationshipType,
    UnderstandingCategory,
)


def _make_experience(
    experience_id: str = "EXP-00000001",
    outcome: ExperienceOutcome = ExperienceOutcome.SUCCESS,
    reasoning_capabilities: list[str] | None = None,
    planning_goal: str = "",
    tool_name: str = "",
    pipeline_path: list[str] | None = None,
) -> StructuredExperience:
    return StructuredExperience(
        experience_id=experience_id,
        timestamp=datetime.now(),
        duration_ms=100.0,
        pipeline_path=pipeline_path or ["reasoning", "tool_execution"],
        outcome=outcome,
        user_input="test input",
        reasoning_capabilities=reasoning_capabilities or [],
        planning_goal=planning_goal,
        tool_name=tool_name,
    )


# ===================================================================
# Basic transform tests
# ===================================================================

class TestExperienceBridgeTransform:

    def test_empty_experiences_returns_empty(self):
        bridge = ExperienceBridge()
        result = bridge.transform([])
        assert result == BridgeResult()

    def test_success_experience_creates_concepts(self):
        bridge = ExperienceBridge()
        experience = _make_experience(
            experience_id="EXP-00000001",
            outcome=ExperienceOutcome.SUCCESS,
            reasoning_capabilities=["respond"],
            planning_goal="answer user",
            tool_name="text_tool",
        )
        result = bridge.transform([experience])

        labels = [c.label for c in result.concepts]
        assert "outcome:success" in labels
        assert "respond" in labels
        assert "answer user" in labels
        assert "text_tool" in labels

    def test_failure_experience_creates_failure_concepts(self):
        bridge = ExperienceBridge()
        experience = _make_experience(
            experience_id="EXP-00000002",
            outcome=ExperienceOutcome.FAILURE,
            reasoning_capabilities=["execute_tool"],
        )
        result = bridge.transform([experience])

        labels = [c.label for c in result.concepts]
        assert "outcome:failure" in labels
        assert "execute_tool" in labels

    def test_source_provenance_uses_experience_id(self):
        bridge = ExperienceBridge()
        experience = _make_experience(
            experience_id="EXP-TEST-123",
            outcome=ExperienceOutcome.SUCCESS,
            reasoning_capabilities=["capability_a"],
        )
        result = bridge.transform([experience])

        for concept in result.concepts:
            assert concept.source == "EXP-TEST-123"

    def test_reasoning_capability_extraction(self):
        bridge = ExperienceBridge()
        experience = _make_experience(
            reasoning_capabilities=["analyze", "route", "dispatch"],
        )
        result = bridge.transform([experience])

        capability_concepts = [
            c for c in result.concepts
            if c.metadata.get("field") == "reasoning_capability"
        ]
        labels = [c.label for c in capability_concepts]
        assert set(labels) == {"analyze", "route", "dispatch"}
        for concept in capability_concepts:
            assert concept.domain == ConceptDomain.TECHNICAL

    def test_planning_goal_extraction(self):
        bridge = ExperienceBridge()
        experience = _make_experience(planning_goal="decompose task")
        result = bridge.transform([experience])

        goal_concepts = [
            c for c in result.concepts
            if c.metadata.get("field") == "planning_goal"
        ]
        assert len(goal_concepts) == 1
        assert goal_concepts[0].label == "decompose task"

    def test_tool_extraction(self):
        bridge = ExperienceBridge()
        experience = _make_experience(tool_name="file_reader")
        result = bridge.transform([experience])

        tool_concepts = [
            c for c in result.concepts
            if c.metadata.get("field") == "tool_name"
        ]
        assert len(tool_concepts) == 1
        assert tool_concepts[0].label == "file_reader"
        assert tool_concepts[0].domain == ConceptDomain.TECHNICAL


# ===================================================================
# Pattern tests
# ===================================================================

class TestExperienceBridgePatterns:

    def test_outcome_pattern_detected(self):
        bridge = ExperienceBridge()
        experiences = [
            _make_experience(experience_id=f"EXP-{i:08d}", outcome=ExperienceOutcome.SUCCESS)
            for i in range(3)
        ]
        result = bridge.transform(experiences)

        pattern_labels = [p.label for p in result.patterns]
        assert any("Outcome distribution" in label for label in pattern_labels)

    def test_capability_trend_pattern_success(self):
        bridge = ExperienceBridge()
        experiences = [
            _make_experience(
                experience_id=f"EXP-{i:08d}",
                outcome=ExperienceOutcome.SUCCESS,
                reasoning_capabilities=["stable_cap"],
            )
            for i in range(4)
        ]
        result = bridge.transform(experiences)

        pattern_labels = [p.label for p in result.patterns]
        assert any("Capability trend: stable_cap succeeds" in label for label in pattern_labels)

    def test_capability_trend_pattern_failure(self):
        bridge = ExperienceBridge()
        experiences = [
            _make_experience(
                experience_id=f"EXP-{i:08d}",
                outcome=ExperienceOutcome.FAILURE,
                reasoning_capabilities=["fragile_cap"],
            )
            for i in range(3)
        ]
        result = bridge.transform(experiences)

        pattern_labels = [p.label for p in result.patterns]
        assert any("Capability trend: fragile_cap fails" in label for label in pattern_labels)


# ===================================================================
# Insight tests
# ===================================================================

class TestExperienceBridgeInsights:

    def test_insight_generated_for_experience(self):
        bridge = ExperienceBridge()
        experience = _make_experience(experience_id="EXP-INS-001")
        result = bridge.transform([experience])

        trend_insights = [
            i for i in result.insights
            if i.category == UnderstandingCategory.TREND_INSIGHT
        ]
        assert len(trend_insights) == 1
        assert "EXP-INS-001" in trend_insights[0].summary

    def test_pattern_insight_generated(self):
        bridge = ExperienceBridge()
        experiences = [
            _make_experience(
                experience_id=f"EXP-{i:08d}",
                outcome=ExperienceOutcome.SUCCESS,
                reasoning_capabilities=["trend_cap"],
            )
            for i in range(4)
        ]
        result = bridge.transform(experiences)

        pattern_insights = [
            i for i in result.insights
            if i.category == UnderstandingCategory.PATTERN_INSIGHT
        ]
        assert len(pattern_insights) >= 1


# ===================================================================
# Relationship tests
# ===================================================================

class TestExperienceBridgeRelationships:

    def test_relationship_capability_to_outcome(self):
        bridge = ExperienceBridge()
        experience = _make_experience(
            experience_id="EXP-REL-001",
            outcome=ExperienceOutcome.SUCCESS,
            reasoning_capabilities=["respond"],
        )
        result = bridge.transform([experience])

        rel_types = [r.relationship_type for r in result.relationships]
        assert RelationshipType.CAUSES in rel_types

    def test_relationship_capability_to_failure_is_contradicts(self):
        bridge = ExperienceBridge()
        experience = _make_experience(
            experience_id="EXP-REL-002",
            outcome=ExperienceOutcome.FAILURE,
            reasoning_capabilities=["respond"],
        )
        result = bridge.transform([experience])

        rel_types = [r.relationship_type for r in result.relationships]
        assert RelationshipType.CONTRADICTS in rel_types

    def test_relationship_capability_to_tool(self):
        bridge = ExperienceBridge()
        experience = _make_experience(
            experience_id="EXP-REL-003",
            outcome=ExperienceOutcome.SUCCESS,
            reasoning_capabilities=["execute"],
            tool_name="my_tool",
        )
        result = bridge.transform([experience])

        rel_types = [r.relationship_type for r in result.relationships]
        assert RelationshipType.ASSOCIATED_WITH in rel_types

    def test_relationship_goal_to_capability(self):
        bridge = ExperienceBridge()
        experience = _make_experience(
            experience_id="EXP-REL-004",
            outcome=ExperienceOutcome.SUCCESS,
            reasoning_capabilities=["route"],
            planning_goal="solve problem",
        )
        result = bridge.transform([experience])

        rel_types = [r.relationship_type for r in result.relationships]
        assert RelationshipType.DEPENDS_ON in rel_types

    def test_conflicting_outcomes_create_contradiction_relationship(self):
        bridge = ExperienceBridge()
        experiences = [
            _make_experience(
                experience_id="EXP-C1",
                outcome=ExperienceOutcome.SUCCESS,
                reasoning_capabilities=["ambiguous_cap"],
            ),
            _make_experience(
                experience_id="EXP-C2",
                outcome=ExperienceOutcome.FAILURE,
                reasoning_capabilities=["ambiguous_cap"],
            ),
        ]
        result = bridge.transform(experiences)

        contradiction_rels = [
            r for r in result.relationships
            if r.relationship_type == RelationshipType.CONTRADICTS
        ]
        assert len(contradiction_rels) >= 1


# ===================================================================
# Confidence / frequency tests
# ===================================================================

class TestExperienceBridgeRepetition:

    def test_repeated_experiences_increase_confidence_via_consolidation(self):
        # This test documents that the bridge produces multiple concepts;
        # downstream consolidation (UnderstandingEngine) is responsible for
        # merging them and raising confidence/frequency.
        bridge = ExperienceBridge()
        experiences = [
            _make_experience(
                experience_id=f"EXP-{i:08d}",
                outcome=ExperienceOutcome.SUCCESS,
                reasoning_capabilities=["repeated_cap"],
            )
            for i in range(3)
        ]
        result = bridge.transform(experiences)

        capability_concepts = [
            c for c in result.concepts
            if c.label == "repeated_cap"
        ]
        assert len(capability_concepts) == 3
        for concept in capability_concepts:
            assert concept.frequency == 1


# ===================================================================
# Protocol / dependency tests
# ===================================================================

class TestExperienceSourceProtocol:

    def test_experience_repository_satisfies_protocol(self):
        from atlas.experience.experience_repository import ExperienceRepository

        repository = ExperienceRepository()
        experiences = [
            _make_experience(experience_id="EXP-P1"),
            _make_experience(experience_id="EXP-P2"),
        ]
        for experience in experiences:
            repository.store_experience(experience)

        # Structural subtyping: repository methods satisfy ExperienceSource.
        source: ExperienceSource = repository
        window = source.get_window(10)
        assert len(window) == 2

        by_outcome = source.get_experiences_by_outcome(ExperienceOutcome.SUCCESS, n=10)
        assert len(by_outcome) == 2

    def test_minimal_stub_satisfies_protocol(self):
        class MinimalSource:
            def get_window(self, size: int) -> list[StructuredExperience]:
                return []

            def get_experiences_since(self, since: datetime) -> list[StructuredExperience]:
                return []

            def get_experiences_by_outcome(
                self,
                outcome,
                n: int = 100,
            ) -> list[StructuredExperience]:
                return []

        source: ExperienceSource = MinimalSource()
        assert source.get_window(5) == []

    def test_bridge_does_not_import_experience_repository(self):
        import atlas.understanding.experience_bridge as bridge_module

        # The module should not reference ExperienceRepository in its imports.
        imported_names = dir(bridge_module)
        assert "ExperienceRepository" not in imported_names

        import inspect
        source = inspect.getsource(bridge_module)
        assert "from atlas.experience.experience_repository" not in source
        assert "import atlas.experience.experience_repository" not in source


# ===================================================================
# Edge cases
# ===================================================================

class TestExperienceBridgeEdgeCases:

    def test_experience_with_empty_capabilities(self):
        bridge = ExperienceBridge()
        experience = _make_experience(reasoning_capabilities=[])
        result = bridge.transform([experience])

        assert len(result.concepts) == 1  # Only outcome concept
        assert result.concepts[0].label == "outcome:success"

    def test_experience_with_whitespace_only_fields(self):
        bridge = ExperienceBridge()
        experience = _make_experience(
            planning_goal="   ",
            tool_name="  ",
            reasoning_capabilities=["", "  ", "valid_cap"],
        )
        result = bridge.transform([experience])

        labels = [c.label for c in result.concepts]
        assert "" not in labels
        assert "   " not in labels
        assert "valid_cap" in labels

    def test_partial_outcome_concept(self):
        bridge = ExperienceBridge()
        experience = _make_experience(outcome=ExperienceOutcome.PARTIAL)
        result = bridge.transform([experience])

        labels = [c.label for c in result.concepts]
        assert "outcome:partial" in labels

    def test_skipped_outcome_concept(self):
        bridge = ExperienceBridge()
        experience = _make_experience(outcome=ExperienceOutcome.SKIPPED)
        result = bridge.transform([experience])

        labels = [c.label for c in result.concepts]
        assert "outcome:skipped" in labels
