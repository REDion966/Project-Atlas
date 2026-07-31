"""
Atlas Evolution Knowledge — Repository — Phase 13.5

Bounded in-memory storage for durable evolution knowledge, with
best-effort dual-write persistence through an injected storage adapter.

Follows the same pattern as EvolutionMemory and ExperienceRepository:
  - Memory first; storage writes are best-effort and never break the
    in-memory path.
  - Restore loads persisted knowledge on startup.
  - Append/update semantics: knowledge objects are upserted by key;
    records are appended as bounded deques.
  - Graceful degradation: no storage configured, or storage failure,
    leaves the repository fully functional in memory.

Pure logic. No AI. No autonomous behavior.

Phase 13.5 — Persistent Evolution Knowledge Foundation.
"""

import logging
from collections import deque
from datetime import datetime
from typing import Any

from atlas.evolution.knowledge.models import (
    BottleneckProfile,
    CapabilityEvolution,
    EvolutionKnowledgeSnapshot,
    RecurringOutcomePattern,
    StrategyKnowledge,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serialization helpers (dict ↔ domain model)
# ---------------------------------------------------------------------------


def _dt(value: Any) -> datetime:
    """Parse an ISO timestamp string into a datetime, or return as-is."""
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return datetime.now()
    if isinstance(value, datetime):
        return value
    return datetime.now()


def _pattern_to_dict(pattern: RecurringOutcomePattern) -> dict:
    """Serialize a RecurringOutcomePattern to a JSON-safe dict."""
    return {
        "pattern_id": pattern.pattern_id,
        "area": pattern.area,
        "outcome": pattern.outcome,
        "occurrence_count": pattern.occurrence_count,
        "success_count": pattern.success_count,
        "partial_count": pattern.partial_count,
        "failure_count": pattern.failure_count,
        "inconclusive_count": pattern.inconclusive_count,
        "confidence": pattern.confidence,
        "first_seen": pattern.first_seen.isoformat() if hasattr(pattern.first_seen, "isoformat") else str(pattern.first_seen),
        "last_seen": pattern.last_seen.isoformat() if hasattr(pattern.last_seen, "isoformat") else str(pattern.last_seen),
        "related_ids": list(pattern.related_ids),
        "metadata": dict(pattern.metadata),
    }


def _pattern_from_dict(data: dict) -> RecurringOutcomePattern:
    """Reconstruct a RecurringOutcomePattern from a dict."""
    return RecurringOutcomePattern(
        pattern_id=data.get("pattern_id", ""),
        area=data.get("area", ""),
        outcome=data.get("outcome", "inconclusive"),
        occurrence_count=data.get("occurrence_count", 0),
        success_count=data.get("success_count", 0),
        partial_count=data.get("partial_count", 0),
        failure_count=data.get("failure_count", 0),
        inconclusive_count=data.get("inconclusive_count", 0),
        confidence=data.get("confidence", 0.0),
        first_seen=_dt(data.get("first_seen")),
        last_seen=_dt(data.get("last_seen")),
        related_ids=data.get("related_ids", []),
        metadata=data.get("metadata", {}),
    )


def _strategy_to_dict(strategy: StrategyKnowledge) -> dict:
    """Serialize a StrategyKnowledge to a JSON-safe dict."""
    return {
        "strategy_key": strategy.strategy_key,
        "strategy_name": strategy.strategy_name,
        "success_count": strategy.success_count,
        "failure_count": strategy.failure_count,
        "occurrence_count": strategy.occurrence_count,
        "effectiveness": strategy.effectiveness,
        "confidence": strategy.confidence,
        "avg_regression_risk": strategy.avg_regression_risk,
        "first_seen": strategy.first_seen.isoformat() if hasattr(strategy.first_seen, "isoformat") else str(strategy.first_seen),
        "last_seen": strategy.last_seen.isoformat() if hasattr(strategy.last_seen, "isoformat") else str(strategy.last_seen),
        "related_ids": list(strategy.related_ids),
        "metadata": dict(strategy.metadata),
    }


def _strategy_from_dict(data: dict) -> StrategyKnowledge:
    """Reconstruct a StrategyKnowledge from a dict."""
    return StrategyKnowledge(
        strategy_key=data.get("strategy_key", ""),
        strategy_name=data.get("strategy_name", ""),
        success_count=data.get("success_count", 0),
        failure_count=data.get("failure_count", 0),
        occurrence_count=data.get("occurrence_count", 0),
        effectiveness=data.get("effectiveness", 0.0),
        confidence=data.get("confidence", 0.0),
        avg_regression_risk=data.get("avg_regression_risk", 0.0),
        first_seen=_dt(data.get("first_seen")),
        last_seen=_dt(data.get("last_seen")),
        related_ids=data.get("related_ids", []),
        metadata=data.get("metadata", {}),
    )


def _capability_to_dict(capability: CapabilityEvolution) -> dict:
    """Serialize a CapabilityEvolution to a JSON-safe dict."""
    return {
        "capability_name": capability.capability_name,
        "assessments": list(capability.assessments),
        "observed_count": capability.observed_count,
        "first_seen": capability.first_seen.isoformat() if hasattr(capability.first_seen, "isoformat") else str(capability.first_seen),
        "last_seen": capability.last_seen.isoformat() if hasattr(capability.last_seen, "isoformat") else str(capability.last_seen),
        "related_ids": list(capability.related_ids),
        "metadata": dict(capability.metadata),
    }


def _capability_from_dict(data: dict) -> CapabilityEvolution:
    """Reconstruct a CapabilityEvolution from a dict."""
    return CapabilityEvolution(
        capability_name=data.get("capability_name", ""),
        assessments=data.get("assessments", []),
        observed_count=data.get("observed_count", 0),
        first_seen=_dt(data.get("first_seen")),
        last_seen=_dt(data.get("last_seen")),
        related_ids=data.get("related_ids", []),
        metadata=data.get("metadata", {}),
    )


def _bottleneck_to_dict(bottleneck: BottleneckProfile) -> dict:
    """Serialize a BottleneckProfile to a JSON-safe dict."""
    return {
        "bottleneck_id": bottleneck.bottleneck_id,
        "area": bottleneck.area,
        "description": bottleneck.description,
        "recurrence_count": bottleneck.recurrence_count,
        "first_seen": bottleneck.first_seen.isoformat() if hasattr(bottleneck.first_seen, "isoformat") else str(bottleneck.first_seen),
        "last_seen": bottleneck.last_seen.isoformat() if hasattr(bottleneck.last_seen, "isoformat") else str(bottleneck.last_seen),
        "related_ids": list(bottleneck.related_ids),
        "metadata": dict(bottleneck.metadata),
    }


def _bottleneck_from_dict(data: dict) -> BottleneckProfile:
    """Reconstruct a BottleneckProfile from a dict."""
    return BottleneckProfile(
        bottleneck_id=data.get("bottleneck_id", ""),
        area=data.get("area", ""),
        description=data.get("description", ""),
        recurrence_count=data.get("recurrence_count", 1),
        first_seen=_dt(data.get("first_seen")),
        last_seen=_dt(data.get("last_seen")),
        related_ids=data.get("related_ids", []),
        metadata=data.get("metadata", {}),
    )


def _snapshot_to_dict(snapshot: EvolutionKnowledgeSnapshot) -> dict:
    """Serialize an EvolutionKnowledgeSnapshot to a JSON-safe dict."""
    return {
        "snapshot_id": snapshot.snapshot_id,
        "timestamp": snapshot.timestamp.isoformat() if hasattr(snapshot.timestamp, "isoformat") else str(snapshot.timestamp),
        "pattern_count": snapshot.pattern_count,
        "strategy_count": snapshot.strategy_count,
        "capability_count": snapshot.capability_count,
        "bottleneck_count": snapshot.bottleneck_count,
        "summary_text": snapshot.summary_text,
        "metadata": dict(snapshot.metadata),
    }


def _snapshot_from_dict(data: dict) -> EvolutionKnowledgeSnapshot:
    """Reconstruct an EvolutionKnowledgeSnapshot from a dict."""
    return EvolutionKnowledgeSnapshot(
        snapshot_id=data.get("snapshot_id", ""),
        timestamp=_dt(data.get("timestamp")),
        pattern_count=data.get("pattern_count", 0),
        strategy_count=data.get("strategy_count", 0),
        capability_count=data.get("capability_count", 0),
        bottleneck_count=data.get("bottleneck_count", 0),
        summary_text=data.get("summary_text", ""),
        metadata=data.get("metadata", {}),
    )


class EvolutionKnowledgeRepository:
    """
    Bounded in-memory repository for durable evolution knowledge.

    When a storage adapter is injected, every update dual-writes to
    storage; storage failures are logged and never break the in-memory
    path. restore() loads persisted knowledge on startup.

    Bounds:
      - max_patterns: maximum recurring outcome patterns.
      - max_strategies: maximum strategy knowledge entries.
      - max_capabilities: maximum capability evolutions.
      - max_bottlenecks: maximum bottleneck profiles.
      - max_snapshots: maximum knowledge snapshots retained.
    """

    def __init__(
        self,
        max_patterns: int = 500,
        max_strategies: int = 300,
        max_capabilities: int = 300,
        max_bottlenecks: int = 200,
        max_snapshots: int = 50,
        storage: Any = None,
    ) -> None:
        if any(v <= 0 for v in (
            max_patterns,
            max_strategies,
            max_capabilities,
            max_bottlenecks,
            max_snapshots,
        )):
            raise ValueError("All max sizes must be positive integers")

        self._max_patterns = max_patterns
        self._max_strategies = max_strategies
        self._max_capabilities = max_capabilities
        self._max_bottlenecks = max_bottlenecks
        self._max_snapshots = max_snapshots
        self._storage = storage

        self._patterns: dict[str, RecurringOutcomePattern] = {}
        self._strategies: dict[str, StrategyKnowledge] = {}
        self._capabilities: dict[str, CapabilityEvolution] = {}
        self._bottlenecks: dict[str, BottleneckProfile] = {}
        self._snapshots: deque[EvolutionKnowledgeSnapshot] = deque(maxlen=max_snapshots)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def storage(self) -> Any:
        """Return the injected storage adapter, or None."""
        return self._storage

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def restore(self) -> None:
        """
        Load persisted knowledge from the injected storage adapter.

        If no storage is configured or storage is unavailable, this is
        a no-op. Storage failures are logged and do not crash startup.
        """
        if self._storage is None or not self._storage.is_available():
            return

        try:
            for data in self._storage.load_knowledge_patterns():
                pattern = _pattern_from_dict(data)
                if pattern.pattern_id:
                    self._patterns[pattern.pattern_id] = pattern
        except Exception:
            logger.exception("Failed to restore knowledge patterns from storage")

        try:
            for data in self._storage.load_knowledge_strategies():
                strategy = _strategy_from_dict(data)
                if strategy.strategy_key:
                    self._strategies[strategy.strategy_key] = strategy
        except Exception:
            logger.exception("Failed to restore knowledge strategies from storage")

        try:
            for data in self._storage.load_knowledge_capabilities():
                capability = _capability_from_dict(data)
                if capability.capability_name:
                    self._capabilities[capability.capability_name] = capability
        except Exception:
            logger.exception("Failed to restore knowledge capabilities from storage")

        try:
            for data in self._storage.load_knowledge_bottlenecks():
                bottleneck = _bottleneck_from_dict(data)
                if bottleneck.bottleneck_id:
                    self._bottlenecks[bottleneck.bottleneck_id] = bottleneck
        except Exception:
            logger.exception("Failed to restore knowledge bottlenecks from storage")

        try:
            for data in self._storage.load_knowledge_snapshots():
                snapshot = _snapshot_from_dict(data)
                if snapshot.snapshot_id:
                    self._snapshots.append(snapshot)
        except Exception:
            logger.exception("Failed to restore knowledge snapshots from storage")

    def _try_storage_write(self, method_name: str, data: dict) -> None:
        """Call a storage write method, degrading gracefully on failure."""
        if self._storage is None or not self._storage.is_available():
            return
        try:
            if method_name == "store_knowledge_pattern":
                self._storage.store_knowledge_pattern(data)
            elif method_name == "store_knowledge_strategy":
                self._storage.store_knowledge_strategy(data)
            elif method_name == "store_knowledge_capability":
                self._storage.store_knowledge_capability(data)
            elif method_name == "store_knowledge_bottleneck":
                self._storage.store_knowledge_bottleneck(data)
            elif method_name == "store_knowledge_snapshot":
                self._storage.store_knowledge_snapshot(data)
        except Exception:
            logger.exception(
                "Evolution knowledge storage write failed for %s",
                method_name,
            )

    # ------------------------------------------------------------------
    # Recurring outcome patterns
    # ------------------------------------------------------------------

    def store_pattern(self, pattern: RecurringOutcomePattern) -> None:
        """Store or update a recurring outcome pattern."""
        if (
            len(self._patterns) >= self._max_patterns
            and pattern.pattern_id not in self._patterns
        ):
            return
        self._patterns[pattern.pattern_id] = pattern
        self._try_storage_write("store_knowledge_pattern", _pattern_to_dict(pattern))

    def get_pattern(self, pattern_id: str) -> RecurringOutcomePattern | None:
        """Retrieve a pattern by ID."""
        return self._patterns.get(pattern_id)

    def get_patterns(
        self,
        area: str | None = None,
        n: int | None = None,
    ) -> list[RecurringOutcomePattern]:
        """Return patterns, optionally filtered by canonical area."""
        items = list(self._patterns.values())
        if area is not None:
            items = [p for p in items if p.area == area]
        items.sort(key=lambda p: (p.confidence, p.occurrence_count), reverse=True)
        if n is not None:
            return items[:n]
        return items

    @property
    def pattern_count(self) -> int:
        """Return the number of stored patterns."""
        return len(self._patterns)

    # ------------------------------------------------------------------
    # Strategy knowledge
    # ------------------------------------------------------------------

    def store_strategy(self, strategy: StrategyKnowledge) -> None:
        """Store or update strategy knowledge."""
        if (
            len(self._strategies) >= self._max_strategies
            and strategy.strategy_key not in self._strategies
        ):
            return
        self._strategies[strategy.strategy_key] = strategy
        self._try_storage_write("store_knowledge_strategy", _strategy_to_dict(strategy))

    def get_strategy(self, strategy_key: str) -> StrategyKnowledge | None:
        """Retrieve a strategy by its canonical key."""
        return self._strategies.get(strategy_key)

    def get_strategies(self, n: int | None = None) -> list[StrategyKnowledge]:
        """Return all strategies, most effective first."""
        items = sorted(
            self._strategies.values(),
            key=lambda s: (s.effectiveness, s.confidence),
            reverse=True,
        )
        if n is not None:
            return items[:n]
        return items

    @property
    def strategy_count(self) -> int:
        """Return the number of stored strategies."""
        return len(self._strategies)

    # ------------------------------------------------------------------
    # Capability evolution
    # ------------------------------------------------------------------

    def store_capability(self, capability: CapabilityEvolution) -> None:
        """Store or update a capability evolution."""
        if (
            len(self._capabilities) >= self._max_capabilities
            and capability.capability_name not in self._capabilities
        ):
            return
        self._capabilities[capability.capability_name] = capability
        self._try_storage_write(
            "store_knowledge_capability",
            _capability_to_dict(capability),
        )

    def get_capability(self, capability_name: str) -> CapabilityEvolution | None:
        """Retrieve a capability evolution by name."""
        return self._capabilities.get(capability_name)

    def get_capabilities(self, n: int | None = None) -> list[CapabilityEvolution]:
        """Return all capability evolutions, most recently observed first."""
        items = sorted(
            self._capabilities.values(),
            key=lambda c: c.last_seen,
            reverse=True,
        )
        if n is not None:
            return items[:n]
        return items

    @property
    def capability_count(self) -> int:
        """Return the number of stored capability evolutions."""
        return len(self._capabilities)

    # ------------------------------------------------------------------
    # Bottleneck profiles
    # ------------------------------------------------------------------

    def store_bottleneck(self, bottleneck: BottleneckProfile) -> None:
        """Store or update a bottleneck profile."""
        if (
            len(self._bottlenecks) >= self._max_bottlenecks
            and bottleneck.bottleneck_id not in self._bottlenecks
        ):
            return
        self._bottlenecks[bottleneck.bottleneck_id] = bottleneck
        self._try_storage_write(
            "store_knowledge_bottleneck",
            _bottleneck_to_dict(bottleneck),
        )

    def get_bottleneck(self, bottleneck_id: str) -> BottleneckProfile | None:
        """Retrieve a bottleneck profile by ID."""
        return self._bottlenecks.get(bottleneck_id)

    def get_bottlenecks(self, n: int | None = None) -> list[BottleneckProfile]:
        """Return all bottlenecks, most recurrent first."""
        items = sorted(
            self._bottlenecks.values(),
            key=lambda b: b.recurrence_count,
            reverse=True,
        )
        if n is not None:
            return items[:n]
        return items

    @property
    def bottleneck_count(self) -> int:
        """Return the number of stored bottleneck profiles."""
        return len(self._bottlenecks)

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def store_snapshot(self, snapshot: EvolutionKnowledgeSnapshot) -> None:
        """Store a knowledge snapshot."""
        self._snapshots.append(snapshot)
        self._try_storage_write("store_knowledge_snapshot", _snapshot_to_dict(snapshot))

    def get_latest_snapshot(self) -> EvolutionKnowledgeSnapshot | None:
        """Return the most recent snapshot, or None."""
        if not self._snapshots:
            return None
        return self._snapshots[-1]

    def get_snapshots(self, n: int = 50) -> list[EvolutionKnowledgeSnapshot]:
        """Return the most recent n snapshots, newest first."""
        if n <= 0:
            return []
        return list(reversed(self._snapshots))[:n]

    @property
    def snapshot_count(self) -> int:
        """Return the number of stored snapshots."""
        return len(self._snapshots)

    # ------------------------------------------------------------------
    # Summary and administration
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return a summary of all stored knowledge."""
        return {
            "pattern_count": self.pattern_count,
            "strategy_count": self.strategy_count,
            "capability_count": self.capability_count,
            "bottleneck_count": self.bottleneck_count,
            "snapshot_count": self.snapshot_count,
            "max_patterns": self._max_patterns,
            "max_strategies": self._max_strategies,
            "max_capabilities": self._max_capabilities,
            "max_bottlenecks": self._max_bottlenecks,
            "max_snapshots": self._max_snapshots,
            "storage_available": (
                self._storage is not None and self._storage.is_available()
            ),
        }

    def clear(self) -> None:
        """Clear all stored knowledge in memory."""
        self._patterns.clear()
        self._strategies.clear()
        self._capabilities.clear()
        self._bottlenecks.clear()
        self._snapshots.clear()
