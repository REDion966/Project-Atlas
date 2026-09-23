"""Phase 3.6 — Evidence/provenance tracking: evidence contract.

Investigation result (evidence, not aspiration): Atlas already tracks
evidence/provenance across the relevant domains using its existing structures —
no second provenance framework was introduced.

* External/research knowledge: ``KnowledgeClaim`` → ``CitationRecord``
  (``source_uri``, ``source_kind``, ``section``, ``retrieved_at``, ``metadata``)
  → ``ClaimVerification`` (status/score/evidence summary); preserved through
  ``ResearchSQLiteStorage`` and ``ValidatedKnowledgeRetriever``.
* Experience/evolution history: ``EvolutionRecord`` (``related_ids`` +
  ``metadata`` audit evidence), retrievable by type via ``EvolutionMemory``.
* Development: ``DevelopmentVerification`` → ``VerificationReport`` cites the
  concrete evidence (status, iterations, changed files, all-tests-passed).
* Decisions: ``decision_quality``/``UsefulnessAssessment`` carry evidence-backed
  fields whose numeric scores are derived summaries.

These tests pin that provenance is retained, linked to the stored item, and
survives persistence/retrieval, and that no parallel provenance system exists.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime
from types import SimpleNamespace

from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
)
from atlas.evolution.development_verification import (
    DevelopmentVerification,
    VerificationStatus,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.models import EvolutionRecord
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
from atlas.storage.research_storage import ResearchSQLiteStorage


class TestPhase36EvidenceProvenanceEvidence:
    def test_research_knowledge_links_to_its_evidence(self, tmp_path):
        storage = ResearchSQLiteStorage(db_path=tmp_path / "research.db")
        storage.initialize()
        try:
            citation = CitationRecord(
                record_id="cite:web:p36",
                source_uri="https://example.com/doc",
                source_title="Example Doc",
                source_kind=SourceKind.WEB,
                section="chunk:0000",
                retrieved_at=datetime(2026, 1, 1, 12, 0, 0),
            )
            claim = KnowledgeClaim(
                claim_id="c-p36",
                statement="External fact about provenance tracking",
                citations=(citation,),
                confidence=0.8,
            )
            storage.store_claim(claim)
            storage.store_verification(
                ClaimVerification(
                    verification_id="v-p36",
                    claim_id="c-p36",
                    status=ResearchVerificationStatus.SUPPORTED,
                    score=0.9,
                    evidence_summary="supported by example.com",
                )
            )

            result = ValidatedKnowledgeRetriever(storage).retrieve("provenance tracking")
            assert result.status is ValidatedKnowledgeStatus.OK
            item = result.items[0]
            # The stored knowledge item retains its evidence (citation) verbatim.
            assert item.citations
            evidence = item.citations[0]
            assert evidence.source_uri == "https://example.com/doc"
            assert evidence.source_kind is SourceKind.WEB
            assert evidence.retrieved_at == datetime(2026, 1, 1, 12, 0, 0)
            assert item.validation_status == "SUPPORTED"
        finally:
            storage.close()

    def test_evolution_record_is_linked_audit_evidence(self):
        memory = EvolutionMemory()
        memory.store_record(
            EvolutionRecord(
                record_id="EVID-P36-1",
                event_type="research.ingest",
                description="Research report ingested as governed request.",
                related_ids=["report-p36", "request-p36"],
                metadata={"scope": "KNOWLEDGE", "claim_count": 2},
            )
        )
        records = memory.get_records_by_type("research.ingest")
        assert len(records) == 1
        # The record links back to the artifacts it documents (evidence linkage).
        assert records[0].related_ids == ["report-p36", "request-p36"]
        assert records[0].metadata["scope"] == "KNOWLEDGE"

    def test_development_verification_report_cites_evidence(self):
        outcome = DevelopmentOutcome(
            outcome=DevelopmentOutcomeStatus.SUCCESS,
            proposal_id="PROP-P36",
            plan_id="PLAN-P36",
            iteration=1,
            verification_passed=True,
            test_outcome="passed",
            changed_files=["atlas/example/mod.py"],
        )
        report = DevelopmentVerification().verify(
            SimpleNamespace(
                status=DevelopmentOutcomeStatus.SUCCESS,
                outcomes=[outcome],
                iterations_used=1,
                message="ok",
            )
        )
        assert report.status is VerificationStatus.VERIFIED
        assert report.all_tests_passed is True
        assert report.changed_files == ("atlas/example/mod.py",)
        assert "status=SUCCESS" in report.evidence
        assert "verified_iterations=1" in report.evidence

    def test_provenance_fields_are_bounded_and_preserved_by_design(self):
        # Evidence structures carry provenance fields (no invented metadata):
        # a citation knows its source identity/kind/retrieval time, and a
        # verification knows the claim it concerns.
        citation = CitationRecord(
            record_id="cite:c", source_uri="https://example.com/x",
            source_kind=SourceKind.WEB,
        )
        assert citation.record_id and citation.source_uri
        verification = ClaimVerification(
            verification_id="v", claim_id="c", status=ResearchVerificationStatus.UNVERIFIED
        )
        assert verification.claim_id == "c"

    def test_no_parallel_provenance_framework_exists(self):
        # Provenance reuses the existing research (CitationRecord) and evolution
        # (EvolutionRecord) structures; there is no separate provenance package.
        assert importlib.util.find_spec("atlas.provenance") is None
        assert CitationRecord.__module__.startswith("atlas.research")
        assert EvolutionRecord.__module__.startswith("atlas.evolution")
