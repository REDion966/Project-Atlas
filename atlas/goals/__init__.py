"""
Atlas Goal Intelligence — Phase 8.3 Self-Directed Improvement Planner

Analyzes accumulated evidence and produces prioritized improvement
recommendations. NEVER modifies Atlas autonomously. Recommendations only.

Pure logic. No AI. No infrastructure. No autonomous execution.
"""

from atlas.goals.models import (
    GoalCategory,
    GoalPriority,
    GoalStatus,
    ImprovementGoal,
    ImprovementCandidate,
    GoalDependency,
    ImprovementOpportunity,
    GoalEvaluation,
    RecommendationReport,
    RecommendationItem,
)
from atlas.goals.goal_repository import GoalRepository
from atlas.goals.opportunity_analyzer import OpportunityAnalyzer
from atlas.goals.priority_engine import PriorityEngine
from atlas.goals.dependency_resolver import DependencyResolver
from atlas.goals.recommendation_engine import RecommendationEngine
from atlas.goals.goal_intelligence_engine import GoalIntelligenceEngine

__all__ = [
    "GoalCategory",
    "GoalPriority",
    "GoalStatus",
    "ImprovementGoal",
    "ImprovementCandidate",
    "GoalDependency",
    "ImprovementOpportunity",
    "GoalEvaluation",
    "RecommendationReport",
    "RecommendationItem",
    "GoalRepository",
    "OpportunityAnalyzer",
    "PriorityEngine",
    "DependencyResolver",
    "RecommendationEngine",
    "GoalIntelligenceEngine",
]