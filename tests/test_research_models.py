"""Phase 17.1 — Research models: data model tests.

Covers immutability (frozen + slots), defaults, enum membership, and
serialization compatibility for atlas/research/models.py.
"""

import json
from datetime import datetime
from enum import Enum

import pytest

from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    ResearchPlan,
    ResearchReport,
    ResearchSource,
    SourceKind,
    SourceProfile,
    VerificationStatus,
)


class TestSourceKind:
    def test_members(self):
        expected = {
            SourceKind.DOCUMENT,
            SourceKind.WORKSPACE,
            SourceKind.CODEBASE,
            SourceKind.WEB,
        }
        assert set(SourceKind) == expected

    def test_members_are_enum(self):
        assert issubclass(SourceKind, Enum)


class TestVerificationStatus:
    def test_members(self):
        expected = {
            VerificationStatus.UNVERIFIED,
            VerificationStatus.SUPPORTED,
            VerificationStatus.CONTRADICTED,
            VerificationStatus.AMBIGUOUS,
        }
        assert set(VerificationStatus) == expected


class TestResearchPlan:
    def test_create_minimal(self):
        plan = ResearchPlan(plan_id="P1", query_id="Q1", question="How does it work?")
        assert plan.plan_id == "P1"
        assert plan.query_id == "Q1"
        assert plan.question == "How does it work?"
        assert plan.sub_queries == ()
        assert plan.target_sources == ()
        assert plan.verification_strategy == ""
        assert plan.max_depth == 1
        assert isinstance(plan.created_at, datetime)
        assert plan.metadata == {}

    def test_create_full(self):
        now = datetime.now()
        plan = ResearchPlan(
            plan_id="P2",
            query_id="Q2",
            question="How does storage work?",
            sub_queries=("Q2::00",),
            target_sources=(SourceKind.DOCUMENT,),
            verification_strategy="internal_consistency",
            max_depth=2,
            created_at=now,
            metadata={"scale": 3},
        )
        assert plan.sub_queries == ("Q2::00",)
        assert plan.target_sources == (SourceKind.DOCUMENT,)
        assert plan.verification_strategy == "internal_consistency"
        assert plan.max_depth == 2
        assert plan.created_at == now
        assert plan.metadata == {"scale": 3}

    def test_immutability(self):
        plan = ResearchPlan(plan_id="P3", query_id="Q3", question="Q?")
        with pytest.raises(AttributeError):
            plan.sub_queries = ("changed",)  # type: ignore[misc]
        with pytest.raises((AttributeError, TypeError)):
            plan.target_sources.append(SourceKind.CODEBASE)  # type: ignore[attr-defined]
        with pytest.raises(AttributeError):
            plan.new_field = 1  # type: ignore[attr-defined]


class TestResearchSource:
    def test_create_minimal(self):
        source = ResearchSource(uri="docs/readme.md")
        assert source.uri == "docs/readme.md"
        assert source.kind == SourceKind.DOCUMENT
        assert source.title == ""
        assert isinstance(source.retrieved_at, datetime)
        assert source.metadata == {}

    def test_create_full(self):
        now = datetime.now()
        source = ResearchSource(
            uri="workspace://atlas/planner.py",
            kind=SourceKind.CODEBASE,
            title="planner.py",
            retrieved_at=now,
            metadata={"author": "atlas"},
        )
        assert source.kind == SourceKind.CODEBASE
        assert source.title == "planner.py"
        assert source.retrieved_at == now
        assert source.metadata == {"author": "atlas"}

    def test_immutability(self):
        source = ResearchSource(uri="a.md")
        with pytest.raises(AttributeError):
            source.uri = "b.md"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            source.new_field = 1  # type: ignore[attr-defined]

    def test_to_dict(self):
        source = ResearchSource(uri="a.md", title="A", metadata={"k": 1})
        data = source.to_dict()
        assert data["uri"] == "a.md"
        assert data["kind"] == "DOCUMENT"
        assert data["title"] == "A"
        assert data["metadata"] == {"k": 1}
        assert isinstance(data["retrieved_at"], datetime)


