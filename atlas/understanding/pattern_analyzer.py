"""
Atlas Pattern Analyzer

Detects patterns across concepts and understanding insights.
Identifies recurring themes, correlations, and trends.

Phase 7.1 — Understanding Engine.
"""

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from atlas.understanding.models import (
    Concept,
    ConceptDomain,
    Pattern,
    Relationship,
    RelationshipType,
    UnderstandingCategory,
    UnderstandingInsight,
)


class PatternAnalyzer:
    """
    Analyzes concepts and relationships to detect meaningful patterns.

    This is a pure logic component with no infrastructure dependencies.
    It uses deterministic analysis to identify repeated themes, behavioral
    signals, concept clusters, and temporal trends.

    Pattern detection is entirely rule-based and unit-testable.
    """

    def __init__(self) -> None:
        self._pattern_counter = 0

    def _next_pattern_id(self) -> str:
        """Generate a unique pattern identifier."""
        self._pattern_counter += 1
        return f"PAT-{self._pattern_counter:06d}"

    # ------------------------------------------------------------------
    # Primary analysis entry points
    # ------------------------------------------------------------------

    def analyze_concepts(
        self,
        concepts: list[Concept],
        existing_patterns: list[Pattern] | None = None,
    ) -> list[Pattern]:
        """
        Analyze a list of concepts and return detected patterns.

        Args:
            concepts: A list of Concept instances to analyze.
            existing_patterns: Optional list of previously detected
                patterns for frequency tracking.

        Returns:
            A list of Pattern instances detected from the concepts.
        """
        if not concepts:
            return []

        patterns: list[Pattern] = []

        domain_pattern = self._detect_domain_dominance(concepts)
        if domain_pattern is not None:
            patterns.append(domain_pattern)

        frequency_pattern = self._detect_high_frequency_concepts(concepts)
        if frequency_pattern is not None:
            patterns.append(frequency_pattern)

        return patterns

    def analyze_relationships(
        self,
        relationships: list[Relationship],
        existing_patterns: list[Pattern] | None = None,
    ) -> list[Pattern]:
        """
        Analyze relationships between concepts and detect relational patterns.

        Args:
            relationships: A list of Relationship instances.
            existing_patterns: Optional previously detected patterns.

        Returns:
            A list of Pattern instances detected from the relationships.
        """
        if not relationships:
            return []

        patterns: list[Pattern] = []

        chain_pattern = self._detect_relationship_chains(relationships)
        if chain_pattern is not None:
            patterns.append(chain_pattern)

        return patterns

    def analyze_insights(
        self,
        insights: list[UnderstandingInsight],
        existing_patterns: list[Pattern] | None = None,
    ) -> list[Pattern]:
        """
        Analyze understanding insights for cross-cutting patterns.

        Args:
            insights: A list of UnderstandingInsight instances.
            existing_patterns: Optional previously detected patterns.

        Returns:
            A list of Pattern instances detected across insights.
        """
        if not insights:
            return []

        patterns: list[Pattern] = []

        category_pattern = self._detect_insight_category_trends(insights)
        if category_pattern is not None:
            patterns.append(category_pattern)

        return patterns

    # ------------------------------------------------------------------
    # Specific detection methods
    # ------------------------------------------------------------------

    def _detect_domain_dominance(
        self,
        concepts: list[Concept],
    ) -> Pattern | None:
        """
        Detect if a single concept domain dominates the concept set.
        A domain is dominant if it represents >50% of all concepts.
        """
        if len(concepts) < 3:
            return None

        domain_counts: Counter[ConceptDomain] = Counter(
            c.domain for c in concepts
        )

        total = len(concepts)
        for domain, count in domain_counts.most_common(1):
            ratio = count / total
            if ratio > 0.5:
                related_ids = [
                    c.concept_id for c in concepts
                    if c.domain == domain
                ]
                return Pattern(
                    pattern_id=self._next_pattern_id(),
                    label=f"Dominant Domain: {domain.name}",
                    description=(
                        f"The '{domain.name}' domain represents "
                        f"{count}/{total} concepts ({ratio:.0%}). "
                        f"This may indicate the current focus of activity."
                    ),
                    confidence=round(min(ratio, 1.0), 4),
                    related_concept_ids=related_ids[:20],
                )
        return None

    def _detect_high_frequency_concepts(
        self,
        concepts: list[Concept],
    ) -> Pattern | None:
        """
        Detect concepts that appear with significantly high frequency.
        A concept is flagged if its frequency is >2x the average.
        """
        if len(concepts) < 3:
            return None

        frequencies = [c.frequency for c in concepts]
        avg_frequency = sum(frequencies) / len(frequencies) if frequencies else 0

        if avg_frequency == 0:
            return None

        high_freq = [
            c for c in concepts
            if c.frequency > avg_frequency * 2
        ]

        if not high_freq:
            return None

        high_freq.sort(key=lambda c: c.frequency, reverse=True)
        top = high_freq[:5]

        related_ids = [c.concept_id for c in top]
        labels = ", ".join(c.label for c in top)

        return Pattern(
            pattern_id=self._next_pattern_id(),
            label="High-Frequency Concepts",
            description=(
                f"Concepts appearing significantly more often than average: "
                f"{labels}. Average frequency: {avg_frequency:.1f}."
            ),
            confidence=round(
                min(top[0].frequency / (avg_frequency * 3), 1.0), 4
            ),
            related_concept_ids=related_ids,
        )

    def _detect_relationship_chains(
        self,
        relationships: list[Relationship],
    ) -> Pattern | None:
        """
        Detect frequently repeated relationship types.
        """
        if len(relationships) < 3:
            return None

        type_counts: Counter[RelationshipType] = Counter(
            r.relationship_type for r in relationships
        )

        total = len(relationships)
        for rel_type, count in type_counts.most_common(1):
            ratio = count / total
            if ratio > 0.3:
                related_ids = list(set(
                    r.source_id for r in relationships
                    if r.relationship_type == rel_type
                ))

                return Pattern(
                    pattern_id=self._next_pattern_id(),
                    label=f"Relationship Pattern: {rel_type.name}",
                    description=(
                        f"The '{rel_type.name}' relationship type appears "
                        f"in {count}/{total} relationships ({ratio:.0%}). "
                        f"This is the dominant relationship pattern."
                    ),
                    confidence=round(min(ratio, 1.0), 4),
                    related_concept_ids=related_ids[:20],
                )

        return None

    def _detect_insight_category_trends(
        self,
        insights: list[UnderstandingInsight],
    ) -> Pattern | None:
        """
        Detect dominant categories across understanding insights.
        """
        if len(insights) < 3:
            return None

        category_counts: Counter[UnderstandingCategory] = Counter(
            i.category for i in insights
        )

        total = len(insights)
        for category, count in category_counts.most_common(1):
            ratio = count / total
            if ratio > 0.4:
                related_ids = [
                    i.insight_id for i in insights
                    if i.category == category
                ]

                return Pattern(
                    pattern_id=self._next_pattern_id(),
                    label=f"Insight Category: {category.name}",
                    description=(
                        f"The '{category.name}' insight category represents "
                        f"{count}/{total} insights ({ratio:.0%}). "
                        f"This is the dominant understanding category."
                    ),
                    confidence=round(min(ratio, 1.0), 4),
                    related_concept_ids=related_ids[:20],
                )

        return None

    # ------------------------------------------------------------------
    # Batch analysis
    # ------------------------------------------------------------------

    def analyze_all(
        self,
        concepts: list[Concept],
        relationships: list[Relationship] | None = None,
        insights: list[UnderstandingInsight] | None = None,
    ) -> list[Pattern]:
        """
        Run all available analysis methods and return combined patterns.

        Args:
            concepts: Concepts to analyze.
            relationships: Optional relationships to analyze.
            insights: Optional insights to analyze.

        Returns:
            A combined list of all detected patterns.
        """
        patterns: list[Pattern] = []

        patterns.extend(self.analyze_concepts(concepts))

        if relationships:
            patterns.extend(self.analyze_relationships(relationships))

        if insights:
            patterns.extend(self.analyze_insights(insights))

        return patterns