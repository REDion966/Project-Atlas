"""Phase 3 integration verification — knowledge/experience/context/evidence.

Demonstrates the Phase 3 completion criterion with concrete, deterministic
evidence: Atlas can retain, retrieve, distinguish, and reason over its own
knowledge, experience, context, and evidence — without an external AI model.

Part 1 establishes that the five domains are separately represented and
retrievable, and do not conflate:
  * conversation/context   -> ConversationState / ConversationContext
  * self-knowledge         -> ArchitectureModel (ComponentRegistry-derived)
  * external/world knowledge -> ValidatedKnowledgeItem (SourceKind.WEB citations)
  * experience/history     -> StructuredExperience
  * evidence/provenance    -> CitationRecord / VerificationReport

Part 2 establishes that retrieved knowledge/evidence reaches a reasoning /
planning decision deterministically, with no external model.
"""

from __future__ import annotations

from datetime import datetime

from atlas.conversation.conversation_context import build_conversation_context
from atlas.conversation.conversation_state import ConversationState
from atlas.conversation.message import Message
from atlas.evolution.decision_intelligence import DecisionIntelligenceEngine
from atlas.evolution.development_gap import (
    DevelopmentGapKind,
    assess_development_gap,
)
from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
)
from atlas.evolution.development_verification import (
    DevelopmentVerification,
    VerificationStatus,
)
from atlas.evolution.knowledge.models import StrategyKnowledge
from atlas.experience.experience_repository import ExperienceRepository
from atlas.experience.models import ExperienceOutcome, StructuredExperience
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.models import ReasoningPlan, ReasoningStep
from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    SourceKind,
    VerificationStatus as ResearchVerificationStatus,
)
from atlas.research.validated_retrieval import (
    ValidatedKnowledgeRetriever,
    ValidatedKnowledgeStatus,
)
from atlas.self_knowledge.architecture_model import build_architecture_model
from atlas.storage.research_storage import ResearchSQLiteStorage


def _self_knowledge_model():
    registry = ComponentRegistry()
    registry.register(
        ComponentMetadata(
            name="memory_service",
            package="atlas.memory.service",
            module_path="atlas.memory.service.memory_manager_service.MemoryManagerService",
            description="Memory retrieval, search, ranking, and storage.",
            status=ComponentStatus.HEALTHY,
            provided_capabilities=["memory_search"],
        )
    )
    return build_architecture_model(registry)


class TestPhase3DomainSeparation:
    def test_five_domains_are_separately_represented_and_retrievable(self, tmp_path):
        # 1. Conversation/context — bounded projection of prior turns + state.
        context = build_conversation_context(
            [
                Message(role="user", content="My project is called Atlas."),
                Message(role="assistant", content="Noted."),
            ],
            ConversationState(current_subject="Atlas"),
        )
        assert context.has_history
        assert context.state.current_subject == "Atlas"
        assert "My project is called Atlas." in context.recent_user_turns

        # 2. Self-knowledge — derived from the ComponentRegistry (no citations).
        model = _self_knowledge_model()
        component = next(c for c in model.components if c.name == "memory_service")
        assert component.provided_capabilities == ("memory_search",)
        assert not hasattr(component, "citations")

        # 3. External/world knowledge — provenance-labelled (SourceKind.WEB).
        storage = ResearchSQLiteStorage(db_path=tmp_path / "research.db")
        storage.initialize()
        try:
            storage.store_claim(
                KnowledgeClaim(
                    claim_id="c-ext",
                    statement="External fact about vector databases",
                    citations=(
                        CitationRecord(
                            record_id="cite:ext",
                            source_uri="https://example.com/doc",
                            source_kind=SourceKind.WEB,
                        ),
                    ),
                    confidence=0.8,
                )
            )
            storage.store_verification(
                ClaimVerification(
                    verification_id="v-ext",
                    claim_id="c-ext",
                    status=ResearchVerificationStatus.SUPPORTED,
                    score=0.9,
                )
            )
            result = ValidatedKnowledgeRetriever(storage).retrieve("vector databases")
            assert result.status is ValidatedKnowledgeStatus.OK
            external = result.items[0]
            assert external.citations[0].source_kind is SourceKind.WEB
            assert not hasattr(external, "provided_capabilities")
        finally:
            storage.close()

        # 4. Experience/history — a structured pipeline-execution record.
        repo = ExperienceRepository()
        repo.store_experience(
            StructuredExperience(
                experience_id="EXP-INT-1",
                timestamp=datetime.now(),
                duration_ms=1.0,
                pipeline_path=["understanding", "reasoning"],
                outcome=ExperienceOutcome.SUCCESS,
            )
        )
        experience = repo.get_experience("EXP-INT-1")
        assert experience is not None and experience.pipeline_path == [
            "understanding",
            "reasoning",
        ]
        assert not hasattr(experience, "citations")

        # 5. Evidence/provenance — the citation links knowledge to its source and
        # a verification report cites concrete development evidence.
        assert external.citations[0].source_uri == "https://example.com/doc"
        outcome = DevelopmentOutcome(
            outcome=DevelopmentOutcomeStatus.SUCCESS,
            proposal_id="P",
            plan_id="PL",
            iteration=1,
            verification_passed=True,
            test_outcome="passed",
            changed_files=["atlas/x.py"],
        )
        report = DevelopmentVerification().verify(
            type(
                "R",
                (),
                {
                    "status": DevelopmentOutcomeStatus.SUCCESS,
                    "outcomes": [outcome],
                    "iterations_used": 1,
                    "message": "",
                },
            )()
        )
        assert report.status is VerificationStatus.VERIFIED
        assert report.changed_files == ("atlas/x.py",)


