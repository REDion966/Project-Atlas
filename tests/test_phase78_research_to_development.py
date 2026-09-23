"""Phase 7.8 — Research → capability/development integration: evidence contract.

Investigation result: validated research already feeds Atlas decision-making via
the existing Phase-3/5 bridge (``assess_development_gap`` +
``ValidatedKnowledgeRetriever``), so no new bridge was introduced.

Research informs decisions; it never authorizes or activates anything.
"""

from __future__ import annotations

from atlas.evolution.development_gap import (
    DevelopmentGapKind,
    assess_development_gap,
)
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    SourceKind,
    VerificationStatus,
)
from atlas.research.validated_retrieval import ValidatedKnowledgeRetriever
from atlas.storage.research_storage import ResearchSQLiteStorage

_REQUEST = "adapter already among supported vector databases"


def _store_supported(storage):
    storage.store_claim(
        KnowledgeClaim(
            claim_id="c-r78",
            statement="adapter already among supported vector databases",
            citations=(
                CitationRecord(
                    record_id="cite:r78",
                    source_uri="https://example.com/db",
                    source_kind=SourceKind.WEB,
                ),
            ),
            confidence=0.8,
        )
    )
    storage.store_verification(
        ClaimVerification(
            verification_id="v-r78",
            claim_id="c-r78",
            status=VerificationStatus.SUPPORTED,
            score=0.9,
        )
    )


class TestPhase78ResearchToDevelopment:
    def test_validated_research_changes_a_development_decision(self, tmp_path):
        storage = ResearchSQLiteStorage(db_path=tmp_path / "r.db")
        storage.initialize()
        try:
            _store_supported(storage)
            retriever = ValidatedKnowledgeRetriever(storage)

            without = assess_development_gap(_REQUEST, capability_names=["research.query"])
            with_research = assess_development_gap(
                _REQUEST,
                capability_names=["research.query"],
                knowledge_retriever=retriever,
            )
            assert without.kind is DevelopmentGapKind.MISSING_KNOWLEDGE
            assert with_research.kind is DevelopmentGapKind.MISSING_CAPABILITY
        finally:
            storage.close()

    def test_research_does_not_authorize_or_activate_a_capability(self, tmp_path):
        registry = CapabilityRegistry()
        storage = ResearchSQLiteStorage(db_path=tmp_path / "r.db")
        storage.initialize()
        try:
            _store_supported(storage)
            retriever = ValidatedKnowledgeRetriever(storage)

            # The research-informed decision is advisory only.
            assess_development_gap(
                _REQUEST,
                capability_names=registry.registered_names,
                knowledge_retriever=retriever,
            )
            # Nothing was registered or activated by researching.
            assert registry.registered_names == []
        finally:
            storage.close()

    def test_unverified_research_cannot_justify_a_capability_conclusion(self, tmp_path):
        storage = ResearchSQLiteStorage(db_path=tmp_path / "r.db")
        storage.initialize()
        try:
            storage.store_claim(
                KnowledgeClaim(
                    claim_id="c-raw",
                    statement="adapter already among supported vector databases",
                    confidence=0.4,
                )
            )
            gap = assess_development_gap(
                _REQUEST,
                capability_names=["research.query"],
                knowledge_retriever=ValidatedKnowledgeRetriever(storage),
            )
            # No validation -> research cannot justify a capability conclusion.
            assert gap.kind is DevelopmentGapKind.MISSING_KNOWLEDGE
        finally:
            storage.close()
