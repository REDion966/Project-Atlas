"""
Atlas Learning Memory

Stores LearningInsight, StrategyPerformance, and FailurePattern instances
with bounded capacity.

Phase 7.3 — Learning Engine.

Persistent Learning: an optional storage adapter (duck-typed; e.g.
``SQLiteEvolutionStorage``) may be injected. Insights are dual-written to
storage on store, and ``restore()`` loads previously persisted insights on
startup. Strategy/failure/recommendation aggregates remain in-memory only —
they are derived from insights and rebuilt from the raw stream on restore.

This is a pure logic component: it never imports infrastructure or sqlite3.
"""

from collections import deque
from datetime import datetime
from typing import Any

from atlas.learning_engine.models import (
    FailurePattern,
    ImprovementRecommendation,
    InsightImportance,
    LearningInsight,
    StrategyPerformance,
)


def _iso(value: Any) -> str:
    """Serialize a datetime to ISO text, fail-soft."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    try:
        return value.isoformat()
    except Exception:
        return str(value) if value else ""


def _dt(value: Any) -> datetime:
    """Parse an ISO timestamp back into a datetime, fail-soft."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return datetime.now()
    return datetime.now()


def _insight_to_dict(insight: LearningInsight) -> dict[str, Any]:
    """Serialize a LearningInsight to a JSON-safe dict."""
    return {
        "insight_id": insight.insight_id,
        "category": insight.category.name,
        "title": insight.title,
        "description": insight.description,
        "importance": insight.importance.name,
        "confidence": insight.confidence,
        "observation_count": insight.observation_count,
        "source_pipeline_ids": list(insight.source_pipeline_ids),
        "reusable": insight.reusable,
        "applicable_areas": list(insight.applicable_areas),
        "created_at": _iso(insight.created_at),
        "last_updated": _iso(insight.last_updated),
        "metadata": dict(insight.metadata),
    }


def _insight_from_dict(data: dict[str, Any]) -> LearningInsight:
    """Reconstruct a LearningInsight from a dict."""
    from atlas.learning_engine.models import LearningCategory

    def _category(value: str) -> Any:
        try:
            return LearningCategory[value]
        except (KeyError, TypeError):
            return LearningCategory.OPTIMIZATION

    def _importance(value: str) -> Any:
        try:
            return InsightImportance[value]
        except (KeyError, TypeError):
            return InsightImportance.MEDIUM

    return LearningInsight(
        insight_id=data.get("insight_id", ""),
        category=_category(data.get("category", "")),
        title=data.get("title", ""),
        description=data.get("description", ""),
        importance=_importance(data.get("importance", "")),
        confidence=float(data.get("confidence", 0.5)),
        observation_count=int(data.get("observation_count", 1)),
        source_pipeline_ids=list(data.get("source_pipeline_ids", [])),
        reusable=bool(data.get("reusable", True)),
        applicable_areas=list(data.get("applicable_areas", [])),
        created_at=_dt(data.get("created_at")),
        last_updated=_dt(data.get("last_updated")),
        metadata=dict(data.get("metadata", {})),
    )


