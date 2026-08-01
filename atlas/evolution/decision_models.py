"""
Atlas Evolution — Decision Models — Phase 14.1

Pure data models for adaptive planning and decision intelligence.

These dataclasses carry structured historical evidence from the durable
evolution knowledge layer into planning decisions. They are produced by
``DecisionScorer`` and consumed by ``DecisionIntelligenceEngine`` (Phase
14.2) and downstream planning components.

Pure data. No business logic. No infrastructure. No AI.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class AreaAdjustment:
    """
    Historical adjustment for a single evolution area.

    Attributes:
        area: The normalized evolution area (e.g. "runtime", "reasoning").
        historical_success_rate: Proportion of historical successes in this
            area, from 0.0 to 1.0.
        pattern_confidence: Confidence in the recurring outcome pattern,
            from 0.0 to 1.0.
        occurrence_count: Number of historical occurrences observed.
        adjustment_factor: Multiplier to apply to a priority score.
            1.0 is neutral; values are bounded to [0.5, 1.5].
        recommendation: Planning recommendation derived from the pattern:
            "prefer", "caution", "neutral", or "avoid".
    """

    area: str
    historical_success_rate: float = 0.0
    pattern_confidence: float = 0.0
    occurrence_count: int = 0
    adjustment_factor: float = 1.0
    recommendation: str = "neutral"


@dataclass(frozen=True, slots=True)
class BottleneckAlert:
    """
    A recurring bottleneck that should receive elevated planning attention.

    Attributes:
        bottleneck_id: Unique identifier for the bottleneck profile.
        area: The normalized area the bottleneck applies to.
        recurrence_count: Number of times the bottleneck has recurred.
        description: Human-readable description of the bottleneck.
        severity_boost: Priority boost to apply, derived from recurrence
            count and bounded by the scorer.
    """

    bottleneck_id: str
    area: str
    recurrence_count: int = 1
    description: str = ""
    severity_boost: float = 0.0


@dataclass(frozen=True, slots=True)
class StrategySuggestion:
    """
    Evidence-based guidance for a single improvement strategy.

    Attributes:
        strategy_key: Canonical normalized key for the strategy.
        strategy_name: Human-readable name of the strategy.
        effectiveness: Aggregate effectiveness score, from 0.0 to 1.0.
        confidence: Confidence in the effectiveness assessment, from 0.0
            to 1.0.
        occurrence_count: Number of times the strategy has been observed.
        recommendation: Planning recommendation: "prefer", "avoid", or
            "neutral".
    """

    strategy_key: str
    strategy_name: str = ""
    effectiveness: float = 0.0
    confidence: float = 0.0
    occurrence_count: int = 0
    recommendation: str = "neutral"


@dataclass(frozen=True, slots=True)
class CapabilitySignal:
    """
    A planning signal derived from a capability's trajectory.

    Attributes:
        capability_name: The normalized capability name.
        trajectory: Direction of trajectory: "improving", "declining", or
            "stable".
        latest_assessment: Most recent assessment score, from 0.0 to 1.0.
        signal: Planning signal: "intervene", "monitor", or "defer".
    """

    capability_name: str
    trajectory: str = "stable"
    latest_assessment: float = 0.0
    signal: str = "monitor"


@dataclass(frozen=True, slots=True)
class PlanningContext:
    """
    Structured historical context for adaptive planning decisions.

    Attributes:
        area_adjustments: Per-area historical adjustments indexed by area.
        bottleneck_alerts: Recurring bottlenecks to elevate.
        strategy_suggestions: Per-area ranked strategy suggestions.
        capability_signals: Per-capability planning signals.
        overall_confidence: Aggregate confidence in the context, from 0.0
            to 1.0.
        generated_at: When the context was produced.
        metadata: Optional additional context.
    """

    area_adjustments: dict[str, AreaAdjustment] = field(default_factory=dict)
    bottleneck_alerts: list[BottleneckAlert] = field(default_factory=list)
    strategy_suggestions: dict[str, list[StrategySuggestion]] = field(
        default_factory=dict,
    )
    capability_signals: dict[str, CapabilitySignal] = field(default_factory=dict)
    overall_confidence: float = 0.0
    generated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
