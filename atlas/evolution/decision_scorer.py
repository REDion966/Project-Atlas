"""
Atlas Evolution — Decision Scorer — Phase 14.1

Deterministic scoring functions for adaptive planning decisions.

These functions translate consolidated evolution knowledge into structured
planning guidance. They are pure logic: no AI, no storage access, no side
effects, and no internal service instantiation.

Phase 14.1 introduces the scorer only. Phase 14.2 will wrap it in
DecisionIntelligenceEngine and wire it into the scheduler.
"""

import math
from typing import Any

from atlas.evolution.decision_models import (
    AreaAdjustment,
    BottleneckAlert,
    CapabilitySignal,
    StrategySuggestion,
)
from atlas.evolution.knowledge.models import (
    BottleneckProfile,
    CapabilityEvolution,
    RecurringOutcomePattern,
    StrategyKnowledge,
)


# ---------------------------------------------------------------------------
# Tunable thresholds (constants, not runtime configuration)
# ---------------------------------------------------------------------------

# Area adjustment bounds. Historical evidence can at most halve or increase
# a priority score by 50%.
_MIN_ADJUSTMENT_FACTOR = 0.5
_MAX_ADJUSTMENT_FACTOR = 1.5

# Strategy recommendation thresholds.
_PREFER_EFFECTIVENESS_MIN = 0.7
_AVOID_EFFECTIVENESS_MAX = 0.3
_MIN_STRATEGY_CONFIDENCE = 0.4

# Capability signal thresholds.
_CAPABILITY_DEFER_ASSESSMENT_MIN = 0.7
_CAPABILITY_INTERVENE_ASSESSMENT_MAX = 0.4
_CAPABILITY_TRAJECTORY_THRESHOLD = 0.1

# Bottleneck boost curve parameters.
# The curve is calibrated so that 3 recurrences yields a 0.1 boost and
# 10 recurrences yields a 0.3 boost, with a hard ceiling at 0.4.
_BOOST_LOG_SCALE_MIN_COUNT = 3.0
_BOOST_LOG_SCALE_MIN_VALUE = 0.1
_BOOST_LOG_SCALE_MAX_COUNT = 10.0
_BOOST_LOG_SCALE_MAX_VALUE = 0.3
_BOOST_MAX = 0.4

# Pre-computed log-interpolation coefficients for the bottleneck boost curve.
_LOG10_3 = math.log10(_BOOST_LOG_SCALE_MIN_COUNT)
_LOG10_10 = math.log10(_BOOST_LOG_SCALE_MAX_COUNT)
_BOOST_SLOPE = (
    (_BOOST_LOG_SCALE_MAX_VALUE - _BOOST_LOG_SCALE_MIN_VALUE)
    / (_LOG10_10 - _LOG10_3)
)
_BOOST_INTERCEPT = _BOOST_LOG_SCALE_MIN_VALUE - _BOOST_SLOPE * _LOG10_3


# ---------------------------------------------------------------------------
# Public scoring functions
# ---------------------------------------------------------------------------


def compute_area_adjustment(pattern: RecurringOutcomePattern | None) -> AreaAdjustment:
    """
    Compute a priority adjustment from a recurring outcome pattern.

    Rules:
      - No pattern → neutral adjustment (1.0) and "neutral" recommendation.
      - Success pattern → boost proportional to ``success_rate × confidence``.
      - Failure pattern → penalty proportional to ``failure_rate × confidence``.
      - Adjustment factor is bounded to ``[_MIN_ADJUSTMENT_FACTOR,
        _MAX_ADJUSTMENT_FACTOR]``.

    The recommendation is:
      - "prefer" for strong success patterns (boost >= 1.2)
      - "caution" for weak success or inconclusive patterns (boost > 1.0)
      - "neutral" when adjustment is exactly 1.0 or confidence is negligible
      - "avoid" for strong failure patterns (boost <= 0.8)

    Args:
        pattern: A recurring outcome pattern for an area, or None.

    Returns:
        An ``AreaAdjustment`` carrying the computed factor and recommendation.
    """
    if pattern is None:
        return AreaAdjustment(area="", adjustment_factor=1.0, recommendation="neutral")

    area = pattern.area
    success_rate = _clamp(pattern.success_rate, 0.0, 1.0)
    failure_rate = _clamp(pattern.failure_rate, 0.0, 1.0)
    confidence = _clamp(pattern.confidence, 0.0, 1.0)

    outcome = pattern.outcome.lower()

    if outcome == "success" and confidence > 0.0:
        raw = 1.0 + (success_rate * confidence)
    elif outcome == "failure" and confidence > 0.0:
        raw = 1.0 - (failure_rate * confidence)
    else:
        # Inconclusive or no meaningful confidence → neutral.
        return AreaAdjustment(
            area=area,
            historical_success_rate=success_rate,
            pattern_confidence=confidence,
            occurrence_count=pattern.occurrence_count,
            adjustment_factor=1.0,
            recommendation="neutral",
        )

    adjustment = _clamp(raw, _MIN_ADJUSTMENT_FACTOR, _MAX_ADJUSTMENT_FACTOR)
    recommendation = _recommend_area(adjustment)

    return AreaAdjustment(
        area=area,
        historical_success_rate=success_rate,
        pattern_confidence=confidence,
        occurrence_count=pattern.occurrence_count,
        adjustment_factor=adjustment,
        recommendation=recommendation,
    )


