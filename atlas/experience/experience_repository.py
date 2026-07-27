"""
Atlas ExperienceRepository — Phase 9.0

Bounded in-memory storage for structured experiences, trend analyses,
and tracked goals. Prepares interface compatibility for future persistence
but does not implement disk I/O.

Pure logic. No infrastructure. No AI.
"""

from collections import deque
from datetime import datetime, timedelta
from typing import Any

from atlas.experience.models import (
    StructuredExperience,
    TrendAnalysis,
    TrackedGoal,
)


class ExperienceRepository:
    """
    Bounded repository for experiences, analyses, and tracked goals.

    Storage is in-memory only. Future persistence will be added by
    injecting a storage adapter into this repository while keeping
    the public interface unchanged.
    """

    def __init__(
        self,
        max_experiences: int = 10_000,
        max_analyses: int = 1_000,
        max_tracked_goals: int = 500,
    ):
        for v in (max_experiences, max_analyses, max_tracked_goals):
            if v <= 0:
                raise ValueError("All max sizes must be positive integers")

        self._max_experiences = max_experiences
        self._max_analyses = max_analyses
        self._max_tracked_goals = max_tracked_goals

        self._experiences: deque[StructuredExperience] = deque(maxlen=max_experiences)
        self._analyses: deque[TrendAnalysis] = deque(maxlen=max_analyses)
        self._tracked_goals: dict[str, TrackedGoal] = {}

    # ------------------------------------------------------------------
    # Experiences
    # ------------------------------------------------------------------

    def store_experience(self, experience: StructuredExperience) -> None:
        """Store a structured experience."""
        self._experiences.append(experience)

    def get_experience(self, experience_id: str) -> StructuredExperience | None:
        """Retrieve a single experience by ID."""
        for exp in self._experiences:
            if exp.experience_id == experience_id:
                return exp
        return None

    def get_experiences(self, n: int = 100) -> list[StructuredExperience]:
        """Return the most recent n experiences (newest first)."""
        if n <= 0:
            return []
        return list(reversed(self._experiences))[:n]

    def get_experiences_since(
        self,
        since: datetime,
    ) -> list[StructuredExperience]:
        """Return all experiences since a given timestamp."""
        return [exp for exp in reversed(self._experiences) if exp.timestamp >= since]

    def get_experiences_by_outcome(
        self,
        outcome: Any,
        n: int = 100,
    ) -> list[StructuredExperience]:
        """Return experiences filtered by outcome."""
        if n <= 0:
            return []
        return [
            exp for exp in reversed(self._experiences)
            if exp.outcome == outcome
        ][:n]

    def get_window(self, size: int) -> list[StructuredExperience]:
        """Return the most recent `size` experiences for trend analysis."""
        if size <= 0:
            return []
        return list(reversed(self._experiences))[:size]

    @property
    def experience_count(self) -> int:
        return len(self._experiences)

    # ------------------------------------------------------------------
    # Trend analyses
    # ------------------------------------------------------------------

    def store_analysis(self, analysis: TrendAnalysis) -> None:
        """Store a trend analysis."""
        self._analyses.append(analysis)

    def get_latest_analysis(self) -> TrendAnalysis | None:
        """Return the most recent trend analysis."""
        if not self._analyses:
            return None
        return self._analyses[-1]

    def get_analyses(self, n: int = 50) -> list[TrendAnalysis]:
        """Return the most recent n trend analyses."""
        if n <= 0:
            return []
        return list(reversed(self._analyses))[:n]

    # ------------------------------------------------------------------
    # Tracked goals
    # ------------------------------------------------------------------

    def store_tracked_goal(self, goal: TrackedGoal) -> None:
        """Store or update a tracked goal."""
        if len(self._tracked_goals) >= self._max_tracked_goals and goal.goal_id not in self._tracked_goals:
            return
        self._tracked_goals[goal.goal_id] = goal

    def get_tracked_goal(self, goal_id: str) -> TrackedGoal | None:
        return self._tracked_goals.get(goal_id)

    def get_tracked_goals(self) -> list[TrackedGoal]:
        return list(self._tracked_goals.values())

    def get_tracked_goals_by_outcome(
        self,
        outcome: Any,
    ) -> list[TrackedGoal]:
        return [g for g in self._tracked_goals.values() if g.outcome == outcome]

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        return {
            "experience_count": self.experience_count,
            "analysis_count": len(self._analyses),
            "tracked_goal_count": len(self._tracked_goals),
            "max_experiences": self._max_experiences,
            "max_analyses": self._max_analyses,
            "max_tracked_goals": self._max_tracked_goals,
        }

    def clear(self) -> None:
        """Clear all stored data."""
        self._experiences.clear()
        self._analyses.clear()
        self._tracked_goals.clear()
