"""
Phase 9.1 — Persistent Experience Storage Tests

Tests for:
- ExperienceStorage interface
- Model serialization round-trips
- SQLiteExperienceStorage CRUD and lifecycle
- ExperienceRepository with storage adapter
- Counter restoration
- Self-model snapshot persistence and restoration
- Startup/shutdown continuity
- Graceful degradation (corruption, missing DB)
- Architecture boundaries (no sqlite3 in atlas/experience/)
"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from atlas.cognition.models import CognitionState, PipelineMetrics, PipelineResult
from atlas.experience import serialization
from atlas.experience.experience_accumulator import ExperienceAccumulator
from atlas.experience.experience_repository import ExperienceRepository
from atlas.experience.models import (
    ExperienceOutcome,
    GoalOutcome,
    SelfModelSnapshot,
    StructuredExperience,
    TrackedGoal,
    TrendAnalysis,
)
from atlas.experience.self_model_engine import SelfModelEngine
from atlas.experience.storage_interface import ExperienceStorage, RestoreResult
from atlas.storage.experience_storage import SQLiteExperienceStorage


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _make_experience(exp_id: str = "EXP-00000001", outcome: ExperienceOutcome = ExperienceOutcome.SUCCESS) -> StructuredExperience:
    return StructuredExperience(
        experience_id=exp_id,
        timestamp=datetime.now(),
        duration_ms=10.0,
        pipeline_path=["understanding", "reasoning"],
        outcome=outcome,
        user_input="hello",
        reasoning_goal="respond",
        reasoning_capabilities=["conversation"],
        reasoning_total_count=1,
    )


def _make_analysis() -> TrendAnalysis:
    return TrendAnalysis(
        analysis_id="ANAL-0001",
        timestamp=datetime.now(),
        window_size=4,
        overall_success_rate=0.75,
        capability_trends={"conversation": "improving"},
    )


def _make_goal() -> TrackedGoal:
    return TrackedGoal(
        goal_id="G1",
        recommendation_id="REC-1",
        goal_title="Improve reasoning",
        outcome=GoalOutcome.PENDING,
    )


def _make_snapshot() -> SelfModelSnapshot:
    return SelfModelSnapshot(
        snapshot_id="SELF-000007",
        timestamp=datetime.now(),
        total_experiences=7,
        overall_success_rate=0.85,
        capability_assessments={"conversation": 0.75},
        belief_evidence={"I learn": 0.6},
        trend_summary="Success: improving",
        identity_version=1,
        last_trend_analysis=datetime.now(),
        recent_improvement_evidence=["Better"],
        persistent_challenges=["None"],
    )


class TestStorageInterface(unittest.TestCase):
    """ExperienceStorage ABC contract."""

    def test_abc_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            ExperienceStorage()

    def test_restore_result_defaults(self):
        result = RestoreResult()
        self.assertEqual(result.experience_count, 0)
        self.assertIsNone(result.max_experience_id)


class TestSerializationRoundTrip(unittest.TestCase):
    """Model → dict → model identity."""

    def test_experience_round_trip(self):
        original = _make_experience("EXP-00000042")
        data = serialization.experience_to_dict(original)
        restored = serialization.dict_to_experience(data)
        self.assertEqual(original.experience_id, restored.experience_id)
        self.assertEqual(original.outcome, restored.outcome)
        self.assertEqual(original.pipeline_path, restored.pipeline_path)
        self.assertEqual(original.user_input, restored.user_input)

    def test_analysis_round_trip(self):
        original = _make_analysis()
        data = serialization.analysis_to_dict(original)
        restored = serialization.dict_to_analysis(data)
        self.assertEqual(original.analysis_id, restored.analysis_id)
        self.assertEqual(original.capability_trends, restored.capability_trends)

    def test_goal_round_trip(self):
        original = _make_goal()
        data = serialization.goal_to_dict(original)
        restored = serialization.dict_to_goal(data)
        self.assertEqual(original.goal_id, restored.goal_id)
        self.assertEqual(original.outcome, restored.outcome)

    def test_snapshot_round_trip(self):
        original = _make_snapshot()
        data = serialization.snapshot_to_dict(original)
        restored = serialization.dict_to_snapshot(data)
        self.assertEqual(original.snapshot_id, restored.snapshot_id)
        self.assertEqual(original.capability_assessments, restored.capability_assessments)
        self.assertEqual(original.recent_improvement_evidence, restored.recent_improvement_evidence)

    def test_unknown_enum_defaults_to_first_member(self):
        data = serialization.experience_to_dict(_make_experience())
        data["outcome"] = "NOT_REAL"
        restored = serialization.dict_to_experience(data)
        self.assertIsInstance(restored.outcome, ExperienceOutcome)

    def test_extra_keys_dropped(self):
        data = serialization.experience_to_dict(_make_experience())
        data["future_field"] = "ignored"
        restored = serialization.dict_to_experience(data)
        self.assertFalse(hasattr(restored, "future_field"))


class TestSQLiteStorageLifecycle(unittest.TestCase):
    """Adapter initialization and shutdown."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "test_experience.db"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_initialize_creates_database(self):
        storage = SQLiteExperienceStorage(self.db_path)
        storage.initialize()
        self.assertTrue(storage.is_available())
        self.assertTrue(self.db_path.exists())
        storage.close()

    def test_schema_version_recorded(self):
        storage = SQLiteExperienceStorage(self.db_path)
        storage.initialize()
        self.assertEqual(storage.get_schema_version(), 1)
        storage.close()

    def test_close_marks_unavailable(self):
        storage = SQLiteExperienceStorage(self.db_path)
        storage.initialize()
        storage.close()
        self.assertFalse(storage.is_available())

    def test_double_initialize_idempotent(self):
        storage = SQLiteExperienceStorage(self.db_path)
        storage.initialize()
        storage.initialize()
        self.assertTrue(storage.is_available())
        storage.close()


