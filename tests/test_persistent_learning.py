"""Persistent Learning — reusable learning-insight persistence tests.

Verifies that reusable ``LearningInsight`` objects produced by the
``LearningEngine`` survive across separate operations via the existing
kernel-owned ``SQLiteEvolutionStorage``, retain provenance/confidence, and
can be restored into a fresh ``LearningMemory``. No new storage subsystem;
storage failures degrade gracefully.
"""

from datetime import datetime

import pytest

from atlas.learning_engine.learning_memory import LearningMemory
from atlas.learning_engine.models import (
    InsightImportance,
    LearningCategory,
    LearningInsight,
)


def _insight(insight_id="LRN-1", confidence=0.9, title="Reasoning cache works"):
    return LearningInsight(
        insight_id=insight_id,
        category=LearningCategory.REASONING_STRATEGY,
        title=title,
        description="Caching reasoning outputs is effective",
        importance=InsightImportance.HIGH,
        confidence=confidence,
        observation_count=3,
        source_pipeline_ids=["PIPE-1"],
        reusable=True,
        applicable_areas=["reasoning"],
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        last_updated=datetime(2026, 1, 1, 12, 0, 0),
        metadata={"source": "test", "provenance": "synthetic"},
    )


@pytest.fixture
def storage(tmp_path):
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage

    adapter = SQLiteEvolutionStorage(db_path=tmp_path / "learning.db")
    adapter.initialize()
    return adapter


class TestLearningInsightPersistence:
    def test_insight_persists_across_separate_memories(self, storage):
        # Operation 1: write via one LearningMemory instance.
        first = LearningMemory(storage=storage)
        first.store_insights([_insight()])

        # Operation 2: a fresh memory restores the same insight from storage.
        second = LearningMemory(storage=storage)
        second.restore()
        loaded = second.get_insights(10)
        assert len(loaded) == 1
        assert loaded[0].insight_id == "LRN-1"
        assert loaded[0].title == "Reasoning cache works"

    def test_provenance_and_confidence_retained(self, storage):
        memory = LearningMemory(storage=storage)
        memory.store_insights([_insight()])

        restored = LearningMemory(storage=storage)
        restored.restore()
        insight = restored.get_insights(1)[0]

        assert insight.confidence == pytest.approx(0.9)
        assert insight.observation_count == 3
        assert insight.applicable_areas == ["reasoning"]
        assert insight.metadata == {"source": "test", "provenance": "synthetic"}

    def test_multiple_insights_restore(self, storage):
        memory = LearningMemory(storage=storage)
        memory.store_insights(
            [
                _insight("LRN-1", title="First"),
                _insight("LRN-2", title="Second"),
            ]
        )

        restored = LearningMemory(storage=storage)
        restored.restore()
        assert restored.insight_count == 2

    def test_no_storage_remains_in_memory(self):
        memory = LearningMemory()
        memory.store_insights([_insight()])
        assert memory.insight_count == 1
        assert memory.get_insights(1)[0].insight_id == "LRN-1"

    def test_storage_failure_degrades_gracefully(self, storage, monkeypatch):
        def _boom(data):
            raise RuntimeError("storage exploded")

        monkeypatch.setattr(storage, "store_learning_insight", _boom)
        memory = LearningMemory(storage=storage)
        # Must not raise; in-memory path still works.
        memory.store_insights([_insight()])
        assert memory.insight_count == 1

    def test_restore_is_noop_without_storage(self):
        memory = LearningMemory()
        memory.restore()  # must not raise
        assert memory.insight_count == 0
