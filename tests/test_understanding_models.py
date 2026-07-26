"""
Phase 7.1 — Understanding Engine: Model & Component Tests.
"""

import pytest
from datetime import datetime

from atlas.understanding.models import (
    Concept, ConceptDomain, Relationship, RelationshipType,
    Pattern, UnderstandingInsight, UnderstandingCategory,
    BehavioralSignal, BehavioralDomain, BehaviorExtractor,
)
from atlas.understanding.concept_extractor import ConceptExtractor
from atlas.understanding.pattern_analyzer import PatternAnalyzer
from atlas.understanding.understanding_graph import UnderstandingGraph
from atlas.understanding.understanding_memory import UnderstandingMemory


# ===================================================================
# Model Tests
# ===================================================================

class TestConceptDomain:
    def test_has_expected_domains(self):
        assert ConceptDomain.GENERAL in ConceptDomain
        assert ConceptDomain.BEHAVIORAL in ConceptDomain
        assert ConceptDomain.TECHNICAL in ConceptDomain
        assert ConceptDomain.SYSTEM_METRIC in ConceptDomain
        assert ConceptDomain.USER_PREFERENCE in ConceptDomain


class TestConcept:
    def test_create_minimal(self):
        c = Concept(concept_id="CON-001", label="test")
        assert c.concept_id == "CON-001"
        assert c.label == "test"
        assert c.domain == ConceptDomain.GENERAL
        assert c.confidence == 0.5
        assert c.frequency == 1
        assert isinstance(c.first_seen, datetime)

    def test_create_full(self):
        now = datetime.now()
        c = Concept(concept_id="CON-002", label="api", domain=ConceptDomain.TECHNICAL,
                     confidence=0.9, source="test", frequency=5,
                     first_seen=now, last_seen=now)
        assert c.domain == ConceptDomain.TECHNICAL
        assert c.confidence == 0.9
        assert c.frequency == 5


class TestRelationshipType:
    def test_has_types(self):
        assert RelationshipType.ASSOCIATED_WITH in RelationshipType
        assert RelationshipType.DEPENDS_ON in RelationshipType
        assert RelationshipType.CONTRADICTS in RelationshipType


class TestBehavioralDomain:
    def test_has_domains(self):
        assert BehavioralDomain.COMMUNICATION in BehavioralDomain
        assert BehavioralDomain.DECISION_MAKING in BehavioralDomain


class TestBehaviorExtractor:
    def test_default_returns_empty(self):
        extractor = BehaviorExtractor()
        assert extractor.extract_signals("hello") == []
        assert extractor.extract_signals_from_observations([]) == []


# ===================================================================
# ConceptExtractor Tests
# ===================================================================

class TestConceptExtractor:

    def test_extract_from_empty_text(self):
        extractor = ConceptExtractor()
        assert extractor.extract_from_text("") == []
        assert extractor.extract_from_text("   ") == []

    def test_extract_simple_words(self):
        extractor = ConceptExtractor()
        concepts = extractor.extract_from_text("hello world", source="test")
        assert len(concepts) >= 2
        labels = [c.label for c in concepts]
        assert "hello" in labels
        assert "world" in labels

    def test_extract_detects_technical_domain(self):
        extractor = ConceptExtractor()
        concepts = extractor.extract_from_text("the api interface and module")
        technical = [c for c in concepts if c.domain == ConceptDomain.TECHNICAL]
        assert len(technical) >= 1

    def test_extract_detects_behavioral_domain(self):
        extractor = ConceptExtractor()
        concepts = extractor.extract_from_text("user prefer this feature")
        behavioral = [c for c in concepts if c.domain == ConceptDomain.BEHAVIORAL]
        assert len(behavioral) >= 1

    def test_extract_from_observation(self):
        extractor = ConceptExtractor()
        class MockObs:
            description = "system runtime metrics"
            metric_name = "response_time"
            source = "monitor"
        obs = MockObs()
        concepts = extractor.extract_from_observation(obs)
        assert len(concepts) > 0

    def test_extract_from_data(self):
        extractor = ConceptExtractor()
        data = {"key1": "hello world", "key2": {"sub": "test value"}}
        concepts = extractor.extract_from_data(data)
        assert len(concepts) > 0

    def test_deduplication(self):
        extractor = ConceptExtractor()
        concepts = extractor.extract_from_text("hello hello world")
        hello_concepts = [c for c in concepts if c.label == "hello"]
        assert len(hello_concepts) <= 1
        if hello_concepts:
            assert hello_concepts[0].frequency >= 2

    def test_confidence_threshold(self):
        extractor = ConceptExtractor()
        concepts = extractor.extract_from_text("a")
        # Single letter should be filtered
        assert len(concepts) == 0


