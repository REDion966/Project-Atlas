"""Atlas Long-Term Learning — ProceduralRepository (Track C, Batch 2).

Bounded in-memory store for procedures. Storage-agnostic: persistence is
delegated to an injected :class:`LongTermStorage` protocol adapter
(dual-write, best-effort). Failures in storage writes never break the
in-memory path.

Pure logic. No SQLite. No kernel. No gateway. No runtime. No events.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from typing import Any

from atlas.longterm.models import Procedure

logger = logging.getLogger(__name__)


class ProceduralRepository:
    """Bounded repository for procedural memory.

    Stores :class:`Procedure` objects in memory. When a ``LongTermStorage``
    adapter is injected, writes are dual-routed (best-effort; storage
    failures are logged and swallowed). Reads fall back to memory when
    storage is unavailable.
    """

    def __init__(
        self,
        max_procedures: int = 1_000,
        storage: Any | None = None,
    ) -> None:
        """Initialize the repository.

        Args:
            max_procedures: Maximum number of procedures retained before eviction.
            storage: Optional ``LongTermStorage`` protocol adapter.
        """
        if max_procedures <= 0:
            raise ValueError("max_procedures must be positive")

        self._max_procedures = max_procedures
        self._storage = storage

        self._procedures: deque[Procedure] = deque(maxlen=max_procedures)
        self._procedure_index: dict[str, Procedure] = {}

    # ------------------------------------------------------------------
    # Procedures
    # ------------------------------------------------------------------

    def store_procedure(self, procedure: Procedure) -> None:
        """Store or update a procedure.

        If the procedure already exists, the old entry is replaced. If the
        store is full, the oldest procedure is evicted (and removed from the
        index).
        """
        old = self._procedure_index.get(procedure.procedure_id)
        if old is not None:
            # Replace in place in the deque.
            self._procedures.remove(old)
            self._procedures.append(procedure)
            self._procedure_index[procedure.procedure_id] = procedure
        else:
            if len(self._procedures) == self._max_procedures:
                # Manually evict the oldest so the index stays consistent.
                evicted = self._procedures.popleft()
                self._procedure_index.pop(evicted.procedure_id, None)
            self._procedures.append(procedure)
            self._procedure_index[procedure.procedure_id] = procedure
        self._try_storage_write("store_procedure", procedure)

    def get_procedure(self, procedure_id: str) -> Procedure | None:
        """Retrieve a single procedure by ID."""
        return self._procedure_index.get(procedure_id)

    def get_procedures(self, n: int = 100) -> list[Procedure]:
        """Return the most recent n procedures (newest first)."""
        if n <= 0:
            return []
        return list(reversed(self._procedures))[:n]

    def get_procedures_by_category(self, category: str, n: int = 100) -> list[Procedure]:
        """Return procedures filtered by category (newest first)."""
        if n <= 0:
            return []
        return [p for p in reversed(self._procedures) if p.category == category][:n]

    def get_procedures_by_kind(self, kind: Any, n: int = 100) -> list[Procedure]:
        """Return procedures filtered by kind (newest first)."""
        if n <= 0:
            return []
        return [p for p in reversed(self._procedures) if p.kind == kind][:n]

    def get_procedures_by_tool(self, tool_name: str, n: int = 100) -> list[Procedure]:
        """Return procedures that reference a given tool name (newest first)."""
        if n <= 0:
            return []
        return [
            p for p in reversed(self._procedures)
            if any(s.tool_name == tool_name for s in p.steps)
        ][:n]

    def get_procedures_since(self, since: datetime) -> list[Procedure]:
        """Return procedures with created_at >= the given timestamp (oldest first)."""
        return [p for p in self._procedures if p.created_at >= since]

    def remove_procedure(self, procedure_id: str) -> bool:
        """Remove a procedure. Returns True if removed."""
        procedure = self._procedure_index.pop(procedure_id, None)
        if procedure is None:
            return False
        try:
            self._procedures.remove(procedure)
        except ValueError:
            pass
        return True

    def update_procedure(self, procedure: Procedure) -> None:
        """Alias for :meth:`store_procedure`; updates counters on a procedure."""
        self.store_procedure(procedure)

    @property
    def procedure_count(self) -> int:
        """Number of procedures stored."""
        return len(self._procedures)

    # ------------------------------------------------------------------
    # Summary & admin
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return a summary dict of the repository state."""
        return {
            "procedure_count": self.procedure_count,
            "max_procedures": self._max_procedures,
            "storage_available": self._storage is not None and bool(
                getattr(self._storage, "is_available", lambda: False)()
            ),
        }

    def clear(self) -> None:
        """Clear all stored data."""
        self._procedures.clear()
        self._procedure_index.clear()

    # ------------------------------------------------------------------
    # Storage integration (best-effort dual-write)
    # ------------------------------------------------------------------

    def _try_storage_write(self, method_name: str, data: object) -> None:
        """Write to the storage adapter, degrading gracefully on failure."""
        storage = self._storage
        if storage is None:
            return
        try:
            if not storage.is_available():
                return
            if method_name == "store_procedure":
                storage.store_procedure(data)  # type: ignore[arg-type]
        except Exception:
            logger.exception(
                "Long-term procedure storage write failed for %s", method_name
            )

    def restore(self) -> dict[str, Any]:
        """Load persisted procedures from storage into memory.

        Returns a summary dict: ``{"restored_procedures": int}``.
        If no storage is injected or the storage is unavailable, returns zero.
        """
        storage = self._storage
        if storage is None:
            return {"restored_procedures": 0}
        try:
            if not storage.is_available():
                return {"restored_procedures": 0}
            procedures = storage.load_procedures()
            for proc in procedures:
                if proc.procedure_id in self._procedure_index:
                    continue
                self._procedures.append(proc)
                self._procedure_index[proc.procedure_id] = proc
        except Exception:
            logger.exception("Failed to restore procedures from storage")

        return {"restored_procedures": self.procedure_count}