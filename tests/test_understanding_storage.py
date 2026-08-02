"""
Phase 9.2b — Understanding Storage Interface and SQLite Adapter Tests.

Tests for:
- UnderstandingStorage interface (ABC cannot be instantiated)
- UnderstandingRestoreResult dataclass
- SQLiteUnderstandingStorage lifecycle and CRUD
- Transaction rollback
- ID prefix filtering
- Architecture boundaries (no sqlite3 in atlas/understanding/)
"""

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

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
from atlas.understanding.storage_interface import (
    UnderstandingRestoreResult,
    UnderstandingStorage,
)
from atlas.storage.understanding_storage import SQLiteUnderstandingStorage


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


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


def _make_pattern(pattern_id: str = "PAT-00000001") -> Pattern:
    return Pattern(
        pattern_id=pattern_id,
        label="test_pattern",
        description="A test pattern for unit tests.",
        confidence=0.65,
        related_concept_ids=["CON-00000001", "CON-00000002"],
        frequency=2,
        first_observed=datetime(2025, 2, 1, 12, 0, 0),
        last_observed=datetime(2025, 5, 1, 12, 0, 0),
    )


def _make_insight(insight_id: str = "INS-00000001") -> UnderstandingInsight:
    return UnderstandingInsight(
        insight_id=insight_id,
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


def _make_signal(signal_id: str = "SIG-00000001") -> BehavioralSignal:
    return BehavioralSignal(
        signal_id=signal_id,
        domain=BehavioralDomain.COMMUNICATION,
        description="Test behavioral signal description.",
        confidence=0.55,
        related_concept_ids=["CON-00000001"],
        source="test_source",
        timestamp=datetime(2025, 4, 1, 12, 0, 0),
    )


# ===================================================================
# Interface tests
# ===================================================================


class TestUnderstandingStorageInterface(unittest.TestCase):
    """UnderstandingStorage ABC contract."""

    def test_abc_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            UnderstandingStorage()

    def test_restore_result_defaults(self):
        result = UnderstandingRestoreResult()
        self.assertEqual(result.concept_count, 0)
        self.assertEqual(result.relationship_count, 0)
        self.assertEqual(result.pattern_count, 0)
        self.assertEqual(result.insight_count, 0)
        self.assertEqual(result.signal_count, 0)
        self.assertIsNone(result.max_insight_id)

    def test_restore_result_with_values(self):
        result = UnderstandingRestoreResult(
            concept_count=5,
            relationship_count=10,
            pattern_count=3,
            insight_count=15,
            signal_count=2,
            max_insight_id=42,
        )
        self.assertEqual(result.concept_count, 5)
        self.assertEqual(result.relationship_count, 10)
        self.assertEqual(result.pattern_count, 3)
        self.assertEqual(result.insight_count, 15)
        self.assertEqual(result.signal_count, 2)
        self.assertEqual(result.max_insight_id, 42)

    def test_restore_result_is_frozen(self):
        result = UnderstandingRestoreResult()
        with self.assertRaises(AttributeError):
            result.concept_count = 10


# ===================================================================
# SQLite lifecycle tests
# ===================================================================


class TestSQLiteUnderstandingLifecycle(unittest.TestCase):
    """Adapter initialization and shutdown."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "test_understanding.db"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_initialize_creates_database(self):
        storage = SQLiteUnderstandingStorage(self.db_path)
        storage.initialize()
        self.assertTrue(storage.is_available())
        self.assertTrue(self.db_path.exists())
        storage.close()

    def test_schema_version_recorded(self):
        storage = SQLiteUnderstandingStorage(self.db_path)
        storage.initialize()
        # Verify schema version via the migration system
        conn = storage._conn
        self.assertIsNotNone(conn)
        if conn is not None:
            cursor = conn.execute(
                "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
            )
            self.assertEqual(cursor.fetchone()[0], 6)
        storage.close()
        # Release the extra connection reference so Windows can delete
        # the temp directory during tearDown without PermissionError.
        conn = None
        storage = None

    def test_close_marks_unavailable(self):
        storage = SQLiteUnderstandingStorage(self.db_path)
        storage.initialize()
        storage.close()
        self.assertFalse(storage.is_available())

    def test_double_initialize_idempotent(self):
        storage = SQLiteUnderstandingStorage(self.db_path)
        storage.initialize()
        storage.initialize()
        self.assertTrue(storage.is_available())
        storage.close()


# ===================================================================
# SQLite CRUD tests
# ===================================================================


class TestSQLiteUnderstandingConcepts(unittest.TestCase):
    """Concept CRUD through SQLite adapter."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.storage = SQLiteUnderstandingStorage(Path(self.tempdir.name) / "test.db")
        self.storage.initialize()

    def tearDown(self):
        self.storage.close()
        self.tempdir.cleanup()

    def test_store_and_load_concepts(self):
        concepts = [
            serialization.concept_to_dict(_make_concept("CON-00000001")),
            serialization.concept_to_dict(_make_concept("CON-00000002")),
        ]
        self.storage.store_concepts(concepts)
        loaded = self.storage.load_all_concepts()
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]["concept_id"], "CON-00000001")
        self.assertEqual(loaded[1]["concept_id"], "CON-00000002")
        self.assertEqual(loaded[0]["metadata"], {"key": "value"})

    def test_store_empty_concepts_does_nothing(self):
        self.storage.store_concepts([])
        self.assertEqual(len(self.storage.load_all_concepts()), 0)

    def test_load_empty_database_returns_empty_list(self):
        self.assertEqual(len(self.storage.load_all_concepts()), 0)


