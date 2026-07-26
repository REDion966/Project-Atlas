"""
Atlas OpportunityAnalyzer — Phase 8.3

Consumes accumulated evidence from learning, understanding, world
model, identity, capability profiles, and evolution observations.
Produces ranked ImprovementOpportunity instances.

Deterministic rules. No AI providers. Pure logic.
"""

from datetime import datetime
from typing import Any

from atlas.goals.models import (
    GoalCategory,
    GoalDependency,
    ImprovementCandidate,
    ImprovementOpportunity,
    GoalPriority,
)

# Category mapping from evidence source keywords
CATEGORY_MAP: dict[str, GoalCategory] = {
    "memory": GoalCategory.PERFORMANCE,
    "knowledge": GoalCategory.UNDERSTANDING,
    "understanding": GoalCategory.UNDERSTANDING,
    "reasoning": GoalCategory.CAPABILITY,
    "planning": GoalCategory.CAPABILITY,
    "tool": GoalCategory.TOOLING,
    "evolution": GoalCategory.EVOLUTION,
    "reflection": GoalCategory.UNDERSTANDING,
    "learning": GoalCategory.UNDERSTANDING,
    "identity": GoalCategory.UNDERSTANDING,
    "world_model": GoalCategory.UNDERSTANDING,
    "capability": GoalCategory.CAPABILITY,
    "architecture": GoalCategory.ARCHITECTURE,
    "feedback": GoalCategory.EVOLUTION,
    "reliability": GoalCategory.RELIABILITY,
}


class OpportunityAnalyzer:
    """Analyzes evidence and produces improvement opportunities."""

    def __init__(self):
        self._candidate_counter = 0
        self._opportunity_counter = 0

    def analyze_evidence(self, evidence: dict[str, Any]) -> list[ImprovementCandidate]:
        """
        Analyze a dictionary of evidence sources and produce improvement candidates.

        Args:
            evidence: Dict with keys like 'learning_insights', 'capability_profiles',
                     'reflection_suggestions', 'identity_summary', 'world_model_summary', etc.

        Returns:
            List of ImprovementCandidate instances.
        """
        candidates: list[ImprovementCandidate] = []

        # From learning insights
        learning = evidence.get("learning_insights", {})
        top = learning.get("top_insights", []) if isinstance(learning, dict) else []
        for t in top[:5]:
            title = t.get("title", "")
            importance = t.get("importance", "")
            if title and importance in ("CRITICAL", "HIGH"):
                candidates.append(self._make_candidate(
                    description=f"Learning insight: {title}",
                    category=GoalCategory.UNDERSTANDING,
                    source="learning_engine",
                    confidence=0.6,
                ))

        # From reflection suggestions
        reflections = evidence.get("reflection_suggestions", []) or []
        for s in reflections[:5]:
            pattern = getattr(s, "pattern", "")
            suggestion = getattr(s, "suggestion", "")
            if pattern:
                candidates.append(self._make_candidate(
                    description=f"Reflection: {pattern} — {suggestion}",
                    category=self._infer_category(pattern),
                    source="reflection_engine",
                    confidence=getattr(s, "confidence", 0.5),
                ))

        # From capability profiles (weak areas)
        capabilities = evidence.get("capability_profiles", {})
        if isinstance(capabilities, dict) and "weaknesses" in capabilities:
            for w in capabilities.get("weaknesses", [])[:3]:
                area = w if isinstance(w, str) else getattr(w, "area", str(w))
                candidates.append(self._make_candidate(
                    description=f"Weak capability area: {area}",
                    category=GoalCategory.CAPABILITY,
                    source="capability_profiler",
                    confidence=0.5,
                ))

        # From identity weaknesses
        identity = evidence.get("identity_summary", {})
        if isinstance(identity, dict):
            for w in identity.get("weaknesses", [])[:3]:
                area = w if isinstance(w, str) else getattr(w, "area", str(w))
                candidates.append(self._make_candidate(
                    description=f"Identity weakness: {area}",
                    category=GoalCategory.UNDERSTANDING,
                    source="identity_engine",
                    confidence=0.4,
                ))

        # From world model active goals
        wm = evidence.get("world_model_summary", {})
        if isinstance(wm, dict):
            active_goals = wm.get("active_goals", [])
            for g in active_goals[:3]:
                desc = getattr(g, "description", str(g))[:120]
                candidates.append(self._make_candidate(
                    description=f"World model goal: {desc}",
                    category=GoalCategory.UNDERSTANDING,
                    source="world_model",
                    confidence=0.4,
                ))

        return candidates

    def generate_opportunities(
        self,
        candidates: list[ImprovementCandidate],
        existing_goals: list[Any] | None = None,
    ) -> list[ImprovementOpportunity]:
        """Merge candidates into structured opportunities."""
        if existing_goals is None:
            existing_goals = []

        # Group candidates by category
        by_category: dict[GoalCategory, list[ImprovementCandidate]] = {}
        for c in candidates:
            by_category.setdefault(c.category, []).append(c)

        opportunities: list[ImprovementOpportunity] = []
        for category, cats in by_category.items():
            opp = self._make_opportunity(category, cats)
            opportunities.append(opp)

        return opportunities

    def _make_candidate(
        self,
        description: str,
        category: GoalCategory,
        source: str,
        confidence: float,
    ) -> ImprovementCandidate:
        self._candidate_counter += 1
        return ImprovementCandidate(
            candidate_id=f"CAND-{self._candidate_counter:06d}",
            description=description,
            category=category,
            source=source,
            confidence=confidence,
        )

    def _make_opportunity(
        self,
        category: GoalCategory,
        candidates: list[ImprovementCandidate],
    ) -> ImprovementOpportunity:
        self._opportunity_counter += 1
        avg_confidence = sum(c.confidence for c in candidates) / max(1, len(candidates))
        evidence_count = len(candidates)

        return ImprovementOpportunity(
            opportunity_id=f"OPP-{self._opportunity_counter:06d}",
            title=f"Improve {category.name.lower().replace('_', ' ')}",
            description=f"Based on {evidence_count} evidence signals in {category.name}",
            category=category,
            source_candidates=[c.candidate_id for c in candidates],
            expected_impact=min(0.9, avg_confidence),
            difficulty=1.0 - avg_confidence,
            risk=0.5 - (avg_confidence * 0.3),
            dependency_count=0,
            evidence_frequency=evidence_count,
            confidence=avg_confidence,
            strategic_value=0.5 + avg_confidence * 0.3,
            evidence_sources=list({c.source for c in candidates}),
        )

    @staticmethod
    def _infer_category(evidence_text: str) -> GoalCategory:
        """Infer goal category from evidence text keywords."""
        lowered = evidence_text.lower()
        for keyword, cat in sorted(CATEGORY_MAP.items(), key=lambda x: -len(x[0])):
            if keyword in lowered:
                return cat
        return GoalCategory.UNDERSTANDING