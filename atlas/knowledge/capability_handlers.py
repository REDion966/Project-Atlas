"""Atlas Knowledge — Capability Handlers.

Registers the knowledge capability following the Atlas
``CapabilityRegistry`` pattern (``CapabilityHandler = Callable[[dict], ExecutionResult]``):

  knowledge_retrieval — query the knowledge base for information

The handler is a pure bridge: all work is delegated to the injected
:class:`KnowledgeManager`. Deterministic, read-only, no state mutation.

No handler mutates Atlas state. No handler directly mutates the
``CapabilityRegistry`` — the :meth:`KnowledgeRetrievalHandlerFactory.register`
method is the only registration surface.
"""

from __future__ import annotations

from typing import Any, Callable

from atlas.knowledge.knowledge_manager import KnowledgeManager
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry

CapabilityHandler = Callable[[dict[str, Any]], ExecutionResult]


class KnowledgeRetrievalHandlerFactory:
    """Constructs the knowledge_retrieval capability handler with DI.

    Mirrors the Track A/B/C/D ``*CapabilityFactory`` pattern:
    constructor injection of the :class:`KnowledgeManager`, a ``handlers()``
    method returning the capability map, and a ``register()`` method that
    adds it to a ``CapabilityRegistry``.

    Args:
        knowledge_manager: The kernel-owned :class:`KnowledgeManager`. If
            ``None``, a default instance is created.
    """

    def __init__(
        self,
        knowledge_manager: KnowledgeManager | None = None,
    ) -> None:
        """Initialise the factory with an optional KnowledgeManager."""
        self._knowledge_manager = knowledge_manager or KnowledgeManager()

    @property
    def knowledge_manager(self) -> KnowledgeManager:
        """The injected KnowledgeManager."""
        return self._knowledge_manager

    # ------------------------------------------------------------------
    # Registration surface
    # ------------------------------------------------------------------

    def handlers(self) -> dict[str, CapabilityHandler]:
        """Return the knowledge capabilities keyed by name."""
        return {
            "knowledge_retrieval": self._query_handler,
        }

    def register(self, registry: CapabilityRegistry) -> None:
        """Register all knowledge handlers into a ``CapabilityRegistry``."""
        for name, handler in self.handlers().items():
            registry.register(name, handler)

    # ------------------------------------------------------------------
    # knowledge_retrieval — query the knowledge base
    # ------------------------------------------------------------------

    def _query_handler(self, params: dict[str, Any]) -> ExecutionResult:
        """Query the knowledge base for information.

        Params:
            query (str, required): non-empty query string.
            limit (int, optional): maximum number of results.

        Returns:
            ExecutionResult with query results on success.
        """
        query = params.get("query")
        if not isinstance(query, str) or not query.strip():
            return ExecutionResult(
                capability="knowledge_retrieval",
                success=False,
                error="knowledge_retrieval requires a non-empty 'query' string",
                metadata={"handler": "knowledge_retrieval"},
            )

        try:
            limit = self._normalize_limit(params.get("limit"))
            entries = self._knowledge_manager.query(query.strip())
            if limit is not None:
                entries = entries[:limit]
            return ExecutionResult(
                capability="knowledge_retrieval",
                success=True,
                output={
                    "results": [
                        {"title": e.title, "content": e.content, "source": e.source}
                        for e in entries
                    ],
                    "count": len(entries),
                },
                metadata={"handler": "knowledge_retrieval", "query": query.strip()},
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ExecutionResult(
                capability="knowledge_retrieval",
                success=False,
                error=f"Knowledge query failed: {exc}",
                metadata={"handler": "knowledge_retrieval"},
            )

    @staticmethod
    def _normalize_limit(raw: Any) -> int | None:
        """Coerce an optional limit into a positive int, or None."""
        if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
            return None
        return raw


# ---------------------------------------------------------------------------
# Module-level convenience for registry registration
# ---------------------------------------------------------------------------

_knowledge_factory: KnowledgeRetrievalHandlerFactory | None = None


def knowledge_handlers() -> dict[str, CapabilityHandler]:
    """Return the knowledge capability handlers (cached factory)."""
    global _knowledge_factory
    if _knowledge_factory is None:
        _knowledge_factory = KnowledgeRetrievalHandlerFactory()
    return _knowledge_factory.handlers()
