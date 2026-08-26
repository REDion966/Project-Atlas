"""Evolution Memory persistence and knowledge integration — Phase 13.5.

Covers the durable evolution-knowledge foundation:

- EvolutionMemory insight persistence: store/retrieve, adapter interaction,
  restore from SQLite storage, bounded memory management.
- EvolutionMemory observation restore (write path existed; read path added).
- EvolutionKnowledgeRepository: store/load/restore/memory management for
  patterns, strategies, capabilities, bottlenecks, and snapshots.
- Storage-failure resilience: no failure in the injected adapter may ever
  break the in-memory path (best-effort persistence contract).
"""

from datetime import datetime, timedelta

import pytest

import sqlite3

from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.intelligence_engine import EvolutionIntelligenceEngine
from atlas.evolution.knowledge.models import (
    BottleneckProfile,
    CapabilityEvolution,
    EvolutionKnowledgeSnapshot,
    RecurringOutcomePattern,
    StrategyKnowledge,
)
from atlas.evolution.knowledge.repository import EvolutionKnowledgeRepository
from atlas.evolution.models import (
    EvolutionInsight,
    Observation,
    ObservationCategory,
)
from atlas.storage.evolution_storage import SQLiteEvolutionStorage


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _make_insight(
    insight_id: str = "INS-001",
    proposal_id: str = "PROP-001",
    outcome: str = "success",
    minutes_ago: int = 0,
) -> EvolutionInsight:
    return EvolutionInsight(
        insight_id=insight_id,
        proposal_id=proposal_id,
        execution_record_id=f"REC-{insight_id}",
        tracked_goal_id=f"GOAL-{insight_id}",
        outcome=outcome,
        confidence=0.8,
        effectiveness_score=0.7,
        evidence_summary="evidence for " + insight_id,
        evidence_count=3,
        evidence_quality=0.9,
        regression_risk=0.1,
        analyzed_at=datetime.now() - timedelta(minutes=minutes_ago),
        proposal_title="Title " + proposal_id,
        proposal_summary="Summary " + proposal_id,
        metadata={"source": "test"},
    )


def _make_observation(metric: str = "avg_response_time") -> Observation:
    return Observation(
        category=ObservationCategory.RUNTIME_METRICS,
        metric_name=metric,
        value=42.5,
        unit="ms",
        description="test observation",
        source="SelfObservationEngine",
        metadata={"observation_id": f"OBS-{metric}"},
    )


class _ExplodingStorage:
    """Storage adapter whose every read/write raises — resilience probe."""

    def is_available(self) -> bool:
        return True

    def store_proposal(self, data: dict) -> None:
        raise sqlite3.OperationalError("boom")

    def load_proposals(self) -> list[dict]:
        raise sqlite3.OperationalError("boom")

    def store_approval_request(self, data: dict) -> None:
        raise sqlite3.OperationalError("boom")

    def load_approval_requests(self) -> list[dict]:
        raise sqlite3.OperationalError("boom")

    def store_record(self, data: dict) -> None:
        raise sqlite3.OperationalError("boom")

    def load_records(self) -> list[dict]:
        raise sqlite3.OperationalError("boom")

    def store_insight(self, data: dict) -> None:
        raise sqlite3.OperationalError("boom")

    def load_insights(self, proposal_id=None, limit=50) -> list[dict]:
        raise sqlite3.OperationalError("boom")

    def store_observation(self, data: dict) -> None:
        raise sqlite3.OperationalError("boom")

    def load_observations(self) -> list[dict]:
        raise sqlite3.OperationalError("boom")

    def store_knowledge_pattern(self, data: dict) -> None:
        raise sqlite3.OperationalError("boom")

    def load_knowledge_patterns(self) -> list[dict]:
        raise sqlite3.OperationalError("boom")

    def store_knowledge_strategy(self, data: dict) -> None:
        raise sqlite3.OperationalError("boom")

    def load_knowledge_strategies(self) -> list[dict]:
        raise sqlite3.OperationalError("boom")

    def store_knowledge_capability(self, data: dict) -> None:
        raise sqlite3.OperationalError("boom")

    def load_knowledge_capabilities(self) -> list[dict]:
        raise sqlite3.OperationalError("boom")

    def store_knowledge_bottleneck(self, data: dict) -> None:
        raise sqlite3.OperationalError("boom")

    def load_knowledge_bottlenecks(self) -> list[dict]:
        raise sqlite3.OperationalError("boom")

    def store_knowledge_snapshot(self, data: dict) -> None:
        raise sqlite3.OperationalError("boom")

    def load_knowledge_snapshots(self) -> list[dict]:
        raise sqlite3.OperationalError("boom")


