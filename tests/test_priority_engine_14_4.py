"""
Phase 14.4 — PriorityEngine Historical Evidence Tests.

Verifies the optional ``planning_context`` support added to
``atlas/goals/priority_engine.py``:

  - Legacy behavior (planning_context=None) is byte-for-byte identical to
    the original Phase 8.3 implementation.
  - A PlanningContext adjusts scores via AreaAdjustment.adjustment_factor
    and BottleneckAlert.severity_boost.
  - Adjustment factors and bottleneck boosts remain bounded.
  - Deterministic and backward compatible.

Pure logic tests. No storage, no AI, no infrastructure.
"""

import pytest

from atlas.evolution.decision_models import (
    AreaAdjustment,
    BottleneckAlert,
    PlanningContext,
)
from atlas.goals.models import GoalCategory, ImprovementOpportunity
from atlas.goals.priority_engine import PriorityEngine, WEIGHTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_opportunity(
    opp_id: str = "OPP-1",
    category: GoalCategory = GoalCategory.PERFORMANCE,
) -> ImprovementOpportunity:
    """Create a deterministic improvement opportunity."""
    return ImprovementOpportunity(
        opportunity_id=opp_id,
        title="Improve performance",
        description="A test opportunity.",
        category=category,
        expected_impact=0.9,
        difficulty=0.1,
        risk=0.1,
        dependency_count=0,
        evidence_frequency=10,
        confidence=0.8,
        strategic_value=0.8,
    )


def legacy_score(opportunity: ImprovementOpportunity) -> float:
    """Recompute the original Phase 8.3 score formula directly."""
    norm_frequency = min(1.0, opportunity.evidence_frequency / 10.0)
    score = (
        opportunity.expected_impact * 0.25
        + opportunity.confidence * 0.20
        + norm_frequency * 0.15
        + opportunity.strategic_value * 0.20
        + (1.0 - opportunity.difficulty) * 0.10
        + (1.0 - opportunity.risk) * 0.10
    )
    return round(min(1.0, max(0.0, score)), 4)


def runtime_adjustment(factor: float, occurrence_count: int = 8) -> AreaAdjustment:
    """Create an AreaAdjustment for the runtime area."""
    return AreaAdjustment(
        area="runtime",
        occurrence_count=occurrence_count,
        adjustment_factor=factor,
    )


# ---------------------------------------------------------------------------
# Weight configuration
# ---------------------------------------------------------------------------


class TestWeights:
    """Phase 14.4 weight configuration."""

    def test_weights_sum_to_one(self):
        """The Phase 14.4 weights total exactly 1.0."""
        assert sum(WEIGHTS.values()) == pytest.approx(1.0, abs=1e-9)

    def test_historical_evidence_weight_is_0_10(self):
        """The new historical evidence dimension is weighted 0.10."""
        assert WEIGHTS["historical_evidence"] == pytest.approx(0.10, abs=1e-9)

    def test_existing_weights_renormalized(self):
        """Existing dimensions are re-normalized by 0.90."""
        assert WEIGHTS["expected_impact"] == pytest.approx(0.225, abs=1e-9)
        assert WEIGHTS["confidence"] == pytest.approx(0.180, abs=1e-9)
        assert WEIGHTS["evidence_frequency"] == pytest.approx(0.135, abs=1e-9)
        assert WEIGHTS["strategic_value"] == pytest.approx(0.180, abs=1e-9)
        assert WEIGHTS["ease"] == pytest.approx(0.090, abs=1e-9)
        assert WEIGHTS["safety"] == pytest.approx(0.090, abs=1e-9)


# ---------------------------------------------------------------------------
# Backward compatibility: no planning_context
# ---------------------------------------------------------------------------


class TestWithoutPlanningContext:
    """Behavior without a PlanningContext is identical to Phase 8.3."""

    def test_score_matches_original_formula(self):
        """score_opportunity without context matches the Phase 8.3 formula."""
        engine = PriorityEngine()
        opportunity = make_opportunity()

        assert engine.score_opportunity(opportunity) == legacy_score(opportunity)

    def test_score_range_preserved(self):
        """Scores without context stay within [0.0, 1.0]."""
        engine = PriorityEngine()
        opportunity = make_opportunity()

        score = engine.score_opportunity(opportunity)
        assert 0.0 <= score <= 1.0

    def test_rank_orders_by_score(self):
        """rank() without context preserves original ordering behavior."""
        engine = PriorityEngine()
        high = make_opportunity("HIGH", category=GoalCategory.PERFORMANCE)
        low = ImprovementOpportunity(
            opportunity_id="LOW",
            title="Improve capability",
            description="A low scoring opportunity.",
            category=GoalCategory.CAPABILITY,
            expected_impact=0.1,
            difficulty=0.9,
            risk=0.9,
            evidence_frequency=1,
            confidence=0.1,
            strategic_value=0.1,
        )

        ranked = engine.rank([low, high])

        assert [o.opportunity_id for o in ranked] == ["HIGH", "LOW"]
        assert ranked[0].priority_score == legacy_score(high)
        assert ranked[1].priority_score == legacy_score(low)

    def test_get_top_without_context(self):
        """get_top() without context returns the top N opportunities."""
        engine = PriorityEngine()
        ops = [make_opportunity(f"OPP-{i}") for i in range(5)]

        top = engine.get_top(ops, n=3)

        assert len(top) == 3
        assert all(
            top[i].priority_score >= top[j].priority_score
            for i in range(len(top))
            for j in range(i + 1, len(top))
        )


