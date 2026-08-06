"""Track C — EpisodicRepository tests (Batch 2).

Covers bounded storage, query methods, event handling, storage dual-write
(best-effort), and restore behavior.
"""

from datetime import datetime

import pytest

from atlas.longterm.episode_repository import EpisodicRepository
from atlas.longterm.models import Episode, EpisodeEvent, EpisodeKind


def _make_episode(
    episode_id: str,
    *,
    kind: EpisodeKind = EpisodeKind.PIPELINE,
    outcome: str = "success",
    started_at: datetime | None = None,
    source_experience_id: str = "",
) -> Episode:
    return Episode(
        episode_id=episode_id,
        kind=kind,
        title=f"Episode {episode_id}",
        outcome=outcome,
        started_at=started_at or datetime(2026, 1, 1, 0, 0, 0),
        source_experience_id=source_experience_id,
    )


def _make_event(
    event_id: str,
    episode_id: str,
    *,
    sequence: int = 0,
    event_type: str = "pipeline_start",
) -> EpisodeEvent:
    return EpisodeEvent(
        event_id=event_id,
        episode_id=episode_id,
        sequence=sequence,
        event_type=event_type,
    )


class TestInit:
    def test_defaults(self):
        repo = EpisodicRepository()
        assert repo.episode_count == 0
        assert repo._max_episodes == 10_000
        assert repo._max_events_per_episode == 1_000

    def test_custom_limits(self):
        repo = EpisodicRepository(max_episodes=10, max_events_per_episode=5)
        assert repo._max_episodes == 10
        assert repo._max_events_per_episode == 5

    def test_invalid_max_episodes(self):
        with pytest.raises(ValueError):
            EpisodicRepository(max_episodes=0)

    def test_invalid_max_events(self):
        with pytest.raises(ValueError):
            EpisodicRepository(max_events_per_episode=0)


class TestStoreAndGetEpisode:
    def test_store_and_get(self):
        repo = EpisodicRepository()
        ep = _make_episode("ep1")
        repo.store_episode(ep)
        assert repo.get_episode("ep1") is ep
        assert repo.episode_count == 1

    def test_get_missing(self):
        repo = EpisodicRepository()
        assert repo.get_episode("missing") is None

    def test_store_replaces_existing(self):
        repo = EpisodicRepository()
        ep1 = _make_episode("ep1", outcome="success")
        ep2 = _make_episode("ep1", outcome="failure")
        repo.store_episode(ep1)
        repo.store_episode(ep2)
        assert repo.get_episode("ep1") is ep2
        assert repo.episode_count == 1

    def test_bounded_eviction(self):
        repo = EpisodicRepository(max_episodes=2)
        repo.store_episode(_make_episode("ep1"))
        repo.store_episode(_make_episode("ep2"))
        repo.store_episode(_make_episode("ep3"))
        assert repo.episode_count == 2
        assert repo.get_episode("ep1") is None
        assert repo.get_episode("ep2") is not None
        assert repo.get_episode("ep3") is not None


