"""Atlas Post-Core F4 — Governed Adaptation Decision Engine.

Translates F3 lifecycle assessments into DRAFT ``EvolutionProposal``
candidates using the existing proposal model/boundary.

Pipeline:

    F1 EnvironmentChange
        + F2 FreshnessAssessment
        + F3 LifecycleAssessment
            -> AdaptationDecisionEngine.decide()
            -> AdaptationProposalCandidate       (proposal candidate only)
            -> build_proposals() -> EvolutionProposal (status=DRAFT)
            -> EXISTING ApprovalManager / governance
            -> EXISTING DevelopmentPlanner / SelfDevelopmentLoop

F4 never approves, never executes, never persists, never invents
replacements/fallbacks, and never bypasses governance.
"""

from atlas.evolution.adaptation.models import (
    AdaptationProposalCandidate,
    AdaptationRisk,
)
from atlas.evolution.adaptation.policy import AdaptationDecisionPolicy
from atlas.evolution.adaptation.engine import AdaptationDecisionEngine
from atlas.evolution.adaptation.evaluation import (
    AdaptationEvaluation,
    AdaptationEvaluationState,
    AdaptationFeedback,
    AdaptationFeedbackSignal,
)
from atlas.evolution.adaptation.evaluator import (
    DEFAULT_MAX_ITEMS,
    AdaptationEvaluator,
)
from atlas.evolution.adaptation.orchestrator import (
    AdaptationCycleResult,
    AdaptationOrchestrator,
)

__all__ = [
    "AdaptationCycleResult",
    "AdaptationDecisionEngine",
    "AdaptationDecisionPolicy",
    "AdaptationEvaluation",
    "AdaptationEvaluationState",
    "AdaptationEvaluator",
    "AdaptationFeedback",
    "AdaptationFeedbackSignal",
    "AdaptationOrchestrator",
    "AdaptationProposalCandidate",
    "AdaptationRisk",
    "DEFAULT_MAX_ITEMS",
]