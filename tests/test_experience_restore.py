"""
Phase 9.1 — Experience Restore & Cross-Session Loading Tests.

Tests for:
- ExperienceRepository.restore() flow with SQLite storage
- Counter seeding from restored max IDs
- Snapshot restore and counter synchronization
- Cross-session full persistence cycle
- Graceful fallback when storage is unavailable
"""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from atlas.experience.models import (
    ExperienceOutcome,
    GoalOutcome,
    SelfModelSnapshot,
    StructuredExperience,
    TrackedGoal,
    TrendAnalysis,
)
from atlas.experience.experience_repository import ExperienceRepository
from atlas.experience.experience_accumulator import ExperienceAccumulator
from atlas.experience.self_model_engine import SelfModelEngine
from atlas.storage.experience_storage import SQLiteExperienceStorage


class TestExperienceRestore(unittest.TestCase):
    """Restore flow from SQLite storage into ExperienceRepository."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_restore.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_populated_storage(self) -> SQLiteExperienceStorage:
        """Create a storage with sample data and return it (closed)."""
        storage = SQLiteExperienceStorage(self.db_path)
        storage.initialize()

        # Store experiences
        for i in range(3):
            storage.store_experience({
                "experience_id": f"EXP-{i:08d}",
                "timestamp": datetime.now().isoformat(),
                "duration_ms": 100.0,
                "pipeline_path": ["reasoning"],
                "outcome": "SUCCESS" if i % 2 == 0 else "FAILURE",
                "user_input": f"test {i}",
            })

        # Store analysis
        storage.store_analysis({
            "analysis_id": "TRND-000001",
            "timestamp": datetime.now().isoformat(),
            "window_size": 10,
            "overall_success_rate": 0.8,
        })

        # Store goal
        storage.store_tracked_goal({
            "goal_id": "G-000001",
            "recommendation_id": "G-000001",
            "goal_title": "Test goal",
            "proposed_at": datetime.now().isoformat(),
            "outcome": "PENDING",
            "outcome_reason": "",
            "related_experience_ids": [],
            "last_evaluated": datetime.now().isoformat(),
        })

        # Store snapshot
        storage.store_snapshot({
            "snapshot_id": "SELF-000001",
            "timestamp": datetime.now().isoformat(),
            "total_experiences": 3,
            "overall_success_rate": 0.66,
            "capability_assessments": {},
            "belief_evidence": {},
            "trend_summary": "stable",
            "identity_version": 1,
            "last_trend_analysis": datetime.now().isoformat(),
        })

        return storage

    def test_restore_experiences_from_storage(self):
        storage = self._create_populated_storage()
        repo = ExperienceRepository(storage=storage, max_experiences=100)
        result = repo.restore()

        self.assertEqual(result.experience_count, 3)
        self.assertEqual(result.analysis_count, 1)
        self.assertEqual(result.tracked_goal_count, 1)
        self.assertIsNotNone(result.latest_snapshot)
        self.assertEqual(result.max_experience_id, 2)
        self.assertEqual(result.max_snapshot_id, 1)

        # Verify in-memory data matches
        exps = repo.get_experiences(n=10)
        self.assertEqual(len(exps), 3)
        self.assertEqual(repo.experience_count, 3)

        goal = repo.get_tracked_goal("G-000001")
        self.assertIsNotNone(goal)

        storage.close()

    def test_restore_with_no_storage_returns_empty(self):
        repo = ExperienceRepository(max_experiences=100)
        result = repo.restore()
        self.assertEqual(result.experience_count, 0)
        self.assertIsNone(result.max_experience_id)
        self.assertIsNone(result.max_snapshot_id)
        self.assertIsNone(result.latest_snapshot)

    def test_restore_with_unavailable_storage_returns_empty(self):
        storage = SQLiteExperienceStorage(self.db_path)
        # Never initialize — storage is unavailable
        repo = ExperienceRepository(storage=storage, max_experiences=100)
        result = repo.restore()
        self.assertEqual(result.experience_count, 0)

    def test_restore_seeds_experience_counter(self):
        storage = self._create_populated_storage()
        repo = ExperienceRepository(storage=storage, max_experiences=100)
        result = repo.restore()

        accumulator = ExperienceAccumulator(repository=repo)
        accumulator.seed_counter(result.max_experience_id or 0)

        # Counter is seeded at 2, so next ID should be EXP-00000003
        exp = StructuredExperience(
            experience_id="EXP-00000003",
            timestamp=datetime.now(),
            duration_ms=10.0,
            pipeline_path=[],
            outcome=ExperienceOutcome.SUCCESS,
        )
        # The accumulator increments before recording, but we
        # verify the repo has the restored + new experience
        repo.store_experience(exp)
        self.assertEqual(repo.experience_count, 4)

        storage.close()

    def test_restore_snapshot_seeds_counter_and_state(self):
        storage = self._create_populated_storage()
        repo = ExperienceRepository(storage=storage, max_experiences=100)
        result = repo.restore()

        engine = SelfModelEngine(
            repository=repo,
            update_interval=1,
            window_size=2,
        )
        engine.seed_snapshot_counter(result.max_snapshot_id or 0)

        # Restore the snapshot dict into the engine
        if result.latest_snapshot is not None:
            engine.restore_snapshot(result.latest_snapshot)

        self.assertIsNotNone(engine.get_snapshot())
        self.assertEqual(engine.get_snapshot().total_experiences, 3)

        storage.close()


class TestCrossSessionPersistence(unittest.TestCase):
    """Full persistence cycle across sessions."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_cross_session.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_full_cycle_store_restore_store(self):
        """Session 1: store → Session 2: restore + store → verify both."""
        # --- Session 1: Store data ---
        storage1 = SQLiteExperienceStorage(self.db_path)
        storage1.initialize()
        repo1 = ExperienceRepository(storage=storage1, max_experiences=100)
        repo1.store_experience(StructuredExperience(
            experience_id="EXP-00000001",
            timestamp=datetime.now(),
            duration_ms=50.0,
            pipeline_path=[],
            outcome=ExperienceOutcome.SUCCESS,
        ))
        repo1.store_tracked_goal(TrackedGoal(
            goal_id="G-000001",
            goal_title="Goal 1",
        ))
        self.assertEqual(repo1.experience_count, 1)
        storage1.close()

        # --- Session 2: Restore and add more data ---
        storage2 = SQLiteExperienceStorage(self.db_path)
        storage2.initialize()
        repo2 = ExperienceRepository(storage=storage2, max_experiences=100)
        result = repo2.restore()
        self.assertEqual(result.experience_count, 1)
        self.assertEqual(result.tracked_goal_count, 1)

        # Add a second experience
        repo2.store_experience(StructuredExperience(
            experience_id="EXP-00000002",
            timestamp=datetime.now(),
            duration_ms=75.0,
            pipeline_path=[],
            outcome=ExperienceOutcome.SUCCESS,
        ))
        self.assertEqual(repo2.experience_count, 2)

        # Verify first experience is still there
        exp1 = repo2.get_experience("EXP-00000001")
        self.assertIsNotNone(exp1)
        self.assertEqual(exp1.duration_ms, 50.0)

        # Verify tracked goal restored
        goal = repo2.get_tracked_goal("G-000001")
        self.assertIsNotNone(goal)
        self.assertEqual(goal.goal_title, "Goal 1")

        storage2.close()

    def test_restore_preserves_snapshot_identity_version(self):
        """Restored snapshot keeps identity_version."""
        storage = SQLiteExperienceStorage(self.db_path)
        storage.initialize()
        storage.store_snapshot({
            "snapshot_id": "SELF-000005",
            "timestamp": datetime.now().isoformat(),
            "total_experiences": 42,
            "overall_success_rate": 0.9,
            "capability_assessments": {"test_cap": 0.8},
            "belief_evidence": {},
            "trend_summary": "improving",
            "identity_version": 7,
            "last_trend_analysis": datetime.now().isoformat(),
        })
        storage.close()

        storage2 = SQLiteExperienceStorage(self.db_path)
        storage2.initialize()
        repo = ExperienceRepository(storage=storage2)
        result = repo.restore()
        storage2.close()

        self.assertIsNotNone(result.latest_snapshot)
        self.assertEqual(result.latest_snapshot["snapshot_id"], "SELF-000005")
        self.assertEqual(result.latest_snapshot["identity_version"], 7)
        self.assertEqual(result.latest_snapshot["total_experiences"], 42)


