"""
Phase 9.2b — Understanding Serialization Round-Trip Tests.

Tests for model → dict → model identity for all 5 understanding model types.
"""

import unittest
from datetime import datetime, timedelta

from atlas.understanding import serialization
from atlas.understanding.models import (
    BehavioralDomain,
    BehavioralSignal,
    Concept,
    ConceptDomain,
    Pattern,
    Relationship,
    RelationshipType,
    UnderstandingCategory,
    UnderstandingInsight,
)


def _make_concept(concept_id: str = "CON-00000001") -> Concept:
    return Concept(
        concept_id=concept_id,
        label="test_concept",
        domain=ConceptDomain.TECHNICAL,
        confidence=0.75,
        source="test_source",
        frequency=3,
        first_seen=datetime(2025, 1, 1, 12, 0, 0),
        last_seen=datetime(2025, 6, 1, 12, 0, 0),
        metadata={"key": "value"},
    )


def _make_relationship() -> Relationship:
    return Relationship(
        source_id="CON-00000001",
        target_id="CON-00000002",
        relationship_type=RelationshipType.DEPENDS_ON,
        weight=0.8,
        confidence=0.6,
        observed_count=5,
        first_observed=datetime(2025, 1, 1, 12, 0, 0),
        last_observed=datetime(2025, 6, 1, 12, 0, 0),
    )


def _make_pattern() -> Pattern:
    return Pattern(
        pattern_id="PAT-00000001",
        label="test_pattern",
        description="A test pattern for unit tests.",
        confidence=0.65,
        related_concept_ids=["CON-00000001", "CON-00000002"],
        frequency=2,
        first_observed=datetime(2025, 2, 1, 12, 0, 0),
        last_observed=datetime(2025, 5, 1, 12, 0, 0),
    )


def _make_insight() -> UnderstandingInsight:
    return UnderstandingInsight(
        insight_id="INS-00000001",
        category=UnderstandingCategory.CONCEPT_INSIGHT,
        summary="Test insight summary.",
        detail="Test insight detail with more information.",
        confidence=0.7,
        related_concept_ids=["CON-00000001"],
        related_pattern_ids=["PAT-00000001"],
        source="test_source",
        timestamp=datetime(2025, 3, 1, 12, 0, 0),
        metadata={"origin": "test"},
    )


def _make_signal() -> BehavioralSignal:
    return BehavioralSignal(
        signal_id="SIG-00000001",
        domain=BehavioralDomain.COMMUNICATION,
        description="Test behavioral signal description.",
        confidence=0.55,
        related_concept_ids=["CON-00000001"],
        source="test_source",
        timestamp=datetime(2025, 4, 1, 12, 0, 0),
    )


class TestConceptSerializationRoundTrip(unittest.TestCase):
    """Concept → dict → Concept identity."""

    def test_concept_round_trip(self):
        original = _make_concept("CON-00000042")
        data = serialization.concept_to_dict(original)
        restored = serialization.dict_to_concept(data)
        self.assertEqual(original.concept_id, restored.concept_id)
        self.assertEqual(original.label, restored.label)
        self.assertEqual(original.domain, restored.domain)
        self.assertEqual(original.confidence, restored.confidence)
        self.assertEqual(original.source, restored.source)
        self.assertEqual(original.frequency, restored.frequency)
        self.assertEqual(original.first_seen, restored.first_seen)
        self.assertEqual(original.last_seen, restored.last_seen)
        self.assertEqual(original.metadata, restored.metadata)

    def test_unknown_enum_defaults_to_first_member(self):
        data = serialization.concept_to_dict(_make_concept())
        data["domain"] = "NOT_REAL"
        restored = serialization.dict_to_concept(data)
        self.assertIsInstance(restored.domain, ConceptDomain)

    def test_extra_keys_dropped(self):
        data = serialization.concept_to_dict(_make_concept())
        data["future_field"] = "ignored"
        restored = serialization.dict_to_concept(data)
        self.assertFalse(hasattr(restored, "future_field"))

    def test_datetime_preservation(self):
        original = _make_concept()
        data = serialization.concept_to_dict(original)
        restored = serialization.dict_to_concept(data)
        self.assertEqual(original.first_seen, restored.first_seen)
        self.assertEqual(original.last_seen, restored.last_seen)

    def test_missing_optional_fields_default_correctly(self):
        data = {
            "concept_id": "CON-DEFAULT",
            "label": "default_concept",
            "domain": "GENERAL",
            "first_seen": "2025-01-01T00:00:00",
            "last_seen": "2025-01-01T00:00:00",
        }
        restored = serialization.dict_to_concept(data)
        self.assertEqual(restored.confidence, 0.5)
        self.assertEqual(restored.frequency, 1)
        self.assertEqual(restored.metadata, {})

    def test_empty_metadata_serializes_correctly(self):
        concept = _make_concept()
        concept.metadata = {}
        data = serialization.concept_to_dict(concept)
        self.assertEqual(data["metadata"], {})


class TestRelationshipSerializationRoundTrip(unittest.TestCase):
    """Relationship → dict → Relationship identity."""

    def test_relationship_round_trip(self):
        original = _make_relationship()
        data = serialization.relationship_to_dict(original)
        restored = serialization.dict_to_relationship(data)
        self.assertEqual(original.source_id, restored.source_id)
        self.assertEqual(original.target_id, restored.target_id)
        self.assertEqual(original.relationship_type, restored.relationship_type)
        self.assertEqual(original.weight, restored.weight)
        self.assertEqual(original.confidence, restored.confidence)
        self.assertEqual(original.observed_count, restored.observed_count)
        self.assertEqual(original.first_observed, restored.first_observed)
        self.assertEqual(original.last_observed, restored.last_observed)

    def test_no_metadata_field(self):
        original = _make_relationship()
        data = serialization.relationship_to_dict(original)
        self.assertNotIn("metadata", data)

    def test_datetime_preservation(self):
        original = _make_relationship()
        data = serialization.relationship_to_dict(original)
        restored = serialization.dict_to_relationship(data)
        self.assertEqual(original.first_observed, restored.first_observed)
        self.assertEqual(original.last_observed, restored.last_observed)