@pytest.fixture
def sqlite_storage(tmp_path):
    storage = SQLiteEvolutionStorage(db_path=tmp_path / "evolution.db")
    storage.initialize()
    yield storage
    storage.close()


# ---------------------------------------------------------------------------
# A — Evolution insights in EvolutionMemory
# ---------------------------------------------------------------------------


class TestInsightMemoryOperations:
    def test_store_and_retrieve(self):
        mem = EvolutionMemory()
        assert mem.insight_count == 0
        assert mem.get_insights() == []

        ins = _make_insight()
        mem.store_insight(ins)
        assert mem.insight_count == 1
        assert mem.get_insight("INS-001") is ins
        assert mem.get_insights() == [ins]

    def test_newest_first_ordering(self):
        mem = EvolutionMemory()
        old = _make_insight("INS-OLD", minutes_ago=30)
        new = _make_insight("INS-NEW", minutes_ago=1)
        mem.store_insight(old)
        mem.store_insight(new)
        assert [i.insight_id for i in mem.get_insights()] == ["INS-NEW", "INS-OLD"]

    def test_filter_by_proposal_and_limit(self):
        mem = EvolutionMemory()
        mem.store_insight(_make_insight("INS-A", proposal_id="P1", minutes_ago=10))
        mem.store_insight(_make_insight("INS-B", proposal_id="P2", minutes_ago=5))
        mem.store_insight(_make_insight("INS-C", proposal_id="P1", minutes_ago=1))

        p1 = mem.get_insights(proposal_id="P1")
        assert [i.insight_id for i in p1] == ["INS-C", "INS-A"]
        assert [i.insight_id for i in mem.get_insights(n=2)] == ["INS-C", "INS-B"]
        assert mem.get_insights(n=0) == []

    def test_get_insight_miss_returns_none(self):
        mem = EvolutionMemory()
        assert mem.get_insight("NOPE") is None

    def test_bounded_memory_management(self):
        mem = EvolutionMemory(max_insights=2)
        for idx in range(4):
            mem.store_insight(_make_insight(f"INS-{idx}"))
        assert mem.insight_count == 2
        # Oldest evicted, newest retained.
        assert mem.get_insight("INS-0") is None
        assert [i.insight_id for i in mem.get_insights()] == ["INS-3", "INS-2"]

    def test_summary_includes_insight_count(self):
        mem = EvolutionMemory()
        mem.store_insight(_make_insight())
        assert mem.summary()["insight_count"] == 1

    def test_clear_removes_insights(self):
        mem = EvolutionMemory()
        mem.store_insight(_make_insight())
        mem.clear()
        assert mem.insight_count == 0


