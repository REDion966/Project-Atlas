"""
Atlas Evolution Knowledge — Automatic Consolidation Pipeline — Phase 13.6

Pure orchestration layer that feeds raw evolution activity into the
EvolutionKnowledgeConsolidator and stores the resulting durable knowledge
in EvolutionKnowledgeRepository.

The pipeline:
  - Records evolution insights as they are produced.
  - Records weaknesses from completed improvement planning.
  - Triggers consolidation and persists durable knowledge.
  - Is idempotent: duplicate records are skipped by the consolidator.
  - Degrades gracefully: missing consolidator, repository, or records are
    ignored.

No infrastructure. No AI. No autonomous decisions.
"""

import logging
from typing import Any

from atlas.evolution.knowledge.consolidator import EvolutionKnowledgeConsolidator
from atlas.evolution.knowledge.repository import EvolutionKnowledgeRepository

logger = logging.getLogger(__name__)


class EvolutionKnowledgePipeline:
    """
    Automatic consolidation pipeline for persistent evolution knowledge.

    Wires raw evolution outputs (insights, weaknesses) into the consolidator
    and persists the resulting durable knowledge objects. All dependencies
    are optional; missing pieces are skipped without error.
    """

    def __init__(
        self,
        consolidator: EvolutionKnowledgeConsolidator | None = None,
        repository: EvolutionKnowledgeRepository | None = None,
    ) -> None:
        """
        Initialise the pipeline.

        Args:
            consolidator: The consolidator that aggregates raw records.
            repository: The repository that stores durable knowledge.
        """
        self._consolidator = consolidator
        self._repository = repository

    @property
    def consolidator(self) -> EvolutionKnowledgeConsolidator | None:
        """Return the injected consolidator, or None."""
        return self._consolidator

    @property
    def repository(self) -> EvolutionKnowledgeRepository | None:
        """Return the injected repository, or None."""
        return self._repository

    def record_insight(self, insight: Any) -> bool:
        """
        Feed a single EvolutionInsight into the consolidator.

        Args:
            insight: An EvolutionInsight instance.

        Returns:
            True if the insight was recorded, False otherwise.
        """
        if self._consolidator is None or insight is None:
            return False
        try:
            return self._consolidator.record_insight(insight)
        except Exception:
            logger.exception("Failed to record insight in knowledge pipeline")
            return False

    def record_insights(self, insights: Any) -> int:
        """
        Feed multiple insights into the consolidator.

        Args:
            insights: An iterable of EvolutionInsight instances.

        Returns:
            The number of newly recorded insights.
        """
        if self._consolidator is None or insights is None:
            return 0
        try:
            return self._consolidator.record_insights(insights)
        except Exception:
            logger.exception("Failed to record insights in knowledge pipeline")
            return 0

    def record_weakness(self, weakness: Any) -> bool:
        """
        Feed a single Weakness into the consolidator.

        Args:
            weakness: A Weakness instance.

        Returns:
            True if the weakness was recorded, False otherwise.
        """
        if self._consolidator is None or weakness is None:
            return False
        try:
            return self._consolidator.record_weakness(weakness)
        except Exception:
            logger.exception("Failed to record weakness in knowledge pipeline")
            return False

    def record_weaknesses(self, weaknesses: Any) -> int:
        """
        Feed multiple weaknesses into the consolidator.

        Args:
            weaknesses: An iterable of Weakness instances.

        Returns:
            The number of newly recorded weaknesses.
        """
        if self._consolidator is None or weaknesses is None:
            return 0
        try:
            return self._consolidator.record_weaknesses(weaknesses)
        except Exception:
            logger.exception("Failed to record weaknesses in knowledge pipeline")
            return 0

    def consolidate(self) -> dict[str, int]:
        """
        Materialize durable knowledge and store it in the repository.

        Returns:
            A dict with counts of stored patterns, strategies, capabilities,
            and bottlenecks.
        """
        counts = {
            "patterns": 0,
            "strategies": 0,
            "capabilities": 0,
            "bottlenecks": 0,
        }
        if self._consolidator is None or self._repository is None:
            return counts

        try:
            materialized = self._consolidator.consolidate()
        except Exception:
            logger.exception("Knowledge consolidation failed")
            return counts

        for pattern in materialized.get("outcome_patterns", []):
            try:
                self._repository.store_pattern(pattern)
                counts["patterns"] += 1
            except Exception:
                logger.exception("Failed to store outcome pattern %s", pattern.pattern_id)

        for strategy in materialized.get("strategies", []):
            try:
                self._repository.store_strategy(strategy)
                counts["strategies"] += 1
            except Exception:
                logger.exception("Failed to store strategy %s", strategy.strategy_key)

        for capability in materialized.get("capabilities", []):
            try:
                self._repository.store_capability(capability)
                counts["capabilities"] += 1
            except Exception:
                logger.exception(
                    "Failed to store capability %s", capability.capability_name
                )

        for bottleneck in materialized.get("bottlenecks", []):
            try:
                self._repository.store_bottleneck(bottleneck)
                counts["bottlenecks"] += 1
            except Exception:
                logger.exception(
                    "Failed to store bottleneck %s", bottleneck.bottleneck_id
                )

        try:
            snapshot = self._consolidator.build_snapshot()
            self._repository.store_snapshot(snapshot)
        except Exception:
            logger.exception("Failed to store knowledge snapshot")

        return counts
