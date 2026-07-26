"""
Atlas GoalIntelligenceEngine — Phase 8.3

Main orchestrator for goal intelligence.

Pipeline:
  Collect evidence → Analyze opportunities → Merge duplicates →
  Resolve dependencies → Prioritize → Generate recommendation report →
  Store results → Return RecommendationReport

Recommendations only. No autonomous execution. Pure logic.
"""

from datetime import datetime
from typing import Any

from atlas.goals.models import (
    GoalCategory,
    GoalStatus,
    GoalPriority,
    ImprovementGoal,
    ImprovementCandidate,
    ImprovementOpportunity,
    GoalEvaluation,
    RecommendationReport,
)
from atlas.goals.goal_repository import GoalRepository
from atlas.goals.opportunity_analyzer import OpportunityAnalyzer
from atlas.goals.priority_engine import PriorityEngine
from atlas.goals.dependency_resolver import DependencyResolver
from atlas.goals.recommendation_engine import RecommendationEngine


class GoalIntelligenceEngine:
    """
    Orchestrates goal intelligence — evidence analysis → recommendations.

    Dependencies are all optional via injection. Pure logic.
    NEVER modifies Atlas autonomously. Recommendations only.
    """

    def __init__(
        self,
        repository: GoalRepository | None = None,
        analyzer: OpportunityAnalyzer | None = None,
        priority_engine: PriorityEngine | None = None,
        dependency_resolver: DependencyResolver | None = None,
        recommendation_engine: RecommendationEngine | None = None,
    ):
        self._repository = repository or GoalRepository()
        self._analyzer = analyzer or OpportunityAnalyzer()
        self._priority = priority_engine or PriorityEngine()
        self._resolver = dependency_resolver or DependencyResolver()
        self._recommender = recommendation_engine or RecommendationEngine()
        self._analysis_count = 0

    def analyze(
        self,
        evidence: dict[str, Any],
    ) -> RecommendationReport:
        """
        Run the full goal intelligence pipeline.

        Args:
            evidence: Dict with keys like 'learning_insights', 'capability_profiles',
                     'reflection_suggestions', 'identity_summary', 'world_model_summary'.

        Returns:
            A RecommendationReport with prioritized recommendations.
        """
        self._analysis_count += 1

        # 1. Collect evidence → analyze opportunities
        candidates = self._analyzer.analyze_evidence(evidence)
        for c in candidates:
            self._repository.store_candidate(c)

        # 2. Merge into opportunities
        opportunities = self._analyzer.generate_opportunities(candidates)

        # 3. Resolve dependencies
        blocked = self._resolver.find_blocked(opportunities)
        for b in blocked:
            self._repository.store_evaluation(b)
        ordered = self._resolver.resolve_order(opportunities)

        # 4. Prioritize
        prioritized = self._priority.rank(ordered)
        for opp in prioritized:
            self._repository.store_opportunity(opp)

        # 5. Generate recommendation report
        report = self._recommender.generate_report(prioritized, blocked)
        self._repository.store_report(report)

        # 6. Store goals derived from opportunities
        for opp in prioritized[:10]:
            goal = ImprovementGoal(
                goal_id=f"GOAL-{opp.opportunity_id}",
                title=opp.title,
                description=opp.description,
                category=opp.category,
                priority=self._score_to_priority(opp.priority_score),
                status=GoalStatus.RECOMMENDED,
                evidence_count=opp.evidence_frequency,
                confidence=opp.confidence,
            )
            self._repository.store_goal(goal)

        return report

    def get_latest_report(self) -> RecommendationReport | None:
        return self._repository.get_latest_report()

    @property
    def analysis_count(self) -> int:
        return self._analysis_count

    @property
    def repository(self):
        return self._repository

    @staticmethod
    def _score_to_priority(score: float) -> GoalPriority:
        if score >= 0.7:
            return GoalPriority.CRITICAL
        if score >= 0.5:
            return GoalPriority.HIGH
        if score >= 0.3:
            return GoalPriority.MEDIUM
        if score >= 0.1:
            return GoalPriority.LOW
        return GoalPriority.DEFERRED