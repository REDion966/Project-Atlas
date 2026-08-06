"""Track C — LongTermCapabilityFactory tests (Batch 4)."""

from atlas.longterm.capability_handlers import LongTermCapabilityFactory
from atlas.longterm.episode_repository import EpisodicRepository
from atlas.longterm.evolution_integration import (
    IngestHandoffResult,
    LongTermIngestBridge,
)
from atlas.longterm.models import Episode, EpisodeKind
from atlas.longterm.procedure_repository import ProceduralRepository
from atlas.reasoning.execution.registry import CapabilityRegistry


def _make_episode(episode_id: str, outcome: str = "success") -> Episode:
    return Episode(
        episode_id=episode_id,
        kind=EpisodeKind.PIPELINE,
        title=f"Episode {episode_id}",
        outcome=outcome,
    )


class _FakeSink:
    """Accepting sink fake for governed-ingest tests."""

    def __init__(self, accept: bool = True):
        self.accept = accept
        self.requests = []

    def enqueue_request(self, request) -> IngestHandoffResult:
        self.requests.append(request)
        if not self.accept:
            return IngestHandoffResult(False, error="refused")
        return IngestHandoffResult(True, request_id=request.request_id)


class TestRegistration:
    def test_handlers_registered(self):
        registry = CapabilityRegistry()
        factory = LongTermCapabilityFactory()
        factory.register(registry)
        assert registry.has("memory.episodic_query")
        assert registry.has("memory.procedure_query")
        assert registry.has("memory.consolidate")
        assert registry.count == 3


class TestEpisodicQuery:
    def test_empty_repository(self):
        factory = LongTermCapabilityFactory()
        result = factory.handlers()["memory.episodic_query"]({})
        assert result.success
        assert result.output["episodes"] == []

    def test_returns_stored_episodes(self):
        repository = EpisodicRepository()
        repository.store_episode(_make_episode("ep1"))
        factory = LongTermCapabilityFactory(episodes=repository)
        result = factory.handlers()["memory.episodic_query"]({})
        assert result.success
        assert result.output["episodes"][0]["episode_id"] == "ep1"

    def test_filter_by_outcome(self):
        repository = EpisodicRepository()
        repository.store_episode(_make_episode("ep1", outcome="success"))
        repository.store_episode(_make_episode("ep2", outcome="failure"))
        factory = LongTermCapabilityFactory(episodes=repository)
        result = factory.handlers()["memory.episodic_query"](
            {"outcome": "failure"}
        )
        assert result.success
        assert [e["episode_id"] for e in result.output["episodes"]] == ["ep2"]

    def test_invalid_since_fails_closed(self):
        factory = LongTermCapabilityFactory()
        result = factory.handlers()["memory.episodic_query"]({"since": "nope"})
        assert not result.success
        assert result.error


class TestProcedureQuery:
    def test_empty_repository(self):
        factory = LongTermCapabilityFactory()
        result = factory.handlers()["memory.procedure_query"]({})
        assert result.success
        assert result.output["procedures"] == []


class TestConsolidate:
    def test_fails_closed_without_sink(self):
        repository = EpisodicRepository()
        repository.store_episode(_make_episode("ep1"))
        factory = LongTermCapabilityFactory(episodes=repository)
        result = factory.handlers()["memory.consolidate"]({})
        assert not result.success
        assert "sink" in result.error

    def test_repositories_not_mutated(self):
        repository = EpisodicRepository()
        repository.store_episode(_make_episode("ep1"))
        factory = LongTermCapabilityFactory(episodes=repository)
        factory.handlers()["memory.consolidate"]({})
        assert repository.episode_count == 1
        assert repository.get_episode("ep1") is not None

    def test_accepting_sink_succeeds(self):
        repository = EpisodicRepository()
        repository.store_episode(
            Episode(
                episode_id="ep1",
                kind=EpisodeKind.PIPELINE,
                title="t",
                outcome="success",
                importance=0.05,
            )
        )
        sink = _FakeSink(accept=True)
        bridge = LongTermIngestBridge(sink=sink)
        factory = LongTermCapabilityFactory(episodes=repository, evolve_bridge=bridge)
        result = factory.handlers()["memory.consolidate"]({})
        assert result.success
        assert result.output["accepted"] is True
        assert len(sink.requests) == 1

    def test_refusing_sink_fails(self):
        repository = EpisodicRepository()
        repository.store_episode(_make_episode("ep1"))
        sink = _FakeSink(accept=False)
        bridge = LongTermIngestBridge(sink=sink)
        factory = LongTermCapabilityFactory(episodes=repository, evolve_bridge=bridge)
        result = factory.handlers()["memory.consolidate"]({})
        assert not result.success
        assert "refused" in result.error
