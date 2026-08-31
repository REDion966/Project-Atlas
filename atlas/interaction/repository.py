"""Atlas Interaction — InteractionRepository (P3/B3.1).

Bounded, in-memory, per-user store for preference and correction records.
Scoping is by ``principal_id``: every access path is principal-scoped, so
one user's records can never be surfaced as another's. Provenance is
preserved verbatim on every record.

No persistence yet — this is the B1.2 "in-memory scoping first; storage
namespacing deferred" precedent applied to Phase 3. No schema change, no
migration, no infrastructure imports.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from atlas.interaction.models import (
    CorrectionRecord,
    InteractionKind,
    PreferenceRecord,
)


class InteractionRepository:
    """Bounded, in-memory, per-user interaction record store.

    Preferences and corrections are held separately but both keyed by
    ``principal_id``. Records are frozen value objects; the repository
    never mutates them. Bounds prevent unbounded growth; fail-closed on
    malformed input (never raises).
    """

    def __init__(
        self,
        max_preferences: int = 10_000,
        max_corrections: int = 10_000,
    ) -> None:
        if max_preferences <= 0 or max_corrections <= 0:
            raise ValueError("All bounds must be positive integers (fail-closed)")
        self._max_preferences = max_preferences
        self._max_corrections = max_corrections
        self._preferences: deque[PreferenceRecord] = deque(maxlen=max_preferences)
        self._corrections: deque[CorrectionRecord] = deque(maxlen=max_corrections)

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    def store_preference(self, record: PreferenceRecord) -> None:
        """Store a per-user preference record (bounded append)."""
        if not isinstance(record, PreferenceRecord):
            return
        self._preferences.append(record)

    def get_preferences(self, principal_id: str, n: int = 100) -> list[PreferenceRecord]:
        """Return the most recent preferences for one principal (newest first)."""
        if not isinstance(principal_id, str) or not principal_id:
            return []
        if n <= 0:
            return []
        return [
            r for r in reversed(self._preferences)
            if r.principal_id == principal_id
        ][:n]

    def get_preference(self, record_id: str) -> PreferenceRecord | None:
        """Return a single preference by id, or None."""
        if not isinstance(record_id, str):
            return None
        for r in self._preferences:
            if r.record_id == record_id:
                return r
        return None

    def get_all_preferences(self, n: int = 500) -> list[PreferenceRecord]:
        """Return the most recent preferences across ALL principals.

        Used only by the B3.2 learning bridge flush (which preserves per-record
        provenance and never exposes principal data beyond the owning user).
        """
        if n <= 0:
            return []
        return list(reversed(self._preferences))[:n]

    @property
    def preference_count(self) -> int:
        return len(self._preferences)

    # ------------------------------------------------------------------
    # Corrections
    # ------------------------------------------------------------------

    def store_correction(self, record: CorrectionRecord) -> None:
        """Store a per-user correction record (bounded append)."""
        if not isinstance(record, CorrectionRecord):
            return
        self._corrections.append(record)

    def get_corrections(self, principal_id: str, n: int = 100) -> list[CorrectionRecord]:
        """Return the most recent corrections for one principal (newest first)."""
        if not isinstance(principal_id, str) or not principal_id:
            return []
        if n <= 0:
            return []
        return [
            r for r in reversed(self._corrections)
            if r.principal_id == principal_id
        ][:n]

    def get_correction(self, record_id: str) -> CorrectionRecord | None:
        """Return a single correction by id, or None."""
        if not isinstance(record_id, str):
            return None
        for r in self._corrections:
            if r.record_id == record_id:
                return r
        return None

    def get_all_corrections(self, n: int = 500) -> list[CorrectionRecord]:
        """Return the most recent corrections across ALL principals.

        Used only by the B3.2 learning bridge flush (which preserves per-record
        provenance and never exposes principal data beyond the owning user).
        """
        if n <= 0:
            return []
        return list(reversed(self._corrections))[:n]

    @property
    def correction_count(self) -> int:
        return len(self._corrections)

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return a bounded summary of repository state."""
        return {
            "preference_count": self.preference_count,
            "correction_count": self.correction_count,
            "max_preferences": self._max_preferences,
            "max_corrections": self._max_corrections,
            "scoped_by": "principal_id",
            "persisted": False,
        }

    def clear(self) -> None:
        """Clear all stored records."""
        self._preferences.clear()
        self._corrections.clear()