class TestSQLiteStorageExperiences(unittest.TestCase):
    """Experience CRUD through SQLite adapter."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.storage = SQLiteExperienceStorage(Path(self.tempdir.name) / "test.db")
        self.storage.initialize()

    def tearDown(self):
        self.storage.close()
        self.tempdir.cleanup()

    def test_store_and_load_experience(self):
        exp = _make_experience("EXP-00000001")
        self.storage.store_experience(serialization.experience_to_dict(exp))
        loaded = self.storage.load_experience("EXP-00000001")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["experience_id"], "EXP-00000001")
        self.assertEqual(loaded["pipeline_path"], ["understanding", "reasoning"])
        self.assertTrue(loaded["tool_success"] in (True, False))

    def test_load_experiences_ordered_oldest_first(self):
        for i in range(3):
            exp = _make_experience(f"EXP-{i:08d}")
            self.storage.store_experience(serialization.experience_to_dict(exp))
        loaded = self.storage.load_experiences()
        self.assertEqual(len(loaded), 3)
        self.assertEqual(loaded[0]["experience_id"], "EXP-00000000")

    def test_load_by_outcome(self):
        success = _make_experience("EXP-SUCCESS", ExperienceOutcome.SUCCESS)
        failure = _make_experience("EXP-FAILURE", ExperienceOutcome.FAILURE)
        self.storage.store_experience(serialization.experience_to_dict(success))
        self.storage.store_experience(serialization.experience_to_dict(failure))
        loaded = self.storage.load_experiences_by_outcome("FAILURE")
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["experience_id"], "EXP-FAILURE")

    def test_load_since_timestamp(self):
        now = datetime.now().isoformat()
        exp = _make_experience("EXP-0001")
        self.storage.store_experience(serialization.experience_to_dict(exp))
        loaded = self.storage.load_experiences_since(now)
        self.assertEqual(len(loaded), 1)

    def test_get_max_experience_id(self):
        self.storage.store_experience(serialization.experience_to_dict(_make_experience("EXP-00000005")))
        self.storage.store_experience(serialization.experience_to_dict(_make_experience("EXP-00000010")))
        self.assertEqual(self.storage.get_max_experience_id(), 10)


class TestSQLiteStorageAnalyses(unittest.TestCase):
    """Trend analysis CRUD."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.storage = SQLiteExperienceStorage(Path(self.tempdir.name) / "test.db")
        self.storage.initialize()

    def tearDown(self):
        self.storage.close()
        self.tempdir.cleanup()

    def test_store_and_load_latest_analysis(self):
        analysis = _make_analysis()
        self.storage.store_analysis(serialization.analysis_to_dict(analysis))
        loaded = self.storage.load_latest_analysis()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["analysis_id"], "ANAL-0001")
        self.assertEqual(loaded["capability_trends"], {"conversation": "improving"})

    def test_load_analyses_limit(self):
        for i in range(3):
            analysis = TrendAnalysis(
                analysis_id=f"ANAL-{i:04d}",
                timestamp=datetime.now() + timedelta(seconds=i),
                window_size=2,
            )
            self.storage.store_analysis(serialization.analysis_to_dict(analysis))
        loaded = self.storage.load_analyses(limit=2)
        self.assertEqual(len(loaded), 2)


