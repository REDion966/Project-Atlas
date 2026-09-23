"""Phase 4.8 — Evidence-based decision making: evidence contract.

Investigation result: reasoning/planning already consume evidence to influence
decisions via the existing Phase 3 evidence architecture, so no new evidence
framework was introduced.

* ``CapabilityAnalyzer(learning_provider=...)`` — retrieved strategy evidence
  changes capability selection (bounded).
* ``DecisionIntelligenceEngine`` — persisted knowledge produces a
  ``PlanningContext`` consumed by planning.
* ``compute_decision_quality`` — research evidence strength feeds the decision.
* Unsupported/unverified information is not treated as authoritative.
"""

from __future__ import annotations

from atlas.evolution.decision_intelligence import DecisionIntelligenceEngine
from atlas.evolution.decision_quality import compute_decision_quality
from atlas.evolution.knowledge.models import (
    CapabilityEvolution,
    StrategyKnowledge,
)
from atlas.learning_engine.models import StrategyPerformance
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.models import ReasoningPlan, ReasoningStep
from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    SourceKind,
    VerificationStatus,
)
from atlas.research.validated_retrieval import (
    ValidatedKnowledgeRetriever,
    ValidatedKnowledgeStatus,
)
from atlas.storage.research_storage import ResearchSQLiteStorage


class _Provider:
    def get_strategy_by_name(self, name):
        if name == "task_execution":
            return StrategyPerformance(
                strategy_id="S",
                strategy_name="task_execution",
                strategy_type="capability",
                total_uses=10,
                success_count=10,
                failure_count=0,
            )
        return None


class _KnowledgeQuery:
    def __init__(self):
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
                capability_name="memory_retrieval", assessments=[0.6], observed_count=1
            )
        ]

    def get_patterns_by_area(self, area, n=20):
        return []

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


class TestPhase48EvidenceDecisions:
    def test_retained_evidence_changes_capability_selection(self):
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

    def test_persisted_knowledge_produces_planning_context(self):
        context = DecisionIntelligenceEngine(
            knowledge_query=_KnowledgeQuery()
        ).get_planning_context(weaknesses=[type("W", (), {"area": "runtime"})()])
        assert "runtime" in context.strategy_suggestions
        assert context.capability_signals.get("memory_retrieval") is not None

    def test_research_evidence_strength_feeds_the_decision(self):
        no_evidence = compute_decision_quality(
            overall_confidence=0.5,
            previous_attempts=None,
            unknown_target_count=0,
            known_target_count=1,
            dependency_count=0,
            research_confidence=None,
            has_research_claim_support=False,
        )
        with_evidence = compute_decision_quality(
            overall_confidence=0.5,
            previous_attempts=None,
            unknown_target_count=0,
            known_target_count=1,
            dependency_count=0,
            research_confidence=0.9,
            has_research_claim_support=True,
        )
        assert with_evidence["research_evidence_strength"] > 0.0
        assert (
            with_evidence["research_evidence_strength"]
            > no_evidence["research_evidence_strength"]
        )

    def test_unverified_information_does_not_become_authoritative(self, tmp_path):
        storage = ResearchSQLiteStorage(db_path=tmp_path / "r.db")
        storage.initialize()
        try:
            storage.store_claim(
                KnowledgeClaim(
                    claim_id="c",
                    statement="unsupported external claim about widgets",
                    citations=(
                        CitationRecord(
                            record_id="cite",
                            source_uri="https://example.com/x",
                            source_kind=SourceKind.WEB,
                        ),
                    ),
                )
            )
            # No verification → not authoritative.
            result = ValidatedKnowledgeRetriever(storage).retrieve("widgets")
            assert result.status is ValidatedKnowledgeStatus.EMPTY

            # Even a contradicted verification does not make it authoritative.
            storage.store_verification(
                ClaimVerification(
                    verification_id="v",
                    claim_id="c",
                    status=VerificationStatus.CONTRADICTED,
                    score=0.1,
                )
            )
            assert (
                ValidatedKnowledgeRetriever(storage).retrieve("widgets").status
                is ValidatedKnowledgeStatus.EMPTY
            )
        finally:
            storage.close()
