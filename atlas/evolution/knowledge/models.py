"""
Atlas Evolution Knowledge — Data Models — Phase 13.5

Pure data models for the persistent evolution knowledge layer.

Evolution knowledge is the consolidated, durable long-term layer above
the raw evolution record streams (observations, weaknesses, proposals,
approvals, executions, insights, goals). It captures what Atlas has
repeatedly tried, what repeatedly worked, what repeatedly failed, and
how capabilities evolved over time.

These models are pure data. No business logic. No infrastructure.
No AI. No autonomous behavior.

Phase 13.5 — Persistent Evolution Knowledge Foundation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class RecurringOutcomePattern:
    """
    A recurring outcome pattern for a normalized evolution area.

    Aggregates repeated proposal outcomes in the same area so future
    planning can see whether similar improvements tend to succeed,
    partially succeed, or fail.

    Attributes:
        pattern_id: Unique identifier for this pattern.
        area: The normalized evolution area (e.g. "runtime", "reasoning").
        outcome: The dominant outcome observed ("success", "partial",
            "failure", "inconclusive").
        occurrence_count: Total number of occurrences aggregated.
        success_count: Number of successes observed.
        partial_count: Number of partial outcomes observed.
        failure_count: Number of failures observed.
        inconclusive_count: Number of inconclusive outcomes observed.
        confidence: Confidence in the pattern (0.0 to 1.0), derived from
            occurrence count and outcome consistency.
        first_seen: When the first occurrence was recorded.
        last_seen: When the last occurrence was recorded.
        related_ids: IDs of the source records (proposals/insights)
            aggregated into this pattern.
        metadata: Optional additional context.
    """

    pattern_id: str
    area: str
    outcome: str = "inconclusive"
    occurrence_count: int = 0
    success_count: int = 0
    partial_count: int = 0
    failure_count: int = 0
    inconclusive_count: int = 0
    confidence: float = 0.0
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    related_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """Return the success rate (0.0 to 1.0) across occurrences."""
        if self.occurrence_count == 0:
            return 0.0
        return self.success_count / self.occurrence_count

    @property
    def failure_rate(self) -> float:
        """Return the failure rate (0.0 to 1.0) across occurrences."""
        if self.occurrence_count == 0:
            return 0.0
        return self.failure_count / self.occurrence_count


@dataclass(frozen=True, slots=True)
class StrategyKnowledge:
    """
    Durable knowledge about a repeated improvement strategy.

    Captures whether a particular approach has repeatedly succeeded or
    failed, so future planning can prefer effective strategies and
    avoid ineffective ones.

    Attributes:
        strategy_key: Canonical normalized key for the strategy.
        strategy_name: Human-readable name of the strategy.
        success_count: Number of times this strategy succeeded.
        failure_count: Number of times this strategy failed.
        occurrence_count: Total number of times this strategy was used.
        effectiveness: Aggregate effectiveness score (0.0 to 1.0).
        confidence: Confidence in the effectiveness assessment (0.0 to 1.0).
        avg_regression_risk: Average regression risk across uses (0.0 to 1.0).
        first_seen: When the strategy was first observed.
        last_seen: When the strategy was last observed.
        related_ids: IDs of the source insights/proposals using this strategy.
        metadata: Optional additional context.
    """

    strategy_key: str
    strategy_name: str = ""
    success_count: int = 0
    failure_count: int = 0
    occurrence_count: int = 0
    effectiveness: float = 0.0
    confidence: float = 0.0
    avg_regression_risk: float = 0.0
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    related_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """Return the success rate (0.0 to 1.0) across occurrences."""
        if self.occurrence_count == 0:
            return 0.0
        return self.success_count / self.occurrence_count

    @property
    def is_effective(self) -> bool:
        """Return True if the strategy is considered effective."""
        return self.success_rate >= 0.7 and self.occurrence_count >= 2


@dataclass(frozen=True, slots=True)
class CapabilityEvolution:
    """
    Durable trajectory of a capability across repeated proposals.

    Tracks how a capability's assessed strength has evolved over time
    so self-model and identity consumers can see long-term trends.

    Attributes:
        capability_name: The normalized capability name.
        assessments: Chronological list of assessment scores (0.0 to 1.0).
        observed_count: Number of assessment observations recorded.
        first_seen: When the capability was first observed.
        last_seen: When the capability was last observed.
        related_ids: IDs of the source insights/snapshots contributing.
        metadata: Optional additional context.
    """

    capability_name: str
    assessments: list[float] = field(default_factory=list)
    observed_count: int = 0
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    related_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def latest_assessment(self) -> float:
        """Return the most recent assessment score, or 0.0 if none."""
        if not self.assessments:
            return 0.0
        return self.assessments[-1]

    @property
    def trajectory_direction(self) -> str:
        """
        Return the direction of the capability trajectory.

        Returns "improving", "declining", or "stable" based on comparing
        the first half of assessments to the second half.
        """
        if len(self.assessments) < 2:
            return "stable"
        mid = len(self.assessments) // 2
        first = sum(self.assessments[:mid]) / mid
        second = sum(self.assessments[mid:]) / (len(self.assessments) - mid)
        if second - first >= 0.1:
            return "improving"
        if second - first <= -0.1:
            return "declining"
        return "stable"


@dataclass(frozen=True, slots=True)
class BottleneckProfile:
    """
    A recurring bottleneck detected across the evolution record stream.

    A bottleneck is an area that has repeatedly re-entered the weakness
    cycle, indicating a persistent constraint on Atlas's own operation.

    Attributes:
        bottleneck_id: Unique identifier for this profile.
        area: The normalized area the bottleneck applies to.
        description: Human-readable description built from occurrences.
        recurrence_count: Number of times this bottleneck recurred.
        first_seen: When it was first observed.
        last_seen: When it was last observed.
        related_ids: IDs of source weaknesses/observations/records.
        metadata: Optional additional context.
    """

    bottleneck_id: str
    area: str
    description: str = ""
    recurrence_count: int = 1
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    related_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvolutionKnowledgeSnapshot:
    """
    A point-in-time summary of the evolution knowledge layer.

    Produced by the consolidator or query layer to give downstream
    consumers (self-model, identity, LLM context) a compact view of
    the durable knowledge Atlas has accumulated about itself.

    Attributes:
        snapshot_id: Unique identifier for this snapshot.
        timestamp: When the snapshot was produced.
        pattern_count: Number of recurring outcome patterns.
        strategy_count: Number of tracked strategies.
        capability_count: Number of tracked capability evolutions.
        bottleneck_count: Number of tracked bottlenecks.
        summary_text: Human-readable summary of the knowledge state.
        metadata: Optional additional context.
    """

    snapshot_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    pattern_count: int = 0
    strategy_count: int = 0
    capability_count: int = 0
    bottleneck_count: int = 0
    summary_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