class TestPhase3KnowledgeToReasoningIntegration:
    def test_retrieved_knowledge_reaches_reasoning_without_external_model(self, tmp_path):
        # Retrieved learning evidence changes a reasoning capability decision.
        class _Provider:
            def get_strategy_by_name(self, name):
                if name == "task_execution":
                    from atlas.learning_engine.models import StrategyPerformance

                    return StrategyPerformance(
                        strategy_id="S",
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
        assert [c.name for c in CapabilityAnalyzer().analyze(plan)] == [
            "knowledge_retrieval",
            "task_execution",
        ]
        assert [
            c.name for c in CapabilityAnalyzer(learning_provider=_Provider()).analyze(plan)
        ] == ["task_execution", "knowledge_retrieval"]

        # Persisted knowledge produces a planning context consumed by planning.
        class _Query:
            def get_patterns_by_area(self, area, n=20):
                return []

            def get_bottlenecks(self, min_recurrences=3, n=20):
                return []

            def get_bottlenecks_by_area(self, area, n=20):
                return []

            def get_effective_strategies(self, n=20):
                return [
                    StrategyKnowledge(
                        strategy_key="retry",
                        strategy_name="Retry",
                        effectiveness=0.8,
                        confidence=0.7,
                        occurrence_count=5,
                        metadata={"area": "runtime"},
                    )
                ]

            def get_ineffective_strategies(self, n=20):
                return []

            def get_capabilities(self, n=20):
                return []

        context = DecisionIntelligenceEngine(knowledge_query=_Query()).get_planning_context(
            weaknesses=[type("W", (), {"area": "runtime"})()]
        )
        assert "runtime" in context.strategy_suggestions

        # Validated external knowledge changes a decision (retrieval -> decision).
        storage = ResearchSQLiteStorage(db_path=tmp_path / "r.db")
        storage.initialize()
        try:
            storage.store_claim(
                KnowledgeClaim(
                    claim_id="c-int",
                    statement="adapter already among supported vector databases",
                    confidence=0.8,
                )
            )
            storage.store_verification(
                ClaimVerification(
                    verification_id="v-int",
                    claim_id="c-int",
                    status=ResearchVerificationStatus.SUPPORTED,
                    score=0.9,
                )
            )
            retriever = ValidatedKnowledgeRetriever(storage)
            without = assess_development_gap(
                "adapter already among", capability_names=["research.query"]
            )
            with_knowledge = assess_development_gap(
                "adapter already among",
                capability_names=["research.query"],
                knowledge_retriever=retriever,
            )
            assert without.kind is DevelopmentGapKind.MISSING_KNOWLEDGE
            assert with_knowledge.kind is DevelopmentGapKind.MISSING_CAPABILITY
        finally:
            storage.close()
