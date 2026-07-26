"""
Atlas GoalRepository — Phase 8.3

Bounded storage for improvement goals, candidates, opportunities,
evaluations, and historical recommendations. Configurable capacities.
Pure logic.
"""

from collections import deque
from typing import Any

from atlas.goals.models import (
    GoalCategory,
    GoalPriority,
    GoalStatus,
    ImprovementCandidate,
    ImprovementGoal,
    ImprovementOpportunity,
    GoalEvaluation,
    RecommendationReport,
)


class GoalRepository:
    """Bounded in-memory storage for goal intelligence data."""

    def __init__(
        self,
        max_goals: int = 200,
        max_candidates: int = 500,
        max_opportunities: int = 200,
        max_evaluations: int = 200,
        max_reports: int = 100,
    ):
        for v in [max_goals, max_candidates, max_opportunities, max_evaluations, max_reports]:
            if v <= 0:
                raise ValueError("All max sizes must be positive integers")

        self._goals: dict[str, ImprovementGoal] = {}
        self._max_goals = max_goals
        self._candidates: deque[ImprovementCandidate] = deque(maxlen=max_candidates)
        self._opportunities: deque[ImprovementOpportunity] = deque(maxlen=max_opportunities)
        self._evaluations: deque[GoalEvaluation] = deque(maxlen=max_evaluations)
        self._reports: deque[RecommendationReport] = deque(maxlen=max_reports)

    # ------------------------------------------------------------------
    # Goals
    # ------------------------------------------------------------------
    def store_goal(self, goal: ImprovementGoal) -> None:
        if len(self._goals) >= self._max_goals and goal.goal_id not in self._goals:
            return
        self._goals[goal.goal_id] = goal

    def get_goal(self, goal_id: str) -> ImprovementGoal | None:
        return self._goals.get(goal_id)

    def get_goals_by_status(self, status: GoalStatus) -> list[ImprovementGoal]:
        return [g for g in self._goals.values() if g.status == status]

    def get_goals_by_category(self, category: GoalCategory) -> list[ImprovementGoal]:
        return [g for g in self._goals.values() if g.category == category]

    def get_active_goals(self) -> list[ImprovementGoal]:
        active_statuses = {GoalStatus.PROPOSED, GoalStatus.ANALYZED, GoalStatus.RECOMMENDED,
                           GoalStatus.APPROVED, GoalStatus.IN_PROGRESS}
        return [g for g in self._goals.values() if g.status in active_statuses]

    def get_all_goals(self) -> list[ImprovementGoal]:
        return list(self._goals.values())

    @property
    def goal_count(self) -> int:
        return len(self._goals)

    # ------------------------------------------------------------------
    # Candidates
    # ------------------------------------------------------------------
    def store_candidate(self, candidate: ImprovementCandidate) -> None:
        self._candidates.append(candidate)

    def get_candidates(self, n: int = 50) -> list[ImprovementCandidate]:
        return list(reversed(self._candidates))[:n]

    def get_candidates_by_source(self, source: str) -> list[ImprovementCandidate]:
        return [c for c in reversed(self._candidates) if c.source == source]

    # ------------------------------------------------------------------
    # Opportunities
    # ------------------------------------------------------------------
    def store_opportunity(self, opp: ImprovementOpportunity) -> None:
        self._opportunities.append(opp)

    def get_opportunities(self, n: int = 50) -> list[ImprovementOpportunity]:
        return list(reversed(self._opportunities))[:n]

    # ------------------------------------------------------------------
    # Evaluations
    # ------------------------------------------------------------------
    def store_evaluation(self, evaluation: GoalEvaluation) -> None:
        self._evaluations.append(evaluation)

    def get_evaluations(self, n: int = 20) -> list[GoalEvaluation]:
        return list(reversed(self._evaluations))[:n]

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------
    def store_report(self, report: RecommendationReport) -> None:
        self._reports.append(report)

    def get_latest_report(self) -> RecommendationReport | None:
        items = list(reversed(self._reports))
        return items[0] if items else None

    def get_reports(self, n: int = 10) -> list[RecommendationReport]:
        return list(reversed(self._reports))[:n]

    # ------------------------------------------------------------------
    def summary(self) -> dict[str, int]:
        return {
            "goals": len(self._goals),
            "active_goals": len(self.get_active_goals()),
            "candidates": len(self._candidates),
            "opportunities": len(self._opportunities),
            "evaluations": len(self._evaluations),
            "reports": len(self._reports),
        }

    def clear(self) -> None:
        self._goals.clear()
        self._candidates.clear()
        self._opportunities.clear()
        self._evaluations.clear()
        self._reports.clear()