# ===================================================================
# UnderstandingGraph Tests
# ===================================================================

class TestUnderstandingGraph:

    def test_add_and_get_concept(self):
        graph = UnderstandingGraph()
        c = Concept(concept_id="CON-001", label="test")
        graph.add_concept(c)
        assert graph.concept_count == 1
        assert graph.get_concept("CON-001") is not None

    def test_get_concept_by_label(self):
        graph = UnderstandingGraph()
        graph.add_concept(Concept(concept_id="CON-001", label="test"))
        assert graph.get_concept_by_label("test") is not None
        assert graph.get_concept_by_label("NONEXISTENT") is None

    def test_update_existing_concept(self):
        graph = UnderstandingGraph()
        c1 = Concept(concept_id="CON-001", label="test", frequency=1, confidence=0.5)
        graph.add_concept(c1)
        c2 = Concept(concept_id="CON-001", label="test", frequency=2, confidence=0.9)
        graph.add_concept(c2)
        retrieved = graph.get_concept("CON-001")
        assert retrieved.frequency == 3  # accumulated
        assert retrieved.confidence == 0.9  # max

    def test_add_relationship(self):
        graph = UnderstandingGraph()
        graph.add_concept(Concept(concept_id="CON-001", label="a"))
        graph.add_concept(Concept(concept_id="CON-002", label="b"))
        rel = Relationship(source_id="CON-001", target_id="CON-002",
                           relationship_type=RelationshipType.DEPENDS_ON)
        graph.add_relationship(rel)
        assert graph.relationship_count == 1

    def test_find_related_concepts(self):
        graph = UnderstandingGraph()
        graph.add_concept(Concept(concept_id="CON-001", label="a"))
        graph.add_concept(Concept(concept_id="CON-002", label="b"))
        graph.add_concept(Concept(concept_id="CON-003", label="c"))
        graph.add_relationship(Relationship(
            source_id="CON-001", target_id="CON-002",
            relationship_type=RelationshipType.ASSOCIATED_WITH))
        graph.add_relationship(Relationship(
            source_id="CON-002", target_id="CON-003",
            relationship_type=RelationshipType.ASSOCIATED_WITH))

        related = graph.find_related_concepts("CON-001", max_depth=1)
        assert len(related) == 1
        assert related[0].label == "b"

        related_depth2 = graph.find_related_concepts("CON-001", max_depth=2)
        assert len(related_depth2) == 2

    def test_find_path(self):
        graph = UnderstandingGraph()
        for i in range(4):
            graph.add_concept(Concept(concept_id=f"CON-{i:03d}", label=f"node{i}"))
        graph.add_relationship(Relationship("CON-000", "CON-001", RelationshipType.DEPENDS_ON))
        graph.add_relationship(Relationship("CON-001", "CON-002", RelationshipType.DEPENDS_ON))
        graph.add_relationship(Relationship("CON-002", "CON-003", RelationshipType.DEPENDS_ON))

        paths = graph.find_path("CON-000", "CON-003")
        assert len(paths) == 1
        assert len(paths[0]) == 3

    def test_find_path_no_route(self):
        graph = UnderstandingGraph()
        graph.add_concept(Concept(concept_id="CON-001", label="a"))
        graph.add_concept(Concept(concept_id="CON-002", label="b"))
        paths = graph.find_path("CON-001", "CON-002")
        assert paths == []

    def test_remove_concept(self):
        graph = UnderstandingGraph()
        graph.add_concept(Concept(concept_id="CON-001", label="a"))
        graph.add_relationship(Relationship("CON-001", "CON-002", RelationshipType.ASSOCIATED_WITH))
        assert graph.remove_concept("NONEXISTENT") == False
        assert graph.remove_concept("CON-001") == True

    def test_clear(self):
        graph = UnderstandingGraph()
        graph.add_concept(Concept(concept_id="CON-001", label="a"))
        graph.clear()
        assert graph.concept_count == 0
        assert graph.relationship_count == 0


# ===================================================================
# PatternAnalyzer Tests
# ===================================================================