class TestSourceProfile:
    def test_create_full(self):
        profile = SourceProfile(
            uri="a.md",
            kind=SourceKind.DOCUMENT,
            text="hello world",
            title="A",
            language="markdown",
            content_type="md",
            byte_size=11,
            tokens_estimate=2,
            line_count=2,
        )
        assert profile.uri == "a.md"
        assert profile.kind == SourceKind.DOCUMENT
        assert profile.text == "hello world"
        assert profile.title == "A"
        assert profile.language == "markdown"
        assert profile.content_type == "md"
        assert profile.byte_size == 11
        assert profile.tokens_estimate == 2
        assert profile.line_count == 2
        assert isinstance(profile.loaded_at, datetime)

    def test_immutability(self):
        profile = SourceProfile(uri="a.md", kind=SourceKind.DOCUMENT, text="x")
        with pytest.raises(AttributeError):
            profile.text = "y"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            profile.new_field = 1  # type: ignore[attr-defined]

    def test_to_dict(self):
        profile = SourceProfile(uri="a.md", kind=SourceKind.DOCUMENT, text="x")
        data = profile.to_dict()
        assert data["uri"] == "a.md"
        assert data["kind"] == "DOCUMENT"
        assert data["text"] == "x"
        assert isinstance(data["loaded_at"], datetime)


class TestCitationRecord:
    def test_defaults(self):
        citation = CitationRecord(record_id="C1")
        assert citation.record_id == "C1"
        assert citation.source_uri == ""
        assert citation.source_title == ""
        assert citation.source_kind == SourceKind.DOCUMENT
        assert citation.section == ""
        assert citation.page_or_line == ""

    def test_create_full(self):
        now = datetime.now()
        citation = CitationRecord(
            record_id="C2",
            source_uri="docs/guide.md",
            source_title="Guide",
            source_kind=SourceKind.CODEBASE,
            section="2.1",
            page_or_line="42",
            retrieved_at=now,
        )
        assert citation.source_uri == "docs/guide.md"
        assert citation.source_kind == SourceKind.CODEBASE
        assert citation.section == "2.1"
        assert citation.page_or_line == "42"
        assert citation.retrieved_at == now

    def test_immutability(self):
        citation = CitationRecord(record_id="C3")
        with pytest.raises(AttributeError):
            citation.source_uri = "changed"  # type: ignore[misc]

    def test_to_dict(self):
        citation = CitationRecord(
            record_id="C4",
            source_uri="docs/x.md",
            source_kind=SourceKind.WORKSPACE,
        )
        data = citation.to_dict()
        assert data["record_id"] == "C4"
        assert data["source_uri"] == "docs/x.md"
        assert data["source_kind"] == "WORKSPACE"
        assert isinstance(data["retrieved_at"], datetime)


class TestKnowledgeClaim:
    def test_defaults(self):
        claim = KnowledgeClaim(claim_id="K1", statement="Atlas uses SQLite.")
        assert claim.claim_id == "K1"
        assert claim.statement == "Atlas uses SQLite."
        assert claim.citations == ()
        assert claim.confidence == 0.0
        assert isinstance(claim.extracted_at, datetime)

    def test_with_citations(self):
        citation = CitationRecord(record_id="C1", source_uri="docs/db.md")
        claim = KnowledgeClaim(
            claim_id="K2",
            statement="Storage is SQLite.",
            citations=(citation,),
            confidence=0.9,
        )
        assert claim.citations == (citation,)
        assert claim.confidence == 0.9

    def test_immutability(self):
        claim = KnowledgeClaim(claim_id="K3", statement="x")
        with pytest.raises(AttributeError):
            claim.statement = "y"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            claim.new_field = 1  # type: ignore[attr-defined]

    def test_to_dict(self):
        citation = CitationRecord(record_id="C1", source_uri="docs/db.md")
        claim = KnowledgeClaim(
            claim_id="K4",
            statement="Storage is SQLite.",
            citations=(citation,),
            confidence=0.9,
        )
        data = claim.to_dict()
        assert data["claim_id"] == "K4"
        assert data["confidence"] == 0.9
        assert data["citations"][0]["record_id"] == "C1"
        assert isinstance(data["extracted_at"], datetime)