# ---------------------------------------------------------------------------
# Planning context: area adjustments
# ---------------------------------------------------------------------------


class TestAreaAdjustments:
    """PlanningContext.area_adjustments modify the priority score."""

    def setup_method(self):
        self.engine = PriorityEngine()
        self.opportunity = make_opportunity()  # PERFORMANCE -> runtime
        self.neutral = self.engine.score_opportunity(
            self.opportunity,
            planning_context=PlanningContext(),
        )

    def test_positive_adjustment_boosts_score(self):
        """A historical success adjustment raises the priority score."""
        context = PlanningContext(
            area_adjustments={"runtime": runtime_adjustment(1.4)},
        )

        score = self.engine.score_opportunity(
            self.opportunity,
            planning_context=context,
        )

        assert score > self.neutral

    def test_negative_adjustment_lowers_score(self):
        """A historical failure adjustment lowers the priority score."""
        context = PlanningContext(
            area_adjustments={"runtime": runtime_adjustment(0.6)},
        )

        score = self.engine.score_opportunity(
            self.opportunity,
            planning_context=context,
        )

        assert score < self.neutral

    def test_zero_occurrence_adjustment_is_ignored(self):
        """An adjustment with no occurrences is treated as neutral."""
        context = PlanningContext(
            area_adjustments={"runtime": runtime_adjustment(1.4, occurrence_count=0)},
        )

        score = self.engine.score_opportunity(
            self.opportunity,
            planning_context=context,
        )

        assert score == self.neutral

    def test_adjustment_for_unrelated_area_is_ignored(self):
        """Evidence for another area does not affect this opportunity."""
        context = PlanningContext(
            area_adjustments={"memory": runtime_adjustment(1.4)},
        )

        score = self.engine.score_opportunity(
            self.opportunity,
            planning_context=context,
        )

        assert score == self.neutral

    def test_unmapped_category_stays_neutral(self):
        """Categories without a canonical evolution area remain neutral."""
        architecture = make_opportunity(category=GoalCategory.ARCHITECTURE)

        neutral = self.engine.score_opportunity(
            architecture,
            planning_context=PlanningContext(),
        )
        boosted = self.engine.score_opportunity(
            architecture,
            planning_context=PlanningContext(
                area_adjustments={"runtime": runtime_adjustment(1.4)},
            ),
        )

        assert neutral == boosted


# ---------------------------------------------------------------------------
# Planning context: bottleneck alerts
# ---------------------------------------------------------------------------


class TestBottleneckAlerts:
    """PlanningContext.bottleneck_alerts elevate the priority score."""

    def setup_method(self):
        self.engine = PriorityEngine()
        self.opportunity = make_opportunity()  # PERFORMANCE -> runtime
        self.neutral = self.engine.score_opportunity(
            self.opportunity,
            planning_context=PlanningContext(),
        )

    def test_bottleneck_boost_elevates_score(self):
        """A matching bottleneck alert raises the priority score."""
        context = PlanningContext(
            bottleneck_alerts=[
                BottleneckAlert(
                    bottleneck_id="BOT-1",
                    area="runtime",
                    severity_boost=0.3,
                ),
            ],
        )

        score = self.engine.score_opportunity(
            self.opportunity,
            planning_context=context,
        )

        assert score > self.neutral

    def test_unrelated_bottleneck_is_ignored(self):
        """A bottleneck in another area does not affect the score."""
        context = PlanningContext(
            bottleneck_alerts=[
                BottleneckAlert(
                    bottleneck_id="BOT-1",
                    area="memory",
                    severity_boost=0.4,
                ),
            ],
        )

        score = self.engine.score_opportunity(
            self.opportunity,
            planning_context=context,
        )

        assert score == self.neutral

    def test_strongest_matching_bottleneck_wins(self):
        """The strongest matching bottleneck boost is applied."""
        combined = PlanningContext(
            bottleneck_alerts=[
                BottleneckAlert(
                    bottleneck_id="BOT-1",
                    area="runtime",
                    severity_boost=0.1,
                ),
                BottleneckAlert(
                    bottleneck_id="BOT-2",
                    area="runtime",
                    severity_boost=0.3,
                ),
            ],
        )
        weak = PlanningContext(
            bottleneck_alerts=[
                BottleneckAlert(
                    bottleneck_id="BOT-1",
                    area="runtime",
                    severity_boost=0.1,
                ),
            ],
        )

        strong = self.engine.score_opportunity(
            self.opportunity,
            planning_context=combined,
        )
        weak_score = self.engine.score_opportunity(
            self.opportunity,
            planning_context=weak,
        )

        assert strong > weak_score


