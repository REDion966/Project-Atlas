"""Step 20 — knowledge refresh.

Measured baseline (real Atlas/kernel, before any change): the EXISTING freshness
assessor already computed the refresh decision for stale knowledge
(`StaleKnowledgeCandidate.recommended_action = RESEARCH` with
`provenance_refs`), and Steps 18-19 already represented retained knowledge with
standing and event time. But *nothing* consumed that decision for retained
knowledge: there was no refresh/revalidation seam anywhere (`refresh_knowledge`,
`refresh_requests` and `atlas/research/refresh.py` did not exist), no bounded
refresh request, no replacement decision, and the D2 boundary actively
short-circuits a stale-but-justified claim
(`acquire_external_knowledge(...)` -> `existing_knowledge`, "no external
acquisition"), so a naive route could never re-validate it.

Step 20 adds ONE bounded, deterministic, model-free refresh capability over the
EXISTING boundaries. It writes nothing, deletes nothing, schedules nothing, and
never replaces retained knowledge with weaker evidence.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from atlas.research.knowledge_representation import KnowledgeRecord
from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    ResearchReport,
    SourceKind,
    VerificationStatus,
)
from atlas.research.provenance import ProvenanceEvidence
from atlas.research.refresh import (
    KnowledgeRefresher,
    RefreshStatus,
    ReplacementDecision,
    build_refresh_request,
    compare_replacement,
    plan_refresh,
)

NOW = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
_URL_A = "https://example.com/a"
_URL_B = "https://example.com/b"
_OLD = NOW - timedelta(days=400)
_NEW = NOW - timedelta(days=1)


# ---------------------------------------------------------------------------
# Fixtures (pure)
# ---------------------------------------------------------------------------


def _evidence(uri, retrieved_at):
    return ProvenanceEvidence(
        evidence_id=f"cite:{uri}:0000",
        source_uri=uri,
        source_title=uri.split("/")[2],
        source_kind="WEB",
        section="chunk:0000",
        retrieved_at=retrieved_at,
    )


def _record(
    *,
    claim_id="c1",
    statement="Wibble standard release is 3.1",
    standing="supported",
    retrieved_at=_OLD,
    verified_at=_OLD,
    uris=(_URL_A,),
    verification_status="SUPPORTED",
):
    return KnowledgeRecord(
        record_id=f"knowledge:{claim_id}",
        claim_id=claim_id,
        statement=statement,
        standing=standing,
        established=standing == "verified",
        confidence=0.8,
        verification_status=verification_status,
        evidence=tuple(_evidence(u, retrieved_at) for u in uris),
        retrieved_at=retrieved_at,
        verified_at=verified_at,
        objective=statement,
    )


def _citation(uri, retrieved_at):
    return CitationRecord(
        record_id=f"cite:{uri}:0000",
        source_uri=uri,
        source_title=uri.split("/")[2],
        source_kind=SourceKind.WEB,
        section="chunk:0000",
        retrieved_at=retrieved_at,
    )


def _report(claim_id, statement, uris, outcome, report_id="report:new"):
    citations = tuple(_citation(u, _NEW) for u in uris)
    status = {
        "VERIFIED": VerificationStatus.SUPPORTED,
        "PLAUSIBLE": VerificationStatus.SUPPORTED,
        "CONTESTED": VerificationStatus.CONTRADICTED,
        "UNKNOWN": VerificationStatus.UNVERIFIED,
    }[outcome]
    return ResearchReport(
        report_id=report_id,
        plan_id="plan::new",
        query_id="q-new",
        question="Q",
        findings="",
        claims=(
            KnowledgeClaim(
                claim_id=claim_id,
                statement=statement,
                citations=citations,
                confidence=0.8,
                extracted_at=_NEW,
            ),
        ),
        verifications=(
            ClaimVerification(
                verification_id=f"verify:{claim_id}",
                claim_id=claim_id,
                status=status,
                score=0.75,
                verified_at=_NEW,
                metadata={
                    "outcome": outcome,
                    "supporting": list(uris),
                    "contradicting": [],
                },
            ),
        ),
        citations=(),
    )


class _AcquisitionResult:
    def __init__(self, *, report_ids=(), claim_count=0, sources=(), status="ok"):
        self.report_ids = tuple(report_ids)
        self.claim_count = claim_count
        self.sources = tuple(sources)
        self.status = status
        self.source_evidence = ()
        self.decision = "research"


class _StubAcquisition:
    def __init__(self, result=None, raise_error=False):
        self.result = result
        self.raise_error = raise_error
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def acquire(self, *, question="", sources=(), **kwargs):
        self.calls.append((question, tuple(sources)))
        if self.raise_error:
            raise RuntimeError("pipeline exploded")
        return self.result


class _FakeStorage:
    def __init__(self, reports=()):
        self._reports = list(reports)

    def load_reports(self):
        return list(self._reports)


class _StubAcquirer:
    """The EXISTING D2 boundary's authorization decision, stubbed."""

    def __init__(self, denied=()):
        self.denied = set(denied)

    def authorize(self, urls):
        authorized, denied = [], []
        for url in urls:
            (denied if url in self.denied else authorized).append(url)
        return tuple(authorized), tuple(denied)


