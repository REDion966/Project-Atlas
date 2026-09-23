"""Phase 3.7 — Knowledge retrieval integrated with reasoning: evidence contract.

Investigation result (evidence, not aspiration): Atlas already bridges retrieved
knowledge/evidence into its decision, reasoning and planning paths — no new
reasoning engine, RAG, or vector layer was introduced (Phase 4 is reserved for
the broader reasoning/planning system).

Verified bridges:

* Retained strategy evidence → reasoning capability selection:
  ``CapabilityAnalyzer(learning_provider=...)`` adjusts capability priority from
  stored performance within a bounded range.
* Validated external knowledge → decision: ``assess_development_gap`` consults
  ``ValidatedKnowledgeRetriever`` (a SUPPORTED claim changes the verdict).
* Consolidated/persisted knowledge → planning: ``DecisionIntelligenceEngine``
  reads ``EvolutionKnowledgeQuery`` and produces a ``PlanningContext``.
* Structured turn meaning → reasoning: the ``RuntimeCoordinator`` REASONING
  stage consumes the projected meaning (L7).

These tests pin that retrieved information actually reaches and influences a
reasoning/planning decision, deterministically and without an external model.
"""

from __future__ import annotations

from atlas.evolution.decision_intelligence import DecisionIntelligenceEngine
from atlas.evolution.development_gap import (
    DevelopmentGapKind,
    assess_development_gap,
)
from atlas.evolution.knowledge.models import (
    CapabilityEvolution,
    RecurringOutcomePattern,
    StrategyKnowledge,
)
from atlas.learning_engine.models import StrategyPerformance
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.models import ReasoningPlan, ReasoningStep
from atlas.reasoning.planning import PlanningEngine
from atlas.reasoning.controller import ReasoningController
from atlas.conversation.turn_meaning import TurnMeaning
from atlas.runtime.runtime_coordinator import RuntimeCoordinator
from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    SourceKind,
    VerificationStatus as ResearchVerificationStatus,
)
from atlas.research.validated_retrieval import ValidatedKnowledgeRetriever


class _FakeKnowledgeQuery:
    """Minimal stand-in for the persisted knowledge query surface."""

    def __init__(self) -> None:
        self._patterns = [
            RecurringOutcomePattern(
                pattern_id="PAT-runtime-failure",
                area="runtime",
                outcome="failure",
                occurrence_count=10,
                success_count=0,
                failure_count=10,
                confidence=0.9,
            )
        ]
        self._strategies = [
            StrategyKnowledge(
                strategy_key="retry",
                strategy_name="Retry",
                effectiveness=0.8,
                confidence=0.7,
                occurrence_count=5,
                metadata={"area": "runtime"},
            )
        ]
        self._capabilities = [
            CapabilityEvolution(
                capability_name="memory_retrieval",
                assessments=[0.6, 0.7],
                observed_count=2,
            )
        ]

    def get_patterns_by_area(self, area, n=20):
        return [p for p in self._patterns if p.area == area]

    def get_bottlenecks(self, min_recurrences=3, n=20):
        return []

    def get_bottlenecks_by_area(self, area, n=20):
        return []

    def get_effective_strategies(self, n=20):
        return list(self._strategies)

    def get_ineffective_strategies(self, n=20):
        return []

    def get_capabilities(self, n=20):
        return list(self._capabilities)


def _coordinator() -> RuntimeCoordinator:
    registry = CapabilityRegistry()
    for name in ("conversation", "knowledge_retrieval", "task_execution"):
        registry.register(
            name,
            lambda params, _n=name: ExecutionResult(
                capability=_n, success=True, output={}
            ),
        )
    return RuntimeCoordinator(
        reasoning_controller=ReasoningController(),
        capability_analyzer=CapabilityAnalyzer(),
        capability_registry=registry,
        capability_router=CapabilityRouter(registry),
        capability_dispatcher=CapabilityDispatcher(registry),
        planning_engine=PlanningEngine(),
    )


class TestPhase37KnowledgeReasoningEvidence:
    def test_retained_evidence_changes_a_reasoning_decision(self):
        class _Provider:
            def get_strategy_by_name(self, name):
                if name == "task_execution":
                    return StrategyPerformance(
                        strategy_id="S-E",
                        strategy_name="task_execution",
                        strategy_type="capability",
                        total_uses=10,
                        success_count=10,
                        failure_count=0,
                    )
                return None

        plan = ReasoningPlan(
            goal="query then execute",
            steps=[ReasoningStep(action="query"), ReasoningStep(action="execute")],
        )

        without = [c.name for c in CapabilityAnalyzer().analyze(plan)]
        with_evidence = [
            c.name for c in CapabilityAnalyzer(learning_provider=_Provider()).analyze(plan)
        ]

        # Baseline: knowledge_retrieval(8) before task_execution(7).
        assert without == ["knowledge_retrieval", "task_execution"]
        # Retrieved evidence promotes the proven capability in the decision.
        assert with_evidence == ["task_execution", "knowledge_retrieval"]

    def test_persisted_knowledge_produces_a_planning_context(self):
        engine = DecisionIntelligenceEngine(knowledge_query=_FakeKnowledgeQuery())
        weakness = type("Weakness", (), {"area": "runtime"})()

        context = engine.get_planning_context(weaknesses=[weakness])

        assert "runtime" in context.area_adjustments
        assert "runtime" in context.strategy_suggestions
        assert context.capability_signals.get("memory_retrieval") is not None
        assert context.overall_confidence > 0.0

    def test_validated_knowledge_changes_a_decision(self, tmp_path):
        from atlas.storage.research_storage import ResearchSQLiteStorage

        storage = ResearchSQLiteStorage(db_path=tmp_path / "r.db")
        storage.initialize()
        try:
            storage.store_claim(
                KnowledgeClaim(
                    claim_id="c-p37",
                    statement="adapter already among supported vector databases",
                    citations=(
                        CitationRecord(
                            record_id="cite:p37",
                            source_uri="https://example.com/db",
                            source_kind=SourceKind.WEB,
                        ),
                    ),
                    confidence=0.8,
                )
            )
            storage.store_verification(
                ClaimVerification(
                    verification_id="v-p37",
                    claim_id="c-p37",
                    status=ResearchVerificationStatus.SUPPORTED,
                    score=0.9,
                )
            )
            retriever = ValidatedKnowledgeRetriever(storage)

            without = assess_development_gap(
                "adapter already among", capability_names=["research.query"]
            )
            with_validated = assess_development_gap(
                "adapter already among",
                capability_names=["research.query"],
                knowledge_retriever=retriever,
            )

            # Retrieved validated knowledge changes the adjudicated decision.
            assert without.kind is DevelopmentGapKind.MISSING_KNOWLEDGE
            assert with_validated.kind is DevelopmentGapKind.MISSING_CAPABILITY
        finally:
            storage.close()

    def test_structured_meaning_reaches_the_reasoning_stage(self):
        coordinator = _coordinator()
        meaning = TurnMeaning(intent={"goal": "external-goal"}, source_text="hello")

        result = coordinator.process("hello", turn_meaning=meaning)

        reasoning = next(
            stage for stage in result.stages if stage.stage.name == "REASONING"
        )
        assert reasoning.data["meaning"]["goal"] == "external-goal"
        assert "external-goal" in reasoning.data["goal"]