class TestClaimVerification:
    def test_defaults(self):
        verification = ClaimVerification(verification_id="V1", claim_id="K1")
        assert verification.verification_id == "V1"
        assert verification.claim_id == "K1"
        assert verification.status == VerificationStatus.UNVERIFIED
        assert verification.score == 0.0
        assert verification.evidence_summary == ""

    def test_create_full(self):
        now = datetime.now()
        verification = ClaimVerification(
            verification_id="V2",
            claim_id="K2",
            status=VerificationStatus.SUPPORTED,
            score=0.85,
            evidence_summary="Cross-checked against two sources.",
            verified_at=now,
        )
        assert verification.status == VerificationStatus.SUPPORTED
        assert verification.score == 0.85
        assert verification.evidence_summary == "Cross-checked against two sources."
        assert verification.verified_at == now

    def test_immutability(self):
        verification = ClaimVerification(verification_id="V3", claim_id="K3")
        with pytest.raises(AttributeError):
            verification.status = VerificationStatus.SUPPORTED  # type: ignore[misc]

    def test_to_dict(self):
        verification = ClaimVerification(
            verification_id="V4",
            claim_id="K4",
            status=VerificationStatus.CONTRADICTED,
        )
        data = verification.to_dict()
        assert data["verification_id"] == "V4"
        assert data["claim_id"] == "K4"
        assert data["status"] == "CONTRADICTED"
        assert isinstance(data["verified_at"], datetime)


class TestResearchReport:
    def test_create_minimal(self):
        report = ResearchReport(
            report_id="R1",
            plan_id="P1",
            query_id="Q1",
            question="How does it work?",
            findings="It works.",
        )
        assert report.report_id == "R1"
        assert report.plan_id == "P1"
        assert report.query_id == "Q1"
        assert report.question == "How does it work?"
        assert report.findings == "It works."
        assert report.claims == ()
        assert report.verifications == ()
        assert report.citations == ()
        assert report.confidence == 0.0
        assert isinstance(report.created_at, datetime)

    def test_create_full(self):
        claim = KnowledgeClaim(claim_id="K1", statement="s")
        verification = ClaimVerification(verification_id="V1", claim_id="K1")
        citation = CitationRecord(record_id="C1", source_uri="d.md")
        report = ResearchReport(
            report_id="R2",
            plan_id="P2",
            query_id="Q2",
            question="Q?",
            findings="F",
            claims=(claim,),
            verifications=(verification,),
            citations=(citation,),
            confidence=0.75,
        )
        assert report.claims == (claim,)
        assert report.verifications == (verification,)
        assert report.citations == (citation,)
        assert report.confidence == 0.75

    def test_immutability(self):
        report = ResearchReport(
            report_id="R3",
            plan_id="P3",
            query_id="Q3",
            question="Q?",
            findings="F",
        )
        with pytest.raises(AttributeError):
            report.findings = "changed"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            report.new_field = 1  # type: ignore[attr-defined]

    def test_to_dict(self):
        claim = KnowledgeClaim(claim_id="K1", statement="s")
        report = ResearchReport(
            report_id="R4",
            plan_id="P4",
            query_id="Q4",
            question="Q?",
            findings="F",
            claims=(claim,),
        )
        data = report.to_dict()
        assert data["report_id"] == "R4"
        assert data["findings"] == "F"
        assert data["claims"][0]["claim_id"] == "K1"
        assert data["verifications"] == ()
        assert data["citations"] == ()
        assert isinstance(data["created_at"], datetime)


class TestSerializationCompatibility:
    """to_dict() output must remain JSON-compatible after dropping datetimes."""

    def test_nested_records_serialize_to_json(self):
        citation = CitationRecord(record_id="C1", source_uri="docs/db.md")
        claim = KnowledgeClaim(
            claim_id="K1",
            statement="Storage is SQLite.",
            citations=(citation,),
            confidence=0.9,
        )
        report = ResearchReport(
            report_id="R1",
            plan_id="P1",
            query_id="Q1",
            question="Q?",
            findings="F",
            claims=(claim,),
        )
        data = report.to_dict()

        def drop_datetimes(value):
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, dict):
                return {k: drop_datetimes(v) for k, v in value.items()}
            if isinstance(value, (tuple, list)):
                return [drop_datetimes(v) for v in value]
            return value

        payload = json.dumps(drop_datetimes(data))
        parsed = json.loads(payload)
        assert parsed["report_id"] == "R1"
        assert parsed["claims"][0]["claim_id"] == "K1"
        assert parsed["claims"][0]["citations"][0]["source_uri"] == "docs/db.md"

    def test_serialized_kinds_are_stable_strings(self):
        """Enum names in to_dict() are stable identifiers for storage."""
        profile = SourceProfile(uri="a.py", kind=SourceKind.CODEBASE, text="x")
        assert profile.to_dict()["kind"] == "CODEBASE"
        verification = ClaimVerification(
            verification_id="V1", claim_id="K1", status=VerificationStatus.SUPPORTED
        )
        assert verification.to_dict()["status"] == "SUPPORTED"