class TestSQLiteStorageGoals(unittest.TestCase):
    """Tracked goal CRUD."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.storage = SQLiteExperienceStorage(Path(self.tempdir.name) / "test.db")
        self.storage.initialize()

    def tearDown(self):
        self.storage.close()
        self.tempdir.cleanup()

    def test_store_and_load_tracked_goals(self):
        goal = _make_goal()
        self.storage.store_tracked_goal(serialization.goal_to_dict(goal))
        loaded = self.storage.load_tracked_goals()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["goal_id"], "G1")
        self.assertEqual(loaded[0]["outcome"], "PENDING")


class TestSQLiteStorageSnapshots(unittest.TestCase):
    """Self-model snapshot CRUD."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.storage = SQLiteExperienceStorage(Path(self.tempdir.name) / "test.db")
        self.storage.initialize()

    def tearDown(self):
        self.storage.close()
        self.tempdir.cleanup()

    def test_store_and_load_latest_snapshot(self):
        snapshot = _make_snapshot()
        self.storage.store_snapshot(serialization.snapshot_to_dict(snapshot))
        loaded = self.storage.load_latest_snapshot()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["snapshot_id"], "SELF-000007")
        self.assertEqual(loaded["capability_assessments"], {"conversation": 0.75})

    def test_get_max_snapshot_id(self):
        snapshot = _make_snapshot()
        self.storage.store_snapshot(serialization.snapshot_to_dict(snapshot))
        self.assertEqual(self.storage.get_max_snapshot_id(), 7)


