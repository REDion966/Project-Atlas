"""Step 17 — source evaluation and provenance.

Measured baseline (real Atlas/kernel, before any change): the Step 16
``ResearchOutcome`` was aggregate-only — no ``claims``/citations, just
per-source counts — so a caller could not say WHERE a claim came from, nor
whether it was verified or merely retrieved. The raw provenance DID exist in the
existing storage (claims with ``CitationRecord``s, verifications carrying the
verifier's own ``outcome``/``supporting``/``contradicting``), and
``ResearchReport.citations`` was empty while the claims carried the citations —
a trap that silently looks like "no provenance". There was no layer connecting
the outcome to that material and no source evaluation at all.

Step 17 adds ONE bounded, deterministic, model-free representation over the
EXISTING claims/citations/verifications. It writes nothing, invents no
credibility, and treats reachability as evidence of nothing but reachability.
"""

from __future__ import annotations

import json

import pytest

from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    ResearchReport,
    SourceKind,
    VerificationStatus,
)
from atlas.research.provenance import (
    ClaimStanding,
    SourceAuthorization,
    build_research_provenance,
    provenance_from_outcome,
)

_URL_A = "https://example.com/a"
_URL_B = "https://example.com/b"
_DENIED = "https://other.example/x"


def _citation(uri, section="chunk:0000", title="", kind=SourceKind.WEB):
    return CitationRecord(
        record_id=f"cite:{uri}:{section.split(':')[-1]}",
        source_uri=uri,
        source_title=title or uri.split("/")[2],
        source_kind=kind,
        section=section,
    )


def _claim(claim_id, statement, citations, confidence=0.8):
    return KnowledgeClaim(
        claim_id=claim_id,
        statement=statement,
        citations=tuple(citations),
        confidence=confidence,
    )


def _verification(claim_id, outcome, supporting=(), contradicting=(), score=0.75):
    status = {
        "VERIFIED": VerificationStatus.SUPPORTED,
        "PLAUSIBLE": VerificationStatus.SUPPORTED,
        "CONTESTED": VerificationStatus.CONTRADICTED,
        "UNKNOWN": VerificationStatus.UNVERIFIED,
    }[outcome]
    return ClaimVerification(
        verification_id=f"verify:{claim_id}",
        claim_id=claim_id,
        status=status,
        score=score,
        evidence_summary="",
        metadata={
            "outcome": outcome,
            "supporting": list(supporting),
            "contradicting": list(contradicting),
            "checked_sources": len(supporting) + len(contradicting),
        },
    )


def _report(claims=(), verifications=(), report_id="report:1"):
    return ResearchReport(
        report_id=report_id,
        plan_id="plan::1",
        query_id="q1",
        question="Q",
        findings="",
        claims=tuple(claims),
        verifications=tuple(verifications),
        citations=(),
    )


def _provenance(report, **kwargs):
    kwargs.setdefault("objective", "Q")
    return build_research_provenance(reports=[report], **kwargs)


# ---------------------------------------------------------------------------
# 1. Source identity, evaluation and the provenance chain
# ---------------------------------------------------------------------------


class TestSourceEvaluation:
    def test_source_identity_and_evidence_evaluated(self):
        report = _report(
            claims=[_claim("c1", "S", [_citation(_URL_A)])],
            verifications=[_verification("c1", "PLAUSIBLE", supporting=[_URL_A])],
        )
        provenance = _provenance(report, used_sources=[_URL_A])
        source = provenance.sources[0]
        assert source.source_uri == _URL_A
        assert source.identity_known is True
        assert source.authorization == SourceAuthorization.AUTHORIZED.value
        assert source.accessed is True
        assert source.evidence_present is True
        assert source.claim_count == 1
        assert source.supporting_claims == 1
        assert source.title  # carried from the citation identity
        assert source.kind == "WEB"

    def test_denied_source_is_evaluated_as_denied(self):
        provenance = build_research_provenance(
            objective="Q", denied_sources=[_DENIED]
        )
        source = provenance.sources[0]
        assert source.authorization == SourceAuthorization.DENIED.value
        assert source.accessed is False
        assert source.evidence_present is False
        assert any("denied" in f for f in source.findings)
        assert _DENIED in provenance.denied_sources

    def test_used_source_without_evidence_is_flagged(self):
        report = _report(
            claims=[_claim("c1", "S", [_citation(_URL_A)])],
            verifications=[_verification("c1", "PLAUSIBLE", supporting=[_URL_A])],
        )
        provenance = _provenance(report, used_sources=[_URL_A, _URL_B])
        by_uri = {s.source_uri: s for s in provenance.sources}
        assert by_uri[_URL_A].evidence_present is True
        assert by_uri[_URL_B].evidence_present is False
        assert any("no acquired claim cites it" in f for f in by_uri[_URL_B].findings)

    def test_source_evidence_counts_are_used_when_provided(self):
        report = _report()
        evidence = type(
            "E",
            (),
            {
                "source_uri": _URL_A,
                "total_claims": 4,
                "supporting_claims": 3,
                "contradicted_claims": 1,
            },
        )()
        provenance = _provenance(
            report, used_sources=[_URL_A], source_evidence=[evidence]
        )
        source = provenance.sources[0]
        assert (source.claim_count, source.supporting_claims) == (4, 3)
        assert source.contradicted_claims == 1


