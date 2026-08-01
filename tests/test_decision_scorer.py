"""
Phase 14.1 — DecisionScorer Tests.

Tests for ``atlas/evolution/decision_scorer.py`` deterministic scoring logic.
All tests use pure function calls with hand-crafted inputs.

No mocks, no infrastructure, no storage.
"""

import pytest

from atlas.evolution.decision_scorer import (
    compute_area_adjustment,
    compute_bottleneck_alert,
    compute_bottleneck_boost,
    compute_capability_signal,
    compute_strategy_recommendation,
)
from atlas.evolution.knowledge.models import (
    BottleneckProfile,
    CapabilityEvolution,
    RecurringOutcomePattern,
    StrategyKnowledge,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_pattern(
    area: str = "runtime",
    outcome: str = "success",
    occurrence_count: int = 5,
    success_count: int = 0,
    failure_count: int = 0,
    confidence: float = 0.5,
) -> RecurringOutcomePattern:
    """Create a RecurringOutcomePattern with sensible defaults."""
    if outcome == "success":
        success_count = success_count or occurrence_count
    elif outcome == "failure":
        failure_count = failure_count or occurrence_count
    return RecurringOutcomePattern(
        pattern_id=f"PAT-{area}-{outcome}",
        area=area,
        outcome=outcome,
        occurrence_count=occurrence_count,
        success_count=success_count,
        failure_count=failure_count,
        confidence=confidence,
    )


def make_bottleneck(
    area: str = "runtime",
    recurrence_count: int = 3,
) -> BottleneckProfile:
    """Create a BottleneckProfile with sensible defaults."""
    return BottleneckProfile(
        bottleneck_id=f"BOT-{area}",
        area=area,
        description="A recurring bottleneck.",
        recurrence_count=recurrence_count,
    )


def make_strategy(
    key: str = "refactor",
    name: str = "Refactor module",
    effectiveness: float = 0.5,
    confidence: float = 0.5,
    occurrence_count: int = 5,
) -> StrategyKnowledge:
    """Create a StrategyKnowledge instance with the given effectiveness."""
    return StrategyKnowledge(
        strategy_key=key,
        strategy_name=name,
        effectiveness=effectiveness,
        confidence=confidence,
        occurrence_count=occurrence_count,
    )


def make_capability(
    name: str = "memory_retrieval",
    assessments: list[float] | None = None,
) -> CapabilityEvolution:
    """Create a CapabilityEvolution with the given assessment series."""
    assessments = assessments or [0.5]
    return CapabilityEvolution(
        capability_name=name,
        assessments=assessments,
        observed_count=len(assessments),
    )


# ---------------------------------------------------------------------------
# Area adjustment tests
# ---------------------------------------------------------------------------


class TestComputeAreaAdjustment:

    def test_no_pattern_returns_neutral(self):
        """A missing pattern yields a neutral adjustment."""
        adjustment = compute_area_adjustment(None)

        assert adjustment.adjustment_factor == 1.0
        assert adjustment.recommendation == "neutral"

    def test_success_pattern_boosts(self):
        """A strong success pattern yields a boost above 1.0."""
        pattern = make_pattern(
            outcome="success",
            occurrence_count=10,
            success_count=10,
            confidence=0.8,
        )

        adjustment = compute_area_adjustment(pattern)

        assert adjustment.adjustment_factor > 1.0
        assert adjustment.recommendation == "prefer"
        assert adjustment.historical_success_rate == 1.0

    def test_failure_pattern_reduces(self):
        """A strong failure pattern yields a penalty below 1.0."""
        pattern = make_pattern(
            outcome="failure",
            occurrence_count=10,
            failure_count=10,
            confidence=0.8,
        )

        adjustment = compute_area_adjustment(pattern)

        assert adjustment.adjustment_factor < 1.0
        assert adjustment.recommendation == "avoid"
        assert adjustment.historical_success_rate == 0.0

    def test_inconclusive_pattern_is_neutral(self):
        """An inconclusive pattern yields no adjustment."""
        pattern = make_pattern(
            outcome="inconclusive",
            occurrence_count=10,
            confidence=0.8,
        )

        adjustment = compute_area_adjustment(pattern)

        assert adjustment.adjustment_factor == 1.0
        assert adjustment.recommendation == "neutral"

    def test_low_confidence_is_neutral(self):
        """A pattern with zero confidence yields a neutral adjustment."""
        pattern = make_pattern(
            outcome="success",
            occurrence_count=10,
            success_count=10,
            confidence=0.0,
        )

        adjustment = compute_area_adjustment(pattern)

        assert adjustment.adjustment_factor == 1.0
        assert adjustment.recommendation == "neutral"

    def test_weak_success_is_caution(self):
        """A weak success boost lands in the 'caution' band."""
        pattern = make_pattern(
            outcome="success",
            occurrence_count=10,
            success_count=10,
            confidence=0.05,
        )

        adjustment = compute_area_adjustment(pattern)

        assert 1.0 < adjustment.adjustment_factor < 1.2
        assert adjustment.recommendation == "caution"

    def test_adjustment_is_bounded_above(self):
        """The boost never exceeds the maximum adjustment factor."""
        pattern = make_pattern(
            outcome="success",
            occurrence_count=100,
            success_count=100,
            confidence=1.0,
        )

        adjustment = compute_area_adjustment(pattern)

        assert adjustment.adjustment_factor == 1.5

    def test_adjustment_is_bounded_below(self):
        """The penalty never goes below the minimum adjustment factor."""
        pattern = make_pattern(
            outcome="failure",
            occurrence_count=100,
            failure_count=100,
            confidence=1.0,
        )

        adjustment = compute_area_adjustment(pattern)

        assert adjustment.adjustment_factor == 0.5

    def test_partial_success_pattern(self):
        """A success pattern with mixed outcomes uses the success rate."""
        pattern = make_pattern(
            outcome="success",
            occurrence_count=10,
            success_count=5,
            failure_count=5,
            confidence=0.8,
        )

        adjustment = compute_area_adjustment(pattern)

        # raw = 1.0 + 0.5 * 0.8 = 1.4, clamped to 1.4
        assert adjustment.adjustment_factor == pytest.approx(1.4)
        assert adjustment.historical_success_rate == 0.5


# ---------------------------------------------------------------------------
# Bottleneck boost tests
# ---------------------------------------------------------------------------


class TestComputeBottleneckBoost:

    def test_3_recurrences_gives_0_1(self):
        """Three recurrences yields approximately a 0.1 boost."""
        bottleneck = make_bottleneck(recurrence_count=3)

        boost = compute_bottleneck_boost(bottleneck)

        assert boost == pytest.approx(0.1, abs=0.001)

    def test_10_recurrences_gives_0_3(self):
        """Ten recurrences yields approximately a 0.3 boost."""
        bottleneck = make_bottleneck(recurrence_count=10)

        boost = compute_bottleneck_boost(bottleneck)

        assert boost == pytest.approx(0.3, abs=0.001)

    def test_boost_capped_at_0_4(self):
        """The boost never exceeds 0.4 regardless of recurrence count."""
        bottleneck = make_bottleneck(recurrence_count=1000)

        boost = compute_bottleneck_boost(bottleneck)

        assert boost == pytest.approx(0.4, abs=0.001)

    def test_1_recurrence_gives_zero(self):
        """A single recurrence yields no boost."""
        bottleneck = make_bottleneck(recurrence_count=1)

        boost = compute_bottleneck_boost(bottleneck)

        assert boost == pytest.approx(0.0, abs=0.001)

    def test_boost_increases_with_recurrence(self):
        """Boost is monotonically increasing with recurrence count."""
        previous = -1.0
        for count in range(1, 21):
            bottleneck = make_bottleneck(recurrence_count=count)
            boost = compute_bottleneck_boost(bottleneck)
            assert boost >= previous
            previous = boost


# ---------------------------------------------------------------------------
# Bottleneck alert tests
# ---------------------------------------------------------------------------


class TestComputeBottleneckAlert:

    def test_alert_carries_source_fields(self):
        """The alert preserves identity and area from the profile."""
        bottleneck = make_bottleneck(area="memory", recurrence_count=10)

        alert = compute_bottleneck_alert(bottleneck)

        assert alert.bottleneck_id == bottleneck.bottleneck_id
        assert alert.area == "memory"
        assert alert.recurrence_count == 10
        assert alert.severity_boost == pytest.approx(0.3, abs=0.001)


# ---------------------------------------------------------------------------
# Strategy recommendation tests
# ---------------------------------------------------------------------------


class TestComputeStrategyRecommendation:

    def test_high_effectiveness_prefer(self):
        """A strong, confident strategy is recommended to prefer."""
        strategy = make_strategy(effectiveness=0.85, confidence=0.5)

        suggestion = compute_strategy_recommendation(strategy)

        assert suggestion.recommendation == "prefer"
        assert suggestion.effectiveness == pytest.approx(0.85)

    def test_low_effectiveness_avoid(self):
        """A weak, confident strategy is recommended to avoid."""
        strategy = make_strategy(effectiveness=0.2, confidence=0.5)

        suggestion = compute_strategy_recommendation(strategy)

        assert suggestion.recommendation == "avoid"

    def test_moderate_effectiveness_neutral(self):
        """A strategy in the middle band receives a neutral recommendation."""
        strategy = make_strategy(effectiveness=0.5, confidence=0.5)

        suggestion = compute_strategy_recommendation(strategy)

        assert suggestion.recommendation == "neutral"

    def test_prefer_requires_confidence(self):
        """High effectiveness with low confidence is not 'prefer'."""
        strategy = make_strategy(effectiveness=1.0, confidence=0.1)

        suggestion = compute_strategy_recommendation(strategy)

        assert suggestion.recommendation == "neutral"

    def test_avoid_requires_confidence(self):
        """Low effectiveness with low confidence is not 'avoid'."""
        strategy = make_strategy(effectiveness=0.0, confidence=0.1)

        suggestion = compute_strategy_recommendation(strategy)

        assert suggestion.recommendation == "neutral"

    def test_exact_prefer_threshold(self):
        """The exact effectiveness threshold yields 'prefer'."""
        strategy = make_strategy(effectiveness=0.7, confidence=0.4)

        suggestion = compute_strategy_recommendation(strategy)

        assert suggestion.recommendation == "prefer"

    def test_exact_avoid_threshold(self):
        """The exact effectiveness threshold yields 'avoid'."""
        strategy = make_strategy(effectiveness=0.3, confidence=0.4)

        suggestion = compute_strategy_recommendation(strategy)

        assert suggestion.recommendation == "avoid"


# ---------------------------------------------------------------------------
# Capability signal tests
# ---------------------------------------------------------------------------


class TestComputeCapabilitySignal:

    def test_improving_high_assessment_defers(self):
        """A strongly-improving capability signals deferral."""
        cap = make_capability(assessments=[0.4, 0.5, 0.6, 0.8])

        signal = compute_capability_signal(cap)

        assert signal.trajectory == "improving"
        assert signal.signal == "defer"

    def test_improving_low_assessment_monitors(self):
        """An improving but still low capability signals monitoring."""
        cap = make_capability(assessments=[0.1, 0.2, 0.3, 0.4])

        signal = compute_capability_signal(cap)

        assert signal.trajectory == "improving"
        assert signal.signal == "monitor"

    def test_declining_intervenes(self):
        """A declining capability signals intervention."""
        cap = make_capability(assessments=[0.8, 0.7, 0.6, 0.5])

        signal = compute_capability_signal(cap)

        assert signal.trajectory == "declining"
        assert signal.signal == "intervene"

    def test_stable_low_intervenes(self):
        """A stable but low capability signals intervention."""
        cap = make_capability(assessments=[0.3, 0.3, 0.3, 0.3])

        signal = compute_capability_signal(cap)

        assert signal.trajectory == "stable"
        assert signal.signal == "intervene"

    def test_stable_high_monitors(self):
        """A stable, strong capability signals monitoring."""
        cap = make_capability(assessments=[0.75, 0.75, 0.75, 0.75])

        signal = compute_capability_signal(cap)

        assert signal.trajectory == "stable"
        assert signal.signal == "monitor"

    def test_single_assessment_is_stable(self):
        """A single assessment has no trajectory and is monitored."""
        cap = make_capability(assessments=[0.2])

        signal = compute_capability_signal(cap)

        assert signal.trajectory == "stable"
        assert signal.signal == "intervene"


# ---------------------------------------------------------------------------
# Determinism and edge cases
# ---------------------------------------------------------------------------


class TestDeterminism:

    def test_area_adjustment_is_deterministic(self):
        """Identical patterns always produce identical adjustments."""
        pattern = make_pattern(
            outcome="success",
            occurrence_count=20,
            success_count=18,
            confidence=0.75,
        )

        results = [compute_area_adjustment(pattern) for _ in range(100)]

        assert all(r == results[0] for r in results)

    def test_bottleneck_boost_is_deterministic(self):
        """Identical bottlenecks always produce identical boosts."""
        bottleneck = make_bottleneck(recurrence_count=7)

        results = [compute_bottleneck_boost(bottleneck) for _ in range(100)]

        assert all(r == results[0] for r in results)

    def test_strategy_recommendation_is_deterministic(self):
        """Identical strategies always produce identical suggestions."""
        strategy = make_strategy(effectiveness=0.6, confidence=0.5)

        results = [compute_strategy_recommendation(strategy) for _ in range(100)]

        assert all(r == results[0] for r in results)

    def test_capability_signal_is_deterministic(self):
        """Identical capabilities always produce identical signals."""
        cap = make_capability(assessments=[0.5, 0.6, 0.7])

        results = [compute_capability_signal(cap) for _ in range(100)]

        assert all(r == results[0] for r in results)


class TestEdgeCases:

    def test_bottleneck_zero_recurrence_treated_as_one(self):
        """A zero recurrence count is treated as one (no boost)."""
        bottleneck = make_bottleneck(recurrence_count=0)

        boost = compute_bottleneck_boost(bottleneck)

        assert boost == pytest.approx(0.0, abs=0.001)

    def test_negative_effectiveness_clamped(self):
        """Negative strategy effectiveness is clamped to 0.0."""
        strategy = make_strategy(effectiveness=-0.5, confidence=1.0)

        suggestion = compute_strategy_recommendation(strategy)

        assert suggestion.effectiveness == pytest.approx(0.0)
        assert suggestion.recommendation == "avoid"

    def test_effectiveness_above_one_clamped(self):
        """Strategy effectiveness above 1.0 is clamped."""
        strategy = make_strategy(effectiveness=1.5, confidence=1.0)

        suggestion = compute_strategy_recommendation(strategy)

        assert suggestion.effectiveness == pytest.approx(1.0)
        assert suggestion.recommendation == "prefer"

    def test_outcome_case_insensitive(self):
        """Outcome matching is case-insensitive."""
        pattern_upper = make_pattern(
            outcome="SUCCESS",
            occurrence_count=10,
            success_count=10,
            confidence=0.8,
        )
        pattern_lower = make_pattern(
            outcome="success",
            occurrence_count=10,
            success_count=10,
            confidence=0.8,
        )

        upper = compute_area_adjustment(pattern_upper)
        lower = compute_area_adjustment(pattern_lower)

        assert upper.adjustment_factor == lower.adjustment_factor
        assert upper.recommendation == lower.recommendation
