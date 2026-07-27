"""
Atlas ExperienceRepository — Phase 9.1

Bounded storage for structured experiences, trend analyses, and tracked
goals. Defaults to in-memory mode. When an ExperienceStorage adapter is
injected, the repository dual-writes to memory and storage; storage writes
are best-effort and never break the in-memory path.

Pure logic. No infrastructure imports.
"""

import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Any

from atlas.experience.models import (
    StructuredExperience,
    TrendAnalysis,
    TrackedGoal,
)
from atlas.experience import serialization
from atlas.experience.storage_interface import ExperienceStorage, RestoreResult


logger = logging.getLogger(__name__)


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
        storage: ExperienceStorage | None = None,
    ):
        for v in (max_experiences, max_analyses, max_tracked_goals):
            if v <= 0:
                raise ValueError("All max sizes must be positive integers")

        self._max_experiences = max_experiences
        self._max_analyses = max_analyses
        self._max_tracked_goals = max_tracked_goals
        self._storage = storage

        self._experiences: deque[StructuredExperience] = deque(maxlen=max_experiences)
        self._analyses: deque[TrendAnalysis] = deque(maxlen=max_analyses)
        self._tracked_goals: dict[str, TrackedGoal] = {}

    # ------------------------------------------------------------------
    # Experiences
    # ------------------------------------------------------------------

    def store_experience(self, experience: StructuredExperience) -> None:
        """Store a structured experience. Memory first; storage is best-effort."""
        self._experiences.append(experience)
        self._try_storage_write(
            "store_experience",
            serialization.experience_to_dict(experience),
        )

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
        """Store a trend analysis. Memory first; storage is best-effort."""
        self._analyses.append(analysis)
        self._try_storage_write(
            "store_analysis",
            serialization.analysis_to_dict(analysis),
        )

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
        """Store or update a tracked goal. Memory first; storage is best-effort."""
        if len(self._tracked_goals) >= self._max_tracked_goals and goal.goal_id not in self._tracked_goals:
            return
        self._tracked_goals[goal.goal_id] = goal
        self._try_storage_write(
            "store_tracked_goal",
            serialization.goal_to_dict(goal),
        )

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
            "storage_available": self._storage is not None and self._storage.is_available(),
        }

    def clear(self) -> None:
        """Clear all stored data."""
        self._experiences.clear()
        self._analyses.clear()
        self._tracked_goals.clear()

    # ------------------------------------------------------------------
    # Persistence integration (Phase 9.1)
    # ------------------------------------------------------------------

    def restore(self) -> RestoreResult:
        """
        Load persisted data from the injected storage adapter into memory.

        Returns a RestoreResult with counts and IDs required to seed
        counters in upstream components. If no storage is injected or the
        storage is unavailable, returns an empty result.
        """
        if self._storage is None or not self._storage.is_available():
            return RestoreResult()

        try:
            for exp_dict in self._storage.load_experiences(limit=self._max_experiences):
                self._experiences.append(serialization.dict_to_experience(exp_dict))
        except Exception:
            logger.exception("Failed to restore experiences from storage")

        try:
            analysis_dict = self._storage.load_latest_analysis()
            if analysis_dict is not None:
                self._analyses.append(serialization.dict_to_analysis(analysis_dict))
        except Exception:
            logger.exception("Failed to restore latest analysis from storage")

        try:
            for goal_dict in self._storage.load_tracked_goals():
                if len(self._tracked_goals) >= self._max_tracked_goals:
                    break
                self._tracked_goals[goal_dict["goal_id"]] = serialization.dict_to_goal(goal_dict)
        except Exception:
            logger.exception("Failed to restore tracked goals from storage")

        latest_snapshot: dict | None = None
        try:
            latest_snapshot = self._storage.load_latest_snapshot()
        except Exception:
            logger.exception("Failed to load latest snapshot from storage")

        max_experience_id: int | None = None
        max_snapshot_id: int | None = None
        try:
            max_experience_id = self._storage.get_max_experience_id()
        except Exception:
            logger.exception("Failed to read max experience ID from storage")

        try:
            max_snapshot_id = self._storage.get_max_snapshot_id()
        except Exception:
            logger.exception("Failed to read max snapshot ID from storage")

        return RestoreResult(
            experience_count=self.experience_count,
            analysis_count=len(self._analyses),
            tracked_goal_count=len(self._tracked_goals),
            max_experience_id=max_experience_id,
            max_snapshot_id=max_snapshot_id,
            latest_snapshot=latest_snapshot,
        )

    def persist_snapshot(self, data: dict) -> None:
        """
        Persist a self-model snapshot dictionary.

        Safe to call even when no storage is configured. Storage failures are
        swallowed so the shutdown path never crashes.
        """
        self._try_storage_write("store_snapshot", data)

    def _try_storage_write(self, method_name: str, data: dict) -> None:
        """Call a storage write method, degrading gracefully on failure."""
        if self._storage is None or not self._storage.is_available():
            return
        try:
            write_method = getattr(self._storage, method_name)
            write_method(data)
        except Exception:
            logger.exception("Experience storage write failed for %s", method_name)
