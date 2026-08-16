"""Post-Core Hardening — SQLite understanding-counter overflow clamp.

Reproduces the exact OverflowError observed in full-suite runs:

  atlas/understanding/understanding_engine.py:328
    storage.store_concepts(...)
  atlas/storage/understanding_storage.py:185
    conn.executemany(sql, params)
  OverflowError: Python int too large to convert to SQLite INTEGER

Root cause: concept/pattern ``frequency`` and relationship
``observed_count`` are unbounded ``+=`` accumulators. The dev database
already held concept frequencies near 3.8e18 (compounded across
restore+merge cycles); the next merge crossed 2**63 - 1 and aborted the
batch write. The fix saturates those INTEGER binds at 2**63 - 1,
preserving the counter's meaning while keeping writes loss-free.

No schema change. No migration. No new storage subsystem.
"""

import os
import tempfile
import unittest

from atlas.storage.understanding_storage import SQLiteUnderstandingStorage


class TestIntClamp(unittest.TestCase):

    def test_small_values_pass_through(self):
        storage = SQLiteUnderstandingStorage()
        self.assertEqual(storage._clamp_int(5, 1), 5)
        self.assertEqual(storage._clamp_int(0, 1), 0)
        self.assertEqual(storage._clamp_int(2**63 - 1, 1), 2**63 - 1)

    def test_oversized_values_clamp_to_max_int64(self):
        storage = SQLiteUnderstandingStorage()
        self.assertEqual(storage._clamp_int(2**63, 1), 2**63 - 1)
        self.assertEqual(storage._clamp_int(2**100, 1), 2**63 - 1)

    def test_non_int_falls_back_to_default(self):
        storage = SQLiteUnderstandingStorage()
        self.assertEqual(storage._clamp_int("huge", 1), 1)
        self.assertEqual(storage._clamp_int(None, 1), 1)
        self.assertEqual(storage._clamp_int(2.5, 1), 1)
        self.assertEqual(storage._clamp_int(True, 1), 1)


class TestStoreConceptsOverflow(unittest.TestCase):
    """Real SQLite round-trip: huge frequency must persist, not overflow."""

    def setUp(self):
        self.db_path = os.path.join(
            tempfile.gettempdir(), "test_atlas_overflow_clamp_concepts.db"
        )
        self.storage = SQLiteUnderstandingStorage(db_path=self.db_path)
        self.storage.initialize()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        try:
            self.storage.clear_all()
            self.storage.close()
            os.remove(self.db_path)
        except OSError:
            pass

    def test_huge_frequency_persists_clamped(self):
        huge = 2**100  # exceeds SQLite signed 64-bit range
        self.storage.store_concepts(
            [
                {
                    "concept_id": "C-HUGE",
                    "label": "cleanup",
                    "domain": "TECHNICAL",
                    "confidence": 0.5,
                    "source": "test",
                    "frequency": huge,
                    "first_seen": "2026-01-01T00:00:00",
                    "last_seen": "2026-01-01T00:00:00",
                    "metadata": {},
                }
            ]
        )
        loaded = self.storage.load_all_concepts()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["frequency"], 2**63 - 1)
        self.assertTrue(self.storage.is_available())

    def test_relationship_observed_count_clamped(self):
        self.storage.store_relationships(
            [
                {
                    "source_id": "C-A",
                    "target_id": "C-B",
                    "relationship_type": "ASSOCIATED_WITH",
                    "weight": 0.5,
                    "confidence": 0.5,
                    "observed_count": 2**63 + 1,
                    "first_observed": "2026-01-01T00:00:00",
                    "last_observed": "2026-01-01T00:00:00",
                }
            ]
        )
        loaded = self.storage.load_all_relationships()
        self.assertEqual(loaded[0]["observed_count"], 2**63 - 1)
        self.assertTrue(self.storage.is_available())

    def test_pattern_frequency_clamped(self):
        self.storage.store_patterns(
            [
                {
                    "pattern_id": "P-HUGE",
                    "label": "recurring-cleanup",
                    "description": "recurring pattern",
                    "confidence": 0.5,
                    "related_concept_ids": ["C-HUGE"],
                    "frequency": 2**63 + 10,
                    "first_observed": "2026-01-01T00:00:00",
                    "last_observed": "2026-01-01T00:00:00",
                }
            ]
        )
        loaded = self.storage.load_all_patterns()
        self.assertEqual(loaded[0]["frequency"], 2**63 - 1)
        self.assertTrue(self.storage.is_available())

    def test_normal_frequency_unchanged(self):
        """Normal counters are stored exactly — no clamp side effects."""
        self.storage.store_concepts(
            [
                {
                    "concept_id": "C-NORMAL",
                    "label": "boot",
                    "domain": "TECHNICAL",
                    "confidence": 0.5,
                    "source": "test",
                    "frequency": 42,
                    "first_seen": "2026-01-01T00:00:00",
                    "last_seen": "2026-01-01T00:00:00",
                    "metadata": {},
                }
            ]
        )
        loaded = self.storage.load_all_concepts()
        self.assertEqual(loaded[0]["frequency"], 42)


if __name__ == "__main__":
    unittest.main()
