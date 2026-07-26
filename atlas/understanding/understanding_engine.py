"""
Atlas Understanding Engine

Orchestrates the Understanding Layer pipeline:
Observation → Extract concepts → Connect concepts → Find patterns → Generate understanding → Return structured insights

Phase 7.1 — Understanding Engine.
"""

from datetime import datetime
from typing import Any

from atlas.understanding.models import (
    BehavioralDomain,
    BehavioralSignal,
    Concept,
    ConceptDomain,
    Pattern,
    Relationship,
    RelationshipType,
    UnderstandingCategory,
    UnderstandingInsight,
    BehaviorExtractor,
)
from atlas.understanding.concept_extractor import ConceptExtractor
from atlas.understanding.pattern_analyzer import PatternAnalyzer
from atlas.understanding.understanding_graph import UnderstandingGraph
from atlas.understanding.understanding_memory import UnderstandingMemory


class UnderstandingEngine:
    """
    Orchestrates the Understanding Layer pipeline.

    This is a pure logic component with no infrastructure dependencies.
    It does not call AI providers, access memory, query knowledge, or
    interact with the EventBus. It receives data through method parameters
    and returns structured UnderstandingInsight instances.

    The pipeline:
        1. Extract concepts from input data.
        2. Add concepts to the understanding graph.
        3. Detect relationships between concepts.
        4. Analyze concepts and relationships for patterns.
        5. Generate structured understanding insights.
        6. Store results in understanding memory.

    Future reasoning components should consume UnderstandingInsight
    instances instead of raw memories whenever possible.
    """

    def __init__(
        self,
        memory: UnderstandingMemory | None = None,
        graph: UnderstandingGraph | None = None,
        extractor: ConceptExtractor | None = None,
        analyzer: PatternAnalyzer | None = None,
        behavior_extractor: BehaviorExtractor | None = None,
    ) -> None:
        """
        Initialise the Understanding Engine.

        All dependencies are optional — defaults are created if not
        provided. This allows dependency injection for testing.

        Args:
            memory: UnderstandingMemory instance.
            graph: UnderstandingGraph instance.
            extractor: ConceptExtractor instance.
            analyzer: PatternAnalyzer instance.
            behavior_extractor: Pluggable BehaviorExtractor instance.
        """
        self._memory = memory or UnderstandingMemory()
        self._graph = graph or UnderstandingGraph()
        self._extractor = extractor or ConceptExtractor()
        self._analyzer = analyzer or PatternAnalyzer()
        self._behavior_extractor = behavior_extractor or BehaviorExtractor()
        self._insight_counter = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def memory(self) -> UnderstandingMemory:
        """Return the understanding memory."""
        return self._memory

    @property
    def graph(self) -> UnderstandingGraph:
        """Return the understanding graph."""
        return self._graph

    @property
    def behavior_extractor(self) -> BehaviorExtractor:
        """Return the behavior extractor. Can be replaced at runtime."""
        return self._behavior_extractor

    @behavior_extractor.setter
    def behavior_extractor(self, extractor: BehaviorExtractor) -> None:
        """Set a custom behavior extractor."""
        self._behavior_extractor = extractor

    # ------------------------------------------------------------------
    # Core pipeline
    # ------------------------------------------------------------------

    def process_text(
        self,
        text: str,
        source: str = "",
    ) -> list[UnderstandingInsight]:
        """
        Process text through the full Understanding Layer pipeline.

        Args:
            text: The input text to analyze.
            source: Source identifier for provenance.

        Returns:
            A list of UnderstandingInsight instances.
        """
        if not text or not text.strip():
            return []

        insights: list[UnderstandingInsight] = []

        # 1. Extract concepts
        concepts = self._extractor.extract_from_text(text, source=source)

        # 2. Add to graph
        self._graph.add_concepts(concepts)
        for concept in concepts:
            self._memory.store_concept(concept)

        # 3. Auto-connect similar concepts
        self._auto_connect_concepts(concepts)

        # 4. Detect patterns
        patterns = self._analyzer.analyze_concepts(concepts)
        for pattern in patterns:
            self._memory.store_pattern(pattern)

        # 5. Generate concept insights
        for concept in concepts:
            insight = self._generate_concept_insight(concept)
            insights.append(insight)
            self._memory.store_insight(insight)

        # 6. Generate pattern insights
        for pattern in patterns:
            insight = self._generate_pattern_insight(pattern, concepts)
            if insight is not None:
                insights.append(insight)
                self._memory.store_insight(insight)

        # 7. Extract behavioral signals
        signals = self._behavior_extractor.extract_signals(text, source=source)
        for signal in signals:
            self._memory.store_signal(signal)

        return insights

    def process_observation(
        self,
        observation: Any,
        source: str = "",
    ) -> list[UnderstandingInsight]:
        """
        Process an observation object through the Understanding Layer.

        Args:
            observation: An observation object.
            source: Optional source override.

        Returns:
            A list of UnderstandingInsight instances.
        """
        # First extract concepts from the observation
        concepts = self._extractor.extract_from_observation(
            observation, source=source,
        )

        # Also try to get description as text
        texts: list[str] = []
        if hasattr(observation, "description") and observation.description:
            texts.append(str(observation.description))
        if hasattr(observation, "metric_name") and observation.metric_name:
            texts.append(str(observation.metric_name))

        # Process extracted concepts
        insights: list[UnderstandingInsight] = []

        self._graph.add_concepts(concepts)
        for concept in concepts:
            self._memory.store_concept(concept)

        self._auto_connect_concepts(concepts)
        patterns = self._analyzer.analyze_concepts(concepts)

        for pattern in patterns:
            self._memory.store_pattern(pattern)

        for concept in concepts:
            insight = self._generate_concept_insight(concept)
            insights.append(insight)
            self._memory.store_insight(insight)

        # Extract behavioral signals
        for text in texts:
            signals = self._behavior_extractor.extract_signals(text, source=source)
            for signal in signals:
                self._memory.store_signal(signal)

        return insights

    # ------------------------------------------------------------------
    # Analysis queries
    # ------------------------------------------------------------------

    def get_current_understanding(
        self,
        n_insights: int = 20,
    ) -> dict[str, Any]:
        """
        Return a snapshot of current understanding state.

        Args:
            n_insights: Number of recent insights to include.

        Returns:
            A dictionary with concepts, patterns, insights, and
            behavioral signals summary.
        """
        return {
            "concepts": [
                {"id": c.concept_id, "label": c.label, "domain": c.domain.name, "confidence": c.confidence}
                for c in self._graph.get_all_concepts()[-50:]
            ],
            "patterns": [
                {"id": p.pattern_id, "label": p.label, "confidence": p.confidence}
                for p in self._memory.get_patterns(10)
            ],
            "insights": [
                {"id": i.insight_id, "summary": i.summary, "category": i.category.name, "confidence": i.confidence}
                for i in self._memory.get_insights(n_insights)
            ],
            "signal_count": self._memory.signal_count,
            "memory_summary": self._memory.summary(),
        }

    def get_understanding_for_concept(
        self,
        label: str,
        depth: int = 1,
    ) -> dict[str, Any]:
        """
        Get understanding data related to a specific concept label.

        Args:
            label: The concept label to look up.
            depth: Relationship traversal depth.

        Returns:
            A dictionary with the concept, related concepts, and
            related patterns.
        """
        concept = self._graph.get_concept_by_label(label)
        if concept is None:
            return {"found": False, "label": label}

        related = self._graph.find_related_concepts(concept.concept_id, max_depth=depth)

        return {
            "found": True,
            "concept": {
                "id": concept.concept_id,
                "label": concept.label,
                "domain": concept.domain.name,
                "confidence": concept.confidence,
                "frequency": concept.frequency,
            },
            "related_concepts": [
                {"id": c.concept_id, "label": c.label, "domain": c.domain.name}
                for c in related
            ],
            "relationship_count": len(self._graph.get_relationships(concept.concept_id)),
        }

    # ------------------------------------------------------------------
    # Internal pipeline helpers
    # ------------------------------------------------------------------

    def _auto_connect_concepts(
        self,
        concepts: list[Concept],
    ) -> None:
        """
        Automatically connect concepts that share the same domain
        with an ASSOCIATED_WITH relationship.
        """
        if len(concepts) < 2:
            return

        for i in range(len(concepts)):
            for j in range(i + 1, len(concepts)):
                c1 = concepts[i]
                c2 = concepts[j]

                if c1.domain == c2.domain and c1.domain != ConceptDomain.GENERAL:
                    relationship = Relationship(
                        source_id=c1.concept_id,
                        target_id=c2.concept_id,
                        relationship_type=RelationshipType.ASSOCIATED_WITH,
                        weight=0.5,
                        confidence=min(c1.confidence, c2.confidence),
                    )
                    self._graph.add_relationship(relationship)
                    self._memory.store_relationship(relationship)

    def _generate_concept_insight(
        self,
        concept: Concept,
    ) -> UnderstandingInsight:
        """Generate an understanding insight from a single concept."""
        self._insight_counter += 1
        insight_id = f"INS-{self._insight_counter:06d}"

        domain_label = concept.domain.name.lower().replace("_", " ")

        return UnderstandingInsight(
            insight_id=insight_id,
            category=UnderstandingCategory.CONCEPT_INSIGHT,
            summary=f"Concept '{concept.label}' identified in {domain_label} domain.",
            detail=(
                f"The concept '{concept.label}' was extracted from '{concept.source}' "
                f"with {concept.confidence:.0%} confidence. "
                f"It has been observed {concept.frequency} time(s) "
                f"in the '{domain_label}' domain. "
                f"This concept may inform understanding of {domain_label} topics."
            ),
            confidence=concept.confidence,
            related_concept_ids=[concept.concept_id],
            source=concept.source,
        )

    def _generate_pattern_insight(
        self,
        pattern: Pattern,
        concepts: list[Concept],
    ) -> UnderstandingInsight | None:
        """Generate an understanding insight from a detected pattern."""
        if not pattern.related_concept_ids:
            return None

        self._insight_counter += 1
        insight_id = f"INS-{self._insight_counter:06d}"

        return UnderstandingInsight(
            insight_id=insight_id,
            category=UnderstandingCategory.PATTERN_INSIGHT,
            summary=f"Pattern detected: {pattern.label}",
            detail=pattern.description,
            confidence=pattern.confidence,
            related_concept_ids=pattern.related_concept_ids,
            related_pattern_ids=[pattern.pattern_id],
        )