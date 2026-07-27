"""
Phase 9.2b — UnderstandingEngine Persistence Integration Tests.

Tests for:
- Engine accepts storage adapter
- No storage keeps old behavior
- Consolidation writes to storage
- Restore loads concepts and rebuilds graph
- Restore clears existing memory first
- Restore is idempotent
- Insight counter restored correctly
- Storage failure does not break engine
- close() delegates correctly
"""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from atlas.understanding import serialization
from atlas.understanding.experience_bridge import ExperienceBridge
from atlas.understanding.models import (
    Concept,
    ConceptDomain,
    Pattern,
    Relationship,
    RelationshipType,
    UnderstandingCategory,
    UnderstandingInsight,
)
from atlas.understanding.storage_interface import (
    UnderstandingRestoreResult,
    UnderstandingStorage,
)
from atlas.understanding.understanding_engine import UnderstandingEngine
from atlas.storage.understanding_storage import SQLiteUnderstandingStorage


def _make_concept(concept_id: str = "CON-TEST-001") -> Concept:
    return Concept(
        concept_id=concept_id,
        label="test_concept",
        domain=ConceptDomain.TECHNICAL,
        confidence=0.75,
        source="test",
        frequency=3,
        first_seen=datetime(2025, 1, 1),
        last_seen=datetime(2025, 6, 1),
        metadata={"key": "value"},
    )


def _make_relationship(source_id: str = "CON-A", target_id: str = "CON-B") -> Relationship:
    return Relationship(
        source_id=source_id,
        target_id=target_id,
        relationship_type=RelationshipType.DEPENDS_ON,
        weight=0.8,
        confidence=0.6,
        observed_count=5,
        first_observed=datetime(2025, 1, 1),
        last_observed=datetime(2025, 6, 1),
    )


def _make_pattern() -> Pattern:
    return Pattern(
        pattern_id="PAT-TEST-001",
        label="test_pattern",
        description="A test pattern.",
        confidence=0.65,
        related_concept_ids=["CON-A"],
        frequency=2,
        first_observed=datetime(2025, 2, 1),
        last_observed=datetime(2025, 5, 1),
    )


def _make_insight(insight_id: str = "INS-TEST-001") -> UnderstandingInsight:
    return UnderstandingInsight(
        insight_id=insight_id,
        category=UnderstandingCategory.CONCEPT_INSIGHT,
        summary="Test summary.",
        detail="Test detail.",
        confidence=0.7,
        related_concept_ids=["CON-A"],
        source="test",
        timestamp=datetime(2025, 3, 1),
        metadata={"origin": "test"},
    )


class TestEngineAcceptsStorage(unittest.TestCase):
    """Engine constructor accepts storage adapter."""

    def test_engine_with_storage_initializes(self):
        tempdir = tempfile.TemporaryDirectory()
        try:
            storage = SQLiteUnderstandingStorage(Path(tempdir.name) / "test.db")
            engine = UnderstandingEngine(understanding_storage=storage)
            self.assertIsNotNone(engine)
            self.assertTrue(storage.is_available())
            engine.close()
        finally:
            tempdir.cleanup()

    def test_engine_without_storage_keeps_old_behavior(self):
        engine = UnderstandingEngine()
        result = engine.process_text("hello world", source="test")
        self.assertGreater(len(result), 0)


class TestNoStorageBehavior(unittest.TestCase):
    """No storage keeps old behavior."""

    def test_process_text_no_storage(self):
        engine = UnderstandingEngine()
        result = engine.process_text("hello world", source="test")
        self.assertGreater(len(result), 0)

    def test_process_experiences_no_storage(self):
        from atlas.experience.models import ExperienceOutcome, StructuredExperience

        engine = UnderstandingEngine()
        exp = StructuredExperience(
            experience_id="EXP-NO-STORAGE",
            timestamp=datetime.now(),
            duration_ms=100.0,
            pipeline_path=["test"],
            outcome=ExperienceOutcome.SUCCESS,
            user_input="test",
            reasoning_capabilities=["test_cap"],
        )
        result = engine.process_experiences([exp])
        self.assertGreater(len(result), 0)

    def test_restore_no_storage_returns_empty(self):
        engine = UnderstandingEngine()
        result = engine.restore()
        self.assertIsInstance(result, UnderstandingRestoreResult)
        self.assertEqual(result.concept_count, 0)
        self.assertEqual(result.insight_count, 0)
        self.assertIsNone(result.max_insight_id)


