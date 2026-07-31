"""
Atlas Evolution Knowledge — Phase 13.5

Persistent evolution memory: the durable, consolidated long-term
knowledge layer about Atlas itself.

This package aggregates the raw evolution record streams (observations,
weaknesses, proposals, approvals, executions, insights, goals) into
durable knowledge: recurring outcome patterns, strategy effectiveness,
capability evolution history, and recurring bottlenecks.

Pure logic. No AI. No infrastructure. No autonomous behavior.
"""

from atlas.evolution.knowledge.models import (
    BottleneckProfile,
    CapabilityEvolution,
    EvolutionKnowledgeSnapshot,
    RecurringOutcomePattern,
    StrategyKnowledge,
)
from atlas.evolution.knowledge.normalizer import (
    insight_area,
    is_canonical_area,
    normalize_area,
    normalize_capability,
    normalize_outcome_key,
    normalize_strategy,
    normalize_weakness_key,
)
from atlas.evolution.knowledge.consolidator import EvolutionKnowledgeConsolidator
from atlas.evolution.knowledge.repository import EvolutionKnowledgeRepository
from atlas.evolution.knowledge.query import EvolutionKnowledgeQuery
from atlas.evolution.knowledge.pipeline import EvolutionKnowledgePipeline

__all__ = [
    "EvolutionKnowledgePipeline",
    "BottleneckProfile",
    "CapabilityEvolution",
    "EvolutionKnowledgeConsolidator",
    "EvolutionKnowledgeQuery",
    "EvolutionKnowledgeRepository",
    "EvolutionKnowledgeSnapshot",
    "RecurringOutcomePattern",
    "StrategyKnowledge",
    "insight_area",
    "is_canonical_area",
    "normalize_area",
    "normalize_capability",
    "normalize_outcome_key",
    "normalize_strategy",
    "normalize_weakness_key",
]