def _refresher(*, acquisition=None, reports=(), acquirer=None, capability=None):
    return KnowledgeRefresher(
        acquirer=acquirer if acquirer is not None else _StubAcquirer(),
        acquisition=acquisition,
        storage=_FakeStorage(reports),
        capability_state_provider=(lambda: capability) if capability else None,
    )


# ---------------------------------------------------------------------------
# 1. Refresh requests
# ---------------------------------------------------------------------------


class TestRefreshRequest:
    def test_fresh_knowledge_requires_no_refresh(self):
        request = build_refresh_request(_record(retrieved_at=_NEW, verified_at=_NEW), now=NOW)
        assert request.required is False
        assert request.action == "none"
        assert request.temporal_status == "current_relative"

    def test_stale_knowledge_produces_a_bounded_request(self):
        request = build_refresh_request(_record(), now=NOW)
        assert request.required is True
        assert request.action == "research"
        assert request.temporal_status == "historical"
        assert request.claim_id == "c1"
        assert request.record_id == "knowledge:c1"
        # existing provenance/source information is reused
        assert request.sources == (_URL_A,)
        assert "SOURCE_AGE" in request.reasons
        assert request.query == "Wibble standard release is 3.1"

    def test_verification_age_only_requests_verify(self):
        request = build_refresh_request(
            _record(retrieved_at=_NEW, verified_at=_OLD), now=NOW
        )
        assert request.required is True
        assert request.action == "verify"

    def test_temporal_unknown_is_explicit_and_not_refreshed(self):
        blank = KnowledgeRecord(
            record_id="knowledge:blank",
            claim_id="blank",
            statement="Wibble standard unknown",
            standing="supported",
            established=False,
            evidence=(),
        )
        request = build_refresh_request(blank, now=NOW)
        assert request.required is False
        assert request.temporal_status == "undated"
        outcome = _refresher().refresh(blank, now=NOW)
        assert outcome.status is RefreshStatus.REVIEW_REQUIRED
        assert outcome.request.required is False
        assert "governed review" in outcome.reason

    def test_plan_is_ordered_and_bounded(self):
        records = [_record(claim_id="c_b"), _record(claim_id="c_a")]
        requests = plan_refresh(records, now=NOW)
        assert [r.claim_id for r in requests] == ["c_a", "c_b"]
        assert all(len(r.sources) <= 8 for r in requests)

    def test_request_is_deterministic(self):
        first = build_refresh_request(_record(), now=NOW)
        second = build_refresh_request(_record(), now=NOW)
        assert first == second
        json.dumps(first.to_dict())


# ---------------------------------------------------------------------------
# 2. Replacement comparison
# ---------------------------------------------------------------------------


