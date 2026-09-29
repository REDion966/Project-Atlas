"""Step 21 — continuous information monitoring.

Measured baseline (real Atlas/kernel, before any change): nothing ran
continuously. ``Atlas.tick()`` referenced no monitor/refresh/freshness at all (its
body drives only the task manager, the evolution scheduler, the goal executor and
the autonomy dispatcher), the Steps 19-20 temporal and refresh surfaces were
purely on-demand, and there was no monitoring target, observation or attention
concept anywhere (`monitor_knowledge`, `atlas/research/monitoring.py` absent).

Step 21 adds ONE bounded, deterministic, model-free monitoring pass that REUSES
the existing temporal overlay and refresh plan. It observes only: it fetches
nothing, writes nothing, replaces nothing, promotes nothing, and it is
deliberately not wired into ``Atlas.tick()``.
"""

from __future__ import annotations

import inspect
import json
from datetime import datetime, timedelta, timezone

import pytest

from atlas.research.knowledge_representation import KnowledgeRecord
from atlas.research.monitoring import (
    AttentionKind,
    KnowledgeMonitor,
    MonitoringStatus,
    attention_for,
)
from atlas.research.provenance import ProvenanceEvidence
from atlas.research.refresh import KnowledgeRefresher, RefreshRequest, plan_refresh

NOW = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
_URL_A = "https://example.com/a"
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
    confidence=0.8,
    uris=(_URL_A,),
):
    return KnowledgeRecord(
        record_id=f"knowledge:{claim_id}",
        claim_id=claim_id,
        statement=statement,
        standing=standing,
        established=standing == "verified",
        confidence=confidence,
        verification_status="SUPPORTED",
        evidence=tuple(_evidence(u, retrieved_at) for u in uris),
        retrieved_at=retrieved_at,
        verified_at=verified_at,
        objective=statement,
    )


class _Retriever:
    """Minimal retrieval double (status + records), like the kernel's."""

    def __init__(self, records=(), status="ok"):
        self._records = tuple(records)
        self._status = status

    def retrieve(self, query):
        return type(
            "R",
            (),
            {"status": self._status, "query": query, "records": self._records, "message": ""},
        )()


class _StubAcquirer:
    def __init__(self, denied=()):
        self.denied = set(denied)

    def authorize(self, urls):
        authorized, denied = [], []
        for url in urls:
            (denied if url in self.denied else authorized).append(url)
        return tuple(authorized), tuple(denied)


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


def _monitor(records=(), *, status="ok", refresher=None):
    return KnowledgeMonitor(
        retriever=_Retriever(records, status=status),
        refresher=refresher,
    )


def _refresher(*, acquisition=None, acquirer=None):
    return KnowledgeRefresher(
        acquirer=acquirer if acquirer is not None else _StubAcquirer(),
        acquisition=acquisition,
        storage=_FakeStorage(),
    )


# ---------------------------------------------------------------------------
# 1. Attention detection (fresh / stale / uncertain / unknown)
# ---------------------------------------------------------------------------


