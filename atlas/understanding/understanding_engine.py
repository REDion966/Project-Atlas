"""
Atlas Understanding Engine — Phase 8.2.1a Full Consolidation

Orchestrates the Understanding Layer pipeline with full consolidation.
Both process_text() and process_observation() use identical consolidation.

New pipeline:
  Observation → Concept Extraction → Consolidation → Graph Update →
  Abstraction → Relationship Detection → Relationship Consolidation →
  Pattern Analysis → Pattern Consolidation → Insight Generation →
  Insight Consolidation

Every entry point deepens understanding instead of accumulating duplicates.
"""

from typing import Any

from atlas.experience.models import StructuredExperience
from atlas.understanding.models import (
    BehavioralSignal,
    Concept,
    Pattern,
    Relationship,
    RelationshipType,
    UnderstandingCategory,
    UnderstandingInsight,
    BehaviorExtractor,
)
from atlas.understanding.concept_extractor import ConceptExtractor
from atlas.understanding.experience_bridge import ExperienceBridge
from atlas.understanding.pattern_analyzer import PatternAnalyzer
from atlas.understanding.understanding_graph import UnderstandingGraph
from atlas.understanding.understanding_memory import UnderstandingMemory

# --- Phase 8.2.1a: Consolidation layer ---
from atlas.understanding.consolidation.concept_consolidator import ConceptConsolidator
from atlas.understanding.consolidation.relationship_consolidator import RelationshipConsolidator
from atlas.understanding.consolidation.pattern_consolidator import PatternConsolidator
from atlas.understanding.consolidation.insight_consolidator import InsightConsolidator
from atlas.understanding.consolidation.understanding_scorer import UnderstandingScorer
from atlas.understanding.consolidation.abstraction_registry import AbstractionRegistry


