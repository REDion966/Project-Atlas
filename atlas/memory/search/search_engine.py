"""
Atlas Memory Search Engine

Filters memories by keyword, tags, and importance,
then ranks results.
"""

from __future__ import annotations

from typing import Any

from atlas.memory.enums import MemoryImportance
from atlas.memory.models.memory import Memory
from atlas.memory.ranking.ranking_engine import RankingEngine
from atlas.memory.repository.memory_repository import MemoryRepository


class MemorySearchEngine:
    """Searches and filters memories."""

    def __init__(
        self,
        repository: MemoryRepository,
        ranking_engine: RankingEngine,
    ) -> None:
        self._repository = repository
        self._ranking_engine = ranking_engine

    def search(
        self,
        keyword: str | None = None,
        tags: list[str] | None = None,
        minimum_importance: int | None = None,
        limit: int | None = None,
        session_context: Any | None = None,
    ) -> list[Memory]:
        """Search memories with optional filters.

        P1/B1.2 — ``session_context`` is attribution only (recorded, not
        filtering) until storage namespacing is justified.
        """

        raw = self._repository.load()

        memories = [
            Memory.from_dict(data)
            for data in raw.values()
        ]

        if keyword is not None:
            keyword_lower = keyword.lower()
            memories = [
                m for m in memories
                if keyword_lower in m.title.lower()
                or keyword_lower in m.content.lower()
            ]

        if tags is not None:
            tags_set = set(tags)
            memories = [
                m for m in memories
                if tags_set & set(m.tags)
            ]

        if minimum_importance is not None:
            memories = [
                m for m in memories
                if m.importance.value >= minimum_importance
            ]

        memories = self._ranking_engine.rank(memories)

        if limit is not None:
            memories = memories[:limit]

        self._last_session_context = session_context
        return memories

    @property
    def last_session_context(self) -> Any | None:
        return getattr(self, "_last_session_context", None)