class TestAttentionDetection:
    def test_fresh_record_requires_no_attention(self):
        report = _monitor([_record(retrieved_at=_NEW, verified_at=_NEW)]).monitor(
            "q", now=NOW
        )
        observation = report.observations[0]
        assert observation.attention == AttentionKind.FRESH.value
        assert observation.requires_attention is False
        assert observation.refresh_required is False
        assert report.fresh_count == 1
        assert report.attention_required == ()

    def test_stale_record_requires_attention_and_is_a_refresh_candidate(self):
        report = _monitor([_record()]).monitor("q", now=NOW)
        observation = report.observations[0]
        assert observation.attention == AttentionKind.STALE.value
        assert observation.requires_attention is True
        assert observation.refresh_required is True
        assert observation.age_days == 400.0
        assert "SOURCE_AGE" in observation.reasons
        assert report.refresh_candidates == (observation,)

    def test_uncertain_record_requires_attention_but_no_refresh(self):
        # low confidence with fresh timestamps -> the EXISTING assessor is
        # UNCERTAIN -> the Step 19 status is unknown -> attention is uncertain.
        report = _monitor(
            [_record(confidence=0.1, retrieved_at=_NEW, verified_at=_NEW)]
        ).monitor("q", now=NOW)
        observation = report.observations[0]
        assert observation.temporal_status == "unknown"
        assert observation.attention == AttentionKind.UNCERTAIN.value
        assert observation.requires_attention is True
        assert observation.refresh_required is False
        assert "governed review" in " ".join(observation.findings)

    def test_temporally_unknown_record_is_explicit(self):
        blank = KnowledgeRecord(
            record_id="knowledge:blank",
            claim_id="blank",
            statement="Wibble standard unknown",
            standing="supported",
            established=False,
            evidence=(),
        )
        report = _monitor([blank]).monitor("q", now=NOW)
        observation = report.observations[0]
        assert observation.attention == AttentionKind.TEMPORALLY_UNKNOWN.value
        assert observation.requires_attention is True
        assert observation.refresh_required is False
        assert observation.age_days is None

    def test_attention_mapping_never_assumes_freshness(self):
        assert attention_for("historical") == (AttentionKind.STALE, True)
        assert attention_for("undated") == (AttentionKind.TEMPORALLY_UNKNOWN, True)
        assert attention_for("unknown") == (AttentionKind.UNCERTAIN, True)
        assert attention_for("current_relative") == (AttentionKind.FRESH, False)
        assert attention_for("") == (AttentionKind.UNKNOWN, False)
        assert attention_for("something-else") == (AttentionKind.UNKNOWN, False)


# ---------------------------------------------------------------------------
# 2. Targets, determinism and idempotency
# ---------------------------------------------------------------------------


class TestTargetsAndDeterminism:
    def test_monitoring_targets_are_represented(self):
        report = _monitor([_record(claim_id="c9")]).monitor("q", now=NOW)
        target = report.targets[0]
        assert target.record_id == "knowledge:c9"
        assert target.claim_id == "c9"
        assert target.standing == "supported"
        assert target.temporal_status == "historical"
        assert target.monitored is True
        assert target.sources == (_URL_A,)

    def test_multiple_items_are_monitored_in_order(self):
        report = _monitor(
            [
                _record(claim_id="c_b"),
                _record(claim_id="c_a", retrieved_at=_NEW, verified_at=_NEW),
                _record(claim_id="c_c"),
            ]
        ).monitor("q", now=NOW)
        assert [t.claim_id for t in report.targets] == ["c_a", "c_b", "c_c"]
        assert [o.claim_id for o in report.observations] == ["c_a", "c_b", "c_c"]
        assert report.observed_count == 3
        assert len(report.attention_required) == 2

    def test_observations_are_deterministic(self):
        first = _monitor([_record()]).monitor("q", now=NOW)
        second = _monitor([_record()]).monitor("q", now=NOW)
        assert first == second
        assert first.to_dict() == second.to_dict()
        json.dumps(first.to_dict())

    def test_duplicate_observations_are_collapsed(self):
        # two records with the same identity would produce the same observation
        duplicate = _record(claim_id="c1")
        report = _monitor([duplicate, duplicate]).monitor("q", now=NOW)
        assert len(report.observations) == 1
        assert len(report.targets) == 2

    def test_observation_ids_are_stable_and_identifying(self):
        report = _monitor([_record(claim_id="c1")]).monitor("q", now=NOW)
        assert report.observations[0].observation_id == (
            "monitor:knowledge:c1:stale"
        )

    def test_empty_and_unavailable_store_are_explicit(self):
        empty = _monitor([]).monitor("q", now=NOW)
        assert empty.status is MonitoringStatus.EMPTY
        assert empty.observations == ()
        assert any("nothing to monitor" in f for f in empty.findings)

        unavailable = _monitor([], status="store_unavailable").monitor("q", now=NOW)
        assert unavailable.status is MonitoringStatus.STORE_UNAVAILABLE
        assert unavailable.observations == ()

        broken = _monitor([], status="store_error").monitor("q", now=NOW)
        assert broken.status is MonitoringStatus.STORE_ERROR

    def test_bounded(self):
        records = [_record(claim_id=f"c{i:02d}") for i in range(30)]
        report = _monitor(records).monitor("q", now=NOW)
        assert len(report.targets) <= 8
        assert len(report.observations) <= 8


