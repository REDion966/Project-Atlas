"""
Atlas Understanding Consolidation — Phase 8.2.1

Deepens understanding by consolidating duplicate concepts,
relationships, and patterns. Prevents knowledge bloat by
merging semantically identical entities and strengthening
existing ones with repeated evidence.

Pure logic only. No AI providers. No infrastructure.
"""

from atlas.understanding.consolidation.concept_consolidator import ConceptConsolidator
from atlas.understanding.consolidation.relationship_consolidator import RelationshipConsolidator
from atlas.understanding.consolidation.pattern_consolidator import PatternConsolidator
from atlas.understanding.consolidation.understanding_scorer import UnderstandingScorer
from atlas.understanding.consolidation.abstraction_engine import AbstractionEngine
from atlas.understanding.consolidation.insight_consolidator import InsightConsolidator
from atlas.understanding.consolidation.abstraction_registry import (
    AbstractionRegistry,
    AbstractionRule,
)

__all__ = [
    "ConceptConsolidator",
    "RelationshipConsolidator",
    "PatternConsolidator",
    "InsightConsolidator",
    "UnderstandingScorer",
    "AbstractionEngine",
    "AbstractionRegistry",
    "AbstractionRule",
]