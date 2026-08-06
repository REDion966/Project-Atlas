"""Track C — LongTermSQLiteStorage tests (Batch 5)."""

from datetime import datetime

import pytest

from atlas.longterm.models import (
    ConsolidationRecord,
    ConsolidationStatus,
    Episode,
    EpisodeEvent,
    EpisodeKind,
    Procedure,
    ProcedureKind,
    ProcedureStep,
)
from atlas.storage.longterm_storage import LongTermSQLiteStorage


@pytest.fixture()
def storage(tmp_path):
    adapter = LongTermSQLiteStorage(db_path=tmp_path / "atlas_experience.db")
    adapter.initialize()
    yield adapter
    adapter.close()


def _make_episode(episode_id: str = "ep1") -> Episode:
    return Episode(
        episode_id=episode_id,
        kind=EpisodeKind.PIPELINE,
        title=f"Episode {episode_id}",
        outcome="success",
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        ended_at=datetime(2026, 1, 1, 12, 0, 5),
        importance=0.7,
        tags=("pipeline", "research"),
        metadata={"pipeline_path": ["understanding", "reasoning"]},
        events=(
            EpisodeEvent(
                event_id=f"event:{episode_id}:0",
                episode_id=episode_id,
                sequence=0,
                event_type="pipeline_start",
            ),
        ),
    )


def _make_procedure(procedure_id: str = "p1") -> Procedure:
    return Procedure(
        procedure_id=procedure_id,
        name=f"Procedure {procedure_id}",
        kind=ProcedureKind.DISTILLED,
        category="research",
        source_episode_ids=("ep1", "ep2"),
        success_count=2,
        failure_count=1,
        confidence=0.66,
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        last_used_at=datetime(2026, 1, 2, 12, 0, 0),
        tags=("distilled",),
        steps=(
            ProcedureStep(
                step_id="pstep:0000",
                description="search via search",
                tool_name="search",
                parameters={"event_type": "tool_execution"},
            ),
        ),
    )


class TestLifecycle:
    def test_initialize_and_available(self, storage):
        assert storage.is_available()

    def test_close_marks_unavailable(self, tmp_path):
        adapter = LongTermSQLiteStorage(db_path=tmp_path / "db.sqlite")
        adapter.initialize()
        adapter.close()
        assert not adapter.is_available()

    def test_init_failure_sets_unavailable(self, tmp_path):
        adapter = LongTermSQLiteStorage(db_path=tmp_path / "db.sqlite")
        adapter.initialize()
        assert adapter.get_schema_version() == 9


class TestEpisodes:
    def test_store_and_load_episode(self, storage):
        episode = _make_episode()
        storage.store_episode(episode)
        loaded = storage.load_episode("ep1")
        assert loaded is not None
        assert loaded.episode_id == "ep1"
        assert loaded.outcome == "success"
        assert loaded.importance == 0.7
        assert loaded.event_count == 1

    def test_load_episodes_sorted(self, storage):
        storage.store_episode(_make_episode("ep1"))
        storage.store_episode(_make_episode("ep2"))
        episodes = storage.load_episodes()
        assert [e.episode_id for e in episodes] == ["ep1", "ep2"]

    def test_load_missing_returns_none(self, storage):
        assert storage.load_episode("missing") is None

    def test_upsert_replaces(self, storage):
        storage.store_episode(_make_episode("ep1"))
        updated = Episode(
            episode_id="ep1",
            kind=EpisodeKind.TASK,
            title="Updated",
            outcome="failure",
            started_at=datetime(2026, 3, 3),
        )
        storage.store_episode(updated)
        loaded = storage.load_episode("ep1")
        assert loaded is not None
        assert loaded.title == "Updated"
        assert loaded.outcome == "failure"


class TestEpisodeEvents:
    def test_store_and_load_events(self, storage):
        storage.store_episode(_make_episode("ep1"))
        event = EpisodeEvent(
            event_id="event:ep1:1",
            episode_id="ep1",
            sequence=1,
            event_type="tool_execution",
            metadata={"tool_name": "search"},
        )
        storage.store_episode_event(event)
        events = storage.load_episode_events("ep1")
        assert [e.event_type for e in events] == ["pipeline_start", "tool_execution"]

    def test_duplicate_event_ignored(self, storage):
        storage.store_episode(_make_episode("ep1"))
        event = EpisodeEvent(
            event_id="event:ep1:9",
            episode_id="ep1",
            sequence=9,
            event_type="a",
        )
        storage.store_episode_event(event)
        storage.store_episode_event(event)
        assert len(storage.load_episode_events("ep1")) == 2


class TestProcedures:
    def test_store_and_load_procedure(self, storage):
        procedure = _make_procedure()
        storage.store_procedure(procedure)
        loaded = storage.load_procedure("p1")
        assert loaded is not None
        assert loaded.category == "research"
        assert loaded.confidence == 0.66
        assert loaded.step_count == 1

    def test_load_procedures_sorted(self, storage):
        storage.store_procedure(_make_procedure("p1"))
        storage.store_procedure(_make_procedure("p2"))
        assert [p.procedure_id for p in storage.load_procedures()] == ["p1", "p2"]

    def test_load_missing_returns_none(self, storage):
        assert storage.load_procedure("missing") is None


class TestConsolidationRecords:
    def test_store_and_load(self, storage):
        record = ConsolidationRecord(
            record_id="consol:1",
            status=ConsolidationStatus.PENDING,
            operation="forget",
            target_type="episode",
            target_ids=("e1", "e2"),
            reason="test",
            created_at=datetime(2026, 1, 1, 12, 0, 0),
        )
        storage.store_consolidation_record(record)
        loaded = storage.load_consolidation_records()
        assert len(loaded) == 1
        assert loaded[0].target_ids == ("e1", "e2")
        assert loaded[0].status == ConsolidationStatus.PENDING

    def test_duplicate_record_ignored(self, storage):
        record = ConsolidationRecord(
            record_id="consol:1",
            reason="x",
            created_at=datetime(2026, 1, 1),
        )
        storage.store_consolidation_record(record)
        storage.store_consolidation_record(record)
        assert len(storage.load_consolidation_records()) == 1