def compute_bottleneck_boost(bottleneck: BottleneckProfile) -> float:
    """
    Compute a priority boost from a recurring bottleneck profile.

    Uses logarithmic scaling so that early recurrences matter more than
    later ones:

      - 3 recurrences → approximately 0.1 boost
      - 10 recurrences → approximately 0.3 boost
      - boost is capped at ``_BOOST_MAX`` (0.4)

    Args:
        bottleneck: A bottleneck profile with a positive recurrence count.

    Returns:
        A severity boost in the range [0.0, _BOOST_MAX].
    """
    count = max(1, bottleneck.recurrence_count)
    if count <= _BOOST_LOG_SCALE_MIN_COUNT:
        # Linear interpolation from 0 boost at 1 recurrence to the
        # calibrated minimum at 3 recurrences.
        fraction = (count - 1) / (_BOOST_LOG_SCALE_MIN_COUNT - 1)
        raw = fraction * _BOOST_LOG_SCALE_MIN_VALUE
    else:
        # Logarithmic interpolation calibrated at 3 and 10 recurrences.
        raw = _BOOST_SLOPE * math.log10(count) + _BOOST_INTERCEPT
    return _clamp(raw, 0.0, _BOOST_MAX)


def compute_bottleneck_alert(bottleneck: BottleneckProfile) -> BottleneckAlert:
    """
    Build a ``BottleneckAlert`` from a ``BottleneckProfile``.

    Args:
        bottleneck: The source bottleneck profile.

    Returns:
        A populated ``BottleneckAlert`` with the computed severity boost.
    """
    return BottleneckAlert(
        bottleneck_id=bottleneck.bottleneck_id,
        area=bottleneck.area,
        recurrence_count=bottleneck.recurrence_count,
        description=bottleneck.description,
        severity_boost=compute_bottleneck_boost(bottleneck),
    )


def compute_strategy_recommendation(strategy: StrategyKnowledge) -> StrategySuggestion:
    """
    Build a ``StrategySuggestion`` from consolidated strategy knowledge.

    Rules:
      - effectiveness >= 0.7 and confidence >= 0.4 → "prefer"
      - effectiveness <= 0.3 and confidence >= 0.4 → "avoid"
      - Otherwise → "neutral"

    Args:
        strategy: The consolidated strategy knowledge.

    Returns:
        A ``StrategySuggestion`` with the recommendation field set.
    """
    effectiveness = _clamp(strategy.effectiveness, 0.0, 1.0)
    confidence = _clamp(strategy.confidence, 0.0, 1.0)

    if effectiveness >= _PREFER_EFFECTIVENESS_MIN and confidence >= _MIN_STRATEGY_CONFIDENCE:
        recommendation = "prefer"
    elif effectiveness <= _AVOID_EFFECTIVENESS_MAX and confidence >= _MIN_STRATEGY_CONFIDENCE:
        recommendation = "avoid"
    else:
        recommendation = "neutral"

    return StrategySuggestion(
        strategy_key=strategy.strategy_key,
        strategy_name=strategy.strategy_name,
        effectiveness=effectiveness,
        confidence=confidence,
        occurrence_count=strategy.occurrence_count,
        recommendation=recommendation,
    )


def compute_capability_signal(cap: CapabilityEvolution) -> CapabilitySignal:
    """
    Build a ``CapabilitySignal`` from a capability evolution trajectory.

    Rules:
      - "improving" trajectory + latest assessment >= 0.7 → "defer"
      - "declining" trajectory → "intervene"
      - "stable" trajectory + latest assessment <= 0.4 → "intervene"
      - Otherwise → "monitor"

    Args:
        cap: The capability evolution history.

    Returns:
        A ``CapabilitySignal`` with the derived planning signal.
    """
    trajectory = cap.trajectory_direction
    latest = _clamp(cap.latest_assessment, 0.0, 1.0)

    if trajectory == "improving" and latest >= _CAPABILITY_DEFER_ASSESSMENT_MIN:
        signal = "defer"
    elif trajectory == "declining":
        signal = "intervene"
    elif trajectory == "stable" and latest <= _CAPABILITY_INTERVENE_ASSESSMENT_MAX:
        signal = "intervene"
    else:
        signal = "monitor"

    return CapabilitySignal(
        capability_name=cap.capability_name,
        trajectory=trajectory,
        latest_assessment=latest,
        signal=signal,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clamp(value: Any, minimum: float, maximum: float) -> float:
    """Clamp a numeric value to the inclusive range [minimum, maximum]."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    return min(maximum, max(minimum, numeric))


def _recommend_area(adjustment: float) -> str:
    """Map an adjustment factor to a textual recommendation."""
    if adjustment >= 1.2:
        return "prefer"
    if adjustment > 1.0:
        return "caution"
    if adjustment <= 0.8:
        return "avoid"
    return "neutral"