class UnderstandingEngine:
    """
    Orchestrates the Understanding Layer pipeline with full consolidation.

    Both entry points (process_text, process_observation) use identical
    consolidation logic. Storage is always synchronized — graph and
    memory never diverge.

    Dependencies are all optional via injection. Defaults are created
    if not provided, enabling dependency injection for testing.
    """

    def __init__(
        self,
        memory: UnderstandingMemory | None = None,
        graph: UnderstandingGraph | None = None,
        extractor: ConceptExtractor | None = None,
        analyzer: PatternAnalyzer | None = None,
        behavior_extractor: BehaviorExtractor | None = None,
        concept_consolidator: ConceptConsolidator | None = None,
        relationship_consolidator: RelationshipConsolidator | None = None,
        pattern_consolidator: PatternConsolidator | None = None,
        insight_consolidator: InsightConsolidator | None = None,
        understanding_scorer: UnderstandingScorer | None = None,
        abstraction_registry: AbstractionRegistry | None = None,
        experience_bridge: ExperienceBridge | None = None,
    ) -> None:
        self._memory = memory or UnderstandingMemory()
        self._graph = graph or UnderstandingGraph()
        self._extractor = extractor or ConceptExtractor()
        self._analyzer = analyzer or PatternAnalyzer()
        self._behavior_extractor = behavior_extractor or BehaviorExtractor()
        self._experience_bridge = experience_bridge or ExperienceBridge()

        # Consolidation layer — pass storage refs for auto-sync
        self._concept_consolidator = concept_consolidator or ConceptConsolidator(
            memory=self._memory, graph=self._graph,
        )
        self._relationship_consolidator = relationship_consolidator or RelationshipConsolidator()
        self._pattern_consolidator = pattern_consolidator or PatternConsolidator()
        self._insight_consolidator = insight_consolidator or InsightConsolidator()
        self._understanding_scorer = understanding_scorer or UnderstandingScorer()
        self._abstraction_registry = abstraction_registry or AbstractionRegistry()
        self._insight_counter = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def memory(self) -> UnderstandingMemory:
        return self._memory

    @property
    def graph(self) -> UnderstandingGraph:
        return self._graph

    @property
    def behavior_extractor(self) -> BehaviorExtractor:
        return self._behavior_extractor

    @behavior_extractor.setter
    def behavior_extractor(self, extractor: BehaviorExtractor) -> None:
        self._behavior_extractor = extractor

    # ------------------------------------------------------------------
    # Core pipeline — unified for both entry points
    # ------------------------------------------------------------------

    def process_text(
        self,
        text: str,
        source: str = "",
    ) -> list[UnderstandingInsight]:
        """Process text through the full consolidation pipeline."""
        if not text or not text.strip():
            return []
        return self._run_pipeline(source=source, text=text)

    def process_observation(
        self,
        observation: Any,
        source: str = "",
    ) -> list[UnderstandingInsight]:
        """Process observation through the full consolidation pipeline — identical to process_text."""
        texts: list[str] = []
        if hasattr(observation, "description") and observation.description:
            texts.append(str(observation.description))
        if hasattr(observation, "metric_name") and observation.metric_name:
            texts.append(str(observation.metric_name))

        combined_text = " ".join(texts) if texts else str(observation)
        if not combined_text.strip():
            return []

        return self._run_pipeline(source=source or "observation", text=combined_text)

    def process_experiences(
        self,
        experiences: list[StructuredExperience],
        source: str = "experience_bridge",
    ) -> list[UnderstandingInsight]:
        """
        Process structured experiences through the full consolidation pipeline.

        Uses ExperienceBridge to transform experiences into concepts, patterns,
        insights, and relationships, then consolidates them through the same
        path as process_text().
        """
        if not experiences:
            return []

        bridge_result = self._experience_bridge.transform(experiences)

        return self._consolidate_and_store(
            concepts=bridge_result.concepts,
            relationships=bridge_result.relationships,
            patterns=bridge_result.patterns,
            insights=bridge_result.insights,
            source=source,
        )

    def _run_pipeline(self, source: str, text: str) -> list[UnderstandingInsight]:
        """Common pipeline with full consolidation for text/observation input."""

        # 1. Extract raw concepts
        raw_concepts = self._extractor.extract_from_text(text, source=source)

        # 2. Consolidate against existing concepts (storage-aware)
        existing_concepts = self._graph.get_all_concepts()
        concepts = self._concept_consolidator.consolidate(raw_concepts, existing_concepts)

        # 3. Generate abstractions
        abstractions = self._abstraction_registry.generate_abstractions(concepts)
        for abs_concept in abstractions:
            merged = self._concept_consolidator.try_merge_with_existing(
                abs_concept, self._graph.get_all_concepts(),
            )
            if merged is None:
                self._graph.add_concepts([abs_concept])
                self._memory.store_concept(abs_concept)
                concepts = concepts + [abs_concept]

        # 4. Auto-connect concepts → relationships
        new_relationships = self._auto_connect_concepts(concepts)

        # 5-10. Consolidation and storage through shared path
        return self._consolidate_and_store(
            concepts=concepts,
            relationships=new_relationships,
            patterns=self._analyzer.analyze_concepts(concepts),
            insights=self._build_text_insights(concepts, source),
            source=source,
            text=text,
        )

    def _consolidate_and_store(
        self,
        concepts: list[Concept],
        relationships: list[Relationship],
        patterns: list[Pattern],
        insights: list[UnderstandingInsight],
        source: str,
        text: str | None = None,
    ) -> list[UnderstandingInsight]:
        """
        Shared consolidation path for all understanding inputs.

        This method is used by process_text(), process_observation(), and
        process_experiences() to avoid duplicating consolidation logic.
        """
        # 0. Consolidate concepts against existing graph (storage-aware)
        existing_concepts = self._graph.get_all_concepts()
        concepts = self._concept_consolidator.consolidate(concepts, existing_concepts)

        # 1. Generate abstractions (only meaningful for text-derived concepts;
        # experience-derived concepts may already be abstract, but running
        # abstraction registry is safe and idempotent).
        abstractions = self._abstraction_registry.generate_abstractions(concepts)
        for abs_concept in abstractions:
            merged = self._concept_consolidator.try_merge_with_existing(
                abs_concept, self._graph.get_all_concepts(),
            )
            if merged is None:
                self._graph.add_concepts([abs_concept])
                self._memory.store_concept(abs_concept)
                concepts = concepts + [abs_concept]

        # 2. Consolidate relationships (authoritative source: memory)
        existing_rels = self._memory.get_relationships()
        consolidated_rels = self._relationship_consolidator.consolidate(
            relationships, existing_rels,
        )
        # Sync: clear memory relationships, re-add consolidated
        self._memory.clear_relationships()
        for rel in consolidated_rels:
            self._memory.store_relationship(rel)
            self._graph.add_relationship(rel)

        # 3. Consolidate patterns
        existing_patterns = self._memory.get_patterns()
        consolidated_patterns = self._pattern_consolidator.consolidate(
            patterns, existing_patterns,
        )
        self._memory.clear_patterns()
        for pattern in consolidated_patterns:
            self._memory.store_pattern(pattern)

        # 4. Generate and consolidate insights
        raw_insights: list[UnderstandingInsight] = []
        for concept in concepts:
            insight = self._generate_concept_insight(concept)
            raw_insights.append(insight)

        for pattern in consolidated_patterns:
            insight = self._generate_pattern_insight(pattern, concepts)
            if insight is not None:
                raw_insights.append(insight)

        # Add externally supplied insights (e.g., from experience bridge)
        raw_insights.extend(insights)

        existing_insights = self._memory.get_insights()
        consolidated_insights = self._insight_consolidator.consolidate(
            raw_insights, existing_insights,
        )
        self._memory.clear_insights()
        for ins in consolidated_insights:
            self._memory.store_insight(ins)

        # 5. Behavioral signals (only when text is provided)
        if text is not None:
            signals = self._behavior_extractor.extract_signals(text, source=source)
            for signal in signals:
                self._memory.store_signal(signal)

        return consolidated_insights

    def _build_text_insights(
        self,
        concepts: list[Concept],
        source: str,
    ) -> list[UnderstandingInsight]:
        """Build initial insights for text-derived concepts (legacy helper)."""
        # Text pipeline does not pre-generate insights; they are generated
        # inside _consolidate_and_store. This helper returns an empty list
        # so the signature remains uniform.
        return []

    # ------------------------------------------------------------------
    # Analysis queries
    # ------------------------------------------------------------------

    def get_current_understanding(self, n_insights: int = 20) -> dict[str, Any]:
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
            "abstraction_summary": self._abstraction_registry.summary(),
            "understanding_score": self._understanding_scorer.calculate(
                self._graph.get_all_concepts(),
                self._memory.get_relationships(),
                self._memory.get_patterns(),
            ),
        }

    def get_understanding_for_concept(self, label: str, depth: int = 1) -> dict[str, Any]:
        concept = self._graph.get_concept_by_label(label)
        if concept is None:
            return {"found": False, "label": label}

        related = self._graph.find_related_concepts(concept.concept_id, max_depth=depth)
        return {
            "found": True,
            "concept": {"id": concept.concept_id, "label": concept.label,
                       "domain": concept.domain.name, "confidence": concept.confidence,
                       "frequency": concept.frequency},
            "related_concepts": [
                {"id": c.concept_id, "label": c.label, "domain": c.domain.name} for c in related
            ],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _auto_connect_concepts(self, concepts: list[Concept]) -> list[Relationship]:
        """Auto-connect same-domain concepts. Returns new relationships."""
        relationships: list[Relationship] = []
        if len(concepts) < 2:
            return relationships

        for i in range(len(concepts)):
            for j in range(i + 1, len(concepts)):
                c1, c2 = concepts[i], concepts[j]
                if c1.domain == c2.domain and c1.domain is not None:
                    rel = Relationship(
                        source_id=c1.concept_id,
                        target_id=c2.concept_id,
                        relationship_type=RelationshipType.ASSOCIATED_WITH,
                        weight=0.5,
                        confidence=min(c1.confidence, c2.confidence),
                    )
                    relationships.append(rel)
        return relationships

    def _generate_concept_insight(self, concept: Concept) -> UnderstandingInsight:
        self._insight_counter += 1
        domain_label = concept.domain.name.lower().replace("_", " ")
        return UnderstandingInsight(
            insight_id=f"INS-{self._insight_counter:06d}",
            category=UnderstandingCategory.CONCEPT_INSIGHT,
            summary=f"Concept '{concept.label}' identified in {domain_label} domain.",
            detail=f"Extracted from '{concept.source}' with {concept.confidence:.0%} confidence. "
                   f"Observed {concept.frequency} time(s).",
            confidence=concept.confidence,
            related_concept_ids=[concept.concept_id],
            source=concept.source,
        )

    def _generate_pattern_insight(
        self, pattern: Pattern, concepts: list[Concept],
    ) -> UnderstandingInsight | None:
        if not pattern.related_concept_ids:
            return None
        self._insight_counter += 1
        return UnderstandingInsight(
            insight_id=f"INS-{self._insight_counter:06d}",
            category=UnderstandingCategory.PATTERN_INSIGHT,
            summary=f"Pattern detected: {pattern.label}",
            detail=pattern.description,
            confidence=pattern.confidence,
            related_concept_ids=pattern.related_concept_ids,
            related_pattern_ids=[pattern.pattern_id],
        )