class TestRepositoryWithStorage(unittest.TestCase):
    """ExperienceRepository dual-write and restore behavior."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.storage = SQLiteExperienceStorage(Path(self.tempdir.name) / "repo.db")
        self.storage.initialize()
        self.repo = ExperienceRepository(storage=self.storage)

    def tearDown(self):
        self.storage.close()
        self.tempdir.cleanup()

    def test_store_and_restore_experience(self):
        exp = _make_experience("EXP-00000001")
        self.repo.store_experience(exp)

        new_repo = ExperienceRepository(storage=self.storage)
        result = new_repo.restore()
        self.assertEqual(result.experience_count, 1)
        self.assertEqual(new_repo.get_experience("EXP-00000001").experience_id, "EXP-00000001")

    def test_store_and_restore_analysis(self):
        analysis = _make_analysis()
        self.repo.store_analysis(analysis)

        new_repo = ExperienceRepository(storage=self.storage)
        new_repo.restore()
        self.assertIsNotNone(new_repo.get_latest_analysis())

    def test_store_and_restore_tracked_goal(self):
        goal = _make_goal()
        self.repo.store_tracked_goal(goal)

        new_repo = ExperienceRepository(storage=self.storage)
        new_repo.restore()
        self.assertEqual(len(new_repo.get_tracked_goals()), 1)

    def test_restore_returns_max_ids(self):
        self.repo.store_experience(_make_experience("EXP-00000005"))
        self.repo.persist_snapshot(serialization.snapshot_to_dict(_make_snapshot()))

        new_repo = ExperienceRepository(storage=self.storage)
        result = new_repo.restore()
        self.assertEqual(result.max_experience_id, 5)
        self.assertEqual(result.max_snapshot_id, 7)
        self.assertIsNotNone(result.latest_snapshot)

    def test_memory_only_mode(self):
        repo = ExperienceRepository()
        result = repo.restore()
        self.assertEqual(result.experience_count, 0)
        repo.store_experience(_make_experience())
        self.assertEqual(repo.experience_count, 1)


class TestCounterRestoration(unittest.TestCase):
    """Prevent ID collisions after restart."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.storage = SQLiteExperienceStorage(Path(self.tempdir.name) / "counters.db")
        self.storage.initialize()

    def tearDown(self):
        self.storage.close()
        self.tempdir.cleanup()

    def test_accumulator_counter_seeded_after_restore(self):
        self.storage.store_experience(serialization.experience_to_dict(_make_experience("EXP-00000005")))

        repo = ExperienceRepository(storage=self.storage)
        result = repo.restore()
        accumulator = ExperienceAccumulator(repository=repo)
        accumulator.seed_counter(result.max_experience_id or 0)

        exp = accumulator.record(CognitionState(), PipelineResult(success=True))
        self.assertEqual(exp.experience_id, "EXP-00000006")

    def test_snapshot_counter_seeded_after_restore(self):
        self.storage.store_snapshot(serialization.snapshot_to_dict(_make_snapshot()))

        repo = ExperienceRepository(storage=self.storage)
        result = repo.restore()
        engine = SelfModelEngine(repository=repo, update_interval=1, window_size=2)
        engine.seed_snapshot_counter(result.max_snapshot_id or 0)

        for _ in range(2):
            repo.store_experience(_make_experience())
        snapshot = engine.update()
        self.assertEqual(snapshot.snapshot_id, "SELF-000008")