class TestQueryEpisodes:
    def test_get_episodes_newest_first(self):
        repo = EpisodicRepository()
        repo.store_episode(_make_episode("ep1", started_at=datetime(2026, 1, 1)))
        repo.store_episode(_make_episode("ep2", started_at=datetime(2026, 1, 2)))
        episodes = repo.get_episodes()
        assert [e.episode_id for e in episodes] == ["ep2", "ep1"]

    def test_get_episodes_limit(self):
        repo = EpisodicRepository()
        for i in range(5):
            repo.store_episode(_make_episode(f"ep{i}"))
        assert len(repo.get_episodes(n=2)) == 2

    def test_get_episodes_zero_limit(self):
        repo = EpisodicRepository()
        repo.store_episode(_make_episode("ep1"))
        assert repo.get_episodes(n=0) == []

    def test_get_episodes_since(self):
        repo = EpisodicRepository()
        repo.store_episode(_make_episode("ep1", started_at=datetime(2026, 1, 1)))
        repo.store_episode(_make_episode("ep2", started_at=datetime(2026, 1, 2)))
        since = datetime(2026, 1, 2)
        episodes = repo.get_episodes_since(since)
        assert [e.episode_id for e in episodes] == ["ep2"]

    def test_get_by_kind(self):
        repo = EpisodicRepository()
        repo.store_episode(_make_episode("ep1", kind=EpisodeKind.PIPELINE))
        repo.store_episode(_make_episode("ep2", kind=EpisodeKind.TASK))
        tasks = repo.get_episodes_by_kind(EpisodeKind.TASK)
        assert [e.episode_id for e in tasks] == ["ep2"]

    def test_get_by_outcome(self):
        repo = EpisodicRepository()
        repo.store_episode(_make_episode("ep1", outcome="success"))
        repo.store_episode(_make_episode("ep2", outcome="failure"))
        failures = repo.get_episodes_by_outcome("failure")
        assert [e.episode_id for e in failures] == ["ep2"]

    def test_get_by_source(self):
        repo = EpisodicRepository()
        repo.store_episode(_make_episode("ep1", source_experience_id="exp1"))
        repo.store_episode(_make_episode("ep2", source_experience_id="exp2"))
        result = repo.get_episodes_by_source("exp1")
        assert [e.episode_id for e in result] == ["ep1"]


class TestRemoveEpisode:
    def test_remove_existing(self):
        repo = EpisodicRepository()
        repo.store_episode(_make_episode("ep1"))
        assert repo.remove_episode("ep1") is True
        assert repo.episode_count == 0

    def test_remove_missing(self):
        repo = EpisodicRepository()
        assert repo.remove_episode("missing") is False

    def test_remove_clears_events(self):
        repo = EpisodicRepository()
        repo.store_episode(_make_episode("ep1"))
        repo.store_event(_make_event("e1", "ep1"))
        repo.remove_episode("ep1")
        assert repo.get_events("ep1") == []


class TestEvents:
    def test_store_and_get_events(self):
        repo = EpisodicRepository()
        repo.store_episode(_make_episode("ep1"))
        repo.store_event(_make_event("e1", "ep1", sequence=0))
        repo.store_event(_make_event("e2", "ep1", sequence=1))
        events = repo.get_events("ep1")
        assert [e.event_id for e in events] == ["e1", "e2"]

    def test_store_event_replaces_duplicate(self):
        repo = EpisodicRepository()
        repo.store_episode(_make_episode("ep1"))
        repo.store_event(_make_event("e1", "ep1", sequence=0, event_type="a"))
        repo.store_event(_make_event("e1", "ep1", sequence=0, event_type="b"))
        events = repo.get_events("ep1")
        assert len(events) == 1
        assert events[0].event_type == "b"

    def test_get_event(self):
        repo = EpisodicRepository()
        repo.store_episode(_make_episode("ep1"))
        repo.store_event(_make_event("e1", "ep1"))
        assert repo.get_event("ep1", "e1") is not None
        assert repo.get_event("ep1", "missing") is None

    def test_events_bounded(self):
        repo = EpisodicRepository(max_events_per_episode=2)
        repo.store_episode(_make_episode("ep1"))
        for i in range(5):
            repo.store_event(_make_event(f"e{i}", "ep1", sequence=i))
        events = repo.get_events("ep1")
        assert len(events) == 2

    def test_remove_events(self):
        repo = EpisodicRepository()
        repo.store_episode(_make_episode("ep1"))
        repo.store_event(_make_event("e1", "ep1"))
        assert repo.remove_events("ep1") is True
        assert repo.get_events("ep1") == []

    def test_remove_events_missing(self):
        repo = EpisodicRepository()
        assert repo.remove_events("missing") is False


class TestSummaryAndClear:
    def test_summary(self):
        repo = EpisodicRepository(max_episodes=5)
        repo.store_episode(_make_episode("ep1"))
        summary = repo.summary()
        assert summary["episode_count"] == 1
        assert summary["max_episodes"] == 5
        assert summary["storage_available"] is False

    def test_clear(self):
        repo = EpisodicRepository()
        repo.store_episode(_make_episode("ep1"))
        repo.store_event(_make_event("e1", "ep1"))
        repo.clear()
        assert repo.episode_count == 0
        assert repo.get_events("ep1") == []


