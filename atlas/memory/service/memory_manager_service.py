"""
Atlas Memory Service

Single orchestration layer for the Atlas memory subsystem.
Delegates to MemoryRepository, MemorySearchEngine, and RankingEngine.
"""

from __future__ import annotations

from atlas.memory.models.memory import Memory
from atlas.memory.ranking.ranking_engine import RankingEngine
from atlas.memory.repository.memory_repository import MemoryRepository
from atlas.memory.search.search_engine import MemorySearchEngine


class MemoryManagerService:
    """Orchestrates memory operations by delegating to specialised components."""

    def __init__(
        self,
        repository: MemoryRepository,
        ranking_engine: RankingEngine,
        search_engine: MemorySearchEngine,
    ) -> None:
        self._repository = repository
        self._ranking_engine = ranking_engine
        self._search_engine = search_engine

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add_memory(self, memory: Memory) -> None:
        """Persist a new memory."""
        self._repository.add(memory)

    def get_memory(self, memory_id: str) -> Memory | None:
        """Retrieve a single memory by ID."""
        return self._repository.get(memory_id)

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory by ID. Returns True if deleted."""
        return self._repository.delete(memory_id)

    def list_memories(self) -> list[Memory]:
        """Return all memories."""
        raw = self._repository.load()
        return [
            Memory.from_dict(data)
            for data in raw.values()
        ]

    # ------------------------------------------------------------------
    # Search / Rank
    # ------------------------------------------------------------------

    def search(
        self,
        keyword: str | None = None,
        tags: list[str] | None = None,
        minimum_importance: int | None = None,
        limit: int | None = None,
    ) -> list[Memory]:
        """Search and filter memories, returning ranked results."""
        return self._search_engine.search(
            keyword=keyword,
            tags=tags,
            minimum_importance=minimum_importance,
            limit=limit,
        )

    def rank(
        self,
        memories: list[Memory],
    ) -> list[Memory]:
        """Rank a list of memories using the default strategy."""
        return self._ranking_engine.rank(memories)
