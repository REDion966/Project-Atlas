"""Step 19 — temporal and freshness-aware knowledge.

Measured baseline (real Atlas/kernel, before any change): the pipeline recorded
plenty of EVENT time (citation ``retrieved_at``, claim ``extracted_at``,
verification ``verified_at``) and an existing freshness assessor
(``atlas.evolution.freshness``) already existed — but neither reached retained
knowledge:

  * Step 17 ``ProvenanceEvidence``/``ProvenanceClaim`` carried NO timestamp at
    all (the citation/claim/verification timestamps were dropped);
  * Step 18 ``KnowledgeRecord`` therefore carried no temporal metadata, and
    ``RetainedKnowledgeRetriever`` dropped the ``extracted_at``/``verified_at``
    the underlying item already exposed;
  * nothing bridged retained knowledge to the existing freshness assessor (no
    production code constructs a ``KnowledgeRef``), and there was no content-time
    (when the knowledge is ABOUT) concept anywhere.

Step 19 adds ONE bounded, deterministic, model-free temporal overlay over that
material. It invents no dates, no validity periods and no thresholds — the age
judgement is the EXISTING assessor with its shipped default policy.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from atlas.evolution.freshness.assessor import KnowledgeFreshnessAssessor
from atlas.evolution.freshness.policy import FreshnessPolicy
from atlas.research.knowledge_representation import KnowledgeRecord
from atlas.research.provenance import ProvenanceEvidence
from atlas.research.temporal import (
    TemporalStatus,
    assess_record_temporal,
    assess_temporal,
    temporal_from_retained,
)

NOW = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
_URL = "https://example.com/a"


def _evidence(retrieved_at=None, metadata=None, uri=_URL):
    return ProvenanceEvidence(
        evidence_id=f"cite:{uri}:0000",
        source_uri=uri,
        source_title="a",
        source_kind="WEB",
        section="chunk:0000",
        retrieved_at=retrieved_at,
        metadata=dict(metadata or {}),
    )


def _record(
    *,
    claim_id="c1",
    standing="supported",
    retrieved_at=None,
    extracted_at=None,
    verified_at=None,
    evidence=None,
    knowledge_time="",
    confidence=0.8,
    verification_status="SUPPORTED",
):
    return KnowledgeRecord(
        record_id=f"knowledge:{claim_id}",
        claim_id=claim_id,
        statement="Wibble standard release is 7.3",
        standing=standing,
        established=standing == "verified",
        confidence=confidence,
        verification_status=verification_status,
        evidence=tuple(evidence if evidence is not None else (_evidence(retrieved_at),)),
        retrieved_at=retrieved_at,
        extracted_at=extracted_at,
        verified_at=verified_at,
        knowledge_time=knowledge_time,
    )


def _fresh_record(days=1, **kwargs):
    stamp = NOW - timedelta(days=days)
    return _record(
        retrieved_at=stamp,
        extracted_at=stamp,
        verified_at=stamp,
        evidence=(_evidence(stamp),),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. Temporal metadata representation
# ---------------------------------------------------------------------------


class TestTemporalRepresentation:
    def test_event_times_are_represented(self):
        view = assess_record_temporal(_fresh_record(), now=NOW)
        assert view.retrieved_at == NOW - timedelta(days=1)
        assert view.extracted_at == NOW - timedelta(days=1)
        assert view.verified_at == NOW - timedelta(days=1)
        assert view.assessed_at == NOW
        assert view.has_event_time is True
        assert view.age_days == 1.0

    def test_content_time_is_distinct_from_acquisition_time(self):
        view = assess_record_temporal(
            _fresh_record(knowledge_time="2019-05-01T00:00:00+00:00"), now=NOW
        )
        # content time (when the knowledge is ABOUT) ...
        assert view.knowledge_time == "2019-05-01T00:00:00+00:00"
        assert view.knowledge_time_known is True
        # ... versus when Atlas acquired/verified it, kept separate
        assert view.retrieved_at == NOW - timedelta(days=1)
        assert view.verified_at == NOW - timedelta(days=1)
        assert any(
            "kept distinct from when" in f for f in view.findings
        )

    def test_content_time_unknown_is_reported_not_invented(self):
        view = assess_record_temporal(_fresh_record(), now=NOW)
        assert view.knowledge_time == ""
        assert view.knowledge_time_known is False
        assert any("never inferred" in f for f in view.findings)

    def test_content_time_read_from_recorded_source_metadata(self):
        record = _record(
            retrieved_at=NOW - timedelta(days=1),
            verified_at=NOW - timedelta(days=1),
            evidence=(
                _evidence(NOW - timedelta(days=1), {"published_at": "2025-06-01T00:00:00"}),
            ),
        )
        view = assess_record_temporal(record, now=NOW)
        assert view.knowledge_time == "2025-06-01T00:00:00"
        assert view.knowledge_time_known is True

    def test_serialization_is_json_safe_and_bounded(self):
        view = assess_record_temporal(_fresh_record(), now=NOW)
        payload = view.to_dict()
        json.dumps(payload)
        assert payload["status"] == "current_relative"
        assert payload["retrieved_at"].startswith("2026-01-09")
        assert payload["has_event_time"] is True

    def test_immutable(self):
        view = assess_record_temporal(_fresh_record(), now=NOW)
        with pytest.raises(Exception):
            view.status = TemporalStatus.HISTORICAL  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. Deterministic status evaluation (reusing the existing assessor)
# ---------------------------------------------------------------------------


class TestStatusEvaluation:
    def test_recent_evidence_is_current_relative(self):
        view = assess_record_temporal(_fresh_record(days=1), now=NOW)
        assert view.status is TemporalStatus.CURRENT_RELATIVE
        assert view.reasons == ()
        assert any("not a statement that the content is true now" in f for f in view.findings)

    def test_old_evidence_is_historical(self):
        view = assess_record_temporal(_fresh_record(days=400), now=NOW)
        assert view.status is TemporalStatus.HISTORICAL
        assert "SOURCE_AGE" in view.reasons
        assert view.age_days == 400.0
        assert view.rationale  # the EXISTING assessor's own rationale

    def test_existing_assessor_policy_drives_the_threshold(self):
        # A 2-day-old record is current under the default policy ...
        assert (
            assess_record_temporal(_fresh_record(days=2), now=NOW).status
            is TemporalStatus.CURRENT_RELATIVE
        )
        # ... and historical under an injected EXISTING policy (no new threshold
        # is invented here; the assessor's policy decides).
        strict = KnowledgeFreshnessAssessor(
            policy=FreshnessPolicy(
                max_source_age=timedelta(days=1),
                max_verification_age=timedelta(days=1),
                min_confidence=0.5,
            )
        )
        view = assess_record_temporal(_fresh_record(days=2), assessor=strict, now=NOW)
        assert view.status is TemporalStatus.HISTORICAL

    def test_deterministic_for_the_same_clock(self):
        first = assess_record_temporal(_fresh_record(days=400), now=NOW)
        second = assess_record_temporal(_fresh_record(days=400), now=NOW)
        assert first == second
        assert first.to_dict() == second.to_dict()

    def test_many_records_are_ordered_deterministically(self):
        records = [
            _fresh_record(claim_id="c_b"),
            _fresh_record(claim_id="c_a"),
            _fresh_record(claim_id="c_c"),
        ]
        views = assess_temporal(records, now=NOW)
        assert [v.claim_id for v in views] == ["c_a", "c_b", "c_c"]

    def test_mixed_naive_and_aware_timestamps_do_not_break(self):
        naive = datetime(2026, 1, 9, 12, 0, 0)  # the pipeline records naive times
        record = _record(
            retrieved_at=naive,
            extracted_at=naive,
            verified_at=naive,
            evidence=(_evidence(naive),),
        )
        view = assess_record_temporal(record, now=NOW)
        assert view.status is TemporalStatus.CURRENT_RELATIVE


# ---------------------------------------------------------------------------
# 3. Missing temporal evidence stays unknown
# ---------------------------------------------------------------------------


class TestMissingEvidence:
    def test_no_timestamps_is_undated_never_current(self):
        blank = _record(evidence=(), retrieved_at=None)
        view = assess_record_temporal(blank, now=NOW)
        assert view.status is TemporalStatus.UNDATED
        assert view.has_event_time is False
        assert view.status is not TemporalStatus.CURRENT_RELATIVE
        assert any("never assumed current" in f for f in view.findings)

    def test_missing_provenance_reason_is_preserved(self):
        blank = _record(evidence=(), retrieved_at=None)
        view = assess_record_temporal(blank, now=NOW)
        assert "MISSING_PROVENANCE" in view.reasons
        # the EXISTING assessor's own rationale is preserved verbatim
        assert view.rationale == "no-provenance"

    def test_no_validity_period_is_invented(self):
        view = assess_record_temporal(_fresh_record(), now=NOW)
        payload = json.dumps(view.to_dict())
        assert "valid_until" not in payload
        assert "expires" not in payload
        assert view.knowledge_time == ""


# ---------------------------------------------------------------------------
# 4. Provenance and standing preservation
# ---------------------------------------------------------------------------


class TestPreservation:
    def test_standing_and_identity_are_carried(self):
        record = _fresh_record(claim_id="c9", standing="verified")
        view = assess_record_temporal(record, now=NOW)
        assert view.record_id == "knowledge:c9"
        assert view.claim_id == "c9"
        assert view.standing == "verified"
        assert view.justified is True

    def test_assessment_does_not_mutate_the_record(self):
        record = _fresh_record()
        before = record.to_dict()
        assess_record_temporal(record, now=NOW)
        assert record.to_dict() == before

    def test_temporal_overlay_of_a_retained_result(self):
        class _Retained:
            status = type("S", (), {"value": "ok"})()
            query = "wibble"
            message = ""
            records = (_fresh_record(claim_id="c1"), _fresh_record(claim_id="c2", standing="verified"))

        overlay = temporal_from_retained(_Retained(), now=NOW)
        assert overlay.status == "ok"
        assert overlay.query == "wibble"
        assert len(overlay.entries) == 2
        assert len(overlay.current_relative) == 2
        json.dumps(overlay.to_dict())


# ---------------------------------------------------------------------------
# 5. Real Atlas/kernel validation
# ---------------------------------------------------------------------------


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


def _started_atlas(monkeypatch, tmp_path):
    _tmp_storage(monkeypatch, tmp_path)
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    return atlas


def _seed(storage, claim_id, statement, retrieved_at, *, content_time=""):
    from atlas.research.models import (
        CitationRecord,
        ClaimVerification,
        KnowledgeClaim,
        SourceKind,
        VerificationStatus,
    )

    metadata = {"published_at": content_time} if content_time else {}
    storage.store_claim(
        KnowledgeClaim(
            claim_id=claim_id,
            statement=statement,
            citations=(
                CitationRecord(
                    record_id=f"cite:{claim_id}:0000",
                    source_uri=f"https://example.com/{claim_id}",
                    source_title=claim_id,
                    source_kind=SourceKind.WEB,
                    section="chunk:0000",
                    retrieved_at=retrieved_at,
                    metadata=dict(metadata),
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
            metadata={
                "outcome": "PLAUSIBLE",
                "supporting": [f"https://example.com/{claim_id}"],
                "contradicting": [],
            },
        )
    )


class TestRealKernel:
    def test_current_relative_and_historical_through_the_kernel(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            storage = atlas._research_storage
            _seed(storage, "cur", "Wibble standard current probe", NOW - timedelta(days=1))
            _seed(storage, "old", "Wibble standard historical probe", NOW - timedelta(days=400))

            current = atlas.temporal_knowledge("Wibble standard current probe", now=NOW)
            assert current.status == "ok"
            assert current.entries[0].status is TemporalStatus.CURRENT_RELATIVE
            assert current.entries[0].knowledge_time_known is False

            historical = atlas.temporal_knowledge(
                "Wibble standard historical probe", now=NOW
            )
            assert historical.entries[0].status is TemporalStatus.HISTORICAL
            assert historical.entries[0].age_days == 400.0
        finally:
            atlas.shutdown()

    def test_temporal_metadata_reaches_the_retrieval_surface(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _seed(atlas._research_storage, "cur", "Wibble standard probe", NOW - timedelta(days=1))
            retained = atlas.retained_knowledge("Wibble standard probe")
            assert retained.status.value == "ok"
            record = retained.records[0]
            assert record.retrieved_at == NOW - timedelta(days=1)
            assert record.extracted_at == NOW - timedelta(days=1)
            assert record.verified_at == NOW - timedelta(days=1)
            # and the timestamp survives serialization (ISO)
            assert record.to_dict()["retrieved_at"].startswith("2026-01-09")
            # the existing validated-knowledge surface is unchanged
            item = atlas.validated_knowledge("Wibble standard probe").items[0]
            assert item.extracted_at == NOW - timedelta(days=1)
            assert item.verified_at == NOW - timedelta(days=1)
        finally:
            atlas.shutdown()

    def test_temporal_view_survives_a_kernel_restart(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _seed(atlas._research_storage, "old", "Wibble standard probe", NOW - timedelta(days=400))
            before = atlas.temporal_knowledge("Wibble standard probe", now=NOW)
            assert before.entries[0].status is TemporalStatus.HISTORICAL
        finally:
            atlas.shutdown()

        from atlas.kernel.atlas import Atlas

        atlas2 = Atlas()
        atlas2.start()
        try:
            after = atlas2.temporal_knowledge("Wibble standard probe", now=NOW)
            assert after.entries[0].status is TemporalStatus.HISTORICAL
            assert after.entries[0].age_days == 400.0
            assert after.entries[0].retrieved_at == NOW - timedelta(days=400)
        finally:
            atlas2.shutdown()

    def test_unjustified_and_absent_knowledge_have_no_temporal_entry(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            from atlas.research.models import (
                CitationRecord,
                ClaimVerification,
                KnowledgeClaim,
                SourceKind,
                VerificationStatus,
            )

            storage = atlas._research_storage
            storage.store_claim(
                KnowledgeClaim(
                    claim_id="claim:contested-step19",
                    statement="Wibble standard is contested",
                    citations=(
                        CitationRecord(
                            record_id="cite:contested:0000",
                            source_uri="https://example.com/c",
                            source_title="c",
                            source_kind=SourceKind.WEB,
                            section="chunk:0000",
                            retrieved_at=NOW - timedelta(days=1),
                        ),
                    ),
                    confidence=0.8,
                    extracted_at=NOW - timedelta(days=1),
                )
            )
            storage.store_verification(
                ClaimVerification(
                    verification_id="verify:claim:contested-step19",
                    claim_id="claim:contested-step19",
                    status=VerificationStatus.CONTRADICTED,
                    score=0.6,
                    verified_at=NOW - timedelta(days=1),
                    metadata={"outcome": "CONTESTED", "supporting": [], "contradicting": []},
                )
            )
            # contested knowledge is not retained, so it has NO temporal entry
            contested = atlas.temporal_knowledge("Wibble standard is contested", now=NOW)
            assert contested.status == "empty"
            assert contested.entries == ()
            # and unknown topics have none either
            absent = atlas.temporal_knowledge("Nothing recorded at all", now=NOW)
            assert absent.status == "empty"
            assert absent.entries == ()
        finally:
            atlas.shutdown()

    def test_event_time_only_never_claims_content_currency(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _seed(
                atlas._research_storage,
                "content",
                "Wibble standard content probe",
                NOW - timedelta(days=1),
                content_time="2025-06-01T00:00:00+00:00",
            )
            tk = atlas.temporal_knowledge("Wibble standard content probe", now=NOW)
            entry = tk.entries[0]
            assert entry.knowledge_time == "2025-06-01T00:00:00+00:00"
            assert entry.knowledge_time_known is True
            # status reflects acquisition recency, not the content date
            assert entry.status is TemporalStatus.CURRENT_RELATIVE
            assert entry.retrieved_at == NOW - timedelta(days=1)
        finally:
            atlas.shutdown()

    def test_temporal_assessment_is_read_only(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            storage = atlas._research_storage
            _seed(storage, "cur", "Wibble standard probe", NOW - timedelta(days=1))
            before = (
                len(storage.load_claims()),
                len(storage.load_verifications()),
                len(storage.load_citations()),
                len(storage.load_reports()),
            )
            for _ in range(3):
                atlas.temporal_knowledge("Wibble standard probe", now=NOW)
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

    def test_steps_1_to_18_preserved(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            question = "What is the current release of the Zorblax protocol?"
            assert atlas.knowledge_need(question).kind.value == "missing"
            outcome = atlas.research_knowledge_need(question)
            assert atlas.research_provenance(outcome).claims == ()
            assert atlas.knowledge_retention(outcome).records == ()
            assert atlas.retained_knowledge(question).status.value == "empty"
            assert atlas.chat("Which component owns memory_search?").metadata[
                "architecture"
            ]["kind"] == "ownership"
            assert atlas.chat("Is research available?").metadata[
                "builtin_intent"
            ] == "capability_state"
        finally:
            atlas.shutdown()
