"""
Atlas Learning Memory

Stores LearningInsight, StrategyPerformance, and FailurePattern instances
with bounded capacity.

Phase 7.3 — Learning Engine.
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


class LearningMemory:
    """
    Bounded in-memory store for learning data.

    Maintains separate bounded queues for insights, strategies,
    failure patterns, and recommendations.

    This is a pure logic component with no infrastructure dependencies.
    """

    def __init__(
        self,
        max_insights: int = 500,
        max_strategies: int = 50,
        max_failures: int = 100,
        max_recommendations: int = 100,
    ) -> None:
        if any(v <= 0 for v in (max_insights, max_strategies, max_failures, max_recommendations)):
            raise ValueError("All limits must be positive integers")

        self._insights: deque[LearningInsight] = deque(maxlen=max_insights)
        self._strategies: dict[str, StrategyPerformance] = {}
        self._failures: deque[FailurePattern] = deque(maxlen=max_failures)
        self._recommendations: deque[ImprovementRecommendation] = deque(maxlen=max_recommendations)

    # ------------------------------------------------------------------
    # Insights
    # ------------------------------------------------------------------

    def store_insights(self, insights: list[LearningInsight]) -> None:
        """Store multiple insights."""
        for insight in insights:
            self._insights.append(insight)

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