class TestProvenanceChain:
    def test_research_source_evidence_claim_chain(self):
        report = _report(
            claims=[_claim("c1", "The Zorblax release is 7.3", [_citation(_URL_A)])],
            verifications=[_verification("c1", "PLAUSIBLE", supporting=[_URL_A])],
        )
        provenance = _provenance(report, used_sources=[_URL_A], report_ids=["report:1"])
        # research -> report ids
        assert provenance.report_ids == ("report:1",)
        assert provenance.stored_reports == 1
        # research -> source
        assert provenance.sources[0].source_uri == _URL_A
        # source -> evidence (citation metadata, distinct from the claim)
        assert provenance.evidence[0].evidence_id == "cite:https://example.com/a:0000"
        assert provenance.evidence[0].source_uri == _URL_A
        assert provenance.evidence[0].section == "chunk:0000"
        # evidence -> claim
        claim = provenance.claims[0]
        assert claim.claim_id == "c1"
        assert claim.evidence_ids == ("cite:https://example.com/a:0000",)
        assert claim.source_uris == (_URL_A,)

    def test_metadata_is_distinguished_from_evidence(self):
        # A citation with no claim is metadata about a location, never evidence.
        report = _report(
            claims=[_claim("c1", "S", [_citation(_URL_A)])],
            verifications=[_verification("c1", "PLAUSIBLE", supporting=[_URL_A])],
        )
        provenance = _provenance(report)
        assert isinstance(provenance.evidence[0].to_dict()["evidence_id"], str)
        assert "statement" not in provenance.evidence[0].to_dict()
        assert provenance.claims[0].statement == "S"

    def test_claim_without_citation_is_flagged(self):
        report = _report(
            claims=[_claim("c1", "S", [])],
            verifications=[_verification("c1", "UNKNOWN")],
        )
        provenance = _provenance(report)
        claim = provenance.claims[0]
        assert any("no citation recorded" in f for f in claim.findings)
        assert provenance.has_insufficient_provenance is True

    def test_multiple_sources_supporting_one_claim(self):
        report = _report(
            claims=[_claim("c1", "S", [_citation(_URL_A), _citation(_URL_B)])],
            verifications=[
                _verification("c1", "VERIFIED", supporting=[_URL_A, _URL_B], score=0.95)
            ],
        )
        provenance = _provenance(report, used_sources=[_URL_A, _URL_B])
        claim = provenance.claims[0]
        assert claim.supporting_sources == (_URL_A, _URL_B)
        assert claim.source_uris == (_URL_A, _URL_B)
        assert claim.standing == ClaimStanding.VERIFIED.value
        assert provenance.established_claim_ids == ("c1",)


# ---------------------------------------------------------------------------
# 2. Verification standing: established vs merely retrieved
# ---------------------------------------------------------------------------