class _FakeStorage:
    """Minimal LongTermStorage-compatible fake for tests."""

    def __init__(self, available: bool = True):
        self._available = available
        self.episodes: list[Episode] = []
        self.events: list[EpisodeEvent] = []
        self.store_calls: list[str] = []

    def initialize(self) -> None:
        self._available = True

    def close(self) -> None:
        self._available = False

    def is_available(self) -> bool:
        return self._available

    def store_episode(self, episode: Episode) -> None:
        self.store_calls.append("store_episode")
        self.episodes.append(episode)

    def load_episodes(self) -> list[Episode]:
        return list(self.episodes)

    def load_episode(self, episode_id: str) -> Episode | None:
        for ep in self.episodes:
            if ep.episode_id == episode_id:
                return ep
        return None

    def store_episode_event(self, event: EpisodeEvent) -> None:
        self.store_calls.append("store_episode_event")
        self.events.append(event)

    def load_episode_events(self, episode_id: str) -> list[EpisodeEvent]:
        return [e for e in self.events if e.episode_id == episode_id]

    def store_procedure(self, procedure) -> None:
        pass

    def load_procedures(self) -> list:
        return []

    def load_procedure(self, procedure_id: str):
        return None

    def store_consolidation_record(self, record) -> None:
        pass

    def load_consolidation_records(self) -> list:
        return []


class TestStorageIntegration:
    def test_dual_write_episode(self):
        storage = _FakeStorage()
        repo = EpisodicRepository(storage=storage)
        ep = _make_episode("ep1")
        repo.store_episode(ep)
        assert "store_episode" in storage.store_calls
        assert len(storage.episodes) == 1

    def test_dual_write_event(self):
        storage = _FakeStorage()
        repo = EpisodicRepository(storage=storage)
        repo.store_episode(_make_episode("ep1"))
        repo.store_event(_make_event("e1", "ep1"))
        assert "store_episode_event" in storage.store_calls
        assert len(storage.events) == 1

    def test_storage_unavailable_does_not_break(self):
        storage = _FakeStorage(available=False)
        repo = EpisodicRepository(storage=storage)
        ep = _make_episode("ep1")
        repo.store_episode(ep)  # Should not raise
        assert repo.get_episode("ep1") is ep

    def test_storage_write_failure_does_not_break(self):
        class _BrokenStorage(_FakeStorage):
            def store_episode(self, episode: Episode) -> None:
                raise RuntimeError("storage down")

        storage = _BrokenStorage()
        repo = EpisodicRepository(storage=storage)
        ep = _make_episode("ep1")
        repo.store_episode(ep)  # Should not raise
        assert repo.get_episode("ep1") is ep

    def test_restore_no_storage(self):
        repo = EpisodicRepository()
        result = repo.restore()
        assert result == {"restored_episodes": 0, "restored_events": 0}

    def test_restore_from_storage(self):
        storage = _FakeStorage()
        ep = _make_episode("ep1")
        ev = _make_event("e1", "ep1")
        storage.episodes.append(ep)
        storage.events.append(ev)

        repo = EpisodicRepository(storage=storage)
        result = repo.restore()
        assert result["restored_episodes"] == 1
        assert result["restored_events"] == 1
        assert repo.get_episode("ep1") is not None
        assert repo.get_events("ep1") == [ev]

    def test_restore_skips_existing(self):
        storage = _FakeStorage()
        ep = _make_episode("ep1")
        storage.episodes.append(ep)

        repo = EpisodicRepository(storage=storage)
        repo.store_episode(_make_episode("ep1", outcome="failure"))
        result = repo.restore()
        assert result["restored_episodes"] == 1
        ep = repo.get_episode("ep1")
        assert ep is not None
        assert ep.outcome == "failure"
