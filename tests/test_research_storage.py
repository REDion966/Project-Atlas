"""Phase 17.6 — Research SQLite Storage tests."""

from datetime import datetime

import pytest

from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    ResearchReport,
    ResearchSource,
    SourceKind,
    SourceProfile,
    VerificationStatus,
)
from atlas.storage.research_storage import ResearchSQLiteStorage


@pytest.fixture
def storage(tmp_path):
    adapter = ResearchSQLiteStorage(db_path=tmp_path / "research_test.db")
    adapter.initialize()
    assert adapter.is_available()
    yield adapter
    adapter.close()


def make_source(uri="docs/guide.md"):
    return ResearchSource(uri=uri, kind=SourceKind.DOCUMENT, title="guide.md")


def make_claim(statement="Atlas uses SQLite.", uri="docs/guide.md"):
    return KnowledgeClaim(
        claim_id=f"claim-test:{abs(hash(statement)) % 10000}",
        statement=statement,
        citations=(
            CitationRecord(
                record_id=f"cite:{uri}:0000",
                source_uri=uri,
                source_kind=SourceKind.DOCUMENT,
            ),
        ),
        confidence=0.7,
    )


def make_verification(claim_id="claim-test:1"):
    return ClaimVerification(
        verification_id=f"verify:{claim_id}",
        claim_id=claim_id,
        status=VerificationStatus.SUPPORTED,
        score=0.85,
    )


def make_report():
    claim = make_claim()
    verification = make_verification(claim.claim_id)
    return ResearchReport(
        report_id="report:test:1",
        plan_id="plan::test",
        query_id="test",
        question="What is storage?",
        findings="Atlas uses SQLite.",
        confidence=0.85,
        claims=(claim,),
        verifications=(verification,),
        citations=claim.citations,
    )


class TestLifecycle:
    def test_initialize_and_close(self, tmp_path):
        adapter = ResearchSQLiteStorage(db_path=tmp_path / "x.db")
        adapter.initialize()
        assert adapter.is_available()
        adapter.close()
        assert not adapter.is_available()

    def test_unavailable_write_raises(self):
        adapter = ResearchSQLiteStorage()  # never initialized
        with pytest.raises(Exception):
            adapter.store_source(make_source())


class TestSourceRoundTrip:
    def test_store_and_load(self, storage):
        storage.store_source(make_source())
        sources = storage.load_sources()
        assert len(sources) == 1
        assert sources[0].uri == "docs/guide.md"
        assert sources[0].kind == SourceKind.DOCUMENT

    def test_append_only_ignores_duplicate(self, storage):
        storage.store_source(make_source())
        storage.store_source(make_source())  # same uri → INSERT OR IGNORE
        assert len(storage.load_sources()) == 1


class TestClaimRoundTrip:
    def test_store_and_load(self, storage):
        claim = make_claim()
        storage.store_claim(claim)
        loaded = storage.load_claims()
        assert len(loaded) == 1
        assert loaded[0].claim_id == claim.claim_id
        assert loaded[0].statement == claim.statement
        assert loaded[0].confidence == claim.confidence
        assert len(loaded[0].citations) == 1
        assert loaded[0].citations[0].source_uri == "docs/guide.md"

    def test_upsert_is_idempotent(self, storage):
        claim = make_claim()
        storage.store_claim(claim)
        storage.store_claim(claim)
        assert len(storage.load_claims()) == 1


class TestVerificationRoundTrip:
    def test_store_and_load(self, storage):
        verification = make_verification()
        storage.store_verification(verification)
        loaded = storage.load_verifications()
        assert len(loaded) == 1
        assert loaded[0].verification_id == verification.verification_id
        assert loaded[0].status == VerificationStatus.SUPPORTED
        assert loaded[0].score == 0.85


class TestCitationRoundTrip:
    def test_store_and_load(self, storage):
        citation = CitationRecord(
            record_id="cite:x:0000", source_uri="x", source_kind=SourceKind.CODEBASE
        )
        storage.store_citation(citation)
        loaded = storage.load_citations()
        assert loaded[0].source_kind == SourceKind.CODEBASE


class TestReportRoundTrip:
    def test_store_and_load_nested(self, storage):
        report = make_report()
        storage.store_report(report)
        loaded = storage.load_reports()
        assert len(loaded) == 1
        assert loaded[0].report_id == report.report_id
        assert loaded[0].question == "What is storage?"
        assert loaded[0].confidence == 0.85
        assert len(loaded[0].claims) == 1
        assert len(loaded[0].verifications) == 1
        assert len(loaded[0].citations) == 1

    def test_append_only_reports(self, storage):
        storage.store_report(make_report())
        storage.store_report(make_report())  # same report_id → INSERT OR IGNORE
        assert len(storage.load_reports()) == 1


class TestMigration:
    def test_schema_version_reaches_v7(self, tmp_path):
        adapter = ResearchSQLiteStorage(db_path=tmp_path / "m.db")
        adapter.initialize()
        assert adapter.get_schema_version() >= 7
        adapter.close()

    def test_migrations_are_additive(self, tmp_path):
        adapter = ResearchSQLiteStorage(db_path=tmp_path / "m.db")
        adapter.initialize()
        tables = {
            row[0]
            for row in adapter._execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {"research_sources", "research_claims", "research_verifications",
                "research_citations", "research_reports"}.issubset(tables)
        # Existing schema tables are untouched
        assert "experiences" in tables
        adapter.close()


class TestSerialization:
    def test_datetime_round_trip(self, storage):
        source = make_source()
        storage.store_source(source)
        loaded = storage.load_sources()
        assert isinstance(loaded[0].retrieved_at, datetime)

    def test_metadata_dict_round_trip(self, storage):
        source = ResearchSource(
            uri="u", kind=SourceKind.DOCUMENT, metadata={"k": "v"}
        )
        storage.store_source(source)
        loaded = storage.load_sources()
        assert loaded[0].metadata == {"k": "v"}


class TestRecovery:
    def test_close_then_reopen_persists(self, tmp_path):
        path = tmp_path / "persist.db"
        adapter = ResearchSQLiteStorage(db_path=path)
        adapter.initialize()
        adapter.store_source(make_source())
        adapter.close()

        reopened = ResearchSQLiteStorage(db_path=path)
        reopened.initialize()
        assert len(reopened.load_sources()) == 1
        reopened.close()


class TestProfileStorageCompatibility:
    def test_store_source_accepts_source_metadata(self, storage):
        storage.store_source(make_source())
        assert len(storage.load_sources()) == 1
