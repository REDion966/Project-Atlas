"""
Atlas Context Engine

Builds relevant context from Atlas memory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from atlas.memory.models.memory import Memory
from atlas.memory.service.memory_manager_service import MemoryManagerService

if TYPE_CHECKING:
    from atlas.session.context import SessionContext


class ContextEngine:
    """
    Retrieves relevant memories through MemoryService.

    P1/B1.2 — session-scoped context is accepted and forwarded as
    attribution only; storage namespacing is deferred (no query filtering
    yet — the envelope is carried so P2 can depend on it).
    """

    def __init__(
        self,
        memory_service: MemoryManagerService,
    ) -> None:
        self._memory_service = memory_service
        self._last_session_context: SessionContext | None = None

    @property
    def last_session_context(self) -> SessionContext | None:
        return self._last_session_context

    def build_context(
        self,
        query: str,
        limit: int | None = None,
        session_context: SessionContext | None = None,
    ) -> list[Memory]:
        """
        Return relevant memories for a query.

        When ``session_context`` is provided it is recorded as attribution
        (exposed via :attr:`last_session_context`) but does not yet alter
        the query filter — storage namespacing is deferred per roadmap.
        """

        if not query or not query.strip():
            self._last_session_context = session_context
            return []

        self._last_session_context = session_context
        kwargs: dict[str, Any] = {"keyword": query, "limit": limit}
        if session_context is not None:
            kwargs["session_context"] = session_context
        return self._memory_service.search(**kwargs)  # type: ignore[arg-type]