class TestInsightPersistenceAdapterInteraction:
    def test_write_reaches_sqlite_adapter(self, sqlite_storage):
        mem = EvolutionMemory(storage=sqlite_storage)
        mem.store_insight(_make_insight("INS-PERSIST"))

        loaded = sqlite_storage.load_insights()
        assert len(loaded) == 1
        assert loaded[0]["insight_id"] == "INS-PERSIST"
        assert loaded[0]["outcome"] == "success"

    def test_serialization_is_json_safe(self, sqlite_storage):
        import json

        from atlas.evolution.evolution_memory import (
            _evolution_insight_to_dict as to_dict,
        )

        data = to_dict(_make_insight())
        json.dumps(data)  # must not raise
        sqlite_storage.store_insight(data)

    def test_restore_from_storage(self, sqlite_storage):
        writer = EvolutionMemory(storage=sqlite_storage)
        writer.store_insight(_make_insight("INS-R1", minutes_ago=20))
        writer.store_insight(_make_insight("INS-R2", minutes_ago=1))

        reader = EvolutionMemory(storage=sqlite_storage)
        reader.restore()

        assert reader.insight_count == 2
        restored = reader.get_insight("INS-R1")
        assert restored is not None
        assert restored.outcome == "success"
        assert restored.metadata == {"source": "test"}
        # Newest-first retrieval returns one of the two restored insights.
        assert reader.get_insights(n=1)[0].insight_id in {"INS-R1", "INS-R2"}

    def test_engine_routes_persistence_through_memory(self, sqlite_storage):
        memory = EvolutionMemory(storage=sqlite_storage)
        engine = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            storage=sqlite_storage,
        )
        engine._persist_insight(_make_insight("INS-VIA-MEM"))

        # Single path: visible in BOTH the memory layer and the adapter.
        assert memory.get_insight("INS-VIA-MEM") is not None
        rows = sqlite_storage.load_insights()
        assert [d["insight_id"] for d in rows] == ["INS-VIA-MEM"]


class TestObservationRestore:
    def test_persist_then_restore_round_trip(self, sqlite_storage):
        writer = EvolutionMemory(storage=sqlite_storage)
        writer.persist_observation(_make_observation("metric_a"))
        writer.persist_observation(_make_observation("metric_b"))

        reader = EvolutionMemory(storage=sqlite_storage)
        reader.restore()

        assert reader.observation_count == 2
        names = {o.metric_name for o in reader._observations}
        assert names == {"metric_a", "metric_b"}
        first = next(
            o for o in reader._observations if o.metric_name == "metric_a"
        )
        assert first.category is ObservationCategory.RUNTIME_METRICS
        assert first.value == 42.5
        assert first.unit == "ms"
        assert first.source == "SelfObservationEngine"


# ---------------------------------------------------------------------------
# Empty-storage and no-storage behavior
# ---------------------------------------------------------------------------


class TestEmptyAndMissingStorage:
    def test_restore_without_storage_is_noop(self):
        mem = EvolutionMemory()
        mem.restore()  # must not raise
        assert mem.insight_count == 0
        assert mem.observation_count == 0

    def test_restore_with_empty_sqlite_storage(self, tmp_path):
        storage = SQLiteEvolutionStorage(db_path=tmp_path / "empty.db")
        storage.initialize()
        try:
            mem = EvolutionMemory(storage=storage)
            mem.restore()
            assert mem.insight_count == 0
            assert mem.observation_count == 0
            assert mem.proposal_count == 0
        finally:
            storage.close()

    def test_unavailable_storage_skips_writes(self):
        class _Unavailable:
            def is_available(self) -> bool:
                return False

            def store_insight(self, data: dict) -> None:
                raise AssertionError("must not be called when unavailable")

        mem = EvolutionMemory(storage=_Unavailable())
        mem.store_insight(_make_insight())
        assert mem.insight_count == 1  # memory path intact


# ---------------------------------------------------------------------------
# Storage-failure resilience (best-effort persistence contract)
# ---------------------------------------------------------------------------


class TestStorageFailureResilience:
    def test_insight_store_survives_adapter_failure(self):
        mem = EvolutionMemory(storage=_ExplodingStorage())
        mem.store_insight(_make_insight())
        assert mem.insight_count == 1
        assert mem.get_insight("INS-001") is not None

    def test_restore_survives_adapter_failure(self):
        mem = EvolutionMemory(storage=_ExplodingStorage())
        mem.restore()  # every load raises; must be swallowed
        assert mem.insight_count == 0
        assert mem.observation_count == 0


# ---------------------------------------------------------------------------
# B-F — EvolutionKnowledgeRepository: patterns/strategies/capabilities/
# bottlenecks/snapshots
# ---------------------------------------------------------------------------


