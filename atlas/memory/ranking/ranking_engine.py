"""
Atlas Ranking Engine

Provides sorting and ranking for memory items.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from atlas.memory.models.memory import Memory


class RankingEngine:
    """Sorts and ranks memories."""

    @staticmethod
    def sort_by_importance(
        memories: list[Memory],
    ) -> list[Memory]:
        """Sort memories by importance, highest first."""

        return sorted(
            memories,
            key=lambda m: m.importance.value,
            reverse=True,
        )

    @staticmethod
    def sort_by_recency(
        memories: list[Memory],
    ) -> list[Memory]:
        """Sort memories by creation time, newest first."""

        return sorted(
            memories,
            key=lambda m: datetime.fromisoformat(m.created_at),
            reverse=True,
        )

    @staticmethod
    def sort_by_score(
        memories: list[Memory],
    ) -> list[Memory]:
        """Sort memories by score, highest first.

        Falls back to importance when no score is set.
        """

        def _score(memory: Memory) -> Any:
            return getattr(memory, "score", memory.importance.value)

        return sorted(
            memories,
            key=_score,
            reverse=True,
        )

    @staticmethod
    def rank(
        memories: list[Memory],
    ) -> list[Memory]:
        """Rank memories using score as the default strategy."""

        return RankingEngine.sort_by_score(memories)