class TestSelfModelSnapshotPersistence(unittest.TestCase):
    """SelfModelEngine persists and restores snapshots."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.storage = SQLiteExperienceStorage(Path(self.tempdir.name) / "snapshots.db")
        self.storage.initialize()
        self.repo = ExperienceRepository(storage=self.storage)

    def tearDown(self):
        self.storage.close()
        self.tempdir.cleanup()

    def test_update_persists_snapshot(self):
        engine = SelfModelEngine(repository=self.repo, update_interval=1, window_size=2)
        for _ in range(2):
            self.repo.store_experience(_make_experience())
        engine.update()

        loaded = self.storage.load_latest_snapshot()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["snapshot_id"], "SELF-000001")

    def test_restore_snapshot_continues_counter(self):
        snapshot = _make_snapshot()
        engine = SelfModelEngine(repository=self.repo, update_interval=1, window_size=2)
        engine.restore_snapshot(serialization.snapshot_to_dict(snapshot))
        self.assertEqual(engine.get_snapshot().snapshot_id, "SELF-000007")

        for _ in range(2):
            self.repo.store_experience(_make_experience())
        new_snapshot = engine.update()
        # Counter is seeded to restored numeric ID; _build_snapshot increments
        # before formatting, so next ID is restored_id + 1.
        self.assertEqual(new_snapshot.snapshot_id, "SELF-000008")


class TestGracefulDegradation(unittest.TestCase):
    """Storage failures do not crash Atlas."""

    def test_corrupted_database_degrades_gracefully(self):
        tempdir = tempfile.TemporaryDirectory()
        db_path = Path(tempdir.name) / "corrupt.db"
        db_path.write_text("this is not sqlite data")

        storage = SQLiteExperienceStorage(db_path)
        storage.initialize()
        self.assertFalse(storage.is_available())

        # Repository should still work in memory
        repo = ExperienceRepository(storage=storage)
        repo.store_experience(_make_experience())
        self.assertEqual(repo.experience_count, 1)

        tempdir.cleanup()

    def test_unavailable_storage_skips_writes(self):
        storage = SQLiteExperienceStorage()
        storage.initialize()
        storage.close()

        repo = ExperienceRepository(storage=storage)
        repo.store_experience(_make_experience())
        self.assertEqual(repo.experience_count, 1)


class TestStartupShutdownContinuity(unittest.TestCase):
    """End-to-end restart persistence via Atlas kernel."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["ATLAS_EXPERIENCE_DB"] = str(Path(self.tempdir.name) / "atlas_experience.db")

    def tearDown(self):
        self.tempdir.cleanup()
        os.environ.pop("ATLAS_EXPERIENCE_DB", None)

    def test_atlas_start_shutdown_creates_storage(self):
        # We cannot easily start full Atlas in unit tests because it needs AI
        # providers. Instead test the storage/repository interaction directly.
        storage = SQLiteExperienceStorage(os.environ["ATLAS_EXPERIENCE_DB"])
        storage.initialize()
        repo = ExperienceRepository(storage=storage)

        # Simulate pipeline recording
        accumulator = ExperienceAccumulator(repository=repo)
        state = CognitionState(user_input="hello")
        result = PipelineResult(success=True, metrics=PipelineMetrics(total_duration_ms=100.0))
        accumulator.record(state, result)

        # Simulate self-model update
        engine = SelfModelEngine(repository=repo, update_interval=1, window_size=1)
        engine.update()

        # Simulate shutdown persist
        snapshot = engine.get_snapshot()
        repo.persist_snapshot(serialization.snapshot_to_dict(snapshot))
        storage.close()

        # Simulate restart
        storage2 = SQLiteExperienceStorage(os.environ["ATLAS_EXPERIENCE_DB"])
        storage2.initialize()
        repo2 = ExperienceRepository(storage=storage2)
        result = repo2.restore()

        self.assertEqual(result.experience_count, 1)
        self.assertEqual(repo2.get_experiences(1)[0].user_input, "hello")
        self.assertIsNotNone(result.latest_snapshot)
        self.assertEqual(result.max_snapshot_id, 1)
        storage2.close()


class TestArchitectureBoundaries(unittest.TestCase):
    """Ensure Phase 9.1 maintains pure logic boundaries."""

    def test_no_sqlite3_imports_in_experience(self):
        import atlas.experience.serialization as ser_mod
        import atlas.experience.experience_repository as repo_mod
        import atlas.experience.experience_accumulator as acc_mod
        import atlas.experience.self_model_engine as self_mod
        import atlas.experience.storage_interface as iface_mod

        for mod in (ser_mod, repo_mod, acc_mod, self_mod, iface_mod):
            source = mod.__doc__ or ""
            source += "\n".join(str(v) for v in mod.__dict__.values())
            self.assertNotIn("sqlite3", source, f"{mod.__name__} imports sqlite3")
            self.assertNotIn("atlas.storage", source, f"{mod.__name__} imports atlas.storage")

    def test_storage_interface_is_in_pure_logic_layer(self):
        from atlas.experience.storage_interface import ExperienceStorage
        self.assertTrue(hasattr(ExperienceStorage, "store_experience"))

    def test_sqlite_adapter_implements_interface(self):
        self.assertTrue(issubclass(SQLiteExperienceStorage, ExperienceStorage))


if __name__ == "__main__":
    unittest.main()