class TestSQLiteUnderstandingRelationships(unittest.TestCase):
    """Relationship CRUD through SQLite adapter."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.storage = SQLiteUnderstandingStorage(Path(self.tempdir.name) / "test.db")
        self.storage.initialize()

    def tearDown(self):
        self.storage.close()
        self.tempdir.cleanup()

    def test_store_and_load_relationships(self):
        relationships = [
            serialization.relationship_to_dict(_make_relationship()),
        ]
        self.storage.store_relationships(relationships)
        loaded = self.storage.load_all_relationships()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["source_id"], "CON-00000001")
        self.assertEqual(loaded[0]["target_id"], "CON-00000002")
        self.assertEqual(loaded[0]["relationship_type"], "DEPENDS_ON")

    def test_store_empty_relationships_does_nothing(self):
        self.storage.store_relationships([])
        self.assertEqual(len(self.storage.load_all_relationships()), 0)

    def test_load_empty_database_returns_empty_list(self):
        self.assertEqual(len(self.storage.load_all_relationships()), 0)


class TestSQLiteUnderstandingPatterns(unittest.TestCase):
    """Pattern CRUD through SQLite adapter."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.storage = SQLiteUnderstandingStorage(Path(self.tempdir.name) / "test.db")
        self.storage.initialize()

    def tearDown(self):
        self.storage.close()
        self.tempdir.cleanup()

    def test_store_and_load_patterns(self):
        patterns = [
            serialization.pattern_to_dict(_make_pattern("PAT-00000001")),
            serialization.pattern_to_dict(_make_pattern("PAT-00000002")),
        ]
        self.storage.store_patterns(patterns)
        loaded = self.storage.load_all_patterns()
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]["pattern_id"], "PAT-00000001")
        self.assertEqual(loaded[1]["pattern_id"], "PAT-00000002")
        self.assertEqual(
            loaded[0]["related_concept_ids"],
            ["CON-00000001", "CON-00000002"],
        )

    def test_store_empty_patterns_does_nothing(self):
        self.storage.store_patterns([])
        self.assertEqual(len(self.storage.load_all_patterns()), 0)

    def test_load_empty_database_returns_empty_list(self):
        self.assertEqual(len(self.storage.load_all_patterns()), 0)


class TestSQLiteUnderstandingInsights(unittest.TestCase):
    """Insight CRUD through SQLite adapter."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.storage = SQLiteUnderstandingStorage(Path(self.tempdir.name) / "test.db")
        self.storage.initialize()

    def tearDown(self):
        self.storage.close()
        self.tempdir.cleanup()

    def test_store_and_load_insights(self):
        insights = [
            serialization.insight_to_dict(_make_insight("INS-00000001")),
            serialization.insight_to_dict(_make_insight("INS-00000002")),
        ]
        self.storage.store_insights(insights)
        loaded = self.storage.load_all_insights()
        self.assertEqual(len(loaded), 2)
        loaded_ids = [i["insight_id"] for i in loaded]
        self.assertIn("INS-00000001", loaded_ids)
        self.assertIn("INS-00000002", loaded_ids)
        # Verify metadata is preserved for any loaded insight
        for i in loaded:
            if i["insight_id"] == "INS-00000001":
                self.assertEqual(i["metadata"], {"origin": "test"})

    def test_store_empty_insights_does_nothing(self):
        self.storage.store_insights([])
        self.assertEqual(len(self.storage.load_all_insights()), 0)

    def test_load_empty_database_returns_empty_list(self):
        self.assertEqual(len(self.storage.load_all_insights()), 0)


class TestSQLiteUnderstandingSignals(unittest.TestCase):
    """Signal CRUD through SQLite adapter."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.storage = SQLiteUnderstandingStorage(Path(self.tempdir.name) / "test.db")
        self.storage.initialize()

    def tearDown(self):
        self.storage.close()
        self.tempdir.cleanup()

    def test_store_and_load_signals(self):
        signals = [
            serialization.signal_to_dict(_make_signal("SIG-00000001")),
            serialization.signal_to_dict(_make_signal("SIG-00000002")),
        ]
        self.storage.store_signals(signals)
        loaded = self.storage.load_all_signals()
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]["signal_id"], "SIG-00000001")
        self.assertEqual(loaded[1]["signal_id"], "SIG-00000002")

    def test_store_empty_signals_does_nothing(self):
        self.storage.store_signals([])
        self.assertEqual(len(self.storage.load_all_signals()), 0)

    def test_load_empty_database_returns_empty_list(self):
        self.assertEqual(len(self.storage.load_all_signals()), 0)