class TestStanding:
    def test_verified_requires_multi_source_corroboration(self):
        verified = _provenance(
            _report(
                claims=[_claim("c1", "S", [_citation(_URL_A), _citation(_URL_B)])],
                verifications=[
                    _verification("c1", "VERIFIED", supporting=[_URL_A, _URL_B])
                ],
            )
        )
        single = _provenance(
            _report(
                claims=[_claim("c2", "S", [_citation(_URL_A)])],
                verifications=[_verification("c2", "PLAUSIBLE", supporting=[_URL_A])],
            )
        )
        assert verified.claims[0].verified is True
        assert single.claims[0].verified is False
        assert single.claims[0].standing == ClaimStanding.SUPPORTED.value

    def test_merely_retrieved_is_not_established(self):
        provenance = _provenance(
            _report(
                claims=[_claim("c1", "S", [_citation(_URL_A)])],
                verifications=[_verification("c1", "UNKNOWN")],
            )
        )
        claim = provenance.claims[0]
        assert claim.standing == ClaimStanding.UNVERIFIED.value
        assert claim.merely_retrieved is True
        assert provenance.established_claim_ids == ()
        assert provenance.supported_claim_ids == ()
        assert provenance.unverified_claim_ids == ("c1",)

    def test_missing_verification_is_unknown_not_trusted(self):
        provenance = _provenance(
            _report(claims=[_claim("c1", "S", [_citation(_URL_A)])])
        )
        assert provenance.claims[0].standing == ClaimStanding.UNKNOWN.value
        assert provenance.claims[0].verified is False
        assert provenance.has_insufficient_provenance is True

    def test_conflicting_evidence_is_surfaced_not_trusted(self):
        provenance = _provenance(
            _report(
                claims=[_claim("c1", "S", [_citation(_URL_A), _citation(_URL_B)])],
                verifications=[
                    _verification(
                        "c1", "CONTESTED", supporting=[_URL_A], contradicting=[_URL_B]
                    )
                ],
            )
        )
        claim = provenance.claims[0]
        assert claim.standing == ClaimStanding.CONTESTED.value
        assert claim.contradicting_sources == (_URL_B,)
        assert provenance.contested_claim_ids == ("c1",)
        assert provenance.has_conflicts is True
        assert provenance.established_claim_ids == ()
        assert any("conflicting" in f for f in provenance.findings)

    def test_one_source_claim_is_never_reported_as_verified(self):
        provenance = _provenance(
            _report(
                claims=[_claim("c1", "S", [_citation(_URL_A)])],
                verifications=[_verification("c1", "PLAUSIBLE", supporting=[_URL_A])],
            ),
            used_sources=[_URL_A],
        )
        assert provenance.claims[0].verified is False
        assert provenance.established_claim_ids == ()
        assert any("multi-source corroboration" in f for f in provenance.findings)


# ---------------------------------------------------------------------------
# 3. Insufficiency, determinism and bounds
# ---------------------------------------------------------------------------


class TestInsufficiencyAndBounds:
    def test_missing_report_is_reported_as_insufficient(self):
        provenance = build_research_provenance(
            objective="Q", report_ids=["report:absent"], used_sources=[_URL_A]
        )
        assert provenance.stored_reports == 0
        assert provenance.has_insufficient_provenance is True
        assert any("no stored research report" in f for f in provenance.findings)

    def test_no_false_trust_without_any_evidence(self):
        provenance = build_research_provenance(objective="Q")
        assert provenance.established_claim_ids == ()
        assert provenance.retained_for_learning is False
        assert provenance.has_insufficient_provenance is True

    def test_deterministic_and_serializable(self):
        report = _report(
            claims=[_claim("c1", "S", [_citation(_URL_A)])],
            verifications=[_verification("c1", "PLAUSIBLE", supporting=[_URL_A])],
        )
        first = build_research_provenance(
            objective="Q", reports=[report], used_sources=[_URL_A]
        )
        second = build_research_provenance(
            objective="Q", reports=[report], used_sources=[_URL_A]
        )
        assert first == second
        json.dumps(first.to_dict())

    def test_bounded_and_immutable(self):
        claims = [
            _claim(f"c{i}", "S" * 900, [_citation(f"https://example.com/{i}")])
            for i in range(120)
        ]
        provenance = build_research_provenance(objective="x" * 5000, reports=[_report(claims)])
        assert len(provenance.claims) <= 40
        assert len(provenance.evidence) <= 40
        assert len(provenance.sources) <= 12
        assert len(provenance.objective) <= 400
        assert all(len(c.statement) <= 400 for c in provenance.claims)
        with pytest.raises(Exception):
            provenance.objective = "other"  # type: ignore[misc]

    def test_retains_claim_level_provenance_for_learning(self):
        report = _report(
            claims=[_claim("c1", "S", [_citation(_URL_A)], confidence=0.8)],
            verifications=[_verification("c1", "PLAUSIBLE", supporting=[_URL_A])],
        )
        provenance = _provenance(report)
        claim = provenance.claims[0]
        assert provenance.retained_for_learning is True
        assert claim.claim_id and claim.statement and claim.confidence == 0.8
        assert claim.verification_score == 0.75
        assert claim.evidence_ids

    def test_none_outcome_is_empty_not_invented(self):
        provenance = provenance_from_outcome(None)
        assert provenance.claims == ()
        assert provenance.established_claim_ids == ()
        assert provenance.has_insufficient_provenance is True