class TestReplacementComparison:
    def test_stronger_evidence_is_accepted(self):
        decision, reason = compare_replacement(
            _record(standing="supported"), _record(claim_id="new", standing="verified")
        )
        assert decision is ReplacementDecision.ACCEPTED
        assert "at least as strong" in reason

    def test_equal_evidence_is_accepted(self):
        decision, _ = compare_replacement(
            _record(standing="supported"), _record(claim_id="new", standing="supported")
        )
        assert decision is ReplacementDecision.ACCEPTED

    def test_weaker_evidence_preserves_the_original(self):
        decision, reason = compare_replacement(
            _record(standing="verified"), _record(claim_id="new", standing="supported")
        )
        assert decision is ReplacementDecision.WEAKER_EVIDENCE
        assert "weaker" in reason

    def test_unjustified_evidence_preserves_the_original(self):
        unjustified = KnowledgeRecord(
            record_id="knowledge:new",
            claim_id="new",
            statement="S",
            standing="supported",
            established=False,
            justified=False,
            evidence=(),
        )
        decision, _ = compare_replacement(_record(standing="supported"), unjustified)
        assert decision is ReplacementDecision.UNJUSTIFIED

    def test_no_candidate_preserves_the_original(self):
        decision, reason = compare_replacement(_record(), None)
        assert decision is ReplacementDecision.NO_CANDIDATE
        assert "no refreshed evidence" in reason


# ---------------------------------------------------------------------------
# 3. Refresh execution (stub boundary)
# ---------------------------------------------------------------------------