# ---------------------------------------------------------------------------
# 3. Reuse of the Step 20 refresh path
# ---------------------------------------------------------------------------


class TestRefreshReuse:
    def test_observation_reuses_the_existing_refresh_request(self):
        record = _record()
        report = _monitor([record]).monitor("q", now=NOW)
        expected = plan_refresh([record], now=NOW)[0]
        observation = report.observations[0]
        assert isinstance(observation.request, RefreshRequest)
        assert observation.request == expected
        assert observation.request.required is True
        assert observation.action == "research"
        json.dumps(observation.to_dict())

    def test_monitor_only_never_touches_the_acquisition_boundary(self):
        acquisition = _StubAcquisition()
        monitor = _monitor([_record()], refresher=_refresher(acquisition=acquisition))
        report = monitor.monitor("q", now=NOW)
        assert report.refresh_candidates
        assert acquisition.calls == []

    def test_explicit_monitor_and_refresh_runs_step_20(self):
        acquisition = _StubAcquisition()
        monitor = _monitor([_record()], refresher=_refresher(acquisition=acquisition))
        run = monitor.monitor_and_refresh("q", now=NOW)
        assert run.refresh is not None
        assert acquisition.calls  # the explicit call DID try the recorded source
        assert run.refresh.outcomes[0].request.claim_id == "c1"
        json.dumps(run.to_dict())

    def test_no_candidate_means_no_refresh_at_all(self):
        acquisition = _StubAcquisition()
        monitor = _monitor(
            [_record(retrieved_at=_NEW, verified_at=_NEW)],
            refresher=_refresher(acquisition=acquisition),
        )
        run = monitor.monitor_and_refresh("q", now=NOW)
        assert run.refresh is None
        assert run.refreshed_count == 0
        assert acquisition.calls == []

    def test_without_a_refresher_nothing_is_fetched(self):
        monitor = _monitor([_record()], refresher=None)
        run = monitor.monitor_and_refresh("q", now=NOW)
        assert run.refresh is None
        assert run.report.refresh_candidates  # still observed

    def test_denied_refresh_is_explicit_and_preserves(self):
        monitor = _monitor(
            [_record()], refresher=_refresher(acquirer=_StubAcquirer(denied={_URL_A}))
        )
        run = monitor.monitor_and_refresh("q", now=NOW)
        outcome = run.refresh.outcomes[0]
        assert outcome.status.value == "no_authorized_source"
        assert outcome.denied_sources == (_URL_A,)
        assert outcome.original_preserved is True
        assert run.preserved_count == 1
        assert run.refreshed_count == 0

    def test_failed_refresh_is_explicit_and_preserves(self):
        monitor = _monitor(
            [_record()],
            refresher=_refresher(acquisition=_StubAcquisition(raise_error=True)),
        )
        run = monitor.monitor_and_refresh("q", now=NOW)
        outcome = run.refresh.outcomes[0]
        assert outcome.status.value == "failed"
        assert outcome.original_preserved is True
        assert run.refreshed_count == 0


# ---------------------------------------------------------------------------
# 4. Real Atlas/kernel validation
# ---------------------------------------------------------------------------


