"""
Atlas RecommendationEngine — Phase 8.3

Generates structured engineering recommendations from prioritized
opportunities. No code generation. No implementation. Only recommendations.
Pure logic.
"""

from datetime import datetime

from atlas.goals.models import (
    GoalCategory,
    ImprovementOpportunity,
    RecommendationItem,
    RecommendationReport,
)


class RecommendationEngine:
    """Generates structured recommendations from improvement opportunities."""

    def __init__(self):
        self._item_counter = 0
        self._report_counter = 0

    def generate_report(
        self,
        prioritized: list[ImprovementOpportunity],
        blocked_goals: list[any] = None,
    ) -> RecommendationReport:
        """
        Generate a complete recommendation report.

        Args:
            prioritized: Ranked list of opportunities.
            blocked_goals: List of GoalEvaluation for blocked goals.

        Returns:
            A RecommendationReport with human-readable recommendations.
        """
        blocked_goals = blocked_goals or []
        self._report_counter += 1
        report_id = f"RPT-{self._report_counter:06d}"

        items: list[RecommendationItem] = []
        for opp in prioritized[:10]:
            item = self._make_recommendation(opp)
            items.append(item)

        # Build summary
        total = len(items)
        top_categories = {}
        for item in items[:3]:
            cat_name = item.category.name.lower().replace("_", " ")
            top_categories[cat_name] = top_categories.get(cat_name, 0) + 1

        summary_parts = [f"Generated {total} improvement recommendations."]
        if top_categories:
            cats = ", ".join(f"{v} in {k}" for k, v in top_categories.items())
            summary_parts.append(f"Top categories: {cats}.")
        if blocked_goals:
            summary_parts.append(f"{len(blocked_goals)} goals are blocked by dependencies.")

        return RecommendationReport(
            report_id=report_id,
            generated_at=datetime.now(),
            total_opportunities=len(prioritized),
            total_goals=len(items),
            total_recommendations=total,
            top_recommendations=items[:5],
            prioritized_opportunities=prioritized[:10],
            blocked_goals=blocked_goals,
            summary=" ".join(summary_parts),
        )

    def _make_recommendation(self, opp: ImprovementOpportunity) -> RecommendationItem:
        self._item_counter += 1
        item_id = f"REC-{self._item_counter:06d}"

        problem = f"Area needing improvement: {opp.title}"
        evidence = (
            f"Based on {opp.evidence_frequency} evidence signals "
            f"from {', '.join(opp.evidence_sources[:3]) or 'analysis'}. "
            f"Confidence: {opp.confidence:.0%}."
        )
        reasoning = (
            f"This opportunity scores {opp.priority_score:.2f} on priority "
            f"(impact: {opp.expected_impact:.0%}, "
            f"strategic value: {opp.strategic_value:.0%}). "
            f"Addressing this would improve {opp.category.name.lower().replace('_', ' ')}."
        )
        benefit = (
            f"Expected to strengthen {opp.category.name.lower().replace('_', ' ')} "
            f"capabilities with impact rating of {opp.expected_impact:.0%}."
        )

        if opp.difficulty < 0.4:
            effort = "Low effort — straightforward improvement"
        elif opp.difficulty < 0.7:
            effort = "Moderate effort — requires planning"
        else:
            effort = "Significant effort — complex change"

        if opp.risk < 0.3:
            risk = "Low risk — well-understood area"
        elif opp.risk < 0.6:
            risk = "Moderate risk — requires testing"
        else:
            risk = "High risk — needs careful validation"

        return RecommendationItem(
            item_id=item_id,
            problem=problem,
            evidence=evidence,
            reasoning=reasoning,
            expected_benefit=benefit,
            estimated_effort=effort,
            estimated_risk=risk,
            required_dependencies=[d.target_goal_id for d in opp.dependencies],
            confidence=opp.confidence,
            category=opp.category,
        )