class TestRefreshExecution:
    def test_not_required_never_touches_the_boundary(self):
        acquisition = _StubAcquisition(_AcquisitionResult())
        outcome = _refresher(acquisition=acquisition).refresh(
            _record(retrieved_at=_NEW, verified_at=_NEW), now=NOW
        )
        assert outcome.status is RefreshStatus.NOT_REQUIRED
        assert acquisition.calls == []
        assert outcome.original is not None
        assert outcome.replaced is False

    def test_no_recorded_sources_is_deny_by_default(self):
        outcome = _refresher().refresh(
            _record(uris=()), now=NOW
        )
        assert outcome.status is RefreshStatus.NO_AUTHORIZED_SOURCE
        assert "deny-by-default" in outcome.reason

    def test_denied_source_fetches_nothing_and_preserves(self):
        acquisition = _StubAcquisition(_AcquisitionResult())
        outcome = _refresher(
            acquisition=acquisition, acquirer=_StubAcquirer(denied={_URL_A})
        ).refresh(_record(), now=NOW)
        assert outcome.status is RefreshStatus.NO_AUTHORIZED_SOURCE
        assert outcome.denied_sources == (_URL_A,)
        assert outcome.fetch_sources == ()
        assert acquisition.calls == []
        assert outcome.original_preserved is True
        assert outcome.replacement is None

    def test_unavailable_research_capability_fails_closed(self):
        acquisition = _StubAcquisition(_AcquisitionResult())
        outcome = _refresher(
            acquisition=acquisition, capability="unavailable"
        ).refresh(_record(), now=NOW)
        assert outcome.status is RefreshStatus.FAILED
        assert acquisition.calls == []
        assert outcome.original_preserved is True

    def test_raising_acquisition_fails_closed(self):
        outcome = _refresher(
            acquisition=_StubAcquisition(raise_error=True)
        ).refresh(_record(), now=NOW)
        assert outcome.status is RefreshStatus.FAILED
        assert outcome.original_preserved is True

    def test_run_without_evidence_is_insufficient(self):
        acquisition = _StubAcquisition(_AcquisitionResult(status="noop"))
        outcome = _refresher(acquisition=acquisition).refresh(_record(), now=NOW)
        assert outcome.status is RefreshStatus.INSUFFICIENT
        assert outcome.decision == ReplacementDecision.NO_CANDIDATE.value
        assert outcome.original_preserved is True
        assert acquisition.calls  # the authorized source WAS tried

    def test_equal_evidence_refreshes(self):
        report = _report("c_new", "Wibble standard release is 9.9", (_URL_A,), "PLAUSIBLE")
        acquisition = _StubAcquisition(
            _AcquisitionResult(report_ids=("report:new",), claim_count=1, sources=(_URL_A,))
        )
        outcome = _refresher(acquisition=acquisition, reports=[report]).refresh(
            _record(standing="supported"), now=NOW
        )
        assert outcome.status is RefreshStatus.REFRESHED
        assert outcome.replaced is True
        assert outcome.replacement.claim_id == "c_new"
        assert outcome.replacement.to_dict()["claim_id"] == "c_new"
        assert outcome.original.claim_id == "c1"
        assert outcome.report_ids == ("report:new",)

    def test_stronger_evidence_refreshes(self):
        report = _report(
            "c_new", "Wibble standard release is 9.9", (_URL_A, _URL_B), "VERIFIED"
        )
        acquisition = _StubAcquisition(
            _AcquisitionResult(report_ids=("report:new",), claim_count=1)
        )
        outcome = _refresher(acquisition=acquisition, reports=[report]).refresh(
            _record(standing="supported"), now=NOW
        )
        assert outcome.status is RefreshStatus.REFRESHED
        assert outcome.candidate_standing == "verified"

    def test_weaker_evidence_preserves_the_original(self):
        report = _report("c_new", "Wibble standard release is 9.9", (_URL_A,), "PLAUSIBLE")
        acquisition = _StubAcquisition(
            _AcquisitionResult(report_ids=("report:new",), claim_count=1)
        )
        outcome = _refresher(acquisition=acquisition, reports=[report]).refresh(
            _record(standing="verified", uris=(_URL_A, _URL_B)), now=NOW
        )
        assert outcome.status is RefreshStatus.PRESERVED
        assert outcome.decision == ReplacementDecision.WEAKER_EVIDENCE.value
        assert outcome.replacement is None
        assert outcome.original_preserved is True

    def test_contested_refresh_evidence_is_never_accepted(self):
        report = _report("c_new", "Wibble standard release is 0.1", (_URL_A,), "CONTESTED")
        acquisition = _StubAcquisition(
            _AcquisitionResult(report_ids=("report:new",), claim_count=1)
        )
        outcome = _refresher(acquisition=acquisition, reports=[report]).refresh(
            _record(standing="supported"), now=NOW
        )
        assert outcome.replacement is None
        assert outcome.original_preserved is True
        assert outcome.status in (RefreshStatus.INSUFFICIENT, RefreshStatus.PRESERVED)

    def test_non_web_sources_pass_through_the_resolver(self):
        acquisition = _StubAcquisition(_AcquisitionResult())
        record = _record(uris=("/tmp/local-note.md",))
        outcome = _refresher(acquisition=acquisition).refresh(record, now=NOW)
        assert outcome.status is RefreshStatus.INSUFFICIENT  # tried, nothing usable
        assert outcome.fetch_sources == ("/tmp/local-note.md",)
        assert outcome.denied_sources == ()

    def test_refresh_all_is_bounded_and_deterministic(self):
        acquisition = _StubAcquisition(_AcquisitionResult())
        records = [_record(claim_id=f"c{i}") for i in range(10)]
        refresher = _refresher(acquisition=acquisition)
        first = refresher.refresh_all(records, now=NOW)
        second = refresher.refresh_all(records, now=NOW)
        assert first.to_dict() == second.to_dict()
        assert len(first.outcomes) <= 3
        json.dumps(first.to_dict())


# ---------------------------------------------------------------------------
# 4. Real Atlas/kernel validation
# ---------------------------------------------------------------------------


GLOBAL_IP = "93.184.216.34"
_TEXT = "The Wibble standard release is 9.9. Atlas preserves provenance on refresh."


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


def _started_atlas(monkeypatch, tmp_path, *, calls=None, allowlisted=False):
    if allowlisted:
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
    _tmp_storage(monkeypatch, tmp_path)
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    return atlas


