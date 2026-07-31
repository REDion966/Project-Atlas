"""
Atlas EvolutionStorage Interface — Phase 11.3 / 12.3 / 13.5

Abstract interface for persistent evolution storage. Defined in the pure
logic layer so infrastructure adapters in atlas/storage/ can implement it
without leaking infrastructure imports into the domain layer.

No infrastructure imports. No database imports. Pure contract only.

Phase 12.3 — Added store_insight() and load_insights() for evolution
outcome persistence.
Phase 13.5 — Added observation, knowledge pattern, strategy, capability,
bottleneck, and snapshot persistence for the Persistent Evolution
Knowledge layer.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvolutionRestoreResult:
    """Result of restoring persisted evolution state into EvolutionMemory."""

    proposal_count: int = 0
    approval_request_count: int = 0
    record_count: int = 0


class EvolutionStorage(ABC):
    """
    Interface for persistent evolution storage backends.

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
    # Proposals
    # ------------------------------------------------------------------

    @abstractmethod
    def store_proposal(self, data: dict) -> None:
        """Persist a single evolution proposal dictionary."""

    @abstractmethod
    def load_proposals(self) -> list[dict]:
        """Load all stored proposals, oldest first."""

    # ------------------------------------------------------------------
    # Approval requests
    # ------------------------------------------------------------------

    @abstractmethod
    def store_approval_request(self, data: dict) -> None:
        """Persist a single approval request dictionary."""

    @abstractmethod
    def load_approval_requests(self) -> list[dict]:
        """Load all stored approval requests, oldest first."""

    # ------------------------------------------------------------------
    # Evolution records
    # ------------------------------------------------------------------

    @abstractmethod
    def store_record(self, data: dict) -> None:
        """Persist a single evolution record dictionary."""

    @abstractmethod
    def load_records(self) -> list[dict]:
        """Load all stored evolution records, oldest first."""

    # ------------------------------------------------------------------
    # Evolution insights (Phase 12.3+)
    # ------------------------------------------------------------------

    @abstractmethod
    def store_insight(self, data: dict) -> None:
        """Persist a single evolution insight dictionary."""

    @abstractmethod
    def load_insights(
        self,
        proposal_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        Load persisted evolution insights.

        Args:
            proposal_id: Optional filter by proposal_id.
            limit: Maximum number of insights to return.

        Returns:
            A list of insight dictionaries, newest first.
        """

    # ------------------------------------------------------------------
    # Evolution observations (Phase 13.5+)
    # ------------------------------------------------------------------

    @abstractmethod
    def store_observation(self, data: dict) -> None:
        """Persist a single evolution observation dictionary."""

    @abstractmethod
    def load_observations(self) -> list[dict]:
        """Load all stored evolution observations, oldest first."""

    # ------------------------------------------------------------------
    # Evolution knowledge (Phase 13.5+)
    # ------------------------------------------------------------------

    @abstractmethod
    def store_knowledge_pattern(self, data: dict) -> None:
        """Persist a single recurring outcome pattern dictionary."""

    @abstractmethod
    def load_knowledge_patterns(self) -> list[dict]:
        """Load all stored knowledge patterns, oldest first."""

    @abstractmethod
    def store_knowledge_strategy(self, data: dict) -> None:
        """Persist a single strategy knowledge dictionary."""

    @abstractmethod
    def load_knowledge_strategies(self) -> list[dict]:
        """Load all stored knowledge strategies, oldest first."""

    @abstractmethod
    def store_knowledge_capability(self, data: dict) -> None:
        """Persist a single capability evolution dictionary."""

    @abstractmethod
    def load_knowledge_capabilities(self) -> list[dict]:
        """Load all stored knowledge capabilities, oldest first."""

    @abstractmethod
    def store_knowledge_bottleneck(self, data: dict) -> None:
        """Persist a single bottleneck profile dictionary."""

    @abstractmethod
    def load_knowledge_bottlenecks(self) -> list[dict]:
        """Load all stored knowledge bottlenecks, oldest first."""

    @abstractmethod
    def store_knowledge_snapshot(self, data: dict) -> None:
        """Persist a single knowledge snapshot dictionary."""

    @abstractmethod
    def load_knowledge_snapshots(self) -> list[dict]:
        """Load all stored knowledge snapshots, oldest first."""

    # ------------------------------------------------------------------
    # Administration
    # ------------------------------------------------------------------

    @abstractmethod
    def clear_all(self) -> None:
        """Remove all persisted evolution data. Use with caution, mainly for tests."""

    @abstractmethod
    def get_schema_version(self) -> int:
        """Return the currently applied schema version."""
