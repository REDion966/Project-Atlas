"""
Tests for Atlas MemoryService.
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
from atlas.memory.service.memory_service import MemoryService


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

    def add(self, memory: Memory) -> None:
        self._memories[memory.id] = memory.to_dict()

    def get(self, memory_id: str) -> Memory | None:
        data = self._memories.get(memory_id)
        if data is None:
            return None
        return Memory.from_dict(data)

    def delete(self, memory_id: str) -> bool:
        if memory_id not in self._memories:
            return False
        del self._memories[memory_id]
        return True


class TestMemoryService(unittest.TestCase):
    """Tests for MemoryService."""

    def setUp(self) -> None:
        self.repository = _MockRepository()
        self.ranking_engine = RankingEngine()
        self.search_engine = MemorySearchEngine(
            repository=self.repository,
            ranking_engine=self.ranking_engine,
        )
        self.service = MemoryService(
            repository=self.repository,
            ranking_engine=self.ranking_engine,
            search_engine=self.search_engine,
        )

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def test_initialisation(self) -> None:
        """Service is instantiated with all three dependencies."""
        self.assertIsInstance(self.service, MemoryService)

    # ------------------------------------------------------------------
    # add_memory
    # ------------------------------------------------------------------

    def test_add_memory(self) -> None:
        """Adding a memory stores it and it can be retrieved."""
        memory = Memory(
            id=str(uuid4()),
            title="Test Memory",
            content="Test content",
        )

        self.service.add_memory(memory)

        loaded = self.service.get_memory(memory.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.id, memory.id)
        self.assertEqual(loaded.title, memory.title)
        self.assertEqual(loaded.content, memory.content)

    # ------------------------------------------------------------------
    # get_memory
    # ------------------------------------------------------------------

    def test_get_memory_exists(self) -> None:
        """get_memory returns the correct memory for an existing ID."""
        memory = Memory(
            id=str(uuid4()),
            title="Existing",
            content="Existing content",
        )

        self.service.add_memory(memory)

        loaded = self.service.get_memory(memory.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.id, memory.id)

    def test_get_memory_nonexistent_returns_none(self) -> None:
        """get_memory returns None for a non-existent ID."""
        result = self.service.get_memory("nonexistent-id")
        self.assertIsNone(result)

    def test_get_memory_invalid_lookup(self) -> None:
        """get_memory returns None for an empty string ID."""
        result = self.service.get_memory("")
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # delete_memory
    # ------------------------------------------------------------------

    def test_delete_memory_exists(self) -> None:
        """delete_memory returns True and removes the memory."""
        memory = Memory(
            id=str(uuid4()),
            title="To Delete",
            content="Delete me",
        )

        self.service.add_memory(memory)
        deleted = self.service.delete_memory(memory.id)

        self.assertTrue(deleted)
        self.assertIsNone(self.service.get_memory(memory.id))

    def test_delete_memory_nonexistent_returns_false(self) -> None:
        """delete_memory returns False for a non-existent ID."""
        result = self.service.delete_memory("nonexistent-id")
        self.assertFalse(result)

    # ------------------------------------------------------------------
    # list_memories
    # ------------------------------------------------------------------

    def test_list_memories_returns_all(self) -> None:
        """list_memories returns all stored memories."""
        a = Memory(id=str(uuid4()), title="A", content="A")
        b = Memory(id=str(uuid4()), title="B", content="B")

        self.service.add_memory(a)
        self.service.add_memory(b)

        results = self.service.list_memories()

        self.assertEqual(len(results), 2)

        ids = {m.id for m in results}
        self.assertIn(a.id, ids)
        self.assertIn(b.id, ids)

    def test_list_memories_empty(self) -> None:
        """list_memories returns an empty list when no memories exist."""
        results = self.service.list_memories()
        self.assertEqual(results, [])

    # ------------------------------------------------------------------
    # search — delegation
    # ------------------------------------------------------------------

    def test_search_delegates_to_search_engine(self) -> None:
        """search passes keyword to the search engine and returns results."""
        memory = Memory(
            id=str(uuid4()),
            title="Python Atlas",
            content="Memory search",
        )

        self.service.add_memory(memory)

        results = self.service.search(keyword="Python")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, memory.id)

    def test_search_without_filters_returns_all_ranked(self) -> None:
        """search without filters returns all memories, ranked."""
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

        self.service.add_memory(low)
        self.service.add_memory(high)

        results = self.service.search()

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].importance, MemoryImportance.HIGH)
        self.assertEqual(results[1].importance, MemoryImportance.LOW)

    def test_search_empty_repository(self) -> None:
        """search on an empty repository returns an empty list."""
        results = self.service.search()
        self.assertEqual(results, [])

    # ------------------------------------------------------------------
    # rank — delegation
    # ------------------------------------------------------------------

    def test_rank_delegates_to_ranking_engine(self) -> None:
        """rank orders memories by importance (falls back from score)."""
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

        results = self.service.rank([low, high])

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].importance, MemoryImportance.HIGH)

    def test_rank_empty_list(self) -> None:
        """rank on an empty list returns an empty list."""
        results = self.service.rank([])
        self.assertEqual(results, [])

    def test_rank_single_memory(self) -> None:
        """rank on a single memory returns a single-element list."""
        memory = Memory(
            id=str(uuid4()),
            title="Solo",
            content="Alone",
        )

        results = self.service.rank([memory])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, memory.id)


if __name__ == "__main__":
    unittest.main()
