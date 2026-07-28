"""
Atlas Evolution Package — Phase 7.0 Self-Evolution Foundation.

This package defines the architecture for Atlas's cognitive self-evolution.
It is architecture-only: no component in this package may directly modify
the repository, execute code, generate code, or perform web research.

All components are pure logic with no AI provider dependencies.
Atlas intelligence owns evolution. AI models are only reasoning resources.

Phase 11.0 — Added EvolutionExecutionEngine and ExecutionLevel.
"""

from atlas.evolution.models import (
    ApprovalDecision,
    ApprovalRequest,
    EvolutionProposal,
    EvolutionRecord,
    ExecutionLevel,
    ExecutionResult,
    ImprovementPlan,
    ImprovementPriority,
    ImprovementStatus,
    Observation,
    ObservationCategory,
    ProposalStatus,
    ResearchQuery,
    ResearchResult,
    Weakness,
)
from atlas.evolution.self_observation import SelfObservationEngine
from atlas.evolution.improvement_planner import ImprovementPlanner
from atlas.evolution.proposal_generator import ProposalGenerator
from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.execution_engine import EvolutionExecutionEngine

__all__ = [
    "ApprovalDecision",
    "ApprovalManager",
    "ApprovalRequest",
    "EvolutionExecutionEngine",
    "EvolutionMemory",
    "EvolutionProposal",
    "EvolutionRecord",
    "ExecutionLevel",
    "ExecutionResult",
    "ImprovementPlan",
    "ImprovementPlanner",
    "ImprovementPriority",
    "ImprovementStatus",
    "Observation",
    "ObservationCategory",
    "ProposalGenerator",
    "ProposalStatus",
    "ResearchQuery",
    "ResearchResult",
    "SelfObservationEngine",
    "Weakness",
]
