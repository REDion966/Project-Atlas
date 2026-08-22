"""Production ``StateReader`` / ``StateWriter`` adapter for the MEMORY scope.

Wraps the real :class:`~atlas.memory.service.memory_manager_service.MemoryManagerService`
and implements the Phase 16 protocols from
:mod:`atlas.evolution.autonomy.applier`.

Namespace (deterministic): ``memory.<memory_id>``.

Key normalization: the adapter accepts both the namespaced form
(``memory.<id>``) and the bare form (``<id>``) so it is compatible with
``MemoryApplier``, which calls ``writer.write(memory_id, entry)`` with the
raw memory id, while also supporting the documented namespace.

Write semantics: idempotent by memory id — ``MemoryRepository.add``
overwrites by id (INSERT-OR-REPLACE style), so repeated application of the
same memory id never creates duplicate state.

Remove semantics: ``MemoryManagerService.delete_memory`` returns True only
if the memory existed; the adapter propagates that as the remove result.

Pure adapter layer: no governance, no AI, no async, no new persistence.
"""

from __future__ import annotations

from typing import Any

from atlas.evolution.autonomy.applier import StateReader, StateWriter
from atlas.memory.enums import MemoryImportance, MemoryType
from atlas.memory.models.memory import Memory
from atlas.memory.service.memory_manager_service import MemoryManagerService

#: Deterministic namespace prefix for MEMORY-scope state keys.
MEMORY_NAMESPACE = "memory."


class MemoryStateAdapter(StateReader, StateWriter):
    """Production memory-scope adapter over ``MemoryManagerService``."""

    def __init__(self, memory_service: MemoryManagerService) -> None:
        if memory_service is None:
            raise ValueError("MemoryManagerService is required")
        self._memory_service = memory_service

    # ------------------------------------------------------------------
    # Key normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(key: str) -> str:
        """Strip the optional ``memory.`` namespace prefix.

        Returns a bare memory id. Accepts both ``memory.<id>`` and ``<id>``.
        """
        if key.startswith(MEMORY_NAMESPACE):
            return key[len(MEMORY_NAMESPACE):]
        return key

    # ------------------------------------------------------------------
    # StateReader
    # ------------------------------------------------------------------

    def read(self, key: str, default: Any = None) -> Any:
        """Return the :class:`Memory` for ``key``, or ``default``."""
        memory_id = self._normalize(key)
        memory = self._memory_service.get_memory(memory_id)
        if memory is None:
            return default
        return memory

    def has(self, key: str) -> bool:
        """Return True when a memory exists for ``key``."""
        memory_id = self._normalize(key)
        return self._memory_service.get_memory(memory_id) is not None

    # ------------------------------------------------------------------
    # StateWriter
    # ------------------------------------------------------------------

    def write(self, key: str, value: Any) -> None:
        """Write a memory for ``key``.

        ``value`` may be a :class:`~atlas.memory.models.memory.Memory`
        instance or a dict with at least ``id``/``memory_id``, ``title``,
        and ``content``. Idempotent: repeated writes of the same id
        overwrite rather than duplicate.
        """
        memory_id = self._normalize(key)
        if isinstance(value, Memory):
            memory = value
        elif isinstance(value, dict):
            memory = self._memory_from_dict(memory_id, value)
        else:
            raise TypeError(
                "MemoryStateAdapter.write expects a Memory or dict, "
                f"got {type(value).__name__}"
            )
        self._memory_service.add_memory(memory)

    def remove(self, key: str) -> bool:
        """Remove the memory for ``key``. Returns True if it existed."""
        memory_id = self._normalize(key)
        return self._memory_service.delete_memory(memory_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _memory_from_dict(memory_id: str, data: dict[str, Any]) -> Memory:
        """Build a :class:`Memory` from an adapter value dict.

        Accepts the ``Memory.to_dict`` shape as well as the applier entry
        shape (``memory_id`` / ``content``). Defaults mirror the Memory
        dataclass defaults so a minimal entry is valid.
        """
        title = data.get("title", memory_id)
        content = data.get("content", "")
        memory_type_val = data.get("memory_type", MemoryType.GENERAL.value)
        importance_val = data.get("importance", MemoryImportance.NORMAL.value)
        kwargs: dict[str, Any] = {
            "id": memory_id,
            "title": str(title),
            "content": str(content),
            "memory_type": MemoryType(memory_type_val),
            "importance": MemoryImportance(importance_val),
            "tags": list(data.get("tags", [])),
            "source": str(data.get("source", "governed_evolution")),
        }
        # Preserve explicit provenance timestamps when supplied; otherwise
        # the Memory dataclass default_factory generates them.
        if data.get("created_at"):
            kwargs["created_at"] = str(data["created_at"])
        if data.get("updated_at"):
            kwargs["updated_at"] = str(data["updated_at"])
        return Memory(**kwargs)