# ---------------------------------------------------------------------------
# 4. Real Atlas/kernel validation
# ---------------------------------------------------------------------------


GLOBAL_IP = "93.184.216.34"
_URL = "https://example.com/zorblax"
_TEXT = (
    "The Zorblax protocol release is 7.3. "
    "Atlas preserves provenance for every acquired claim."
)
_QUESTION = "What is the current release of the Zorblax protocol?"


def _tmp_storage(monkeypatch, tmp_path):
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage
    from atlas.storage.research_storage import ResearchSQLiteStorage

    class TmpEvolution(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "evolution.db")

    class TmpResearch(ResearchSQLiteStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "research.db")

    monkeypatch.setattr("atlas.kernel.atlas.SQLiteEvolutionStorage", TmpEvolution)
    monkeypatch.setattr("atlas.kernel.atlas.ResearchSQLiteStorage", TmpResearch)


def _adapter_factory(transport):
    from atlas.research.sources.web import WebSourceAdapter as Real

    def _factory(*, host_policy=None):
        return Real(
            transport=transport,
            host_policy=host_policy,
            resolver=lambda host: (GLOBAL_IP,),
        )

    return _factory


def _transport(calls, body=_TEXT):
    def _handler(url, timeout, max_bytes):
        calls.append(url)
        return 200, [("Content-Type", "text/plain")], body.encode("utf-8")

    return _handler


def _started_atlas(monkeypatch, tmp_path):
    _tmp_storage(monkeypatch, tmp_path)
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    return atlas


def _allowlisted_atlas(monkeypatch, tmp_path, calls):
    from tests.safe_kernel_config import SAFE_CONFIG_TOML, bound_configuration

    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    cfg = cfg_dir / "config.toml"
    cfg.write_text(
        SAFE_CONFIG_TOML + '\n[research]\nweb_allowed_hosts = ["example.com"]\n',
        encoding="utf-8",
    )
    import atlas.kernel.atlas as kernel_mod

    monkeypatch.setattr(kernel_mod, "Configuration", bound_configuration(cfg))

    import atlas.research.capability_handlers as cap_mod
    import atlas.research.external_acquisition as ext_mod

    factory = _adapter_factory(_transport(calls))
    monkeypatch.setattr(cap_mod, "WebSourceAdapter", factory)
    monkeypatch.setattr(ext_mod, "WebSourceAdapter", factory)
    return _started_atlas(monkeypatch, tmp_path)


