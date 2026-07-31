"""
Atlas Evolution Knowledge — Query — Phase 13.5

Read-only query surface over EvolutionKnowledgeRepository.

The query layer is the contract future consumers (ImprovementPlanner,
SelfModelEngine, IdentityEngine, LLM context) code against. It exposes
deterministic, filtered views of the durable evolution knowledge.

Pure logic. No AI. No infrastructure. Read-only — never mutates state.

Phase 13.5 — Persistent Evolution Knowledge Foundation.
"""

from typing import Any

from atlas.evolution.knowledge.models import (
    BottleneckProfile,
    CapabilityEvolution,
    EvolutionKnowledgeSnapshot,
    RecurringOutcomePattern,
    StrategyKnowledge,
)
from atlas.evolution.knowledge.repository import EvolutionKnowledgeRepository


class EvolutionKnowledgeQuery:
    """
    Read-only queries over the evolution knowledge repository.

    All methods are pure queries over the injected repository. A missing
    repository degrades gracefully: queries return empty results.
    """

    def __init__(self, repository: EvolutionKnowledgeRepository | None = None) -> None:
        """
        Initialise the query surface.

        Args:
            repository: An EvolutionKnowledgeRepository instance.
                Optional — if None, all queries return empty results.
        """
        self._repository = repository

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def repository(self) -> EvolutionKnowledgeRepository | None:
        """Return the injected repository, or None."""
        return self._repository

    # ------------------------------------------------------------------
    # Recurring failures / outcomes
    # ------------------------------------------------------------------

    def get_recurring_failures(
        self,
        min_occurrences: int = 3,
        n: int = 20,
    ) -> list[RecurringOutcomePattern]:
        """
        Return recurring outcome patterns classified as failures.

        Filters patterns whose dominant outcome is "failure", with at
        least min_occurrences occurrences. Sorted by confidence.

        Args:
            min_occurrences: Minimum occurrence count to consider.
            n: Maximum number of patterns to return.

        Returns:
            A list of RecurringOutcomePattern instances.
        """
        if self._repository is None:
            return []
        patterns = [
            p for p in self._repository.get_patterns()
            if p.outcome == "failure" and p.occurrence_count >= min_occurrences
        ]
        patterns.sort(key=lambda p: p.confidence, reverse=True)
        return patterns[:n] if n > 0 else patterns

    def get_recurring_successes(
        self,
        min_occurrences: int = 3,
        n: int = 20,
    ) -> list[RecurringOutcomePattern]:
        """
        Return recurring outcome patterns classified as successes.

        Args:
            min_occurrences: Minimum occurrence count to consider.
            n: Maximum number of patterns to return.

        Returns:
            A list of RecurringOutcomePattern instances.
        """
        if self._repository is None:
            return []
        patterns = [
            p for p in self._repository.get_patterns()
            if p.outcome == "success" and p.occurrence_count >= min_occurrences
        ]
        patterns.sort(key=lambda p: p.confidence, reverse=True)
        return patterns[:n] if n > 0 else patterns

    def get_patterns_by_area(
        self,
        area: str,
        n: int = 20,
    ) -> list[RecurringOutcomePattern]:
        """
        Return all recurring outcome patterns for a canonical area.

        Args:
            area: The canonical area name (e.g. "runtime").
            n: Maximum number of patterns to return.

        Returns:
            A list of RecurringOutcomePattern instances.
        """
        if self._repository is None:
            return []
        return self._repository.get_patterns(area=area, n=n)

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------

    def get_effective_strategies(
        self,
        min_effectiveness: float = 0.7,
        n: int = 20,
    ) -> list[StrategyKnowledge]:
        """
        Return strategies with effectiveness at or above the threshold.

        Args:
            min_effectiveness: Minimum effectiveness (0.0 to 1.0).
            n: Maximum number of strategies to return.

        Returns:
            A list of StrategyKnowledge instances, most effective first.
        """
        if self._repository is None:
            return []
        strategies = [
            s for s in self._repository.get_strategies()
            if s.effectiveness >= min_effectiveness
        ]
        return strategies[:n] if n > 0 else strategies

    def get_ineffective_strategies(
        self,
        max_effectiveness: float = 0.4,
        n: int = 20,
    ) -> list[StrategyKnowledge]:
        """
        Return strategies with effectiveness at or below the threshold.

        Args:
            max_effectiveness: Maximum effectiveness (0.0 to 1.0).
            n: Maximum number of strategies to return.

        Returns:
            A list of StrategyKnowledge instances, least effective first.
        """
        if self._repository is None:
            return []
        strategies = [
            s for s in self._repository.get_strategies()
            if s.effectiveness <= max_effectiveness
        ]
        strategies.sort(key=lambda s: s.effectiveness)
        return strategies[:n] if n > 0 else strategies

    def get_strategy(
        self,
        strategy_key: str,
    ) -> StrategyKnowledge | None:
        """Return a single strategy by its canonical key."""
        if self._repository is None:
            return None
        return self._repository.get_strategy(strategy_key)

    # ------------------------------------------------------------------
    # Capability history
    # ------------------------------------------------------------------

    def get_capability_history(
        self,
        capability_name: str,
    ) -> CapabilityEvolution | None:
        """Return the evolution history for a capability."""
        if self._repository is None:
            return None
        return self._repository.get_capability(capability_name)

    def get_capabilities(
        self,
        n: int = 20,
    ) -> list[CapabilityEvolution]:
        """Return capability evolutions, most recently observed first."""
        if self._repository is None:
            return []
        return self._repository.get_capabilities(n=n)

    def get_improving_capabilities(
        self,
        n: int = 20,
    ) -> list[CapabilityEvolution]:
        """
        Return capability evolutions with an improving trajectory.

        Args:
            n: Maximum number to return.

        Returns:
            A list of CapabilityEvolution instances.
        """
        if self._repository is None:
            return []
        return [
            c for c in self._repository.get_capabilities()
            if c.trajectory_direction == "improving"
        ][:n] if n > 0 else []

    def get_declining_capabilities(
        self,
        n: int = 20,
    ) -> list[CapabilityEvolution]:
        """
        Return capability evolutions with a declining trajectory.

        Args:
            n: Maximum number to return.

        Returns:
            A list of CapabilityEvolution instances.
        """
        if self._repository is None:
            return []
        return [
            c for c in self._repository.get_capabilities()
            if c.trajectory_direction == "declining"
        ][:n] if n > 0 else []

    # ------------------------------------------------------------------
    # Bottlenecks
    # ------------------------------------------------------------------

    def get_bottlenecks(
        self,
        min_recurrences: int = 3,
        n: int = 20,
    ) -> list[BottleneckProfile]:
        """
        Return recurring bottleneck profiles.

        Args:
            min_recurrences: Minimum recurrence count to consider.
            n: Maximum number to return.

        Returns:
            A list of BottleneckProfile instances, most recurrent first.
        """
        if self._repository is None:
            return []
        bottlenecks = [
            b for b in self._repository.get_bottlenecks()
            if b.recurrence_count >= min_recurrences
        ]
        return bottlenecks[:n] if n > 0 else bottlenecks

    def get_bottlenecks_by_area(
        self,
        area: str,
        n: int = 20,
    ) -> list[BottleneckProfile]:
        """
        Return bottlenecks for a canonical area.

        Args:
            area: The canonical area name.
            n: Maximum number to return.

        Returns:
            A list of BottleneckProfile instances.
        """
        if self._repository is None:
            return []
        bottlenecks = [
            b for b in self._repository.get_bottlenecks()
            if b.area == area
        ]
        return bottlenecks[:n] if n > 0 else bottlenecks

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def get_latest_snapshot(self) -> EvolutionKnowledgeSnapshot | None:
        """Return the most recent knowledge snapshot, or None."""
        if self._repository is None:
            return None
        return self._repository.get_latest_snapshot()

    def get_snapshots(self, n: int = 10) -> list[EvolutionKnowledgeSnapshot]:
        """Return the most recent n snapshots, newest first."""
        if self._repository is None:
            return []
        return self._repository.get_snapshots(n=n)

    # ------------------------------------------------------------------
    # Overview
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """
        Return a compact overview of the evolution knowledge layer.

        Returns:
            A dict with counts for each knowledge kind.
        """
        if self._repository is None:
            return {
                "pattern_count": 0,
                "strategy_count": 0,
                "capability_count": 0,
                "bottleneck_count": 0,
                "snapshot_count": 0,
                "available": False,
            }
        return {
            "pattern_count": self._repository.pattern_count,
            "strategy_count": self._repository.strategy_count,
            "capability_count": self._repository.capability_count,
            "bottleneck_count": self._repository.bottleneck_count,
            "snapshot_count": self._repository.snapshot_count,
            "available": True,
        }