class TestPatternAnalyzer:

    def test_analyze_concepts_empty(self):
        analyzer = PatternAnalyzer()
        assert analyzer.analyze_concepts([]) == []

    def test_analyze_few_concepts(self):
        analyzer = PatternAnalyzer()
        concepts = [
            Concept(concept_id="1", label="a", domain=ConceptDomain.TECHNICAL),
            Concept(concept_id="2", label="b"),
        ]
        patterns = analyzer.analyze_concepts(concepts)
        assert len(patterns) == 0  # Need >= 3

    def test_detect_domain_dominance(self):
        analyzer = PatternAnalyzer()
        concepts = [
            Concept(concept_id="1", label="a", domain=ConceptDomain.TECHNICAL),
            Concept(concept_id="2", label="b", domain=ConceptDomain.TECHNICAL),
            Concept(concept_id="3", label="c", domain=ConceptDomain.TECHNICAL),
            Concept(concept_id="4", label="d", domain=ConceptDomain.GENERAL),
        ]
        patterns = analyzer.analyze_concepts(concepts)
        dominant = [p for p in patterns if "Dominant" in p.label]
        assert len(dominant) >= 1

    def test_detect_high_frequency(self):
        analyzer = PatternAnalyzer()
        concepts = [
            Concept(concept_id="1", label="frequent", frequency=10),
            Concept(concept_id="2", label="normal", frequency=1),
            Concept(concept_id="3", label="also_normal", frequency=1),
        ]
        patterns = analyzer.analyze_concepts(concepts)
        freq_patterns = [p for p in patterns if "Frequency" in p.label]
        assert len(freq_patterns) >= 1

    def test_relationships_analyze(self):
        analyzer = PatternAnalyzer()
        rels = [
            Relationship("1", "2", RelationshipType.DEPENDS_ON),
            Relationship("2", "3", RelationshipType.DEPENDS_ON),
            Relationship("3", "4", RelationshipType.DEPENDS_ON),
        ]
        patterns = analyzer.analyze_relationships(rels)
        assert len(patterns) >= 1

    def test_analyze_all(self):
        analyzer = PatternAnalyzer()
        concepts = [
            Concept(concept_id="1", label="a", domain=ConceptDomain.TECHNICAL),
            Concept(concept_id="2", label="b", domain=ConceptDomain.TECHNICAL),
            Concept(concept_id="3", label="c", domain=ConceptDomain.TECHNICAL),
        ]
        patterns = analyzer.analyze_all(concepts)
        assert len(patterns) >= 1


# ===================================================================
# UnderstandingMemory Tests
# ===================================================================

class TestUnderstandingMemory:

    def test_default_limits(self):
        mem = UnderstandingMemory()
        assert mem.concept_count == 0
        assert mem.relationship_count == 0
        assert mem.insight_count == 0

    def test_invalid_limits(self):
        with pytest.raises(ValueError):
            UnderstandingMemory(max_concepts=0)

    def test_store_and_get_concept(self):
        mem = UnderstandingMemory()
        c = Concept(concept_id="CON-001", label="test")
        mem.store_concept(c)
        assert mem.concept_count == 1
        assert mem.get_concept("CON-001") is not None

    def test_store_and_get_relationships(self):
        mem = UnderstandingMemory()
        r = Relationship("1", "2", RelationshipType.ASSOCIATED_WITH)
        mem.store_relationship(r)
        assert mem.relationship_count == 1
        assert len(mem.get_relationships(10)) == 1

    def test_store_and_get_patterns(self):
        mem = UnderstandingMemory()
        p = Pattern(pattern_id="PAT-001", label="test pattern", description="desc")
        mem.store_pattern(p)
        assert mem.pattern_count == 1
        assert mem.get_pattern_by_id("PAT-001") is not None
        assert len(mem.get_patterns(10)) == 1

    def test_store_and_get_insights(self):
        mem = UnderstandingMemory()
        insight = UnderstandingInsight(
            insight_id="INS-001", category=UnderstandingCategory.CONCEPT_INSIGHT,
            summary="test", detail="detail")
        mem.store_insight(insight)
        assert mem.insight_count == 1
        assert len(mem.get_insights(10)) == 1

    def test_store_and_get_signals(self):
        mem = UnderstandingMemory()
        s = BehavioralSignal(signal_id="SIG-001", domain=BehavioralDomain.COMMUNICATION,
                              description="test signal")
        mem.store_signal(s)
        assert mem.signal_count == 1
        assert len(mem.get_signals(10)) == 1

    def test_summary(self):
        mem = UnderstandingMemory()
        summary = mem.summary()
        assert "concept_count" in summary
        assert summary["concept_count"] == 0

    def test_clear(self):
        mem = UnderstandingMemory()
        mem.store_concept(Concept(concept_id="CON-001", label="test"))
        assert mem.concept_count == 1
        mem.clear()
        assert mem.concept_count == 0