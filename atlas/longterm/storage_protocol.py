"""Atlas Long-Term Learning — Storage Protocol (Track C, Batch 1).

Pure interfaces for long-term learning persistence. Implemented by
:class:`~atlas.storage.longterm_storage.LongTermSQLiteStorage` (Batch 2+).

Persistence ONLY: episodes, episode events, procedures, consolidation
records. No business logic. No gateway. No kernel.

Mirrors :mod:`atlas.toolchain.storage_protocol` (Track B) and
:mod:`atlas.research.storage_protocol` (Track A).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from atlas.longterm.models import (
    ConsolidationRecord,
    Episode,
    EpisodeEvent,
    Procedure,
)


@runtime_checkable
class LongTermStorage(Protocol):
    """Persistence surface for Track C long-term learning artifacts.

    All methods are fail-closed: if the adapter is unavailable, write
    methods raise ``sqlite3.OperationalError`` and read methods return
    empty lists (or the adapter marks itself unavailable).
    """

    # -- lifecycle ---------------------------------------------------------

    def initialize(self) -> None:
        """Open the connection and apply additive migrations."""
        ...

    def close(self) -> None:
        """Close the connection cleanly."""
        ...

    def is_available(self) -> bool:
        """Return True when the adapter is initialized and usable."""
        ...

    # -- episodes (idempotent upsert by episode_id) ------------------------

    def store_episode(self, episode: Episode) -> None:
        """Store or update an episode."""
        ...

    def load_episodes(self) -> list[Episode]:
        """Load all episodes sorted by started_at."""
        ...

    def load_episode(self, episode_id: str) -> Episode | None:
        """Load a single episode by its ID."""
        ...

    # -- episode events (append-only log) ----------------------------------

    def store_episode_event(self, event: EpisodeEvent) -> None:
        """Append an episode event (duplicates ignored)."""
        ...

    def load_episode_events(self, episode_id: str) -> list[EpisodeEvent]:
        """Load all events for a given episode, ordered by sequence."""
        ...

    # -- procedures (idempotent upsert by procedure_id) --------------------

    def store_procedure(self, procedure: Procedure) -> None:
        """Store or update a procedure."""
        ...

    def load_procedures(self) -> list[Procedure]:
        """Load all procedures sorted by created_at."""
        ...

    def load_procedure(self, procedure_id: str) -> Procedure | None:
        """Load a single procedure by its ID."""
        ...

    # -- consolidation records (append-only log) ---------------------------

    def store_consolidation_record(self, record: ConsolidationRecord) -> None:
        """Append a consolidation record (duplicates ignored)."""
        ...

    def load_consolidation_records(self) -> list[ConsolidationRecord]:
        """Load all consolidation records sorted by created_at."""
        ...