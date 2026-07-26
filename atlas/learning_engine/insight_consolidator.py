"""
Atlas Insight Consolidator

Merges duplicate learning, strengthens recurring insights, and removes
weak or obsolete learning. Maintains bounded storage.

Phase 7.3 — Learning Engine.
"""

from datetime import datetime
from typing import Any

from atlas.learning_engine.models import (
    InsightImportance,
    LearningInsight,
)


class InsightConsolidator:
    """
    Consolidates learning insights by merging duplicates, strengthening
    recurring patterns, and removing weak or obsolete insights.

    This is a pure logic component with no infrastructure dependencies.
    """

    def __init__(self, max_insights: int = 500) -> None:
        """
        Args:
            max_insights: Maximum number of insights to retain.
        """
        if max_insights <= 0:
            raise ValueError("max_insights must be a positive integer")
        self._max_insights = max_insights

    # ------------------------------------------------------------------
    # Consolidation
    # ------------------------------------------------------------------

    def consolidate(
        self,
        new_insights: list[LearningInsight],
        existing_insights: list[LearningInsight],
    ) -> list[LearningInsight]:
        """
        Merge new insights with existing ones, consolidating duplicates.

        Args:
            new_insights: Newly generated insights.
            existing_insights: Previously stored insights.

        Returns:
            A consolidated list of insights within max_insights limit.
        """
        merged = list(existing_insights)

        for new_insight in new_insights:
            duplicate = self._find_duplicate(new_insight, merged)
            if duplicate is not None:
                self._merge_insight(duplicate, new_insight)
            else:
                merged.append(new_insight)

        # Remove weak insights
        merged = self._remove_weak(merged)

        # Enforce capacity
        if len(merged) > self._max_insights:
            merged.sort(
                key=lambda i: (
                    i.importance.value,
                    i.confidence,
                    i.observation_count,
                ),
                reverse=True,
            )
            merged = merged[:self._max_insights]

        return merged

    def _find_duplicate(
        self,
        insight: LearningInsight,
        existing: list[LearningInsight],
    ) -> LearningInsight | None:
        """
        Find an existing insight that is a duplicate of the given one.

        Duplicates are identified by matching category and title.
        """
        for existing_insight in existing:
            if (existing_insight.category == insight.category
                    and existing_insight.title == insight.title):
                return existing_insight
        return None

    def _merge_insight(
        self,
        existing: LearningInsight,
        new_insight: LearningInsight,
    ) -> None:
        """
        Merge a new insight into an existing duplicate.

        Updates confidence, observation count, and importance.
        """
        existing.observation_count += new_insight.observation_count
        existing.confidence = min(
            existing.confidence + 0.05,
            1.0,
        )
        existing.last_updated = datetime.now()

        # Merge pipeline IDs
        for pid in new_insight.source_pipeline_ids:
            if pid not in existing.source_pipeline_ids:
                existing.source_pipeline_ids.append(pid)

        # Upgrade importance if the new insight is more important
        if new_insight.importance.value < existing.importance.value:
            existing.importance = new_insight.importance

    def _remove_weak(
        self,
        insights: list[LearningInsight],
    ) -> list[LearningInsight]:
        """
        Remove insights that are too weak or obsolete.

        Removes insights with:
        - LOW importance and confidence < 0.3
        - observation_count == 0
        """
        return [
            i for i in insights
            if not (
                i.importance == InsightImportance.LOW
                and i.confidence < 0.3
            )
            and i.observation_count > 0
        ]

    # ------------------------------------------------------------------
    # Strength calculation
    # ------------------------------------------------------------------

    def calculate_strength(
        self,
        insight: LearningInsight,
    ) -> float:
        """
        Calculate the overall strength of an insight (0.0 to 1.0).

        Factors:
        - Importance weight
        - Confidence
        - Observation count (capped at 100)
        """
        importance_weights = {
            InsightImportance.CRITICAL: 1.0,
            InsightImportance.HIGH: 0.8,
            InsightImportance.MEDIUM: 0.5,
            InsightImportance.LOW: 0.3,
        }

        importance_weight = importance_weights.get(insight.importance, 0.5)
        obs_score = min(insight.observation_count / 100.0, 1.0)

        strength = (
            importance_weight * 0.4
            + insight.confidence * 0.4
            + obs_score * 0.2
        )

        return round(min(strength, 1.0), 4)