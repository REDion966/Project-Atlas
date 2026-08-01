"""
Atlas Evolution Package — Phase 7.0 Self-Evolution Foundation.

This package defines the architecture for Atlas's cognitive self-evolution.
It is architecture-only: no component in this package may directly modify
the repository, execute code, generate code, or perform web research.

All components are pure logic with no AI provider dependencies.
Atlas intelligence owns evolution. AI models are only reasoning resources.

Phase 11.0 — Added EvolutionExecutionEngine and ExecutionLevel.
Phase 12.0 — Added EvolutionInsight dataclass for evolution outcome analysis.
Phase 12.1 — Added InsightScorer for deterministic outcome scoring.
Phase 12.2 — Added EvolutionIntelligenceEngine for proposal analysis.
"""

from atlas.evolution.models import (
    ApprovalDecision,
    ApprovalRequest,
    EvolutionInsight,
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
from atlas.evolution.execution_gateway import (
    EvolutionExecutionGateway,
    GatewayExecutionResult,
)
from atlas.evolution.insight_scorer import InsightScorer
from atlas.evolution.intelligence_engine import EvolutionIntelligenceEngine
from atlas.evolution.research_coordinator import ResearchCoordinator

# --- Phase 14.1/14.2: Decision Intelligence ---
from atlas.evolution.decision_models import (
    AreaAdjustment,
    BottleneckAlert,
    CapabilitySignal,
    PlanningContext,
    StrategySuggestion,
)
from atlas.evolution.decision_intelligence import DecisionIntelligenceEngine

# --- Phase 13.1: Governance ---
from atlas.evolution.governance import (
    ConstraintRegistry,
    GovernanceDecision,
    GovernanceRule,
    RuleEngine,
    ScopeType,
)

# --- Phase 13.3: Evolution Scheduler ---
from atlas.evolution.scheduler import EvolutionScheduler, EvolutionSchedulerResult

__all__ = [
    "ApprovalDecision",
    "ApprovalManager",
    "ApprovalRequest",
    "AreaAdjustment",
    "BottleneckAlert",
    "CapabilitySignal",
    "ConstraintRegistry",
    "EvolutionExecutionEngine",
    "EvolutionExecutionGateway",
    "EvolutionInsight",
    "EvolutionIntelligenceEngine",
    "DecisionIntelligenceEngine",
    "PlanningContext",
    "StrategySuggestion",
    "GatewayExecutionResult",
    "EvolutionMemory",
    "EvolutionProposal",
    "EvolutionRecord",
    "EvolutionScheduler",
    "EvolutionSchedulerResult",
    "ExecutionLevel",
    "ExecutionResult",
    "GovernanceDecision",
    "GovernanceRule",
    "ImprovementPlan",
    "ImprovementPlanner",
    "ImprovementPriority",
    "ImprovementStatus",
    "InsightScorer",
    "Observation",
    "ObservationCategory",
    "ProposalGenerator",
    "ProposalStatus",
    "ResearchCoordinator",
    "ResearchQuery",
    "ResearchResult",
    "RuleEngine",
    "ScopeType",
    "SelfObservationEngine",
    "Weakness",
]
