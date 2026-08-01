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
from atlas.goals.execution_models import (
    GoalAuthorization,
    GoalExecutionRecord,
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
        max_authorizations: int = 200,
        max_execution_records: int = 500,
    ):
        for v in [max_goals, max_candidates, max_opportunities, max_evaluations, max_reports,
                  max_authorizations, max_execution_records]:
            if v <= 0:
                raise ValueError("All max sizes must be positive integers")

        self._goals: dict[str, ImprovementGoal] = {}
        self._max_goals = max_goals
        self._candidates: deque[ImprovementCandidate] = deque(maxlen=max_candidates)
        self._opportunities: deque[ImprovementOpportunity] = deque(maxlen=max_opportunities)
        self._evaluations: deque[GoalEvaluation] = deque(maxlen=max_evaluations)
        self._reports: deque[RecommendationReport] = deque(maxlen=max_reports)

        # --- Phase 15.0: Goal execution stores ---
        self._authorizations: dict[str, GoalAuthorization] = {}
        self._max_authorizations = max_authorizations
        self._execution_records: deque[GoalExecutionRecord] = deque(
            maxlen=max_execution_records,
        )

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
    # Authorizations (Phase 15.0)
    # ------------------------------------------------------------------
    def store_authorization(self, authorization: GoalAuthorization) -> None:
        """Store or replace the authorization for a goal.

        Authorizations are keyed by goal_id so re-authorization of a
        failed goal overwrites the previous ticket deterministically.

        Args:
            authorization: The GoalAuthorization to store.
        """
        if (
            len(self._authorizations) >= self._max_authorizations
            and authorization.goal_id not in self._authorizations
        ):
            return
        self._authorizations[authorization.goal_id] = authorization

    def get_authorization(self, goal_id: str) -> GoalAuthorization | None:
        """Return the stored authorization for a goal, or None."""
        return self._authorizations.get(goal_id)

    def get_all_authorizations(self) -> list[GoalAuthorization]:
        """Return all stored authorizations, oldest first."""
        return list(self._authorizations.values())

    @property
    def authorization_count(self) -> int:
        """Return the number of stored authorizations."""
        return len(self._authorizations)

    # ------------------------------------------------------------------
    # Execution records (Phase 15.0)
    # ------------------------------------------------------------------
    def store_execution_record(self, record: GoalExecutionRecord) -> None:
        """Store a goal execution record.

        Args:
            record: The GoalExecutionRecord to store.
        """
        self._execution_records.append(record)

    def get_execution_records(
        self,
        goal_id: str = "",
        n: int = 50,
    ) -> list[GoalExecutionRecord]:
        """Return the most recent n execution records, newest first.

        Args:
            goal_id: If non-empty, only records for this goal are
                returned.
            n: Maximum number of records to return.

        Returns:
            A list of GoalExecutionRecord instances.
        """
        if n <= 0:
            return []
        if goal_id:
            filtered = [
                r for r in reversed(self._execution_records)
                if r.goal_id == goal_id
            ]
        else:
            filtered = list(reversed(self._execution_records))
        return filtered[:n]

    @property
    def execution_record_count(self) -> int:
        """Return the number of stored execution records."""
        return len(self._execution_records)

    # ------------------------------------------------------------------
    def summary(self) -> dict[str, int]:
        return {
            "goals": len(self._goals),
            "active_goals": len(self.get_active_goals()),
            "candidates": len(self._candidates),
            "opportunities": len(self._opportunities),
            "evaluations": len(self._evaluations),
            "reports": len(self._reports),
            "authorizations": len(self._authorizations),
            "execution_records": len(self._execution_records),
        }

    def clear(self) -> None:
        self._goals.clear()
        self._candidates.clear()
        self._opportunities.clear()
        self._evaluations.clear()
        self._reports.clear()
        self._authorizations.clear()
        self._execution_records.clear()