class TestConsolidationWritesToStorage(unittest.TestCase):
    """Consolidation path persists to storage."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.storage = SQLiteUnderstandingStorage(Path(self.tempdir.name) / "test.db")
        self.engine = UnderstandingEngine(understanding_storage=self.storage)

    def tearDown(self):
        self.engine.close()
        self.tempdir.cleanup()

    def test_process_text_writes_concepts(self):
        self.engine.process_text("the api interface and module", source="test")
        concepts = self.storage.load_all_concepts()
        self.assertGreater(len(concepts), 0)

    def test_process_text_writes_insights(self):
        self.engine.process_text("hello world", source="test")
        insights = self.storage.load_all_insights()
        self.assertGreater(len(insights), 0)


class TestRestore(unittest.TestCase):
    """Restore loads persisted data back into memory and graph."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.storage = SQLiteUnderstandingStorage(Path(self.tempdir.name) / "test.db")

    def tearDown(self):
        try:
            self.storage.close()
        except Exception:
            pass
        self.tempdir.cleanup()

    def _write_test_data(self):
        """Write sample data directly to storage."""
        self.storage.store_concepts([
            serialization.concept_to_dict(_make_concept("CON-A")),
            serialization.concept_to_dict(_make_concept("CON-B")),
        ])
        self.storage.store_relationships([
            serialization.relationship_to_dict(_make_relationship("CON-A", "CON-B")),
        ])
        self.storage.store_patterns([
            serialization.pattern_to_dict(_make_pattern()),
        ])
        self.storage.store_insights([
            serialization.insight_to_dict(_make_insight("INS-00000001")),
            serialization.insight_to_dict(_make_insight("INS-00000005")),
        ])

    def test_restore_loads_concepts(self):
        self.storage.initialize()
        self._write_test_data()
        engine = UnderstandingEngine(understanding_storage=self.storage)
        result = engine.restore()
        self.assertEqual(result.concept_count, 2)
        self.assertEqual(result.relationship_count, 1)
        self.assertEqual(result.pattern_count, 1)
        self.assertEqual(result.insight_count, 2)
        engine.close()

    def test_restore_populates_graph(self):
        self.storage.initialize()
        self._write_test_data()
        engine = UnderstandingEngine(understanding_storage=self.storage)
        engine.restore()
        self.assertIsNotNone(engine.graph.get_concept("CON-A"))
        self.assertIsNotNone(engine.graph.get_concept("CON-B"))
        self.assertGreater(engine.graph.relationship_count, 0)
        engine.close()

    def test_restore_clears_existing_memory_first(self):
        self.storage.initialize()
        # First add some data to memory via process_text
        engine = UnderstandingEngine(understanding_storage=self.storage)
        engine.process_text("hello world", source="test")
        initial_concept_count = engine.graph.concept_count
        self.assertGreater(initial_concept_count, 0)
        engine.close()
        # Clear storage and write only test data
        self.storage.initialize()
        self.storage.clear_all()
        self._write_test_data()
        # Restore into a new engine — memory should be loaded from storage only
        engine2 = UnderstandingEngine(understanding_storage=self.storage)
        result = engine2.restore()
        # After restore, only the 2 concepts from _write_test_data should exist
        self.assertEqual(result.concept_count, 2)
        self.assertEqual(engine2.graph.concept_count, 2)
        engine2.close()

    def test_restore_is_idempotent(self):
        self.storage.initialize()
        self._write_test_data()
        engine = UnderstandingEngine(understanding_storage=self.storage)
        result1 = engine.restore()
        result2 = engine.restore()
        # Both restores should produce the same counts
        self.assertEqual(result1.concept_count, result2.concept_count)
        self.assertEqual(result1.relationship_count, result2.relationship_count)
        self.assertEqual(result1.insight_count, result2.insight_count)
        engine.close()

    def test_restore_seeds_insight_counter(self):
        self.storage.initialize()
        # Store insights with INS-00000005 as max
        self.storage.store_insights([
            serialization.insight_to_dict(_make_insight("INS-00000005")),
        ])
        engine = UnderstandingEngine(understanding_storage=self.storage)
        result = engine.restore()
        self.assertEqual(result.max_insight_id, 5)
        # Next generated insight should continue from 5, not restart at 0
        engine.process_text("new input", source="test")
        insights = engine.memory.get_insights(100)
        # Find the insight generated by process_text (it will be INS-00000006+)
        new_ids = [i.insight_id for i in insights if i.insight_id.startswith("INS-")]
        self.assertGreater(len(new_ids), 0)
        # At least one should have ID > 5
        max_numeric = max(
            int(iid.split("-")[1])
            for iid in new_ids
            if len(iid.split("-")) >= 2 and iid.split("-")[1].isdigit()
        )
        self.assertGreaterEqual(max_numeric, 6)
        engine.close()


class TestStorageFailure(unittest.TestCase):
    """Storage failure does not break the understanding pipeline."""

    def test_broken_storage_does_not_break_process_text(self):
        tempdir = tempfile.TemporaryDirectory()
        try:
            # Create a corrupted DB
            db_path = Path(tempdir.name) / "corrupt.db"
            db_path.write_text("not a valid database")
            storage = SQLiteUnderstandingStorage(db_path)
            engine = UnderstandingEngine(understanding_storage=storage)
            # Storage should be unavailable
            self.assertFalse(storage.is_available())
            # Engine should still work in memory-only mode
            result = engine.process_text("hello world", source="test")
            self.assertGreater(len(result), 0)
            engine.close()
        finally:
            tempdir.cleanup()

    def test_broken_storage_restore_returns_empty(self):
        tempdir = tempfile.TemporaryDirectory()
        try:
            db_path = Path(tempdir.name) / "corrupt.db"
            db_path.write_text("not a valid database")
            storage = SQLiteUnderstandingStorage(db_path)
            engine = UnderstandingEngine(understanding_storage=storage)
            result = engine.restore()
            self.assertEqual(result.concept_count, 0)
            engine.close()
        finally:
            tempdir.cleanup()


class TestClose(unittest.TestCase):
    """close() delegates to storage adapter."""

    def test_close_with_storage(self):
        mock_storage = MagicMock(spec=UnderstandingStorage)
        engine = UnderstandingEngine(understanding_storage=mock_storage)
        engine.close()
        mock_storage.close.assert_called_once()

    def test_close_without_storage(self):
        engine = UnderstandingEngine()
        # Should not raise
        engine.close()

    def test_close_on_failed_storage(self):
        tempdir = tempfile.TemporaryDirectory()
        try:
            storage = SQLiteUnderstandingStorage(Path(tempdir.name) / "test.db")
            engine = UnderstandingEngine(understanding_storage=storage)
            engine.close()
            # Should be safe to call close again
            engine.close()
        finally:
            tempdir.cleanup()


if __name__ == "__main__":
    unittest.main()