def _make_pattern(pid="PAT-1", area="testing", outcome="success"):
    return RecurringOutcomePattern(
        pattern_id=pid,
        area=area,
        outcome=outcome,
        occurrence_count=3,
        success_count=2,
        confidence=0.66,
    )


def _make_strategy(key="strat-1"):
    return StrategyKnowledge(
        strategy_key=key,
        strategy_name="Incremental rollout",
        success_count=4,
        effectiveness=0.8,
        confidence=0.75,
    )


def _make_capability(name="reasoning"):
    return CapabilityEvolution(
        capability_name=name,
        assessments=[0.5, 0.6, 0.7],
        observed_count=3,
    )


def _make_bottleneck(bid="BN-1", area="memory"):
    return BottleneckProfile(
        bottleneck_id=bid,
        area=area,
        description="unbounded accumulator",
        recurrence_count=2,
    )


def _make_snapshot(sid="SNAP-1"):
    return EvolutionKnowledgeSnapshot(
        snapshot_id=sid,
        timestamp=datetime.now(),
        pattern_count=1,
        strategy_count=1,
        capability_count=1,
        bottleneck_count=1,
        summary_text="one of each",
    )


class TestKnowledgeRepositoryOperations:
    def test_pattern_store_load_update(self):
        repo = EvolutionKnowledgeRepository()
        repo.store_pattern(_make_pattern())
        assert repo.pattern_count == 1
        assert repo.get_pattern("PAT-1") is not None
        assert repo.get_patterns()[0].outcome == "success"

        updated = RecurringOutcomePattern(
            pattern_id="PAT-1",
            area="testing",
            outcome="failure",
            occurrence_count=3,
            success_count=1,
            confidence=0.33,
        )
        repo.store_pattern(updated)  # upsert by pattern_id
        assert repo.pattern_count == 1
        assert repo.get_pattern("PAT-1").outcome == "failure"

    def test_strategy_store_load(self):
        repo = EvolutionKnowledgeRepository()
        repo.store_strategy(_make_strategy())
        assert repo.strategy_count == 1
        assert repo.get_strategies()[0].strategy_key == "strat-1"
        assert repo.get_strategy("strat-1").effectiveness == pytest.approx(0.8)

    def test_capability_store_load(self):
        repo = EvolutionKnowledgeRepository()
        repo.store_capability(_make_capability())
        assert repo.capability_count == 1
        cap = repo.get_capability("reasoning")
        assert cap is not None
        assert cap.observed_count == 3

    def test_bottleneck_store_load_sorted_by_recurrence(self):
        repo = EvolutionKnowledgeRepository()
        frequent = BottleneckProfile(
            bottleneck_id="BN-HOT",
            area="io",
            description="hot path",
            recurrence_count=9,
        )
        repo.store_bottleneck(_make_bottleneck("BN-COLD", area="cpu"))
        repo.store_bottleneck(frequent)
        ordered = repo.get_bottlenecks()
        assert ordered[0].bottleneck_id == "BN-HOT"
        assert repo.bottleneck_count == 2

    def test_snapshot_store_latest(self):
        repo = EvolutionKnowledgeRepository()
        assert repo.get_latest_snapshot() is None
        older = _make_snapshot("SNAP-OLD")
        newer = _make_snapshot("SNAP-NEW")
        repo.store_snapshot(older)
        repo.store_snapshot(newer)
        assert repo.snapshot_count == 2
        assert repo.get_latest_snapshot().snapshot_id == "SNAP-NEW"
        assert [s.snapshot_id for s in repo.get_snapshots()] == [
            "SNAP-NEW",
            "SNAP-OLD",
        ]

    def test_bounded_memory_limits(self):
        repo = EvolutionKnowledgeRepository(
            max_patterns=2,
            max_snapshots=2,
        )
        for idx in range(4):
            repo.store_pattern(_make_pattern(f"PAT-{idx}"))
            repo.store_snapshot(_make_snapshot(f"SNAP-{idx}"))
        assert repo.pattern_count == 2
        assert repo.snapshot_count == 2

    def test_summary_reports_counts(self):
        repo = EvolutionKnowledgeRepository()
        repo.store_pattern(_make_pattern())
        repo.store_snapshot(_make_snapshot())
        summary = repo.summary()
        assert summary["pattern_count"] == 1
        assert summary["snapshot_count"] == 1
        assert summary["storage_available"] is False

    def test_clear_empties_all_knowledge(self):
        repo = EvolutionKnowledgeRepository()
        repo.store_pattern(_make_pattern())
        repo.store_strategy(_make_strategy())
        repo.store_capability(_make_capability())
        repo.store_bottleneck(_make_bottleneck())
        repo.store_snapshot(_make_snapshot())
        repo.clear()
        assert repo.pattern_count == 0
        assert repo.strategy_count == 0
        assert repo.capability_count == 0
        assert repo.bottleneck_count == 0
        assert repo.snapshot_count == 0


