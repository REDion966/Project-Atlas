"""
Tests for Atlas MemorySearchEngine.
"""

from __future__ import annotations

import unittest
from typing import Any
from uuid import uuid4

from atlas.memory.enums import MemoryImportance
from atlas.memory.models.memory import Memory
from atlas.memory.ranking.ranking_engine import RankingEngine
from atlas.memory.repository.memory_repository import MemoryRepository
from atlas.memory.search.search_engine import MemorySearchEngine


class _MockRepository(MemoryRepository):
    """In-memory repository stub that bypasses file storage."""

    def __init__(
        self,
        memories: list[Memory] | None = None,
    ) -> None:
        self._memories: dict[str, dict[str, Any]] = {}

        if memories is not None:
            for m in memories:
                self._memories[m.id] = m.to_dict()

    def load(self) -> dict:
        return self._memories


class TestMemorySearchEngine(unittest.TestCase):
    """Tests for MemorySearchEngine."""

    def setUp(self) -> None:
        self.ranking_engine = RankingEngine()
        self.engine = MemorySearchEngine(
            repository=_MockRepository(),
            ranking_engine=self.ranking_engine,
        )

    def _make_engine(
        self,
        memories: list[Memory],
    ) -> MemorySearchEngine:
        return MemorySearchEngine(
            repository=_MockRepository(memories),
            ranking_engine=self.ranking_engine,
        )

    # ------------------------------------------------------------------
    # No filters (full retrieval + rank)
    # ------------------------------------------------------------------

    def test_search_without_filters_returns_all_ranked(self) -> None:
        low = Memory(
            id=str(uuid4()),
            title="Low",
            content="Low priority",
            importance=MemoryImportance.LOW,
        )

        high = Memory(
            id=str(uuid4()),
            title="High",
            content="High priority",
            importance=MemoryImportance.HIGH,
        )

        engine = self._make_engine([low, high])

        result = engine.search()

        self.assertEqual(len(result), 2)

        # highest importance first
        self.assertEqual(
            result[0].importance,
            MemoryImportance.HIGH,
        )

    def test_search_empty_repository(self) -> None:
        result = self.engine.search()

        self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # Keyword filter
    # ------------------------------------------------------------------

    def test_search_by_keyword_matches_title(self) -> None:
        memory = Memory(
            id=str(uuid4()),
            title="Python Atlas",
            content="Some content",
        )

        engine = self._make_engine([memory])

        result = engine.search(keyword="Python")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, memory.id)

    def test_search_by_keyword_matches_content(self) -> None:
        memory = Memory(
            id=str(uuid4()),
            title="Title",
            content="Atlas Memory System",
        )

        engine = self._make_engine([memory])

        result = engine.search(keyword="Memory")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, memory.id)

    def test_search_by_keyword_case_insensitive(self) -> None:
        memory = Memory(
            id=str(uuid4()),
            title="Hello World",
            content="hello world",
        )

        engine = self._make_engine([memory])

        result = engine.search(keyword="HELLO")

        self.assertEqual(len(result), 1)

    def test_search_by_keyword_no_match(self) -> None:
        memory = Memory(
            id=str(uuid4()),
            title="Foo",
            content="Bar",
        )

        engine = self._make_engine([memory])

        result = engine.search(keyword="NonExistent")

        self.assertEqual(result, [])

    def test_search_by_keyword_partial_match(self) -> None:
        memory = Memory(
            id=str(uuid4()),
            title="Atlas Memory Engine",
            content="Ranking and searching",
        )

        engine = self._make_engine([memory])

        result = engine.search(keyword="emor")

        self.assertEqual(len(result), 1)

    def test_search_by_keyword_filters_only_matching(self) -> None:
        a = Memory(
            id=str(uuid4()),
            title="Python",
            content="Code",
        )

        b = Memory(
            id=str(uuid4()),
            title="Java",
            content="Code",
        )

        engine = self._make_engine([a, b])

        result = engine.search(keyword="Python")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, a.id)

    # ------------------------------------------------------------------
    # Tags filter
    # ------------------------------------------------------------------

    def test_search_by_tags_single_match(self) -> None:
        memory = Memory(
            id=str(uuid4()),
            title="Tagged",
            content="Content",
            tags=["atlas", "memory"],
        )

        engine = self._make_engine([memory])

        result = engine.search(tags=["atlas"])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, memory.id)

    def test_search_by_tags_multiple_match_any(self) -> None:
        memory = Memory(
            id=str(uuid4()),
            title="Multi",
            content="Content",
            tags=["python"],
        )

        engine = self._make_engine([memory])

        result = engine.search(
            tags=["python", "atlas"],
        )

        self.assertEqual(len(result), 1)

    def test_search_by_tags_no_match(self) -> None:
        memory = Memory(
            id=str(uuid4()),
            title="NoMatch",
            content="Content",
            tags=["python"],
        )

        engine = self._make_engine([memory])

        result = engine.search(tags=["java"])

        self.assertEqual(result, [])

    def test_search_by_tags_empty_list(self) -> None:
        memory = Memory(
            id=str(uuid4()),
            title="Any",
            content="Content",
            tags=["python"],
        )

        engine = self._make_engine([memory])

        # empty tag list - no memory can match an empty set
        result = engine.search(tags=[])

        self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # Importance filter
    # ------------------------------------------------------------------

    def test_search_by_minimum_importance(self) -> None:
        low = Memory(
            id=str(uuid4()),
            title="Low",
            content="Low",
            importance=MemoryImportance.LOW,
        )

        high = Memory(
            id=str(uuid4()),
            title="High",
            content="High",
            importance=MemoryImportance.HIGH,
        )

        engine = self._make_engine([low, high])

        result = engine.search(
            minimum_importance=MemoryImportance.HIGH.value,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, high.id)

    def test_search_by_minimum_importance_inclusive(self) -> None:
        critical = Memory(
            id=str(uuid4()),
            title="Critical",
            content="Critical",
            importance=MemoryImportance.CRITICAL,
        )

        high = Memory(
            id=str(uuid4()),
            title="High",
            content="High",
            importance=MemoryImportance.HIGH,
        )

        engine = self._make_engine([critical, high])

        result = engine.search(
            minimum_importance=MemoryImportance.HIGH.value,
        )

        self.assertEqual(len(result), 2)

    def test_search_by_minimum_importance_excludes_lower(self) -> None:
        low = Memory(
            id=str(uuid4()),
            title="Low",
            content="Low",
            importance=MemoryImportance.LOW,
        )

        normal = Memory(
            id=str(uuid4()),
            title="Normal",
            content="Normal",
            importance=MemoryImportance.NORMAL,
        )

        engine = self._make_engine([low, normal])

        result = engine.search(
            minimum_importance=MemoryImportance.HIGH.value,
        )

        self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # Limit
    # ------------------------------------------------------------------

    def test_search_with_limit(self) -> None:
        memories = [
            Memory(
                id=str(uuid4()),
                title=f"Memory {i}",
                content=f"Content {i}",
                importance=MemoryImportance(int(i) + 1)
                if i < 4
                else MemoryImportance.LOW,
            )
            for i in range(5)
        ]

        engine = self._make_engine(memories)

        result = engine.search(limit=2)

        self.assertLessEqual(len(result), 2)

    def test_search_limit_higher_than_results(self) -> None:
        memories = [
            Memory(
                id=str(uuid4()),
                title=f"Memory {i}",
                content=f"Content {i}",
            )
            for i in range(3)
        ]

        engine = self._make_engine(memories)

        result = engine.search(limit=10)

        self.assertEqual(len(result), 3)

    # ------------------------------------------------------------------
    # Combined filters
    # ------------------------------------------------------------------

    def test_search_combined_filters(self) -> None:
        target = Memory(
            id=str(uuid4()),
            title="Target Item",
            content="Important document",
            tags=["atlas", "search"],
            importance=MemoryImportance.HIGH,
        )

        wrong_tag = Memory(
            id=str(uuid4()),
            title="Wrong Tag",
            content="Important document",
            tags=["other"],
            importance=MemoryImportance.HIGH,
        )

        wrong_importance = Memory(
            id=str(uuid4()),
            title="Target Item",
            content="Important document",
            tags=["atlas"],
            importance=MemoryImportance.LOW,
        )

        engine = self._make_engine(
            [target, wrong_tag, wrong_importance],
        )

        result = engine.search(
            keyword="Important",
            tags=["atlas"],
            minimum_importance=MemoryImportance.NORMAL.value,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, target.id)


if __name__ == "__main__":
    unittest.main()
