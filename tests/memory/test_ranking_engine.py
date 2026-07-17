"""
Tests for Atlas RankingEngine.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from atlas.memory.enums import MemoryImportance
from atlas.memory.models.memory import Memory
from atlas.memory.ranking.ranking_engine import RankingEngine


class TestRankingEngine(unittest.TestCase):
    """Tests for RankingEngine."""

    def setUp(self) -> None:
        self.engine = RankingEngine()

        self.low = Memory(
            id=str(uuid4()),
            title="Low",
            content="Low importance",
            importance=MemoryImportance.LOW,
        )

        self.normal = Memory(
            id=str(uuid4()),
            title="Normal",
            content="Normal importance",
            importance=MemoryImportance.NORMAL,
        )

        self.high = Memory(
            id=str(uuid4()),
            title="High",
            content="High importance",
            importance=MemoryImportance.HIGH,
        )

        self.critical = Memory(
            id=str(uuid4()),
            title="Critical",
            content="Critical importance",
            importance=MemoryImportance.CRITICAL,
        )

    # ------------------------------------------------------------------
    # sort_by_importance
    # ------------------------------------------------------------------

    def test_sort_by_importance_returns_highest_first(self) -> None:
        memories = [
            self.low,
            self.critical,
            self.normal,
            self.high,
        ]

        result = self.engine.sort_by_importance(memories)

        self.assertEqual(
            [m.importance for m in result],
            [
                MemoryImportance.CRITICAL,
                MemoryImportance.HIGH,
                MemoryImportance.NORMAL,
                MemoryImportance.LOW,
            ],
        )

    def test_sort_by_importance_preserves_order_for_equal(self) -> None:
        a = Memory(
            id=str(uuid4()),
            title="A",
            content="A",
            importance=MemoryImportance.HIGH,
        )

        b = Memory(
            id=str(uuid4()),
            title="B",
            content="B",
            importance=MemoryImportance.HIGH,
        )

        result = self.engine.sort_by_importance([b, a])

        self.assertEqual(
            result[0].title,
            "B",
        )

        self.assertEqual(
            result[1].title,
            "A",
        )

    def test_sort_by_importance_empty_list(self) -> None:
        result = self.engine.sort_by_importance([])

        self.assertEqual(result, [])

    def test_sort_by_importance_single_item(self) -> None:
        result = self.engine.sort_by_importance([self.high])

        self.assertEqual(len(result), 1)
        self.assertIs(result[0], self.high)

    # ------------------------------------------------------------------
    # sort_by_recency
    # ------------------------------------------------------------------

    def test_sort_by_recency_returns_newest_first(self) -> None:
        now = datetime.now(UTC)

        old = Memory(
            id=str(uuid4()),
            title="Old",
            content="Old",
            created_at=(now - timedelta(hours=5)).isoformat(),
        )

        mid = Memory(
            id=str(uuid4()),
            title="Mid",
            content="Mid",
            created_at=(now - timedelta(hours=2)).isoformat(),
        )

        new = Memory(
            id=str(uuid4()),
            title="New",
            content="New",
            created_at=now.isoformat(),
        )

        result = self.engine.sort_by_recency([old, new, mid])

        self.assertEqual(
            [m.title for m in result],
            ["New", "Mid", "Old"],
        )

    def test_sort_by_recency_preserves_order_for_equal(self) -> None:
        ts = datetime.now(UTC).isoformat()

        a = Memory(
            id=str(uuid4()),
            title="A",
            content="A",
            created_at=ts,
        )

        b = Memory(
            id=str(uuid4()),
            title="B",
            content="B",
            created_at=ts,
        )

        result = self.engine.sort_by_recency([b, a])

        self.assertEqual(
            result[0].title,
            "B",
        )

        self.assertEqual(
            result[1].title,
            "A",
        )

    def test_sort_by_recency_empty_list(self) -> None:
        result = self.engine.sort_by_recency([])

        self.assertEqual(result, [])

    def test_sort_by_recency_single_item(self) -> None:
        now = datetime.now(UTC)

        memory = Memory(
            id=str(uuid4()),
            title="Only",
            content="Only",
            created_at=now.isoformat(),
        )

        result = self.engine.sort_by_recency([memory])

        self.assertEqual(len(result), 1)
        self.assertIs(result[0], memory)

    # ------------------------------------------------------------------
    # sort_by_score
    # ------------------------------------------------------------------

    def test_sort_by_score_falls_back_to_importance(self) -> None:
        memories = [
            self.low,
            self.critical,
        ]

        result = self.engine.sort_by_score(memories)

        self.assertEqual(
            result[0].importance,
            MemoryImportance.CRITICAL,
        )

        self.assertEqual(
            result[1].importance,
            MemoryImportance.LOW,
        )

    def test_sort_by_score_empty_list(self) -> None:
        result = self.engine.sort_by_score([])

        self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # rank
    # ------------------------------------------------------------------

    def test_rank_falls_back_to_importance(self) -> None:
        result = self.engine.rank(
            [self.low, self.critical],
        )

        self.assertEqual(
            result[0].importance,
            MemoryImportance.CRITICAL,
        )

    def test_rank_empty_list(self) -> None:
        result = self.engine.rank([])

        self.assertEqual(result, [])

    def test_rank_single_item(self) -> None:
        result = self.engine.rank([self.normal])

        self.assertEqual(len(result), 1)
        self.assertIs(result[0], self.normal)


if __name__ == "__main__":
    unittest.main()
