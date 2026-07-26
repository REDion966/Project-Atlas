"""
Atlas Learning Engine — Data Models

Pure data models for the learning engine.
Phase 7.3 — Learning Engine.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class LearningCategory(Enum):
    """Category of learning insight."""

    REASONING_STRATEGY = auto()
    PLANNING_STRATEGY = auto()
    UNDERSTANDING_STRATEGY = auto()
    TOOL_USAGE = auto()
    FAILURE_AVOIDANCE = auto()
    RECOVERED_FAILURE = auto()
    OPTIMIZATION = auto()


class InsightImportance(Enum):
    """Importance level of a learning insight."""

    CRITICAL = auto()
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()


@dataclass(slots=True)
class LearningInsight:
    """
    A structured piece of learning produced by the Learning Engine.

    Attributes:
        insight_id: Unique identifier.
        category: The category of learning.
        title: Concise title.
        description: Detailed description of what was learned.
        importance: Importance level.
        confidence: Confidence in this insight (0.0 to 1.0).
        observation_count: How many observations support this insight.
        source_pipeline_ids: IDs of PipelineResults that contributed.
        reusable: Whether this insight is reusable across contexts.
        applicable_areas: Areas this insight applies to.
        created_at: When this insight was created.
        last_updated: When this insight was last reinforced.
        metadata: Optional additional context.
    """

    insight_id: str
    category: LearningCategory
    title: str
    description: str
    importance: InsightImportance = InsightImportance.MEDIUM
    confidence: float = 0.5
    observation_count: int = 1
    source_pipeline_ids: list[str] = field(default_factory=list)
    reusable: bool = True
    applicable_areas: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StrategyPerformance:
    """
    Performance metrics for a specific reasoning or planning strategy.

    Attributes:
        strategy_id: Unique identifier.
        strategy_name: Human-readable name.
        strategy_type: Type of strategy (reasoning, planning, understanding).
        total_uses: How many times this strategy was used.
        success_count: How many times it succeeded.
        failure_count: How many times it failed.
        avg_confidence: Average confidence score.
        last_used: When this strategy was last used.
        first_used: When this strategy was first used.
    """

    strategy_id: str
    strategy_name: str
    strategy_type: str = "reasoning"
    total_uses: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_confidence: float = 0.0
    last_used: datetime = field(default_factory=datetime.now)
    first_used: datetime = field(default_factory=datetime.now)

    @property
    def success_rate(self) -> float:
        """Return the success rate (0.0 to 1.0)."""
        if self.total_uses == 0:
            return 0.0
        return self.success_count / self.total_uses

    @property
    def is_effective(self) -> bool:
        """Return True if success rate is >= 70%."""
        return self.success_rate >= 0.7


@dataclass(slots=True)
class FailurePattern:
    """
    A detected pattern of failures.

    Attributes:
        pattern_id: Unique identifier.
        description: Description of the failure pattern.
        failure_count: How many times this pattern occurred.
        last_occurrence: When it last occurred.
        common_cause: Identified common cause.
        affected_stages: Which pipeline stages are affected.
        suggested_approach: Suggested way to avoid this failure.
        confidence: Confidence in this pattern (0.0 to 1.0).
    """

    pattern_id: str
    description: str
    failure_count: int = 1
    last_occurrence: datetime = field(default_factory=datetime.now)
    common_cause: str = ""
    affected_stages: list[str] = field(default_factory=list)
    suggested_approach: str = ""
    confidence: float = 0.5


@dataclass(slots=True)
class ImprovementRecommendation:
    """
    A recommendation for improvement derived from learning.

    Attributes:
        recommendation_id: Unique identifier.
        title: Concise title.
        description: Detailed description.
        source_insight_ids: LearningInsight IDs that support this.
        expected_benefit: What would improve.
        target_area: Which area to improve.
        priority: Priority level.
        actionable: Whether this can be acted upon.
        created_at: When this was created.
    """

    recommendation_id: str
    title: str
    description: str
    source_insight_ids: list[str] = field(default_factory=list)
    expected_benefit: str = ""
    target_area: str = ""
    priority: InsightImportance = InsightImportance.MEDIUM
    actionable: bool = True
    created_at: datetime = field(default_factory=datetime.now)