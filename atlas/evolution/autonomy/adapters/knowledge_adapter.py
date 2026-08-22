"""Production ``StateReader`` / ``StateWriter`` adapter for the KNOWLEDGE scope.

Wraps the real :class:`~atlas.knowledge.knowledge_manager.KnowledgeManager`
and implements the Phase 16 protocols from
:mod:`atlas.evolution.autonomy.applier`.

Namespace (deterministic): ``knowledge.<entry_id>`` where ``entry_id`` is
the knowledge entry title (the only stable identifier the current
``KnowledgeBase`` exposes). The bare form ``<entry_id>`` is also accepted
for applier compatibility.

Read semantics: exact title match; ``read`` returns the matching
:class:`~atlas.knowledge.knowledge_entry.KnowledgeEntry` or ``default``.

Write semantics / idempotency: the underlying ``KnowledgeBase.add``
appends to an in-memory flat list and has no idempotency of its own, so the
adapter de-dupes at the adapter level: a write whose title already exists
is a deterministic no-op. This keeps repeated governed applications from
duplicating state without inventing a new persistence layer.

Remove semantics: the current ``KnowledgeManager`` exposes no delete API,
so removal is intentionally unsupported and fails closed with
:class:`StateRemoveUnsupportedError`. This limitation is documented rather
than faked.

Pure adapter layer: no governance, no AI, no async, no new persistence.
"""

from __future__ import annotations

from typing import Any

from atlas.evolution.autonomy.applier import StateReader, StateWriter
from atlas.knowledge.knowledge_entry import KnowledgeEntry
from atlas.knowledge.knowledge_manager import KnowledgeManager

#: Deterministic namespace prefix for KNOWLEDGE-scope state keys.
KNOWLEDGE_NAMESPACE = "knowledge."


class StateRemoveUnsupportedError(NotImplementedError):
    """Raised when a scope's underlying service cannot safely remove state."""


class KnowledgeStateAdapter(StateReader, StateWriter):
    """Production knowledge-scope adapter over ``KnowledgeManager``.

    The adapter is read/write for entries and fails closed on ``remove``
    because the underlying knowledge base has no delete API.
    """

    def __init__(self, knowledge_manager: KnowledgeManager) -> None:
        if knowledge_manager is None:
            raise ValueError("KnowledgeManager is required")
        self._knowledge_manager = knowledge_manager

    # ------------------------------------------------------------------
    # Key normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(key: str) -> str:
        """Strip the optional ``knowledge.`` namespace prefix.

        Returns the entry title key. Accepts both ``knowledge.<title>``
        and ``<title>``.
        """
        if key.startswith(KNOWLEDGE_NAMESPACE):
            return key[len(KNOWLEDGE_NAMESPACE):]
        return key

    @staticmethod
    def _key_of(entry: KnowledgeEntry) -> str:
        """Return the deterministic key for an entry (its title)."""
        return entry.title

    # ------------------------------------------------------------------
    # StateReader
    # ------------------------------------------------------------------

    def read(self, key: str, default: Any = None) -> Any:
        """Return the :class:`KnowledgeEntry` whose title matches ``key``."""
        target = self._normalize(key)
        for entry in self._knowledge_manager.base.all():
            if entry.title == target:
                return entry
        return default

    def has(self, key: str) -> bool:
        """Return True when an entry with title ``key`` exists."""
        target = self._normalize(key)
        return any(entry.title == target for entry in self._knowledge_manager.base.all())

    # ------------------------------------------------------------------
    # StateWriter
    # ------------------------------------------------------------------

    def write(self, key: str, value: Any) -> None:
        """Write a knowledge entry for ``key`` (its title).

        ``value`` may be a :class:`~atlas.knowledge.knowledge_entry.KnowledgeEntry`
        or a dict with ``title``, ``content``, ``source``.

        Idempotency: if an entry with the same title already exists, the
        write is a deterministic no-op (the underlying flat-list append is
        not idempotent, so the adapter enforces the contract instead).
        """
        title = self._normalize(key)
        entry = self._as_entry(title, value)
        if self.has(title):
            return
        self._knowledge_manager.remember(
            title=entry.title,
            content=entry.content,
            source=entry.source,
        )

    def remove(self, key: str) -> bool:
        """Fail closed: the underlying knowledge service has no delete API.

        Raises :class:`StateRemoveUnsupportedError` rather than faking or
        partially removing state.
        """
        raise StateRemoveUnsupportedError(
            "KnowledgeManager exposes no delete API; knowledge removal is "
            "unsupported by the production adapter (fail closed)."
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _as_entry(title: str, value: Any) -> KnowledgeEntry:
        """Build a :class:`KnowledgeEntry` from a dict or an entry."""
        if isinstance(value, KnowledgeEntry):
            return value
        if isinstance(value, dict):
            return KnowledgeEntry(
                title=str(value.get("title", title)),
                content=str(value.get("content", "")),
                source=str(value.get("source", "governed_evolution")),
            )
        raise TypeError(
            "KnowledgeStateAdapter.write expects a KnowledgeEntry or dict, "
            f"got {type(value).__name__}"
        )
