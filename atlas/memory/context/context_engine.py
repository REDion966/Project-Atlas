"""
Atlas Context Engine

Builds relevant context from Atlas memory.
"""

from __future__ import annotations

from atlas.memory.models.memory import Memory
from atlas.memory.service.memory_manager_service import MemoryManagerService


class ContextEngine:
    """
    Retrieves relevant memories through MemoryService.
    """

    def __init__(
        self,
        memory_service: MemoryManagerService,
    ) -> None:
        self._memory_service = memory_service


    def build_context(
        self,
        query: str,
        limit: int | None = None,
    ) -> list[Memory]:
        """
        Return relevant memories for a query.
        """

        if not query or not query.strip():
            return []

        return self._memory_service.search(
            keyword=query,
            limit=limit,
        )