GLOBAL_IP = "93.184.216.34"
_TEXT = "The Wibble standard release is 9.9. Atlas monitors provenance on refresh."


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
    from atlas.research.models import (
        CitationRecord,
        ClaimVerification,
        KnowledgeClaim,
        SourceKind,
        VerificationStatus,
    )

    uri = f"https://example.com/{claim_id}"
    storage.store_claim(
        KnowledgeClaim(
            claim_id=claim_id,
            statement=statement,
            citations=(
                CitationRecord(
                    record_id=f"cite:{claim_id}:0000",
                    source_uri=uri,
                    source_title=claim_id,
                    source_kind=SourceKind.WEB,
                    section="chunk:0000",
                    retrieved_at=retrieved_at,
                ),
            ),
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
    def test_monitoring_is_not_wired_into_tick(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            source = inspect.getsource(type(atlas).tick)
            for marker in ("monitor", "refresh", "freshness", "Monitoring"):
                assert marker not in source
        finally:
            atlas.shutdown()

    def test_monitoring_pass_observes_without_mutating(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            storage = atlas._research_storage
            _seed(storage, "old", "Wibble standard release is 3.1", _OLD)
            _seed(storage, "cur", "Wibble standard current is 9.9", _NEW)
            before = (
                len(storage.load_claims()),
                len(storage.load_verifications()),
                len(storage.load_citations()),
                len(storage.load_reports()),
            )
            report = atlas.monitor_knowledge("Wibble standard", now=NOW)
            assert report.status is MonitoringStatus.OK
            assert {t.claim_id for t in report.targets} == {"old", "cur"}
            attention = {o.claim_id: o.attention for o in report.observations}
            assert attention == {"old": "stale", "cur": "fresh"}
            assert [o.claim_id for o in report.refresh_candidates] == ["old"]
            assert report.fresh_count == 1
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

    def test_monitoring_is_deterministic_and_read_only(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _seed(atlas._research_storage, "old", "Wibble standard release is 3.1", _OLD)
            first = atlas.monitor_knowledge("Wibble standard release", now=NOW)
            second = atlas.monitor_knowledge("Wibble standard release", now=NOW)
            assert first.to_dict() == second.to_dict()
        finally:
            atlas.shutdown()

    def test_monitoring_survives_a_restart(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _seed(atlas._research_storage, "old", "Wibble standard release is 3.1", _OLD)
            before = atlas.monitor_knowledge("Wibble standard release", now=NOW)
            assert before.observations[0].attention == "stale"
        finally:
            atlas.shutdown()

        from atlas.kernel.atlas import Atlas

        atlas2 = Atlas()
        atlas2.start()
        try:
            after = atlas2.monitor_knowledge("Wibble standard release", now=NOW)
            assert after.observations[0].attention == "stale"
            assert after.observations[0].age_days == 400.0
        finally:
            atlas2.shutdown()

    def test_deny_by_default_refresh_after_monitoring_fetches_nothing(
        self, monkeypatch, tmp_path
    ):
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
            run = atlas.monitor_and_refresh_knowledge("Wibble standard release", now=NOW)
            assert run.refresh is not None
            outcome = run.refresh.outcomes[0]
            assert outcome.status.value == "no_authorized_source"
            assert run.refreshed_count == 0
            assert calls == []
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

    def test_authorized_monitoring_refresh_reuses_step_20(self, monkeypatch, tmp_path):
        calls: list[str] = []
        atlas = _started_atlas(monkeypatch, tmp_path, calls=calls, allowlisted=True)
        try:
            storage = atlas._research_storage
            _seed(storage, "old", "Wibble standard release is 3.1", _OLD)
            report = atlas.monitor_knowledge("Wibble standard release", now=NOW)
            assert [o.claim_id for o in report.refresh_candidates] == ["old"]
            assert calls == []  # monitoring itself never fetches

            run = atlas.monitor_and_refresh_knowledge(
                "Wibble standard release", now=NOW
            )
            assert calls == ["https://example.com/old"]
            outcome = run.refresh.outcomes[0]
            assert outcome.status.value == "refreshed"
            assert outcome.original.claim_id == "old"
            assert outcome.replacement is not None
            # the original knowledge is preserved through the refresh
            assert any(c.claim_id == "old" for c in storage.load_claims())
        finally:
            atlas.shutdown()

    def test_steps_1_to_20_preserved(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            question = "What is the current release of the Zorblax protocol?"
            assert atlas.knowledge_need(question).kind.value == "missing"
            outcome = atlas.research_knowledge_need(question)
            assert atlas.research_provenance(outcome).claims == ()
            assert atlas.knowledge_retention(outcome).records == ()
            assert atlas.retained_knowledge(question).status.value == "empty"
            assert atlas.temporal_knowledge(question, now=NOW).entries == ()
            assert atlas.refresh_requests(question, now=NOW) == ()
            observed = atlas.monitor_knowledge(question, now=NOW)
            assert observed.status is MonitoringStatus.EMPTY
            assert atlas.chat("Which component owns memory_search?").metadata[
                "architecture"
            ]["kind"] == "ownership"
            assert atlas.chat("Is research available?").metadata[
                "builtin_intent"
            ] == "capability_state"
        finally:
            atlas.shutdown()