def _seed(storage, claim_id, statement, retrieved_at):
    uri = f"https://example.com/{claim_id}"
    storage.store_claim(
        KnowledgeClaim(
            claim_id=claim_id,
            statement=statement,
            citations=(_citation(uri, retrieved_at),),
            confidence=0.8,
            extracted_at=retrieved_at,
        )
    )
    storage.store_verification(
        ClaimVerification(
            verification_id=f"verify:{claim_id}",
            claim_id=claim_id,
            status=VerificationStatus.SUPPORTED,
            score=0.75,
            verified_at=retrieved_at,
            metadata={"outcome": "PLAUSIBLE", "supporting": [uri], "contradicting": []},
        )
    )


class TestRealKernel:
    def test_fresh_knowledge_needs_no_refresh(self, monkeypatch, tmp_path):
        calls: list[str] = []
        atlas = _started_atlas(monkeypatch, tmp_path, calls=calls, allowlisted=True)
        try:
            _seed(atlas._research_storage, "cur", "Wibble standard current is 9.9", _NEW)
            plans = atlas.refresh_requests("Wibble standard current", now=NOW)
            assert plans and plans[0].required is False
            result = atlas.refresh_knowledge("Wibble standard current", now=NOW)
            assert result.outcomes[0].status is RefreshStatus.NOT_REQUIRED
            assert calls == []
        finally:
            atlas.shutdown()

    def test_stale_plan_and_denied_refresh_preserve_everything(
        self, monkeypatch, tmp_path
    ):
        calls: list[str] = []
        atlas = _started_atlas(monkeypatch, tmp_path, calls=calls, allowlisted=True)
        try:
            storage = atlas._research_storage
            _seed(storage, "old", "Wibble standard release is 3.1", _OLD)
            plans = atlas.refresh_requests("Wibble standard release", now=NOW)
            assert plans[0].required is True
            assert plans[0].action == "research"
            assert plans[0].sources == ("https://example.com/old",)

            before = (
                len(storage.load_claims()),
                len(storage.load_verifications()),
                len(storage.load_citations()),
                len(storage.load_reports()),
            )
            result = atlas.refresh_knowledge("Wibble standard release", now=NOW)
            outcome = result.outcomes[0]
            assert outcome.status is RefreshStatus.REFRESHED
            assert calls == ["https://example.com/old"]
            assert outcome.original.claim_id == "old"
            assert outcome.replacement is not None
            # the ORIGINAL is preserved: nothing is deleted or overwritten
            after = (
                len(storage.load_claims()),
                len(storage.load_verifications()),
                len(storage.load_citations()),
                len(storage.load_reports()),
            )
            assert after[0] >= before[0] and after[1] >= before[1]
            assert any(c.claim_id == "old" for c in storage.load_claims())
            assert {
                r.claim_id for r in atlas.retained_knowledge("Wibble standard release").records
            } >= {"old"}
        finally:
            atlas.shutdown()

    def test_deny_by_default_refresh_fetches_nothing(self, monkeypatch, tmp_path):
        calls: list[str] = []
        atlas = _started_atlas(monkeypatch, tmp_path, calls=calls)
        try:
            storage = atlas._research_storage
            _seed(storage, "old", "Wibble standard release is 3.1", _OLD)
            before = (
                len(storage.load_claims()),
                len(storage.load_verifications()),
                len(storage.load_citations()),
                len(storage.load_reports()),
            )
            result = atlas.refresh_knowledge("Wibble standard release", now=NOW)
            outcome = result.outcomes[0]
            assert outcome.status is RefreshStatus.NO_AUTHORIZED_SOURCE
            assert outcome.denied_sources == ("https://example.com/old",)
            assert outcome.replacement is None
            assert outcome.original_preserved is True
            assert calls == []  # the policy denied before any I/O
            after = (
                len(storage.load_claims()),
                len(storage.load_verifications()),
                len(storage.load_citations()),
                len(storage.load_reports()),
            )
            assert after == before
            assert len(atlas.retained_knowledge("Wibble standard release").records) == 1
        finally:
            atlas.shutdown()

    def test_authorized_refresh_without_evidence_is_insufficient(
        self, monkeypatch, tmp_path
    ):
        calls: list[str] = []
        atlas = _started_atlas(monkeypatch, tmp_path, calls=calls, allowlisted=True)
        try:
            # an empty body establishes no claim -> nothing may replace the original
            import atlas.research.capability_handlers as cap_mod
            import atlas.research.external_acquisition as ext_mod

            empty_factory = _adapter_factory(_transport(calls, body=""))
            monkeypatch.setattr(cap_mod, "WebSourceAdapter", empty_factory)
            monkeypatch.setattr(ext_mod, "WebSourceAdapter", empty_factory)

            storage = atlas._research_storage
            _seed(storage, "old", "Wibble standard release is 3.1", _OLD)
            result = atlas.refresh_knowledge("Wibble standard release", now=NOW)
            outcome = result.outcomes[0]
            assert calls == ["https://example.com/old"]
            assert outcome.status in (
                RefreshStatus.INSUFFICIENT,
                RefreshStatus.PRESERVED,
            )
            assert outcome.replacement is None
            assert outcome.original_preserved is True
            assert any(c.claim_id == "old" for c in storage.load_claims())
        finally:
            atlas.shutdown()

    def test_refreshed_and_preserved_knowledge_survive_a_restart(
        self, monkeypatch, tmp_path
    ):
        calls: list[str] = []
        atlas = _started_atlas(monkeypatch, tmp_path, calls=calls, allowlisted=True)
        try:
            _seed(atlas._research_storage, "old", "Wibble standard release is 3.1", _OLD)
            result = atlas.refresh_knowledge("Wibble standard release", now=NOW)
            assert result.outcomes[0].status is RefreshStatus.REFRESHED
            replacement_id = result.outcomes[0].replacement.claim_id
        finally:
            atlas.shutdown()

        from atlas.kernel.atlas import Atlas

        atlas2 = Atlas()
        atlas2.start()
        try:
            ids = {
                r.claim_id
                for r in atlas2.retained_knowledge("Wibble standard release").records
            }
            # both the refreshed evidence and the original are durable
            assert replacement_id in ids
            assert "old" in ids
        finally:
            atlas2.shutdown()

    def test_refresh_planning_is_read_only(self, monkeypatch, tmp_path):
        calls: list[str] = []
        atlas = _started_atlas(monkeypatch, tmp_path, calls=calls, allowlisted=True)
        try:
            storage = atlas._research_storage
            _seed(storage, "old", "Wibble standard release is 3.1", _OLD)
            before = (
                len(storage.load_claims()),
                len(storage.load_verifications()),
                len(storage.load_citations()),
                len(storage.load_reports()),
            )
            for _ in range(3):
                atlas.refresh_requests("Wibble standard release", now=NOW)
            after = (
                len(storage.load_claims()),
                len(storage.load_verifications()),
                len(storage.load_citations()),
                len(storage.load_reports()),
            )
            assert after == before
            assert calls == []
            assert atlas.pending_promotion_reviews() == []
        finally:
            atlas.shutdown()

    def test_steps_1_to_19_preserved(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            question = "What is the current release of the Zorblax protocol?"
            assert atlas.knowledge_need(question).kind.value == "missing"
            outcome = atlas.research_knowledge_need(question)
            assert atlas.research_provenance(outcome).claims == ()
            assert atlas.knowledge_retention(outcome).records == ()
            assert atlas.retained_knowledge(question).status.value == "empty"
            assert atlas.temporal_knowledge(question, now=NOW).entries == ()
            assert atlas.chat("Which component owns memory_search?").metadata[
                "architecture"
            ]["kind"] == "ownership"
            assert atlas.chat("Is research available?").metadata[
                "builtin_intent"
            ] == "capability_state"
        finally:
            atlas.shutdown()