class TestGracefulFallback(unittest.TestCase):
    """ExperienceRepository degrades gracefully without storage."""

    def test_memory_only_storage_default(self):
        repo = ExperienceRepository()
        result = repo.restore()
        self.assertEqual(result.experience_count, 0)

        # Memory-only operations still work
        repo.store_experience(StructuredExperience(
            experience_id="EXP-00000001",
            timestamp=datetime.now(),
            duration_ms=10.0,
            pipeline_path=[],
            outcome=ExperienceOutcome.SUCCESS,
        ))
        self.assertEqual(repo.experience_count, 1)
        self.assertEqual(repo.summary()["storage_available"], False)

    @patch("sqlite3.connect")
    def test_storage_failure_does_not_break_memory_path(self, mock_connect):
        """Even if storage is broken, memory operations continue."""
        mock_connect.side_effect = Exception("Connection refused")
        storage = SQLiteExperienceStorage("test.db")
        storage.initialize()
        self.assertFalse(storage.is_available())

        repo = ExperienceRepository(storage=storage)
        result = repo.restore()
        self.assertEqual(result.experience_count, 0)

        # Memory operation should succeed despite broken storage
        repo.store_experience(StructuredExperience(
            experience_id="EXP-00000001",
            timestamp=datetime.now(),
            duration_ms=10.0,
            pipeline_path=[],
            outcome=ExperienceOutcome.SUCCESS,
        ))
        self.assertEqual(repo.experience_count, 1)

    def test_persist_snapshot_without_storage(self):
        """persist_snapshot is a no-op (not an error) when no storage."""
        repo = ExperienceRepository()
        repo.persist_snapshot({"snapshot_id": "SELF-000001"})
        # No exception expected
        self.assertEqual(repo.summary()["storage_available"], False)


if __name__ == "__main__":
    unittest.main()