# ---------------------------------------------------------------------------
# Bounding
# ---------------------------------------------------------------------------


class TestBounding:
    """Adjustment factors and severity boosts are bounded."""

    def test_extreme_positive_evidence_stays_bounded(self):
        """Extremely high factors/boosts still produce a score in [0, 1]."""
        engine = PriorityEngine()
        opportunity = make_opportunity()
        context = PlanningContext(
            area_adjustments={"runtime": runtime_adjustment(99.0)},
            bottleneck_alerts=[
                BottleneckAlert(
                    bottleneck_id="BOT-1",
                    area="runtime",
                    severity_boost=5.0,
                ),
            ],
        )

        score = engine.score_opportunity(opportunity, planning_context=context)

        assert 0.0 <= score <= 1.0

    def test_extreme_negative_evidence_stays_bounded(self):
        """Extremely low factors produce a non-negative score."""
        engine = PriorityEngine()
        opportunity = make_opportunity()
        context = PlanningContext(
            area_adjustments={"runtime": runtime_adjustment(0.0)},
            bottleneck_alerts=[
                BottleneckAlert(
                    bottleneck_id="BOT-1",
                    area="runtime",
                    severity_boost=-5.0,
                ),
            ],
        )

        score = engine.score_opportunity(opportunity, planning_context=context)

        assert 0.0 <= score <= 1.0

    def test_bounded_historical_component(self):
        """The raw historical component is clamped to [0.0, 1.0]."""
        engine = PriorityEngine()

        # Max positive evidence
        context = PlanningContext(
            area_adjustments={"runtime": runtime_adjustment(1.5)},
            bottleneck_alerts=[
                BottleneckAlert(
                    bottleneck_id="BOT-1",
                    area="runtime",
                    severity_boost=0.4,
                ),
            ],
        )
        component = engine._historical_component(
            make_opportunity(),
            context,
        )

        assert 0.0 <= component <= 1.0
        assert component == 1.0  # 0.5 + 0.5 + 0.4 capped at 1.0


# ---------------------------------------------------------------------------
# rank / get_top with planning_context
# ---------------------------------------------------------------------------


class TestRankingWithPlanningContext:

    def test_rank_accepts_planning_context(self):
        """rank() accepts an optional planning_context."""
        engine = PriorityEngine()
        ops = [make_opportunity("A"), make_opportunity("B")]
        context = PlanningContext(
            area_adjustments={"runtime": runtime_adjustment(1.4)},
        )

        ranked = engine.rank(ops, planning_context=context)

        assert len(ranked) == 2
        assert all(o.priority_score > 0.0 for o in ranked)

    def test_get_top_accepts_planning_context(self):
        """get_top() accepts an optional planning_context."""
        engine = PriorityEngine()
        ops = [make_opportunity(f"OPP-{i}") for i in range(5)]
        context = PlanningContext(
            area_adjustments={"runtime": runtime_adjustment(1.4)},
        )

        top = engine.get_top(ops, n=2, planning_context=context)

        assert len(top) == 2

    def test_opportunity_scores_populated_with_context(self):
        """priority_score is populated when ranking with a context."""
        engine = PriorityEngine()
        ops = [make_opportunity("A"), make_opportunity("B")]
        context = PlanningContext(
            area_adjustments={"runtime": runtime_adjustment(1.4)},
        )

        ranked = engine.rank(ops, planning_context=context)

        for opportunity in ranked:
            assert opportunity.priority_score > 0.0


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:

    def test_score_is_deterministic(self):
        """Identical inputs produce identical scores."""
        engine = PriorityEngine()
        opportunity = make_opportunity()
        context = PlanningContext(
            area_adjustments={"runtime": runtime_adjustment(1.4)},
            bottleneck_alerts=[
                BottleneckAlert(
                    bottleneck_id="BOT-1",
                    area="runtime",
                    severity_boost=0.3,
                ),
            ],
        )

        scores = {
            engine.score_opportunity(opportunity, planning_context=context)
            for _ in range(20)
        }

        assert len(scores) == 1

    def test_rank_is_deterministic(self):
        """Ranking the same opportunities twice yields the same order."""
        engine = PriorityEngine()
        ops = [
            make_opportunity("A", category=GoalCategory.CAPABILITY),
            make_opportunity("B"),
            make_opportunity("C", category=GoalCategory.TOOLING),
        ]
        context = PlanningContext(
            area_adjustments={
                "runtime": runtime_adjustment(1.4),
                "reasoning": runtime_adjustment(0.6),
            },
        )

        first = engine.rank(ops, planning_context=context)
        second = engine.rank(ops, planning_context=context)

        assert [o.opportunity_id for o in first] == [o.opportunity_id for o in second]