class TestPatternSerializationRoundTrip(unittest.TestCase):
    """Pattern → dict → Pattern identity."""

    def test_pattern_round_trip(self):
        original = _make_pattern()
        data = serialization.pattern_to_dict(original)
        restored = serialization.dict_to_pattern(data)
        self.assertEqual(original.pattern_id, restored.pattern_id)
        self.assertEqual(original.label, restored.label)
        self.assertEqual(original.description, restored.description)
        self.assertEqual(original.confidence, restored.confidence)
        self.assertEqual(original.related_concept_ids, restored.related_concept_ids)
        self.assertEqual(original.frequency, restored.frequency)
        self.assertEqual(original.first_observed, restored.first_observed)
        self.assertEqual(original.last_observed, restored.last_observed)

    def test_no_metadata_field(self):
        original = _make_pattern()
        data = serialization.pattern_to_dict(original)
        self.assertNotIn("metadata", data)

    def test_datetime_preservation(self):
        original = _make_pattern()
        data = serialization.pattern_to_dict(original)
        restored = serialization.dict_to_pattern(data)
        self.assertEqual(original.first_observed, restored.first_observed)
        self.assertEqual(original.last_observed, restored.last_observed)

    def test_empty_related_concept_ids(self):
        pattern = _make_pattern()
        pattern.related_concept_ids = []
        data = serialization.pattern_to_dict(pattern)
        restored = serialization.dict_to_pattern(data)
        self.assertEqual(restored.related_concept_ids, [])


class TestInsightSerializationRoundTrip(unittest.TestCase):
    """UnderstandingInsight → dict → UnderstandingInsight identity."""

    def test_insight_round_trip(self):
        original = _make_insight()
        data = serialization.insight_to_dict(original)
        restored = serialization.dict_to_insight(data)
        self.assertEqual(original.insight_id, restored.insight_id)
        self.assertEqual(original.category, restored.category)
        self.assertEqual(original.summary, restored.summary)
        self.assertEqual(original.detail, restored.detail)
        self.assertEqual(original.confidence, restored.confidence)
        self.assertEqual(original.related_concept_ids, restored.related_concept_ids)
        self.assertEqual(original.related_pattern_ids, restored.related_pattern_ids)
        self.assertEqual(original.source, restored.source)
        self.assertEqual(original.timestamp, restored.timestamp)
        self.assertEqual(original.metadata, restored.metadata)

    def test_unknown_enum_defaults_to_first_member(self):
        data = serialization.insight_to_dict(_make_insight())
        data["category"] = "NOT_REAL"
        restored = serialization.dict_to_insight(data)
        self.assertIsInstance(restored.category, UnderstandingCategory)

    def test_extra_keys_dropped(self):
        data = serialization.insight_to_dict(_make_insight())
        data["future_field"] = "ignored"
        restored = serialization.dict_to_insight(data)
        self.assertFalse(hasattr(restored, "future_field"))

    def test_datetime_preservation(self):
        original = _make_insight()
        data = serialization.insight_to_dict(original)
        restored = serialization.dict_to_insight(data)
        self.assertEqual(original.timestamp, restored.timestamp)

    def test_empty_metadata_serializes_correctly(self):
        insight = _make_insight()
        insight.metadata = {}
        data = serialization.insight_to_dict(insight)
        self.assertEqual(data["metadata"], {})


class TestSignalSerializationRoundTrip(unittest.TestCase):
    """BehavioralSignal → dict → BehavioralSignal identity."""

    def test_signal_round_trip(self):
        original = _make_signal()
        data = serialization.signal_to_dict(original)
        restored = serialization.dict_to_signal(data)
        self.assertEqual(original.signal_id, restored.signal_id)
        self.assertEqual(original.domain, restored.domain)
        self.assertEqual(original.description, restored.description)
        self.assertEqual(original.confidence, restored.confidence)
        self.assertEqual(original.related_concept_ids, restored.related_concept_ids)
        self.assertEqual(original.source, restored.source)
        self.assertEqual(original.timestamp, restored.timestamp)

    def test_no_metadata_field(self):
        original = _make_signal()
        data = serialization.signal_to_dict(original)
        self.assertNotIn("metadata", data)

    def test_datetime_preservation(self):
        original = _make_signal()
        data = serialization.signal_to_dict(original)
        restored = serialization.dict_to_signal(data)
        self.assertEqual(original.timestamp, restored.timestamp)

    def test_unknown_enum_defaults_to_first_member(self):
        data = serialization.signal_to_dict(_make_signal())
        data["domain"] = "NOT_REAL"
        restored = serialization.dict_to_signal(data)
        self.assertIsInstance(restored.domain, BehavioralDomain)

    def test_empty_related_concept_ids(self):
        signal = _make_signal()
        signal.related_concept_ids = []
        data = serialization.signal_to_dict(signal)
        restored = serialization.dict_to_signal(data)
        self.assertEqual(restored.related_concept_ids, [])


if __name__ == "__main__":
    unittest.main()