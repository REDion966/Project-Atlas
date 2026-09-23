"""Phase 5.7 — Capability gap detection: evidence contract.

Investigation result: Atlas already detects genuine capability/knowledge gaps
deterministically and evidence-based, so no new gap detector was introduced.

* ``assess_development_gap`` classifies a request as
  ALREADY_SUPPORTED / MISSING_CAPABILITY / MISSING_KNOWLEDGE / UNCLEAR using
  capability-name overlap and the Phase-3 validated knowledge retriever; it
  fabricates nothing and fails closed to UNCLEAR.
* Capability availability (``CapabilityModel``) distinguishes "exists but
  unavailable" from "exists and available".
* Nothing treats an absent capability as available merely because a model could
  theoretically implement it.
"""

from __future__ import annotations

from atlas.evolution.development_gap import (
    DevelopmentGapKind,
    assess_development_gap,
)
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    SourceKind,
    VerificationStatus,
)
from atlas.research.validated_retrieval import ValidatedKnowledgeRetriever
from atlas.self_knowledge.capability_model import build_capability_model
from atlas.storage.research_storage import ResearchSQLiteStorage


class TestPhase57CapabilityGap:
    def test_gap_kinds_for_supported_missing_and_ambiguous(self):
        supported = assess_development_gap("memory search", capability_names=["memory_search"])
        assert supported.kind is DevelopmentGapKind.ALREADY_SUPPORTED

        missing = assess_development_gap(
            "quantum stabilizer control", capability_names=["memory_search"]
        )
        assert missing.kind is DevelopmentGapKind.MISSING_KNOWLEDGE

        ambiguous = assess_development_gap("   ", capability_names=["memory_search"])
        assert ambiguous.kind is DevelopmentGapKind.UNCLEAR

    def test_validated_knowledge_moves_gap_to_missing_capability(self, tmp_path):
        storage = ResearchSQLiteStorage(db_path=tmp_path / "r.db")
        storage.initialize()
        try:
            storage.store_claim(
                KnowledgeClaim(
                    claim_id="c",
                    statement="adapter already among supported vector databases",
                    confidence=0.8,
                )
            )
            storage.store_verification(
                ClaimVerification(
                    verification_id="v",
                    claim_id="c",
                    status=VerificationStatus.SUPPORTED,
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

    def test_unverified_knowledge_does_not_imply_a_capability(self, tmp_path):
        storage = ResearchSQLiteStorage(db_path=tmp_path / "r.db")
        storage.initialize()
        try:
            storage.store_claim(
                KnowledgeClaim(claim_id="c", statement="unverified widget fact", confidence=0.4)
            )
            gap = assess_development_gap(
                "unverified widget fact",
                capability_names=["memory_search"],
                knowledge_retriever=ValidatedKnowledgeRetriever(storage),
            )
            assert gap.kind is DevelopmentGapKind.MISSING_KNOWLEDGE
        finally:
            storage.close()

    def test_gap_detection_does_not_hallucinate_capabilities(self):
        gap = assess_development_gap(
            "frobnicate the quantum widget", capability_names=["memory_search"]
        )
        assert gap.kind is not DevelopmentGapKind.ALREADY_SUPPORTED
        assert gap.matched == ()

    def test_exists_but_unavailable_is_distinguishable(self):
        registry = ComponentRegistry()
        registry.register(
            ComponentMetadata(
                name="provider",
                package="atlas.example",
                module_path="atlas.example.provider",
                status=ComponentStatus.OFFLINE,
                provided_capabilities=["thing.do"],
            )
        )
        entry = next(
            e for e in build_capability_model(registry).entries if e.name == "thing.do"
        )
        # The capability exists in the model but is currently unavailable.
        assert entry.availability.value == "unavailable"
