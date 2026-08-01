"""
Atlas PriorityEngine — Phase 8.3 / Phase 14.4

Ranks improvement opportunities using weighted multi-dimensional scoring.
Produces sorted improvement list. Deterministic. Pure logic.

Phase 14.4 — Optional ``PlanningContext`` support. When a PlanningContext
is provided, historical evidence from the consolidated evolution knowledge
layer adjusts scores through ``AreaAdjustment.adjustment_factor`` and
``BottleneckAlert.severity_boost``. When ``planning_context`` is None,
scoring is byte-for-byte identical to the original Phase 8.3
implementation.
"""

from atlas.evolution.decision_models import PlanningContext
from atlas.goals.models import GoalCategory, ImprovementOpportunity


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------

# Original Phase 8.3 weights. Used verbatim when planning_context is None so
# existing behavior is preserved exactly (sum = 1.0).
_LEGACY_WEIGHTS = {
    "expected_impact": 0.25,
    "confidence": 0.20,
    "evidence_frequency": 0.15,
    "strategic_value": 0.20,
    "ease": 0.10,       # 1 - difficulty
    "safety": 0.10,     # 1 - risk
}

# Phase 14.4 weights. Existing dimensions are re-normalized to make room for
# the historical evidence dimension while preserving total = 1.0:
#   0.25 * 0.90 = 0.225  0.20 * 0.90 = 0.180  0.15 * 0.90 = 0.135
#   0.20 * 0.90 = 0.180  0.10 * 0.90 = 0.090  0.10 * 0.90 = 0.090
#   historical_evidence = 0.100
# Sum = 0.225 + 0.180 + 0.135 + 0.180 + 0.090 + 0.090 + 0.100 = 1.000
WEIGHTS = {
    "expected_impact": 0.225,
    "confidence": 0.180,
    "evidence_frequency": 0.135,
    "strategic_value": 0.180,
    "ease": 0.090,      # 1 - difficulty
    "safety": 0.090,    # 1 - risk
    "historical_evidence": 0.100,
}

# ---------------------------------------------------------------------------
# Historical evidence bounds and mapping
# ---------------------------------------------------------------------------

# AreaAdjustment.adjustment_factor is bounded to [0.5, 1.5] by the decision
# scorer. Re-clamp defensively so scores always stay bounded.
_ADJUSTMENT_FACTOR_MIN = 0.5
_ADJUSTMENT_FACTOR_MAX = 1.5

# BottleneckAlert.severity_boost is bounded to [0.0, 0.4] by the decision
# scorer. Re-clamp to [0.0, 1.0] defensively.
_BOOST_MIN = 0.0
_BOOST_MAX = 1.0

# Neutral historical component: the midpoint of the bounded [0.0, 1.0] range.
# A neutral factor (1.0) with no bottleneck boost maps exactly to 0.5.
_HISTORICAL_NEUTRAL = 0.5

# Mapping from goal category to the canonical evolution area used by
# PlanningContext.area_adjustments and PlanningContext.bottleneck_alerts.
# Categories without a canonical evolution area remain neutral.
_CATEGORY_TO_AREA: dict[GoalCategory, str] = {
    GoalCategory.PERFORMANCE: "runtime",
    GoalCategory.CAPABILITY: "reasoning",
    GoalCategory.TOOLING: "tools",
    GoalCategory.UNDERSTANDING: "memory",
    GoalCategory.RELIABILITY: "system_health",
}


