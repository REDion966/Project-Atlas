"""Phase 4.6 — Uncertainty-aware decisions: evidence contract.

Investigation result: Atlas already represents and responds to uncertainty
deterministically, so no new uncertainty model was introduced.

* Unresolved ambiguity → L7 ``needs_clarification`` fails closed: the REASONING
  stage yields no capabilities and PLANNING reports a blocked status.
* ``atlas/evolution/decision_quality.py`` — evidence/uncertainty-aware quality
  signals (confidence, unknown targets, research evidence strength).
* ``atlas/evolution/development_verification.py`` — absent/ambiguous evidence is
  reported UNVERIFIABLE, never fabricated VERIFIED.
* ``CapabilityModel`` distinguishes unknown dependency/availability from known.
"""

from __future__ import annotations

from types import SimpleNamespace

from atlas.cognition.models import StageType
from atlas.evolution.decision_quality import compute_decision_quality
from atlas.evolution.development_models import DevelopmentOutcomeStatus
from atlas.evolution.development_verification import (
    DevelopmentVerification,
    VerificationStatus,
)
from atlas.conversation.turn_meaning import TurnMeaning
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.planning.engine import PlanningEngine
from atlas.runtime.runtime_coordinator import RuntimeCoordinator


def _coordinator() -> RuntimeCoordinator:
    registry = CapabilityRegistry()
    for name in ("conversation", "knowledge_retrieval"):
        registry.register(
            name,
            lambda params, _n=name: ExecutionResult(capability=_n, success=True, output={}),
        )
    return RuntimeCoordinator(
        reasoning_controller=ReasoningController(),
        capability_analyzer=CapabilityAnalyzer(),
        capability_registry=registry,
        capability_router=CapabilityRouter(registry),
        capability_dispatcher=CapabilityDispatcher(registry),
        planning_engine=PlanningEngine(),
    )


class TestPhase46Uncertainty:
    def test_unresolved_ambiguity_blocks_reasoning_and_planning(self):
        meaning = TurnMeaning(
            intent={"needs_clarification": True}, source_text="do the thing"
        )
        result = _coordinator().process("do the thing", turn_meaning=meaning)
        by_stage = {stage.stage: stage for stage in result.stages}

        reasoning = by_stage[StageType.REASONING].data
        assert reasoning["capabilities"] == []
        assert reasoning.get("requires_clarification") is True
        assert by_stage[StageType.PLANNING].data["status"] == "blocked"

    def test_certain_meaning_allows_reasoning(self):
        result = _coordinator().process(
            "hello", turn_meaning=TurnMeaning(intent={}, source_text="hello")
        )
        by_stage = {stage.stage: stage for stage in result.stages}
        assert by_stage[StageType.REASONING].data["capabilities"]

    def test_decision_quality_reflects_evidence_and_unknowns(self):
        uncertain = compute_decision_quality(
            overall_confidence=None,
            previous_attempts=None,
            unknown_target_count=5,
            known_target_count=0,
            dependency_count=0,
            research_confidence=None,
            has_research_claim_support=False,
        )
        certain = compute_decision_quality(
            overall_confidence=0.9,
            previous_attempts=None,
            unknown_target_count=0,
            known_target_count=3,
            dependency_count=2,
            research_confidence=0.9,
            has_research_claim_support=True,
        )
        assert certain["final_priority_score"] > uncertain["final_priority_score"]
        assert certain["confidence_score"] > uncertain["confidence_score"]
        assert certain["research_evidence_strength"] > uncertain["research_evidence_strength"]

    def test_absent_evidence_is_unverifiable_not_verified(self):
        report = DevelopmentVerification().verify(
            SimpleNamespace(
                status=DevelopmentOutcomeStatus.FAILED,
                outcomes=[],
                iterations_used=0,
                message="",
            )
        )
        assert report.status is VerificationStatus.UNVERIFIABLE
        assert report.all_tests_passed is None