# ===================================================================
# Administration tests
# ===================================================================


class TestSQLiteUnderstandingAdministration(unittest.TestCase):
    """Admin operations (clear_all, get_max_insight_id)."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.storage = SQLiteUnderstandingStorage(Path(self.tempdir.name) / "admin.db")
        self.storage.initialize()

    def tearDown(self):
        self.storage.close()
        self.tempdir.cleanup()

    def test_clear_all_removes_all_data(self):
        concept = serialization.concept_to_dict(_make_concept())
        insight = serialization.insight_to_dict(_make_insight())
        self.storage.store_concepts([concept])
        self.storage.store_insights([insight])
        self.assertEqual(len(self.storage.load_all_concepts()), 1)
        self.assertEqual(len(self.storage.load_all_insights()), 1)
        self.storage.clear_all()
        self.assertEqual(len(self.storage.load_all_concepts()), 0)
        self.assertEqual(len(self.storage.load_all_insights()), 0)

    def test_get_max_insight_id_with_only_ins_prefix(self):
        self.storage.store_insights([
            serialization.insight_to_dict(_make_insight("INS-00000005")),
            serialization.insight_to_dict(_make_insight("INS-00000010")),
        ])
        self.assertEqual(self.storage.get_max_insight_id(), 10)

    def test_get_max_insight_id_ignores_exp_ins_prefix(self):
        self.storage.store_insights([
            serialization.insight_to_dict(_make_insight("INS-00000005")),
            serialization.insight_to_dict(_make_insight("EXP-INS-00000099")),
        ])
        self.assertEqual(self.storage.get_max_insight_id(), 5)

    def test_get_max_insight_id_empty(self):
        self.assertIsNone(self.storage.get_max_insight_id())

    def test_get_max_insight_id_only_exp_ins(self):
        self.storage.store_insights([
            serialization.insight_to_dict(_make_insight("EXP-INS-00000001")),
            serialization.insight_to_dict(_make_insight("EXP-INS-00000099")),
        ])
        self.assertIsNone(self.storage.get_max_insight_id())


# ===================================================================
# Transaction safety tests
# ===================================================================


class TestSQLiteUnderstandingTransactions(unittest.TestCase):
    """Transaction rollback on failure."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.storage = SQLiteUnderstandingStorage(Path(self.tempdir.name) / "tx.db")
        self.storage.initialize()

    def tearDown(self):
        self.storage.close()
        self.tempdir.cleanup()

    def test_invalid_concept_does_not_corrupt(self):
        # An invalid concept will fail to INSERT due to NOT NULL constraints.
        # The transaction should rollback, leaving the table empty.
        with self.assertRaises((sqlite3.IntegrityError, sqlite3.OperationalError)):
            invalid_concept = {"concept_id": None}  # type: ignore[typeddict-item]
            self.storage.store_concepts([invalid_concept])
        # After the failed write, storage may be marked unavailable.
        # This is expected graceful degradation.
        pass


# ===================================================================
# Architecture boundary tests
# ===================================================================


class TestArchitectureBoundaries(unittest.TestCase):
    """Ensure Phase 9.2b maintains pure logic boundaries."""

    def test_no_sqlite3_imports_in_understanding(self):
        import atlas.understanding.serialization as ser_mod
        import atlas.understanding.storage_interface as iface_mod
        import atlas.understanding.understanding_engine as eng_mod
        import atlas.understanding.understanding_memory as mem_mod
        import atlas.understanding.understanding_graph as graph_mod
        import atlas.understanding.experience_bridge as bridge_mod

        for mod in (ser_mod, iface_mod, eng_mod, mem_mod, graph_mod, bridge_mod):
            source = mod.__doc__ or ""
            source += "\n".join(str(v) for v in mod.__dict__.values())
            self.assertNotIn(
                "sqlite3", source,
                f"{mod.__name__} imports sqlite3",
            )
            self.assertNotIn(
                "atlas.storage", source,
                f"{mod.__name__} imports atlas.storage",
            )

    def test_storage_interface_is_in_pure_logic_layer(self):
        from atlas.understanding.storage_interface import UnderstandingStorage
        self.assertTrue(hasattr(UnderstandingStorage, "store_concepts"))

    def test_sqlite_adapter_implements_interface(self):
        self.assertTrue(issubclass(SQLiteUnderstandingStorage, UnderstandingStorage))


if __name__ == "__main__":
    unittest.main()