class TestRealKernel:
    def test_authorized_research_yields_a_full_provenance_chain(
        self, monkeypatch, tmp_path
    ):
        calls: list[str] = []
        atlas = _allowlisted_atlas(monkeypatch, tmp_path, calls)
        try:
            outcome = atlas.research_knowledge_need(_QUESTION, candidate_urls=[_URL])
            assert outcome.status.value == "researched"
            provenance = atlas.research_provenance(outcome)
            assert provenance.stored_reports == 1
            assert provenance.report_ids == outcome.report_ids
            assert calls == [_URL]
            # source -> evidence -> claim, all linked
            source = provenance.sources[0]
            assert source.source_uri == _URL
            assert source.authorization == SourceAuthorization.AUTHORIZED.value
            assert source.evidence_present is True
            assert provenance.evidence and provenance.claims
            for claim in provenance.claims:
                assert claim.evidence_ids
                assert claim.source_uris == (_URL,)
                assert claim.verification_status == "SUPPORTED"
                assert claim.verification_score > 0
            assert provenance.retained_for_learning is True
        finally:
            atlas.shutdown()

    def test_provenance_matches_the_existing_persistence_layer(
        self, monkeypatch, tmp_path
    ):
        calls: list[str] = []
        atlas = _allowlisted_atlas(monkeypatch, tmp_path, calls)
        try:
            outcome = atlas.research_knowledge_need(_QUESTION, candidate_urls=[_URL])
            provenance = atlas.research_provenance(outcome)
            stored_claims = {c.claim_id for c in atlas._research_storage.load_claims()}
            stored_evidence = {c.record_id for c in atlas._research_storage.load_citations()}
            assert {c.claim_id for c in provenance.claims} == stored_claims
            assert {e.evidence_id for e in provenance.evidence} == stored_evidence
            # and the kernel's own knowledge surface agrees on the claims it returns
            validated = atlas.validated_knowledge("zorblax protocol release")
            by_id = {c.claim_id: c for c in provenance.claims}
            for item in validated.items:
                assert by_id[item.claim_id].verification_score == item.verification_score
                assert by_id[item.claim_id].standing in (
                    ClaimStanding.SUPPORTED.value,
                    ClaimStanding.VERIFIED.value,
                )
        finally:
            atlas.shutdown()

    def test_denied_sources_remain_denied_and_fetch_nothing(
        self, monkeypatch, tmp_path
    ):
        calls: list[str] = []
        atlas = _allowlisted_atlas(monkeypatch, tmp_path, calls)
        try:
            outcome = atlas.research_knowledge_need(
                _QUESTION, candidate_urls=["https://other.example/x"]
            )
            provenance = atlas.research_provenance(outcome)
            assert calls == []
            denied = [s for s in provenance.sources if s.authorization == "denied"]
            assert denied and denied[0].source_uri == "https://other.example/x"
            assert denied[0].evidence_present is False
            assert provenance.claims == ()
            assert provenance.has_insufficient_provenance is True
        finally:
            atlas.shutdown()

    def test_deny_by_default_is_reported_as_insufficient_not_hidden(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            outcome = atlas.research_knowledge_need(_QUESTION)
            provenance = atlas.research_provenance(outcome)
            assert outcome.status.value == "no_authorized_source"
            assert provenance.claims == ()
            assert provenance.stored_reports == 0
            assert provenance.has_insufficient_provenance is True
        finally:
            atlas.shutdown()

    def test_provenance_is_read_only(self, monkeypatch, tmp_path):
        calls: list[str] = []
        atlas = _allowlisted_atlas(monkeypatch, tmp_path, calls)
        try:
            outcome = atlas.research_knowledge_need(_QUESTION, candidate_urls=[_URL])
            storage = atlas._research_storage
            before = (
                len(storage.load_claims()),
                len(storage.load_verifications()),
                len(storage.load_citations()),
                len(storage.load_reports()),
            )
            for _ in range(3):
                atlas.research_provenance(outcome)
            after = (
                len(storage.load_claims()),
                len(storage.load_verifications()),
                len(storage.load_citations()),
                len(storage.load_reports()),
            )
            assert after == before
            assert atlas.pending_promotion_reviews() == []
        finally:
            atlas.shutdown()

    def test_no_unrecognised_outcome_claims_knowledge(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            unknown = type(
                "O",
                (),
                {
                    "objective": "Q",
                    "query": "",
                    "acquisition_id": "",
                    "report_ids": (),
                    "sources": (),
                    "denied_sources": (),
                    "source_evidence": (),
                },
            )()
            provenance = atlas.research_provenance(unknown)
            assert provenance.claims == ()
            assert provenance.established_claim_ids == ()
            assert provenance.has_insufficient_provenance is True
        finally:
            atlas.shutdown()

    def test_self_knowledge_and_earlier_steps_preserved(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            assert atlas.capability_contract("research")["state"] == "available"
            assert atlas.knowledge_need(_QUESTION).kind.value == "missing"
            assert atlas.chat("Which component owns memory_search?").metadata[
                "architecture"
            ]["kind"] == "ownership"
            assert atlas.chat("Is research available?").metadata[
                "builtin_intent"
            ] == "capability_state"
        finally:
            atlas.shutdown()
