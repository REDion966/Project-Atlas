"""Step 18 — knowledge representation and learning.

Measured baseline (real Atlas/kernel, before any change): the durable artifacts
(claims/verifications/citations/reports) already existed and were NOT rebuilt,
and ``validated_knowledge`` already retrieved SUPPORTED claims with citations.
But:

  * ``ValidatedKnowledgeItem`` carried no ``standing`` — a caller could not tell
    a 2+-source ``verified`` claim from a single-source ``supported`` one (Step 17
    knew the standing; retrieval did not expose it);
  * there was no ``evidence_ids`` attribution per retrieved claim;
  * ``contested``/``unverified`` claims existed in the durable store but were
    SILENTLY filtered out — no refusal, no representation;
  * there was no representation of a justified knowledge record at all
    (``KnowledgeRecord``/``retained_knowledge`` did not exist).

Step 18 adds ONE bounded, deterministic, model-free representation over that
material. It writes nothing, promotes nothing, and never turns unverified or
contradictory information into established knowledge.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from atlas.research.knowledge_representation import (
    KnowledgeStatus,
    RetainedKnowledgeRetriever,
    retain_knowledge,
    retention_from_outcome,
)
from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    ResearchReport,
    SourceKind,
    VerificationStatus,
)
from atlas.research.provenance import build_research_provenance

_URL_A = "https://example.com/a"
_URL_B = "https://example.com/b"

#: Fixed timestamps (Step 19): the models default to ``datetime.now()``, so the
#: fixture pins them — otherwise two separately-built fixtures would differ and
#: the determinism assertions would be meaningless.
_T0 = datetime(2026, 1, 1, 12, 0, 0)


def _citation(uri, index=0, retrieved_at=_T0):
    return CitationRecord(
        record_id=f"cite:{uri}:{index:04d}",
        source_uri=uri,
        source_title=uri.split("/")[2],
        source_kind=SourceKind.WEB,
        section=f"chunk:{index:04d}",
        retrieved_at=retrieved_at,
    )


def _claim(claim_id, statement, citations, confidence=0.8, extracted_at=_T0):
    return KnowledgeClaim(
        claim_id=claim_id,
        statement=statement,
        citations=tuple(citations),
        confidence=confidence,
        extracted_at=extracted_at,
    )


def _verification(
    claim_id, outcome, supporting=(), contradicting=(), score=0.75, verified_at=_T0
):
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
        verified_at=verified_at,
        metadata={
            "outcome": outcome,
            "supporting": list(supporting),
            "contradicting": list(contradicting),
        },
    )


def _report(claims, verifications, report_id="report:1"):
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


def _full_report():
    """One report covering every standing and the missing-provenance case."""
    claims = [
        _claim("c_verified", "V", [_citation(_URL_A), _citation(_URL_B)]),
        _claim("c_supported", "S", [_citation(_URL_A)]),
        _claim("c_contested", "C", [_citation(_URL_A), _citation(_URL_B)]),
        _claim("c_unverified", "U", [_citation(_URL_A)]),
        _claim("c_nocite", "N", []),
    ]
    verifications = [
        _verification("c_verified", "VERIFIED", supporting=[_URL_A, _URL_B], score=0.95),
        _verification("c_supported", "PLAUSIBLE", supporting=[_URL_A]),
        _verification(
            "c_contested", "CONTESTED", supporting=[_URL_A], contradicting=[_URL_B]
        ),
        _verification("c_unverified", "UNKNOWN"),
        _verification("c_nocite", "PLAUSIBLE", supporting=[_URL_A]),
    ]
    return _report(claims, verifications)


def _provenance(report, **kwargs):
    kwargs.setdefault("objective", "Q")
    kwargs.setdefault("used_sources", [_URL_A, _URL_B])
    kwargs.setdefault("report_ids", ["report:1"])
    return build_research_provenance(reports=[report], **kwargs)


# ---------------------------------------------------------------------------
# 1. Representation of justified knowledge
# ---------------------------------------------------------------------------


class TestRepresentation:
    def test_justified_claims_become_structured_records(self):
        retention = retain_knowledge(_provenance(_full_report()))
        by_id = {r.claim_id: r for r in retention.records}
        # c_nocite is justified but carries no provenance link -> refused.
        assert set(by_id) == {"c_verified", "c_supported"}
        record = by_id["c_verified"]
        assert record.record_id == "knowledge:c_verified"
        assert record.claim_id == "c_verified"
        assert record.statement == "V"
        assert record.justified is True
        assert record.confidence == 0.8
        assert record.verification_status == "SUPPORTED"
        assert record.verification_score == 0.95
        assert record.verification_outcome == "VERIFIED"

    def test_records_are_immutable_and_bounded(self):
        retention = retain_knowledge(_provenance(_full_report()))
        with pytest.raises(Exception):
            retention.records[0].statement = "other"  # type: ignore[misc]
        assert len(retention.records) <= 40
        assert all(len(r.statement) <= 400 for r in retention.records)


# ---------------------------------------------------------------------------
# 2. Provenance preservation and attribution
# ---------------------------------------------------------------------------


class TestProvenancePreservation:
    def test_record_preserves_the_step17_chain(self):
        provenance = _provenance(_full_report())
        retention = retain_knowledge(provenance)
        record = next(r for r in retention.records if r.claim_id == "c_verified")
        # evidence items (citations) preserved verbatim
        assert {e.evidence_id for e in record.evidence} == {
            f"cite:{_URL_A}:0000",
            f"cite:{_URL_B}:0000",
        }
        assert set(record.source_uris) == {_URL_A, _URL_B}
        # evaluated sources (Step 17 objects) preserved
        assert {s.source_uri for s in record.sources} == {_URL_A, _URL_B}
        assert all(s.authorization == "authorized" for s in record.sources)
        # research lineage preserved
        assert record.report_ids == ("report:1",)
        assert record.objective == "Q"
        assert record.supporting_sources == (_URL_A, _URL_B)

    def test_attribution_reaches_the_serialized_form(self):
        retention = retain_knowledge(_provenance(_full_report()))
        payload = retention.to_dict()
        record = next(r for r in payload["records"] if r["claim_id"] == "c_supported")
        assert record["source_uris"] == [_URL_A]
        assert record["evidence"][0]["source_uri"] == _URL_A
        assert record["evidence"][0]["section"] == "chunk:0000"
        json.dumps(payload)

    def test_retention_rule_is_reported(self):
        payload = retain_knowledge(_provenance(_full_report())).to_dict()
        assert "retained as knowledge only when" in payload["retention_rule"]


# ---------------------------------------------------------------------------
# 3. Promotion / rejection boundaries
# ---------------------------------------------------------------------------


class TestRetentionBoundaries:
    def test_contested_is_refused(self):
        retention = retain_knowledge(_provenance(_full_report()))
        refused = {r.claim_id: r for r in retention.refused}
        assert "c_contested" in refused
        assert refused["c_contested"].standing == "contested"
        assert "conflicting evidence" in refused["c_contested"].reason
        assert "c_contested" not in {r.claim_id for r in retention.records}

    def test_unverified_is_refused(self):
        retention = retain_knowledge(_provenance(_full_report()))
        refused = {r.claim_id: r for r in retention.refused}
        assert refused["c_unverified"].standing == "unverified"
        assert "without supporting evidence" in refused["c_unverified"].reason

    def test_justified_without_a_provenance_link_is_refused(self):
        retention = retain_knowledge(_provenance(_full_report()))
        refused = {r.claim_id: r for r in retention.refused}
        assert refused["c_nocite"].standing == "supported"
        assert "no provenance link" in refused["c_nocite"].reason

    def test_missing_verification_is_not_retained(self):
        report = _report([_claim("c1", "S", [_citation(_URL_A)])], [])
        retention = retain_knowledge(_provenance(report))
        assert retention.records == ()
        assert retention.refused[0].standing == "unknown"

    def test_counts_and_findings(self):
        retention = retain_knowledge(_provenance(_full_report()))
        assert retention.established_count == 1
        assert retention.supported_count == 2
        assert retention.contested_count == 1
        assert retention.unverified_count == 1
        # retained: c_verified + c_supported; refused: contested, unverified, no-cite
        assert retention.retained_count == 2
        assert retention.refused_count == 3
        assert any("refused" in f for f in retention.findings)

    def test_no_retained_record_is_ever_silently_trusted(self):
        retention = retain_knowledge(_provenance(_full_report()))
        for record in retention.records:
            assert record.established is (record.standing == "verified")
            assert record.evidence  # a retained record always has provenance


# ---------------------------------------------------------------------------
# 4. Established vs supported, determinism and dedup
# ---------------------------------------------------------------------------


class TestDeterminismAndDedup:
    def test_established_only_for_multi_source_corroboration(self):
        retention = retain_knowledge(_provenance(_full_report()))
        established = [r for r in retention.records if r.established]
        assert [r.claim_id for r in established] == ["c_verified"]
        supported = [r for r in retention.records if r.claim_id == "c_supported"]
        assert supported[0].established is False

    def test_duplicate_claims_are_collapsed_deterministically(self):
        report = _full_report()
        duplicate = _report(
            [_claim("c_supported", "S", [_citation(_URL_A)])],
            [_verification("c_supported", "PLAUSIBLE", supporting=[_URL_A])],
            report_id="report:2",
        )
        provenance = build_research_provenance(
            objective="Q",
            used_sources=[_URL_A, _URL_B],
            report_ids=["report:1", "report:2"],
            reports=[report, duplicate],
        )
        retention = retain_knowledge(provenance)
        ids = [r.claim_id for r in retention.records]
        assert ids.count("c_supported") == 1
        assert retention.duplicates == ("c_supported",)
        assert any("duplicate" in f for f in retention.findings)

    def test_deterministic_ordering_and_serialization(self):
        first = retain_knowledge(_provenance(_full_report()))
        second = retain_knowledge(_provenance(_full_report()))
        assert first == second
        ids = [r.claim_id for r in first.records]
        assert ids == sorted(ids)
        json.dumps(first.to_dict())

    def test_insufficient_input_retains_nothing(self):
        empty = build_research_provenance(objective="Q")
        retention = retain_knowledge(empty)
        assert retention.records == ()
        assert retention.has_insufficient_input is True
        assert any("nothing was retained" in f for f in retention.findings)

    def test_none_provenance_is_fail_closed(self):
        retention = retain_knowledge(None)
        assert retention.records == ()
        assert retention.has_insufficient_input is True

    def test_retention_from_outcome_adapter(self):
        outcome = type(
            "O",
            (),
            {
                "objective": "Q",
                "query": "",
                "acquisition_id": "",
                "report_ids": ("report:1",),
                "sources": (_URL_A, _URL_B),
                "denied_sources": (),
                "source_evidence": (),
            },
        )()
        retention = retention_from_outcome(outcome, reports=[_full_report()])
        assert {r.claim_id for r in retention.records} == {
            "c_verified",
            "c_supported",
        }


# ---------------------------------------------------------------------------
# 5. Retrieval of retained knowledge (existing store)
# ---------------------------------------------------------------------------


class TestRetrieval:
    def _storage(self, tmp_path, claims):
        from atlas.storage.research_storage import ResearchSQLiteStorage

        store = ResearchSQLiteStorage(str(tmp_path / "r.db"))
        store.initialize()
        for claim, verification in claims:
            store.store_claim(claim)
            store.store_verification(verification)
        return store

    def test_retrieval_returns_standing_aware_records(self, tmp_path):
        store = self._storage(
            tmp_path,
            [
                (
                    _claim("c1", "Wibble standard is 7.3", [_citation(_URL_A)]),
                    _verification("c1", "VERIFIED", supporting=[_URL_A, _URL_B]),
                ),
            ],
        )
        try:
            result = RetainedKnowledgeRetriever(store).retrieve("Wibble standard")
            assert result.status is KnowledgeStatus.OK
            record = result.records[0]
            assert record.claim_id == "c1"
            assert record.standing == "verified"
            assert record.established is True
            assert record.source_uris == (_URL_A,)
            assert record.evidence[0].evidence_id == f"cite:{_URL_A}:0000"
        finally:
            store.close()

    def test_unjustified_claims_are_never_retrieved(self, tmp_path):
        store = self._storage(
            tmp_path,
            [
                (
                    _claim("c_contested", "Wibble standard is 9", [_citation(_URL_A)]),
                    _verification(
                        "c_contested",
                        "CONTESTED",
                        supporting=[_URL_A],
                        contradicting=[_URL_B],
                    ),
                ),
                (
                    _claim("c_unverified", "Wibble standard is 11", [_citation(_URL_A)]),
                    _verification("c_unverified", "UNKNOWN"),
                ),
            ],
        )
        try:
            result = RetainedKnowledgeRetriever(store).retrieve("Wibble standard")
            assert result.status is KnowledgeStatus.EMPTY
            assert result.records == ()
        finally:
            store.close()

    def test_store_unavailable_fails_closed(self):
        result = RetainedKnowledgeRetriever(None).retrieve("anything")
        assert result.status is KnowledgeStatus.STORE_UNAVAILABLE
        assert result.records == ()

    def test_retrieval_is_read_only(self, tmp_path):
        store = self._storage(
            tmp_path,
            [
                (
                    _claim("c1", "Wibble standard is 7.3", [_citation(_URL_A)]),
                    _verification("c1", "PLAUSIBLE", supporting=[_URL_A]),
                ),
            ],
        )
        try:
            before = (
                len(store.load_claims()),
                len(store.load_verifications()),
                len(store.load_citations()),
            )
            for _ in range(3):
                RetainedKnowledgeRetriever(store).retrieve("Wibble standard")
            after = (
                len(store.load_claims()),
                len(store.load_verifications()),
                len(store.load_citations()),
            )
            assert after == before
        finally:
            store.close()


# ---------------------------------------------------------------------------
# 6. Real Atlas/kernel validation
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
    def test_researched_knowledge_is_represented_and_retrievable(
        self, monkeypatch, tmp_path
    ):
        calls: list[str] = []
        atlas = _allowlisted_atlas(monkeypatch, tmp_path, calls)
        try:
            outcome = atlas.research_knowledge_need(_QUESTION, candidate_urls=[_URL])
            assert outcome.status.value == "researched"
            retention = atlas.knowledge_retention(outcome)
            assert retention.retained_count >= 1
            assert retention.refused_count == 0
            for record in retention.records:
                assert record.record_id.startswith("knowledge:")
                assert record.evidence
                assert record.source_uris == (_URL,)
                # single-source corpus: justified but never multi-source established
                assert record.established is False
            assert retention.established_count == 0
            retained = atlas.retained_knowledge("zorblax protocol release")
            assert retained.status is KnowledgeStatus.OK
            assert {r.claim_id for r in retained.records} <= {
                r.claim_id for r in retention.records
            }
        finally:
            atlas.shutdown()

    def test_retrieval_surface_now_exposes_standing_and_evidence(
        self, monkeypatch, tmp_path
    ):
        calls: list[str] = []
        atlas = _allowlisted_atlas(monkeypatch, tmp_path, calls)
        try:
            atlas.research_knowledge_need(_QUESTION, candidate_urls=[_URL])
            result = atlas.validated_knowledge("zorblax protocol release")
            assert result.status.value == "ok"
            for item in result.items:
                assert item.standing in ("verified", "supported")
                assert item.evidence_ids == tuple(
                    c.record_id for c in item.citations
                )
                assert item.validation_status == "SUPPORTED"
        finally:
            atlas.shutdown()

    def test_retained_knowledge_survives_a_kernel_restart(self, monkeypatch, tmp_path):
        calls: list[str] = []
        atlas = _allowlisted_atlas(monkeypatch, tmp_path, calls)
        try:
            atlas.research_knowledge_need(_QUESTION, candidate_urls=[_URL])
            first = atlas.retained_knowledge("zorblax protocol release")
            first_ids = {r.claim_id: r.standing for r in first.records}
            assert first_ids
        finally:
            atlas.shutdown()

        from atlas.kernel.atlas import Atlas

        atlas2 = Atlas()
        atlas2.start()
        try:
            second = atlas2.retained_knowledge("zorblax protocol release")
            assert second.status is KnowledgeStatus.OK
            assert {r.claim_id: r.standing for r in second.records} == first_ids
            for record in second.records:
                assert record.evidence
                assert record.source_uris
        finally:
            atlas2.shutdown()

    def test_denied_and_insufficient_research_retains_nothing(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            denied = atlas.research_knowledge_need(
                _QUESTION, candidate_urls=["https://other.example/x"]
            )
            retention = atlas.knowledge_retention(denied)
            assert retention.records == ()
            assert retention.has_insufficient_input is True
            assert atlas.retained_knowledge("zorblax protocol release").status is (
                KnowledgeStatus.EMPTY
            )
        finally:
            atlas.shutdown()

    def test_contested_knowledge_in_the_store_is_never_retained_as_trusted(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            storage = atlas._research_storage
            storage.store_claim(
                KnowledgeClaim(
                    claim_id="claim:contested-step18",
                    statement="Wibble standard is contested",
                    citations=(_citation(_URL_A),),
                    confidence=0.8,
                )
            )
            storage.store_verification(
                _verification("claim:contested-step18", "CONTESTED", supporting=[_URL_A])
            )
            assert atlas.retained_knowledge("Wibble standard is contested").records == ()
            assert atlas.validated_knowledge("Wibble standard is contested").status.value in (
                "empty",
                "ok",
            )
        finally:
            atlas.shutdown()

    def test_retention_is_read_only_and_never_promotes(self, monkeypatch, tmp_path):
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
            for _ in range(2):
                atlas.knowledge_retention(outcome)
                atlas.retained_knowledge("zorblax protocol release")
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

    def test_steps_1_to_17_preserved(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            need = atlas.knowledge_need(_QUESTION)
            assert need.kind.value == "missing"
            outcome = atlas.research_knowledge_need(_QUESTION)
            assert atlas.research_provenance(outcome).claims == ()
            assert atlas.validated_knowledge(_QUESTION).status.value in (
                "empty",
                "ok",
            )
            assert atlas.chat("Which component owns memory_search?").metadata[
                "architecture"
            ]["kind"] == "ownership"
            assert atlas.chat("Is research available?").metadata[
                "builtin_intent"
            ] == "capability_state"
        finally:
            atlas.shutdown()
