"""
Atlas ExperienceStorage Interface — Phase 9.1

Abstract interface for persistent experience storage. Defined in the pure
logic layer (`atlas/experience/`) so infrastructure adapters in
`atlas/storage/` can implement it without leaking infrastructure imports
into the domain layer.

No infrastructure imports. No database imports. Pure contract only.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class RestoreResult:
    """Result of restoring persisted state into an ExperienceRepository."""

    experience_count: int = 0
    analysis_count: int = 0
    tracked_goal_count: int = 0
    max_experience_id: int | None = None
    max_snapshot_id: int | None = None
    latest_snapshot: dict | None = None


class ExperienceStorage(ABC):
    """
    Interface for persistent experience storage backends.

    Implementations own connection lifecycle, serialization to their backing
    store, schema management, and error handling. Callers pass and receive
    plain JSON-safe dictionaries; no domain objects cross this boundary.
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def initialize(self) -> None:
        """Initialize the storage backend (create files, tables, etc.)."""

    @abstractmethod
    def close(self) -> None:
        """Release resources and close the storage backend."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the storage backend is ready for reads and writes."""

    # ------------------------------------------------------------------
    # Experiences
    # ------------------------------------------------------------------

    @abstractmethod
    def store_experience(self, data: dict) -> None:
        """Persist a single experience dictionary."""

    @abstractmethod
    def load_experiences(self, limit: int = 10000) -> list[dict]:
        """Load experiences ordered oldest first, up to limit."""

    @abstractmethod
    def load_experience(self, experience_id: str) -> dict | None:
        """Load a single experience by its ID."""

    @abstractmethod
    def load_experiences_since(self, iso_timestamp: str) -> list[dict]:
        """Load experiences with timestamp >= the given ISO 8601 string."""

    @abstractmethod
    def load_experiences_by_outcome(self, outcome: str, limit: int = 100) -> list[dict]:
        """Load experiences filtered by outcome name."""

    @abstractmethod
    def get_max_experience_id(self) -> int | None:
        """Return the maximum numeric experience ID, or None if empty."""

    # ------------------------------------------------------------------
    # Trend analyses
    # ------------------------------------------------------------------

    @abstractmethod
    def store_analysis(self, data: dict) -> None:
        """Persist a trend analysis dictionary."""

    @abstractmethod
    def load_latest_analysis(self) -> dict | None:
        """Load the most recent trend analysis."""

    @abstractmethod
    def load_analyses(self, limit: int = 50) -> list[dict]:
        """Load trend analyses ordered oldest first, up to limit."""

    # ------------------------------------------------------------------
    # Tracked goals
    # ------------------------------------------------------------------

    @abstractmethod
    def store_tracked_goal(self, data: dict) -> None:
        """Persist a tracked goal dictionary (insert or update)."""

    @abstractmethod
    def load_tracked_goals(self) -> list[dict]:
        """Load all tracked goals."""

    # ------------------------------------------------------------------
    # Self-model snapshots
    # ------------------------------------------------------------------

    @abstractmethod
    def store_snapshot(self, data: dict) -> None:
        """Persist a self-model snapshot dictionary."""

    @abstractmethod
    def load_latest_snapshot(self) -> dict | None:
        """Load the most recent self-model snapshot."""

    @abstractmethod
    def load_snapshots(self, limit: int = 20) -> list[dict]:
        """Load self-model snapshots ordered oldest first, up to limit."""

    @abstractmethod
    def get_max_snapshot_id(self) -> int | None:
        """Return the maximum numeric snapshot ID, or None if empty."""

    # ------------------------------------------------------------------
    # Administration
    # ------------------------------------------------------------------

    @abstractmethod
    def clear_all(self) -> None:
        """Remove all persisted data. Use with caution, mainly for tests."""

    @abstractmethod
    def get_schema_version(self) -> int:
        """Return the currently applied schema version."""
