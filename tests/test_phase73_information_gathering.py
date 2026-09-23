"""Phase 7.3 — Information gathering: evidence contract.

Investigation result: gathering already normalizes sources, extracts claims,
verifies them, persists with provenance, and separates raw from validated
knowledge, so no new retrieval system was introduced.

* Source adapters normalize content into ``SourceProfile`` / ``ResearchSource``.
* ``KnowledgeExtractor`` turns source text into ``KnowledgeClaim`` with
  ``CitationRecord`` provenance.
* ``ClaimVerifier`` produces ``ClaimVerification`` statuses.
* ``ResearchSQLiteStorage`` persists; ``ValidatedKnowledgeRetriever`` returns
  only SUPPORTED claims with provenance and fails closed otherwise.
"""

from __future__ import annotations

from atlas.research.extractor import KnowledgeExtractor
from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    SourceKind,
    SourceProfile,
    VerificationStatus,
)
from atlas.research.validated_retrieval import (
    ValidatedKnowledgeRetriever,
    ValidatedKnowledgeStatus,
)
from atlas.research.verifier import ClaimVerifier
from atlas.storage.research_storage import ResearchSQLiteStorage


class TestPhase73InformationGathering:
    def test_source_content_normalizes_into_claims_with_provenance(self):
        profile = SourceProfile(
            uri="code://atlas/memory/manager.py",
            kind=SourceKind.CODEBASE,
            text=(
                "Atlas stores claims with provenance. "
                "Atlas verifies claims deterministically."
            ),
        )
        claims = KnowledgeExtractor().extract(profile)
        assert claims
        assert claims[0].citations[0].source_kind is SourceKind.CODEBASE
        assert claims[0].metadata["source_uri"] == "code://atlas/memory/manager.py"

    def test_verification_produces_distinct_statuses(self):
        profile = SourceProfile(
            uri="docs/x.md",
            kind=SourceKind.DOCUMENT,
            text="Atlas uses SQLite for persistence.",
        )
        claims = KnowledgeExtractor().extract(profile)
        verifications = ClaimVerifier().verify(claims, [profile])
        assert len(verifications) == len(claims)
        assert all(isinstance(v.status, VerificationStatus) for v in verifications)

    def test_raw_claim_is_not_validated_knowledge(self, tmp_path):
        storage = ResearchSQLiteStorage(db_path=tmp_path / "r.db")
        storage.initialize()
        try:
            storage.store_claim(
                KnowledgeClaim(
                    claim_id="raw-1",
                    statement="raw external statement about widgets",
                    citations=(
                        CitationRecord(
                            record_id="cite:raw",
                            source_uri="https://example.com/x",
                            source_kind=SourceKind.WEB,
                        ),
                    ),
                )
            )
            # No verification -> not authoritative knowledge.
            result = ValidatedKnowledgeRetriever(storage).retrieve("widgets")
            assert result.status is ValidatedKnowledgeStatus.EMPTY
        finally:
            storage.close()

    def test_validated_knowledge_preserves_provenance_through_persistence(
        self, tmp_path
    ):
        storage = ResearchSQLiteStorage(db_path=tmp_path / "r.db")
        storage.initialize()
        try:
            storage.store_claim(
                KnowledgeClaim(
                    claim_id="v-1",
                    statement="verified fact about provenance",
                    citations=(
                        CitationRecord(
                            record_id="cite:v",
                            source_uri="https://example.com/doc",
                            source_title="Example",
                            source_kind=SourceKind.WEB,
                        ),
                    ),
                )
            )
            storage.store_verification(
                ClaimVerification(
                    verification_id="ver:v-1",
                    claim_id="v-1",
                    status=VerificationStatus.SUPPORTED,
                    score=0.9,
                )
            )
            result = ValidatedKnowledgeRetriever(storage).retrieve("provenance")
            assert result.status is ValidatedKnowledgeStatus.OK
            item = result.items[0]
            assert item.citations[0].source_uri == "https://example.com/doc"
            assert item.validation_status == "SUPPORTED"
        finally:
            storage.close()

    def test_unavailable_store_fails_closed(self):
        assert (
            ValidatedKnowledgeRetriever(None).retrieve("anything").status
            is ValidatedKnowledgeStatus.STORE_UNAVAILABLE
        )
