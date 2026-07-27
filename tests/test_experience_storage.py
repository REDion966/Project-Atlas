"""
Phase 9.1 — SQLite Experience Storage Tests.

Comprehensive tests for:
- SQLiteExperienceStorage lifecycle (init, close, availability)
- CRUD operations for all four data types (experiences, analyses, goals, snapshots)
- Queries (since, by_outcome, max_id, latest)
- Schema migration
- Graceful failure and degradation
- Cross-session reopen persistence
"""

import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from atlas.experience.storage_interface import ExperienceStorage
from atlas.storage.experience_storage import SQLiteExperienceStorage


class TestSQLiteExperienceStorageLifecycle(unittest.TestCase):
    """Initialization, close, and availability."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_experience.db"

    def tearDown(self):
        try:
            self.storage.close()
        except Exception:
            pass
        self.temp_dir.cleanup()

    def test_initialize_creates_db_file(self):
        self.storage = SQLiteExperienceStorage(self.db_path)
        self.assertFalse(self.storage.is_available())
        self.storage.initialize()
        self.assertTrue(self.db_path.exists())
        self.assertTrue(self.storage.is_available())

    def test_double_initialize_is_idempotent(self):
        self.storage = SQLiteExperienceStorage(self.db_path)
        self.storage.initialize()
        version1 = self.storage.get_schema_version()
        self.storage.initialize()
        version2 = self.storage.get_schema_version()
        self.assertEqual(version1, version2)
        self.assertTrue(self.storage.is_available())

    def test_close_marks_unavailable(self):
        self.storage = SQLiteExperienceStorage(self.db_path)
        self.storage.initialize()
        self.assertTrue(self.storage.is_available())
        self.storage.close()
        self.assertFalse(self.storage.is_available())

    def test_implements_storage_interface(self):
        self.storage = SQLiteExperienceStorage(self.db_path)
        self.assertIsInstance(self.storage, ExperienceStorage)

    def test_schema_version_is_current(self):
        self.storage = SQLiteExperienceStorage(self.db_path)
        self.storage.initialize()
        from atlas.storage import migration
        self.assertEqual(self.storage.get_schema_version(), migration.CURRENT_SCHEMA_VERSION)


class TestSQLiteExperienceStorageCRUD(unittest.TestCase):
    """Create, read, update operations for all data types."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_crud.db"
        self.storage = SQLiteExperienceStorage(self.db_path)
        self.storage.initialize()

    def tearDown(self):
        try:
            self.storage.close()
        except Exception:
            pass
        self.temp_dir.cleanup()

    # --- Experiences ---

    def _make_experience_dict(self, exp_id="EXP-00000001", outcome="SUCCESS"):
        return {
            "experience_id": exp_id,
            "timestamp": datetime.now().isoformat(),
            "duration_ms": 150.0,
            "pipeline_path": ["understanding", "reasoning", "tool_execution"],
            "outcome": outcome,
            "user_input": "hello world",
            "conversation_history_length": 5,
            "understanding_insights_count": 2,
            "concepts_extracted": ["concept_a", "concept_b"],
            "world_model_entities": 3,
            "world_model_relations": 2,
            "reasoning_goal": "respond",
            "reasoning_capabilities": ["conversation", "analysis"],
            "reasoning_success_count": 2,
            "reasoning_total_count": 2,
            "planning_goal": "answer user",
            "planning_step_count": 3,
            "planning_validation_errors": 0,
            "tool_name": "echo",
            "tool_success": True,
            "learning_insights_count": 1,
            "reflection_suggestions_count": 0,
            "goal_recommendations_count": 1,
            "identity_version": 1,
            "identity_belief_count": 5,
            "identity_capability_count": 3,
        }

    def test_store_and_load_experience(self):
        data = self._make_experience_dict()
        self.storage.store_experience(data)
        loaded = self.storage.load_experience("EXP-00000001")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["experience_id"], "EXP-00000001")
        self.assertEqual(loaded["outcome"], "SUCCESS")
        self.assertEqual(loaded["user_input"], "hello world")
        self.assertEqual(loaded["reasoning_goal"], "respond")

    def test_store_and_load_multiple_experiences(self):
        for i in range(5):
            data = self._make_experience_dict(f"EXP-{i:08d}")
            self.storage.store_experience(data)
        all_exps = self.storage.load_experiences(limit=100)
        self.assertEqual(len(all_exps), 5)

    def test_load_experiences_limited(self):
        for i in range(10):
            data = self._make_experience_dict(f"EXP-{i:08d}")
            self.storage.store_experience(data)
        limited = self.storage.load_experiences(limit=3)
        self.assertEqual(len(limited), 3)

    def test_load_nonexistent_experience_returns_none(self):
        loaded = self.storage.load_experience("EXP-NONEXISTENT")
        self.assertIsNone(loaded)

    def test_get_max_experience_id(self):
        for i in [3, 1, 7, 5]:
            data = self._make_experience_dict(f"EXP-{i:08d}")
            self.storage.store_experience(data)
        max_id = self.storage.get_max_experience_id()
        self.assertEqual(max_id, 7)

    def test_get_max_experience_id_empty(self):
        max_id = self.storage.get_max_experience_id()
        self.assertIsNone(max_id)

    def test_load_experiences_since(self):
        from datetime import timedelta
        now = datetime.now()
        early = now - timedelta(hours=2)
        later = now - timedelta(hours=1)
        data1 = self._make_experience_dict("EXP-00000001")
        data1["timestamp"] = early.isoformat()
        data2 = self._make_experience_dict("EXP-00000002")
        data2["timestamp"] = later.isoformat()
        self.storage.store_experience(data1)
        self.storage.store_experience(data2)
        since = now - timedelta(minutes=90)
        results = self.storage.load_experiences_since(since.isoformat())
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["experience_id"], "EXP-00000002")

    def test_load_experiences_by_outcome(self):
        for i in range(3):
            self.storage.store_experience(
                self._make_experience_dict(f"EXP-{i:08d}", "SUCCESS")
            )
        self.storage.store_experience(
            self._make_experience_dict("EXP-FAIL", "FAILURE")
        )
        successes = self.storage.load_experiences_by_outcome("SUCCESS", limit=10)
        failures = self.storage.load_experiences_by_outcome("FAILURE", limit=10)
        self.assertEqual(len(successes), 3)
        self.assertEqual(len(failures), 1)

    # --- Trend analyses ---

    def _make_analysis_dict(self, analysis_id="TRND-000001"):
        return {
            "analysis_id": analysis_id,
            "timestamp": datetime.now().isoformat(),
            "window_size": 10,
            "overall_success_rate": 0.8,
            "success_rate_trend": "improving",
            "avg_understanding_insights": 2.5,
            "understanding_trend": "stable",
            "avg_reasoning_success": 0.85,
            "reasoning_trend": "improving",
            "avg_planning_errors": 0.5,
            "planning_trend": "improving",
            "tool_success_rate": 0.9,
            "tool_trend": "stable",
            "learning_insight_rate": 1.2,
            "learning_trend": "improving",
            "identity_stability": 0.95,
            "capability_trends": {"conversation": "stable", "analysis": "improving"},
        }

    def test_store_and_load_analysis(self):
        data = self._make_analysis_dict()
        self.storage.store_analysis(data)
        loaded = self.storage.load_latest_analysis()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["analysis_id"], "TRND-000001")
        self.assertEqual(loaded["success_rate_trend"], "improving")

    def test_load_latest_analysis_returns_most_recent(self):
        data1 = self._make_analysis_dict("TRND-000001")
        data2 = self._make_analysis_dict("TRND-000002")
        self.storage.store_analysis(data1)
        self.storage.store_analysis(data2)
        latest = self.storage.load_latest_analysis()
        self.assertEqual(latest["analysis_id"], "TRND-000002")

    def test_load_latest_analysis_empty(self):
        self.assertIsNone(self.storage.load_latest_analysis())

    def test_load_analyses(self):
        for i in range(3):
            self.storage.store_analysis(self._make_analysis_dict(f"TRND-{i:06d}"))
        analyses = self.storage.load_analyses(limit=10)
        self.assertEqual(len(analyses), 3)

    # --- Tracked goals ---

    def _make_goal_dict(self, goal_id="G-000001"):
        return {
            "goal_id": goal_id,
            "recommendation_id": goal_id,
            "goal_title": "Improve reasoning pipeline",
            "proposed_at": datetime.now().isoformat(),
            "outcome": "PENDING",
            "outcome_reason": "",
            "related_experience_ids": ["EXP-00000001"],
            "last_evaluated": datetime.now().isoformat(),
        }

    def test_store_and_load_tracked_goal(self):
        data = self._make_goal_dict()
        self.storage.store_tracked_goal(data)
        loaded = self.storage.load_tracked_goals()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["goal_id"], "G-000001")
        self.assertEqual(loaded[0]["outcome"], "PENDING")

    def test_store_tracked_goal_uses_proposed_at(self):
        """Verify the timestamp fix: proposed_at is used, not timestamp."""
        data = self._make_goal_dict()
        data["proposed_at"] = "2026-07-01T12:00:00"
        # Do NOT provide 'timestamp' key
        data.pop("timestamp", None)
        self.storage.store_tracked_goal(data)
        loaded = self.storage.load_tracked_goals()
        self.assertEqual(loaded[0]["proposed_at"], "2026-07-01T12:00:00")

    def test_store_tracked_goal_update_existing(self):
        data = self._make_goal_dict("G-000001")
        self.storage.store_tracked_goal(data)
        data["outcome"] = "IMPLEMENTED"
        self.storage.store_tracked_goal(data)
        loaded = self.storage.load_tracked_goals()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["outcome"], "IMPLEMENTED")

    # --- Self-model snapshots ---

    def _make_snapshot_dict(self, snapshot_id="SELF-000001"):
        return {
            "snapshot_id": snapshot_id,
            "timestamp": datetime.now().isoformat(),
            "total_experiences": 100,
            "overall_success_rate": 0.85,
            "capability_assessments": {"conversation": 0.8, "analysis": 0.75},
            "belief_evidence": {"I am improving": 0.9},
            "trend_summary": "improving",
            "identity_version": 3,
            "last_trend_analysis": datetime.now().isoformat(),
            "recent_improvement_evidence": ["Success rate improving"],
            "persistent_challenges": ["Tool execution failures"],
        }

    def test_store_and_load_snapshot(self):
        data = self._make_snapshot_dict()
        self.storage.store_snapshot(data)
        loaded = self.storage.load_latest_snapshot()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["snapshot_id"], "SELF-000001")
        self.assertEqual(loaded["total_experiences"], 100)

    def test_load_latest_snapshot_returns_most_recent(self):
        data1 = self._make_snapshot_dict("SELF-000001")
        data2 = self._make_snapshot_dict("SELF-000002")
        self.storage.store_snapshot(data1)
        self.storage.store_snapshot(data2)
        latest = self.storage.load_latest_snapshot()
        self.assertEqual(latest["snapshot_id"], "SELF-000002")

    def test_load_latest_snapshot_empty(self):
        self.assertIsNone(self.storage.load_latest_snapshot())

    def test_get_max_snapshot_id(self):
        for i in [2, 5, 3]:
            data = self._make_snapshot_dict(f"SELF-{i:06d}")
            self.storage.store_snapshot(data)
        max_id = self.storage.get_max_snapshot_id()
        self.assertEqual(max_id, 5)

    def test_get_max_snapshot_id_empty(self):
        self.assertIsNone(self.storage.get_max_snapshot_id())

    def test_load_snapshots(self):
        for i in range(3):
            self.storage.store_snapshot(self._make_snapshot_dict(f"SELF-{i:06d}"))
        snapshots = self.storage.load_snapshots(limit=10)
        self.assertEqual(len(snapshots), 3)

    # --- Clear all ---

    def test_clear_all(self):
        self.storage.store_experience(self._make_experience_dict())
        self.storage.store_analysis(self._make_analysis_dict())
        self.storage.store_tracked_goal(self._make_goal_dict())
        self.storage.store_snapshot(self._make_snapshot_dict())
        self.storage.clear_all()
        self.assertEqual(len(self.storage.load_experiences()), 0)
        self.assertEqual(len(self.storage.load_analyses()), 0)
        self.assertEqual(len(self.storage.load_tracked_goals()), 0)
        self.assertEqual(len(self.storage.load_snapshots()), 0)