class LearningMemory:
    """
    Bounded in-memory store for learning data.

    Maintains separate bounded queues for insights, strategies,
    failure patterns, and recommendations.

    Persistent Learning: when ``storage`` is injected, insights are dual-written
    to storage on ``store_insights`` and restored via ``restore()``. Storage
    failures are logged and never break the in-memory path.
    """

    def __init__(
        self,
        max_insights: int = 500,
        max_strategies: int = 50,
        max_failures: int = 100,
        max_recommendations: int = 100,
        storage: Any = None,
    ) -> None:
        if any(v <= 0 for v in (max_insights, max_strategies, max_failures, max_recommendations)):
            raise ValueError("All limits must be positive integers")

        self._insights: deque[LearningInsight] = deque(maxlen=max_insights)
        self._strategies: dict[str, StrategyPerformance] = {}
        self._failures: deque[FailurePattern] = deque(maxlen=max_failures)
        self._recommendations: deque[ImprovementRecommendation] = deque(maxlen=max_recommendations)
        self._storage = storage

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def restore(self) -> None:
        """Load previously persisted learning insights from storage.

        No-op when no storage is configured or storage is unavailable.
        Storage failures are logged and never break startup.
        """
        if self._storage is None:
            return
        loader = getattr(self._storage, "load_learning_insights", None)
        if not callable(loader):
            return
        try:
            for data in loader():
                insight = _insight_from_dict(data)
                if insight.insight_id:
                    self._insights.append(insight)
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "Failed to restore learning insights from storage"
            )

    def bind_storage(self, storage: Any) -> None:
        """Attach a storage adapter and restore persisted insights.

        Called once the kernel-owned storage adapter exists (after
        ``_init_tracks``). Fail-soft: a missing or failing storage leaves
        the memory fully functional in-memory.
        """
        self._storage = storage
        self.restore()

    def _try_storage_write(self, insight: LearningInsight) -> None:
        """Dual-write a single insight to storage, degrading gracefully."""
        if self._storage is None:
            return
        writer = getattr(self._storage, "store_learning_insight", None)
        if not callable(writer):
            return
        try:
            writer(_insight_to_dict(insight))
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "Failed to persist learning insight %s", insight.insight_id
            )

    # ------------------------------------------------------------------
    # Insights
    # ------------------------------------------------------------------

    def store_insights(self, insights: list[LearningInsight]) -> None:
        """Store multiple insights, dual-writing each to storage."""
        for insight in insights:
            self._insights.append(insight)
            self._try_storage_write(insight)

    def get_insights(
        self,
        n: int = 50,
        category: Any | None = None,
    ) -> list[LearningInsight]:
        """Return the most recent n insights, optionally filtered."""
        if n <= 0:
            return []

        if category is None:
            return list(reversed(self._insights))[:n]

        filtered = [i for i in reversed(self._insights) if i.category == category]
        return filtered[:n]

    def get_insights_by_importance(
        self,
        importance: InsightImportance,
    ) -> list[LearningInsight]:
        """Return all insights of a given importance level."""
        return [i for i in self._insights if i.importance == importance]

    @property
    def insight_count(self) -> int:
        return len(self._insights)

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------

    def store_strategy(self, strategy: StrategyPerformance) -> None:
        """Store or update a strategy's performance."""
        self._strategies[strategy.strategy_id] = strategy

    def get_strategy(self, strategy_id: str) -> StrategyPerformance | None:
        """Retrieve a strategy by ID."""
        return self._strategies.get(strategy_id)

    def get_strategy_by_name(self, name: str) -> StrategyPerformance | None:
        """Find a strategy by name."""
        for s in self._strategies.values():
            if s.strategy_name == name:
                return s
        return None

    def get_all_strategies(self) -> list[StrategyPerformance]:
        """Return all tracked strategies."""
        return list(self._strategies.values())

    @property
    def strategy_count(self) -> int:
        return len(self._strategies)

    # ------------------------------------------------------------------
    # Failure patterns
    # ------------------------------------------------------------------

    def store_failures(self, patterns: list[FailurePattern]) -> None:
        """Store failure patterns."""
        for pattern in patterns:
            self._failures.append(pattern)

    def get_failures(self, n: int = 20) -> list[FailurePattern]:
        """Return the most recent n failure patterns."""
        if n <= 0:
            return []
        return list(reversed(self._failures))[:n]

    @property
    def failure_count(self) -> int:
        return len(self._failures)

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def store_recommendation(self, rec: ImprovementRecommendation) -> None:
        """Store an improvement recommendation."""
        self._recommendations.append(rec)

    def get_recommendations(self, n: int = 20) -> list[ImprovementRecommendation]:
        """Return the most recent n recommendations."""
        if n <= 0:
            return []
        return list(reversed(self._recommendations))[:n]

    @property
    def recommendation_count(self) -> int:
        return len(self._recommendations)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return a summary of all stored learning data."""
        return {
            "insight_count": self.insight_count,
            "strategy_count": self.strategy_count,
            "failure_count": self.failure_count,
            "recommendation_count": self.recommendation_count,
        }

    def clear(self) -> None:
        """Clear all stored learning data."""
        self._insights.clear()
        self._strategies.clear()
        self._failures.clear()
        self._recommendations.clear()