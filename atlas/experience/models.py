"""
Atlas Experience Models — Phase 9.0

Pure dataclasses for structured experience recording, trend analysis,
and self-model snapshots. No business logic. No infrastructure.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class ExperienceOutcome(Enum):
    """High-level outcome of a pipeline execution."""
    SUCCESS = auto()
    PARTIAL = auto()
    FAILURE = auto()
    SKIPPED = auto()


class GoalOutcome(Enum):
    """Outcome state for a tracked goal or recommendation."""
    PENDING = auto()
    ACCEPTED = auto()
    REJECTED = auto()
    IMPLEMENTED = auto()
    OBSOLETE = auto()


@dataclass(frozen=True, slots=True)
class StructuredExperience:
    """
    Complete structured record of a single cognitive pipeline execution.
    Captures enough context to detect trends, support self-model updates,
    and feed improvement planning — without storing raw data.
    """

    experience_id: str
    timestamp: datetime
    duration_ms: float
    pipeline_path: list[str]
    outcome: ExperienceOutcome

    # Input context
    user_input: str = ""
    conversation_history_length: int = 0

    # Cognition results
    understanding_insights_count: int = 0
    concepts_extracted: list[str] = field(default_factory=list)
    world_model_entities: int = 0
    world_model_relations: int = 0
    reasoning_goal: str = ""
    reasoning_capabilities: list[str] = field(default_factory=list)
    reasoning_success_count: int = 0
    reasoning_total_count: int = 0
    planning_goal: str = ""
    planning_step_count: int = 0
    planning_validation_errors: int = 0
    tool_name: str = ""
    tool_success: bool = False
    learning_insights_count: int = 0
    reflection_suggestions_count: int = 0
    goal_recommendations_count: int = 0

    # Identity snapshot at time of execution
    identity_version: int = 0
    identity_belief_count: int = 0
    identity_capability_count: int = 0


@dataclass(frozen=True, slots=True)
class TrendAnalysis:
    """Directional analysis of a window of experiences."""

    analysis_id: str
    timestamp: datetime
    window_size: int

    overall_success_rate: float = 0.0
    success_rate_trend: str = "stable"            # improving / stable / declining

    avg_understanding_insights: float = 0.0
    understanding_trend: str = "stable"

    avg_reasoning_success: float = 0.0
    reasoning_trend: str = "stable"

    avg_planning_errors: float = 0.0
    planning_trend: str = "stable"                # improving / stable / declining

    tool_success_rate: float = 0.0
    tool_trend: str = "stable"

    learning_insight_rate: float = 0.0
    learning_trend: str = "stable"

    identity_stability: float = 0.0               # 0.0 = changed a lot, 1.0 = unchanged
    capability_trends: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TrackedGoal:
    """A goal or recommendation whose outcome is being tracked."""

    goal_id: str
    recommendation_id: str = ""
    goal_title: str = ""
    proposed_at: datetime = field(default_factory=datetime.now)
    outcome: GoalOutcome = GoalOutcome.PENDING
    outcome_reason: str = ""
    related_experience_ids: list[str] = field(default_factory=list)
    last_evaluated: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class SelfModelSnapshot:
    """
    Atlas's current assessment of itself at a point in time.
    Produced by SelfModelEngine from accumulated experiences.
    """

    snapshot_id: str
    timestamp: datetime
    total_experiences: int
    overall_success_rate: float
    capability_assessments: dict[str, float]    # capability_name → 0.0-1.0 score
    belief_evidence: dict[str, float]            # belief_statement → evidence_strength
    trend_summary: str
    identity_version: int
    last_trend_analysis: datetime
    recent_improvement_evidence: list[str] = field(default_factory=list)
    persistent_challenges: list[str] = field(default_factory=list)