class TestSQLiteExperienceStorageFailure(unittest.TestCase):
    """Graceful degradation on failures."""

    @patch("sqlite3.connect")
    def test_unavailable_on_connection_failure(self, mock_connect):
        """When sqlite3.connect raises, initialize marks unavailable."""
        mock_connect.side_effect = Exception("Connection refused")
        storage = SQLiteExperienceStorage(":memory:")
        storage.initialize()
        self.assertFalse(storage.is_available())

    def test_write_failure_marks_unavailable(self):
        temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(temp_dir.name) / "test_fail.db"
        storage = SQLiteExperienceStorage(db_path)
        storage.initialize()
        self.assertTrue(storage.is_available())
        # Close the underlying connection to simulate failure
        storage.close()
        storage._available = True  # Force-mark available (simulates race)
        with self.assertRaises(Exception):
            storage.store_experience({"experience_id": "EXP-00000001"})
        self.assertFalse(storage.is_available())
        temp_dir.cleanup()


class TestSQLiteExperienceStorageReopen(unittest.TestCase):
    """Cross-session persistence: write, close, reopen, verify."""

    def test_reopen_preserves_all_data(self):
        temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(temp_dir.name) / "test_reopen.db"

        # Session 1: write data
        storage1 = SQLiteExperienceStorage(db_path)
        storage1.initialize()
        storage1.store_experience({
            "experience_id": "EXP-00000001",
            "timestamp": datetime.now().isoformat(),
            "duration_ms": 100.0,
            "pipeline_path": [],
            "outcome": "SUCCESS",
        })
        storage1.store_snapshot({
            "snapshot_id": "SELF-000001",
            "timestamp": datetime.now().isoformat(),
            "total_experiences": 50,
            "overall_success_rate": 0.8,
            "capability_assessments": {},
            "belief_evidence": {},
            "trend_summary": "stable",
            "identity_version": 1,
            "last_trend_analysis": datetime.now().isoformat(),
        })
        storage1.close()

        # Session 2: verify data persists
        storage2 = SQLiteExperienceStorage(db_path)
        storage2.initialize()
        exps = storage2.load_experiences()
        self.assertEqual(len(exps), 1)
        self.assertEqual(exps[0]["experience_id"], "EXP-00000001")
        snap = storage2.load_latest_snapshot()
        self.assertIsNotNone(snap)
        self.assertEqual(snap["total_experiences"], 50)
        storage2.close()

        temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
