"""
Atlas UnderstandingStorage Interface — Phase 9.2b

Abstract interface for persistent understanding storage. Defined in the pure
logic layer (`atlas/understanding/`) so infrastructure adapters in
`atlas/storage/` can implement it without leaking infrastructure imports
into the domain layer.

No infrastructure imports. No database imports. Pure contract only.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class UnderstandingRestoreResult:
    """Result of restoring persisted understanding state into UnderstandingEngine."""

    concept_count: int = 0
    relationship_count: int = 0
    pattern_count: int = 0
    insight_count: int = 0
    signal_count: int = 0
    max_insight_id: int | None = None


class UnderstandingStorage(ABC):
    """
    Interface for persistent understanding storage backends.

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
    # Concepts
    # ------------------------------------------------------------------

    @abstractmethod
    def store_concepts(self, concepts: list[dict]) -> None:
        """Persist a batch of concept dictionaries."""

    @abstractmethod
    def load_all_concepts(self) -> list[dict]:
        """Load all stored concept dictionaries."""

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------

    @abstractmethod
    def store_relationships(self, relationships: list[dict]) -> None:
        """Persist a batch of relationship dictionaries."""

    @abstractmethod
    def load_all_relationships(self) -> list[dict]:
        """Load all stored relationship dictionaries."""

    # ------------------------------------------------------------------
    # Patterns
    # ------------------------------------------------------------------

    @abstractmethod
    def store_patterns(self, patterns: list[dict]) -> None:
        """Persist a batch of pattern dictionaries."""

    @abstractmethod
    def load_all_patterns(self) -> list[dict]:
        """Load all stored pattern dictionaries."""

    # ------------------------------------------------------------------
    # Insights
    # ------------------------------------------------------------------

    @abstractmethod
    def store_insights(self, insights: list[dict]) -> None:
        """Persist a batch of insight dictionaries."""

    @abstractmethod
    def load_all_insights(self) -> list[dict]:
        """Load all stored insight dictionaries."""

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    @abstractmethod
    def store_signals(self, signals: list[dict]) -> None:
        """Persist a batch of behavioral signal dictionaries."""

    @abstractmethod
    def load_all_signals(self) -> list[dict]:
        """Load all stored behavioral signal dictionaries."""

    # ------------------------------------------------------------------
    # Administration
    # ------------------------------------------------------------------

    @abstractmethod
    def clear_all(self) -> None:
        """Remove all persisted understanding data. Use with caution, mainly for tests."""

    @abstractmethod
    def get_max_insight_id(self) -> int | None:
        """Return the maximum numeric insight ID, or None if empty."""