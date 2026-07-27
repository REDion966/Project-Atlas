"""
Atlas OutcomeTracker — Phase 9.0

Tracks whether recommendations or goals produced observable outcomes.
Correlates recommendations from GoalIntelligence with later experiences
and evaluates whether they were accepted, ignored, or obsoleted.

Pure logic. No AI. No infrastructure.
"""

from datetime import datetime
from typing import Any

from atlas.experience.models import GoalOutcome, TrackedGoal
from atlas.experience.experience_repository import ExperienceRepository


class OutcomeTracker:
    """
    Tracks goal and recommendation outcomes over time.

    When a recommendation is produced, OutcomeTracker creates a TrackedGoal.
    As new experiences arrive, it evaluates whether the tracked goal appears
    to have been addressed. No autonomous action is taken — outcomes are
    recorded as evidence only.
    """

    def __init__(self, repository: ExperienceRepository | None = None):
        self._repository = repository or ExperienceRepository()

    def track_recommendation(
        self,
        recommendation: Any,
        related_experience_id: str = "",
    ) -> TrackedGoal | None:
        """
        Begin tracking a recommendation produced by GoalIntelligence.

        Args:
            recommendation: A RecommendationItem-like object.
            related_experience_id: The experience that produced this recommendation.

        Returns:
            A new TrackedGoal, or None if recommendation is invalid.
        """
        if recommendation is None:
            return None

        goal_id = getattr(recommendation, "item_id", "")
        if not goal_id:
            return None

        goal = TrackedGoal(
            goal_id=goal_id,
            recommendation_id=goal_id,
            goal_title=getattr(recommendation, "problem", "")[:200],
            proposed_at=datetime.now(),
            outcome=GoalOutcome.PENDING,
            related_experience_ids=[related_experience_id] if related_experience_id else [],
        )
        self._repository.store_tracked_goal(goal)
        return goal

    def evaluate_outcomes(self) -> list[TrackedGoal]:
        """
        Evaluate all pending tracked goals against recent experiences.

        Returns:
            List of updated tracked goals.
        """
        goals = self._repository.get_tracked_goals_by_outcome(GoalOutcome.PENDING)
        updated: list[TrackedGoal] = []

        for goal in goals:
            new_goal = self._evaluate_single_goal(goal)
            self._repository.store_tracked_goal(new_goal)
            updated.append(new_goal)

        return updated

    def _evaluate_single_goal(self, goal: TrackedGoal) -> TrackedGoal:
        """Evaluate a single pending goal against recent experiences."""
        recent = self._repository.get_experiences(n=100)

        # Filter to experiences after this goal was proposed
        after_proposal = [e for e in recent if e.timestamp >= goal.proposed_at]

        if not after_proposal:
            return goal

        # Heuristic: if goal-related keywords appear in later experiences, mark accepted
        title_lower = goal.goal_title.lower()
        keywords = [w for w in title_lower.split() if len(w) > 4]

        matches = 0
        for exp in after_proposal:
            exp_text = f"{exp.user_input} {' '.join(exp.concepts_extracted)} {exp.reasoning_goal} {exp.planning_goal}".lower()
            if any(kw in exp_text for kw in keywords[:5]):
                matches += 1

        # Need multiple matches before concluding implemented
        if matches >= 3:
            return self._update_goal(goal, GoalOutcome.IMPLEMENTED,
                                     f"Observed {matches} related experiences after proposal.")

        # If many experiences have passed with no matches, likely ignored
        if len(after_proposal) >= 50 and matches == 0:
            return self._update_goal(goal, GoalOutcome.OBSOLETE,
                                     "No related activity observed in 50 subsequent experiences.")

        return goal

    @staticmethod
    def _update_goal(goal: TrackedGoal, outcome: GoalOutcome, reason: str) -> TrackedGoal:
        return TrackedGoal(
            goal_id=goal.goal_id,
            recommendation_id=goal.recommendation_id,
            goal_title=goal.goal_title,
            proposed_at=goal.proposed_at,
            outcome=outcome,
            outcome_reason=reason,
            related_experience_ids=goal.related_experience_ids,
            last_evaluated=datetime.now(),
        )

    def get_outcome_summary(self) -> dict[str, Any]:
        """Return summary statistics of tracked goal outcomes."""
        goals = self._repository.get_tracked_goals()
        summary: dict[str, int] = {}
        for g in goals:
            key = g.outcome.name.lower()
            summary[key] = summary.get(key, 0) + 1
        return {
            "total": len(goals),
            "by_outcome": summary,
        }