class PriorityEngine:
    """
    Ranks opportunities using weighted scoring across 7 dimensions.

    Weights (sum = 1.0, used when planning_context is provided):
        expected_impact:     0.225
        confidence:          0.180
        evidence_frequency:  0.135
        strategic_value:     0.180
        (1 - difficulty):    0.090
        (1 - risk):          0.090
        historical_evidence: 0.100

    When ``planning_context`` is None, the original Phase 8.3 weights are
    used (0.25 / 0.20 / 0.15 / 0.20 / 0.10 / 0.10, sum = 1.0) and scoring is
    identical to the pre-14.4 implementation.

    Historical evidence adjustment (planning_context provided):
      - The opportunity's category is mapped to a canonical evolution area.
      - A matching AreaAdjustment.adjustment_factor scales the historical
        component (bounded to [0.5, 1.5]).
      - The strongest matching BottleneckAlert.severity_boost elevates the
        historical component (bounded to [0.0, 1.0]).
      - The combined historical component is bounded to [0.0, 1.0], with 0.5
        as the neutral midpoint.

    Higher score = higher priority.
    Score range: 0.0 (low priority) to 1.0 (critical).
    """

    WEIGHTS = WEIGHTS

    def score_opportunity(
        self,
        opportunity: ImprovementOpportunity,
        planning_context: PlanningContext | None = None,
    ) -> float:
        """
        Calculate priority score for a single opportunity.

        When ``planning_context`` is None, the score is identical to the
        original Phase 8.3 formula. When provided, historical evidence from
        the context adjusts the score.

        Returns 0.0 to 1.0.
        """
        if planning_context is None:
            score = self._score_dimensions(opportunity, _LEGACY_WEIGHTS)
            return round(min(1.0, max(0.0, score)), 4)

        base_score = self._score_dimensions(opportunity, WEIGHTS)
        historical = self._historical_component(opportunity, planning_context)

        score = (
            base_score
            + WEIGHTS["historical_evidence"] * historical
        )

        return round(min(1.0, max(0.0, score)), 4)

    def rank(
        self,
        opportunities: list[ImprovementOpportunity],
        planning_context: PlanningContext | None = None,
    ) -> list[ImprovementOpportunity]:
        """
        Score and rank opportunities. Returns sorted list (highest first).

        Each opportunity's priority_score field is populated.

        Args:
            opportunities: The opportunities to rank.
            planning_context: Optional PlanningContext with historical
                evidence. If None, scoring is identical to the original
                implementation.
        """
        ranked: list[ImprovementOpportunity] = []
        for opp in opportunities:
            score = self.score_opportunity(opp, planning_context=planning_context)
            # Create new frozen instance with score populated
            ranked.append(ImprovementOpportunity(
                opportunity_id=opp.opportunity_id,
                title=opp.title,
                description=opp.description,
                category=opp.category,
                source_candidates=opp.source_candidates,
                expected_impact=opp.expected_impact,
                difficulty=opp.difficulty,
                risk=opp.risk,
                dependency_count=opp.dependency_count,
                evidence_frequency=opp.evidence_frequency,
                confidence=opp.confidence,
                strategic_value=opp.strategic_value,
                priority_score=score,
                dependencies=opp.dependencies,
                evidence_sources=opp.evidence_sources,
            ))

        ranked.sort(key=lambda o: o.priority_score, reverse=True)
        return ranked

    def get_top(
        self,
        opportunities: list[ImprovementOpportunity],
        n: int = 5,
        planning_context: PlanningContext | None = None,
    ) -> list[ImprovementOpportunity]:
        """Return top N ranked opportunities."""
        ranked = self.rank(
            opportunities,
            planning_context=planning_context,
        )
        return ranked[:n]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_dimensions(
        opportunity: ImprovementOpportunity,
        weights: dict[str, float],
    ) -> float:
        """Weighted multi-dimensional base score (0.0 to 1.0)."""
        # Normalize evidence frequency (cap at 10)
        norm_frequency = min(1.0, opportunity.evidence_frequency / 10.0)

        return (
            opportunity.expected_impact * weights["expected_impact"]
            + opportunity.confidence * weights["confidence"]
            + norm_frequency * weights["evidence_frequency"]
            + opportunity.strategic_value * weights["strategic_value"]
            + (1.0 - opportunity.difficulty) * weights["ease"]
            + (1.0 - opportunity.risk) * weights["safety"]
        )

    @classmethod
    def _historical_component(
        cls,
        opportunity: ImprovementOpportunity,
        planning_context: PlanningContext,
    ) -> float:
        """
        Compute the bounded historical evidence component (0.0 to 1.0).

        Neutral midpoint is 0.5. Positive evidence (adjustment > 1.0 and/or
        a bottleneck boost) pushes above 0.5; negative evidence pushes below.
        """
        area = _CATEGORY_TO_AREA.get(opportunity.category)
        if area is None:
            return _HISTORICAL_NEUTRAL

        adjustment_factor = 1.0
        adjustment = planning_context.area_adjustments.get(area)
        if adjustment is not None and adjustment.occurrence_count > 0:
            adjustment_factor = min(
                _ADJUSTMENT_FACTOR_MAX,
                max(_ADJUSTMENT_FACTOR_MIN, adjustment.adjustment_factor),
            )

        bottleneck_boost = 0.0
        for alert in planning_context.bottleneck_alerts:
            if alert.area == area:
                bounded_boost = min(
                    _BOOST_MAX,
                    max(_BOOST_MIN, alert.severity_boost),
                )
                bottleneck_boost = max(bottleneck_boost, bounded_boost)

        raw = (
            _HISTORICAL_NEUTRAL
            + (adjustment_factor - 1.0)
            + bottleneck_boost
        )
        return min(1.0, max(0.0, raw))