class TestKnowledgeRepositoryPersistence:
    def test_full_round_trip_through_sqlite(self, sqlite_storage):
        writer = EvolutionKnowledgeRepository(storage=sqlite_storage)
        writer.store_pattern(_make_pattern("PAT-RT"))
        writer.store_strategy(_make_strategy("strat-rt"))
        writer.store_capability(_make_capability("cap-rt"))
        writer.store_bottleneck(_make_bottleneck("BN-RT"))
        writer.store_snapshot(_make_snapshot("SNAP-RT"))

        reader = EvolutionKnowledgeRepository(storage=sqlite_storage)
        reader.restore()

        assert reader.pattern_count == 1
        assert reader.get_pattern("PAT-RT").area == "testing"
        assert reader.get_strategy("strat-rt").effectiveness == pytest.approx(0.8)
        assert reader.get_capability("cap-rt").observed_count == 3
        assert reader.get_bottleneck("BN-RT").recurrence_count == 2
        assert reader.get_latest_snapshot().snapshot_id == "SNAP-RT"
        assert reader.summary()["storage_available"] is True

    def test_upsert_persists_single_row(self, sqlite_storage):
        repo = EvolutionKnowledgeRepository(storage=sqlite_storage)
        repo.store_pattern(_make_pattern("PAT-U"))
        mutated = _make_pattern("PAT-U", outcome="partial")
        repo.store_pattern(mutated)

        fresh = EvolutionKnowledgeRepository(storage=sqlite_storage)
        fresh.restore()
        assert fresh.pattern_count == 1
        assert fresh.get_pattern("PAT-U").outcome == "partial"

    def test_restore_empty_storage(self, tmp_path):
        storage = SQLiteEvolutionStorage(db_path=tmp_path / "k_empty.db")
        storage.initialize()
        try:
            repo = EvolutionKnowledgeRepository(storage=storage)
            repo.restore()
            assert repo.pattern_count == 0
            assert repo.strategy_count == 0
            assert repo.capability_count == 0
            assert repo.bottleneck_count == 0
            assert repo.snapshot_count == 0
        finally:
            storage.close()

    def test_restore_without_storage_is_noop(self):
        repo = EvolutionKnowledgeRepository()
        repo.restore()  # must not raise
        assert repo.pattern_count == 0

    def test_writes_survive_adapter_failure(self):
        repo = EvolutionKnowledgeRepository(storage=_ExplodingStorage())
        repo.store_pattern(_make_pattern())
        repo.store_strategy(_make_strategy())
        repo.store_capability(_make_capability())
        repo.store_bottleneck(_make_bottleneck())
        repo.store_snapshot(_make_snapshot())

        # Memory-first contract: everything is present despite raising adapter.
        assert repo.pattern_count == 1
        assert repo.strategy_count == 1
        assert repo.capability_count == 1
        assert repo.bottleneck_count == 1
        assert repo.snapshot_count == 1

    def test_restore_survives_adapter_failure(self):
        repo = EvolutionKnowledgeRepository(storage=_ExplodingStorage())
        repo.restore()  # every load raises; must be swallowed
        assert repo.pattern_count == 0
