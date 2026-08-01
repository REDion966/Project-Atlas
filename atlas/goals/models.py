"""
Atlas Goal Intelligence Models — Phase 8.3

Immutable data models for the goal intelligence system.
All models are pure dataclasses. No business logic. No infrastructure.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class GoalCategory(Enum):
    """Category of improvement goal."""
    ARCHITECTURE = auto()
    PERFORMANCE = auto()
    RELIABILITY = auto()
    UNDERSTANDING = auto()
    CAPABILITY = auto()
    TOOLING = auto()
    EVOLUTION = auto()


class GoalPriority(Enum):
    """Priority level for improvement goals."""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    DEFERRED = 5


class GoalStatus(Enum):
    """
    Lifecycle status of an improvement goal.

    Phase 15 additions:
      ``FAILED`` — execution was attempted and did not complete. This is
      distinct from ``REJECTED`` (a user declined the goal before
      execution). A failed goal requires explicit re-authorization before
      any retry.
    """
    PROPOSED = auto()
    ANALYZED = auto()
    RECOMMENDED = auto()
    APPROVED = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
    REJECTED = auto()
    DEFERRED = auto()
    FAILED = auto()


@dataclass(frozen=True, slots=True)
class ImprovementGoal:
    """A specific improvement goal Atlas has identified."""
    goal_id: str
    title: str
    description: str
    category: GoalCategory
    priority: GoalPriority = GoalPriority.MEDIUM
    status: GoalStatus = GoalStatus.PROPOSED
    evidence_count: int = 0
    confidence: float = 0.5
    proposed_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class ImprovementCandidate:
    """A raw improvement candidate from evidence analysis."""
    candidate_id: str
    description: str
    category: GoalCategory
    source: str = ""                    # e.g. "learning_engine", "reflection"
    confidence: float = 0.3
    evidence_summary: str = ""
    observed_count: int = 1
    first_observed: datetime = field(default_factory=datetime.now)
    last_observed: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class GoalDependency:
    """A dependency relationship between two goals."""
    source_goal_id: str
    target_goal_id: str
    dependency_type: str = "requires"   # "requires", "conflicts_with", "enhances"
    description: str = ""


@dataclass(frozen=True, slots=True)
class ImprovementOpportunity:
    """A structured improvement opportunity with scored dimensions."""
    opportunity_id: str
    title: str
    description: str
    category: GoalCategory
    source_candidates: list[str] = field(default_factory=list)
    expected_impact: float = 0.5        # 0.0 - 1.0
    difficulty: float = 0.5             # 0.0 (easy) - 1.0 (hard)
    risk: float = 0.5                   # 0.0 (safe) - 1.0 (risky)
    dependency_count: int = 0
    evidence_frequency: int = 1
    confidence: float = 0.3
    strategic_value: float = 0.5        # 0.0 - 1.0
    priority_score: float = 0.0         # Computed by PriorityEngine
    dependencies: list[GoalDependency] = field(default_factory=list)
    evidence_sources: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class GoalEvaluation:
    """Evaluation of a goal's current state and progress."""
    goal_id: str
    status: GoalStatus
    current_progress: str = ""
    blockers: list[str] = field(default_factory=list)
    estimated_effort: str = ""
    evidence_quality: float = 0.5
    last_evaluated: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class RecommendationItem:
    """A single structured engineering recommendation."""
    item_id: str
    problem: str
    evidence: str
    reasoning: str
    expected_benefit: str
    estimated_effort: str
    estimated_risk: str
    required_dependencies: list[str] = field(default_factory=list)
    confidence: float = 0.5
    category: GoalCategory = GoalCategory.UNDERSTANDING


@dataclass(frozen=True, slots=True)
class RecommendationReport:
    """Complete recommendation report from a goal intelligence analysis."""
    report_id: str
    generated_at: datetime = field(default_factory=datetime.now)
    total_opportunities: int = 0
    total_goals: int = 0
    total_recommendations: int = 0
    top_recommendations: list[RecommendationItem] = field(default_factory=list)
    prioritized_opportunities: list[ImprovementOpportunity] = field(default_factory=list)
    blocked_goals: list[GoalEvaluation] = field(default_factory=list)
    summary: str = ""
