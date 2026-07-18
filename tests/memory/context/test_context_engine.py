"""
Tests for Atlas ContextEngine.
"""

from __future__ import annotations

import unittest
from typing import Any
from uuid import uuid4

from atlas.memory.context import ContextEngine
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


class TestContextEngine(unittest.TestCase):
    """Tests for ContextEngine."""

    def setUp(self) -> None:
        self.repository = _MockRepository()
        self.ranking_engine = RankingEngine()
        self.search_engine = MemorySearchEngine(
            repository=self.repository,
            ranking_engine=self.ranking_engine,
        )
        self.memory_service = MemoryService(
            repository=self.repository,
            ranking_engine=self.ranking_engine,
            search_engine=self.search_engine,
        )
        self.engine = ContextEngine(
            memory_service=self.memory_service,
        )

    # ------------------------------------------------------------------
    # build_context — happy path
    # ------------------------------------------------------------------

    def test_build_context_returns_relevant_memories(self) -> None:
        """build_context returns memories matching the query keyword."""
        memory = Memory(
            id=str(uuid4()),
            title="Python Tips",
            content="How to use Python decorators",
        )
        unrelated = Memory(
            id=str(uuid4()),
            title="Cooking Recipes",
            content="How to bake bread",
        )

        self.memory_service.add_memory(memory)
        self.memory_service.add_memory(unrelated)

        results = self.engine.build_context(query="Python")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, memory.id)

    # ------------------------------------------------------------------
    # build_context — empty query
    # ------------------------------------------------------------------

    def test_build_context_empty_query_returns_empty(self) -> None:
        """build_context with an empty query returns an empty list."""
        memory = Memory(
            id=str(uuid4()),
            title="Test",
            content="Test content",
        )
        self.memory_service.add_memory(memory)

        results = self.engine.build_context(query="")
        self.assertEqual(results, [])

    def test_build_context_blank_query_returns_empty(self) -> None:
        """build_context with whitespace-only query returns an empty list."""
        memory = Memory(
            id=str(uuid4()),
            title="Test",
            content="Test content",
        )
        self.memory_service.add_memory(memory)

        results = self.engine.build_context(query="   ")
        self.assertEqual(results, [])

    # ------------------------------------------------------------------
    # build_context — no match
    # ------------------------------------------------------------------

    def test_build_context_no_match_returns_empty(self) -> None:
        """build_context returns an empty list when no memories match."""
        memory = Memory(
            id=str(uuid4()),
            title="Python",
            content="Code",
        )
        self.memory_service.add_memory(memory)

        results = self.engine.build_context(query="Rust")
        self.assertEqual(results, [])

    # ------------------------------------------------------------------
    # build_context — empty repository
    # ------------------------------------------------------------------

    def test_build_context_empty_repository_returns_empty(self) -> None:
        """build_context on an empty repository returns an empty list."""
        results = self.engine.build_context(query="anything")
        self.assertEqual(results, [])

    # ------------------------------------------------------------------
    # build_context — limit
    # ------------------------------------------------------------------

    def test_build_context_respects_limit(self) -> None:
        """build_context respects the limit parameter."""
        for i in range(5):
            self.memory_service.add_memory(
                Memory(
                    id=str(uuid4()),
                    title=f"Topic {i}",
                    content=f"Content about topic {i}",
                )
            )

        results = self.engine.build_context(query="topic", limit=2)
        self.assertLessEqual(len(results), 2)

    # ------------------------------------------------------------------
    # build_context — ranking
    # ------------------------------------------------------------------

    def test_build_context_returns_ranked(self) -> None:
        """build_context returns results ranked by importance."""
        low = Memory(
            id=str(uuid4()),
            title="Low importance",
            content="Python",
            importance=MemoryImportance.LOW,
        )
        high = Memory(
            id=str(uuid4()),
            title="High importance",
            content="Python",
            importance=MemoryImportance.HIGH,
        )

        self.memory_service.add_memory(low)
        self.memory_service.add_memory(high)

        results = self.engine.build_context(query="Python")

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].importance, MemoryImportance.HIGH)


if __name__ == "__main__":
    unittest.main()
