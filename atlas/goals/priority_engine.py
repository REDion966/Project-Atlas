"""
Atlas PriorityEngine — Phase 8.3

Ranks improvement opportunities using weighted multi-dimensional scoring.
Produces sorted improvement list. Deterministic. Pure logic.
"""

from atlas.goals.models import ImprovementOpportunity


class PriorityEngine:
    """
    Ranks opportunities using weighted scoring across 7 dimensions.

    Weights (sum = 1.0):
        expected_impact:     0.25
        confidence:          0.20
        evidence_frequency:  0.15
        strategic_value:     0.20
        (1 - difficulty):    0.10
        (1 - risk):          0.10

    Higher score = higher priority.
    Score range: 0.0 (low priority) to 1.0 (critical).
    """

    WEIGHTS = {
        "expected_impact": 0.25,
        "confidence": 0.20,
        "evidence_frequency": 0.15,
        "strategic_value": 0.20,
        "ease": 0.10,       # 1 - difficulty
        "safety": 0.10,     # 1 - risk
    }

    def score_opportunity(self, opportunity: ImprovementOpportunity) -> float:
        """
        Calculate priority score for a single opportunity.

        Returns 0.0 to 1.0.
        """
        # Normalize evidence frequency (cap at 10)
        norm_frequency = min(1.0, opportunity.evidence_frequency / 10.0)

        score = (
            opportunity.expected_impact * self.WEIGHTS["expected_impact"]
            + opportunity.confidence * self.WEIGHTS["confidence"]
            + norm_frequency * self.WEIGHTS["evidence_frequency"]
            + opportunity.strategic_value * self.WEIGHTS["strategic_value"]
            + (1.0 - opportunity.difficulty) * self.WEIGHTS["ease"]
            + (1.0 - opportunity.risk) * self.WEIGHTS["safety"]
        )

        return round(min(1.0, max(0.0, score)), 4)

    def rank(self, opportunities: list[ImprovementOpportunity]) -> list[ImprovementOpportunity]:
        """
        Score and rank opportunities. Returns sorted list (highest first).

        Each opportunity's priority_score field is populated.
        """
        ranked: list[ImprovementOpportunity] = []
        for opp in opportunities:
            score = self.score_opportunity(opp)
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

    def get_top(self, opportunities: list[ImprovementOpportunity], n: int = 5) -> list[ImprovementOpportunity]:
        """Return top N ranked opportunities."""
        ranked = self.rank(opportunities)
        return ranked[:n]