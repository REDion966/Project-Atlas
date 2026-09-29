"""Step 22 — general capability gap detection.

Measured baseline (real Atlas/kernel, before any change): the existing signals
existed but no capability-gap diagnosis did. `Atlas` had NO capability-gap API
(`assess_capability_gap` / `atlas/self_knowledge/capability_gap.py` did not
exist), the EXISTING request-level adjudicator
(`atlas.evolution.development_gap.assess_development_gap`) returned
`missing_knowledge` for a genuinely unsupported operation whenever the knowledge
store held nothing about its subject (its rule infers capability absence from
knowledge presence), and Step 15's `knowledge_need` reported `unsupported_capability`
for an UNAVAILABLE capability — the same kind absence would use, so the two could
not be told apart.

Step 22 adds ONE bounded, deterministic, model-free adjudicator that reconciles
those EXISTING grounded signals into one explainable diagnosis: supported /
temporarily_blocked / governed / missing_knowledge / ambiguous / execution_failure
/ unsupported_capability / unknown.
"""

from __future__ import annotations

import json

import pytest

from atlas.self_knowledge.capability_gap import (
    CapabilityGap,
    CapabilityGapDetector,
    CapabilityGapKind,
    assess_capability_gap,
    capability_names,
)

# A capability-model double with grounded states (the EXISTING model shape).
_ENTRIES = {
    "research.summarize": ("available", ("research",)),
    "open_conversation": ("unavailable", ()),
    "execute": ("blocked", ("approve",)),
    "verify": ("governed", ()),
    "investigate": ("partially_supported", ()),
    "capability_detail": ("unknown", ()),
}


class _Entry:
    def __init__(self, name, state, requires):
        self.name = name
        self.state = state
        self.requires = tuple(requires)


class _Model:
    def __init__(self, entries=_ENTRIES):
        self.entries = tuple(
            _Entry(name, state, requires) for name, (state, requires) in entries.items()
        )

    def find(self, name):
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None


class _Gap:
    """The EXISTING ``DevelopmentGapAssessment`` shape."""

    def __init__(self, kind, matched=()):
        self.kind = type("K", (), {"value": kind})()
        self.matched = tuple(matched)


class _Item:
    statement = "the widget compression format convert operation is documented"


class _KnowledgeResult:
    items = (_Item(),)


class _Retriever:
    def __init__(self, items=True):
        self._items = (_Item(),) if items else ()

    def retrieve(self, query):
        return type("R", (), {"items": self._items, "status": "ok"})()


def _assess(base="missing_capability", *, matched=(), **kwargs):
    kwargs.setdefault("capability_model", _Model())
    kwargs.setdefault("development_gap", _Gap(base, matched))
    return assess_capability_gap("do the widget thing", **kwargs)


# ---------------------------------------------------------------------------
# 1. The four-way distinction
# ---------------------------------------------------------------------------


class TestDistinctions:
    def test_supported_capability_is_no_gap(self):
        gap = _assess("already_supported", matched=("research.summarize",))
        assert gap.kind is CapabilityGapKind.SUPPORTED
        assert gap.is_gap is False
        assert gap.is_supported is True
        assert gap.boundary == "matched_capability"
        assert gap.capability == "research.summarize"
        assert gap.capability_state == "available"

    def test_unavailable_capability_is_not_absence(self):
        gap = _assess("already_supported", matched=("open_conversation",))
        assert gap.kind is CapabilityGapKind.TEMPORARILY_BLOCKED
        assert gap.is_gap is False
        assert gap.capability_state == "unavailable"

    def test_blocked_and_partially_supported_are_also_unavailability(self):
        blocked = _assess("already_supported", matched=("execute",))
        partial = _assess("already_supported", matched=("investigate",))
        assert blocked.kind is CapabilityGapKind.TEMPORARILY_BLOCKED
        assert blocked.capability_state == "blocked"
        assert blocked.requires == ("approve",)
        assert partial.kind is CapabilityGapKind.TEMPORARILY_BLOCKED

    def test_governed_capability_is_authorization_not_absence(self):
        gap = _assess("already_supported", matched=("verify",))
        assert gap.kind is CapabilityGapKind.GOVERNED
        assert gap.boundary == "governance"
        assert gap.is_gap is False
        assert "OWNER approval" in gap.reason

    def test_missing_knowledge_is_a_knowledge_need(self):
        gap = _assess("missing_knowledge")
        assert gap.kind is CapabilityGapKind.MISSING_KNOWLEDGE
        assert gap.boundary == "knowledge"
        assert gap.is_gap is False

    def test_genuine_unsupported_capability_is_a_gap(self):
        gap = _assess("missing_capability")
        assert gap.kind is CapabilityGapKind.UNSUPPORTED_CAPABILITY
        assert gap.is_gap is True
        assert gap.boundary == "unresolved_target"
        assert "validated knowledge" in gap.reason

    def test_ambiguity_is_never_a_gap(self):
        flagged = _assess("missing_capability", ambiguous=True)
        signalled = _assess(
            "missing_capability", knowledge_need={"kind": "ambiguous"}
        )
        assert flagged.kind is CapabilityGapKind.AMBIGUOUS
        assert signalled.kind is CapabilityGapKind.AMBIGUOUS
        assert flagged.is_gap is False

    def test_execution_failure_is_not_capability_absence(self):
        gap = _assess(
            "already_supported", matched=("research.summarize",), execution_failed=True
        )
        assert gap.kind is CapabilityGapKind.EXECUTION_FAILURE
        assert gap.boundary == "execution"
        assert gap.is_gap is False

    def test_execution_failure_without_a_matched_capability_is_not_attributed(self):
        gap = _assess("missing_knowledge", execution_failed=True)
        assert gap.kind is not CapabilityGapKind.EXECUTION_FAILURE
        assert gap.kind is CapabilityGapKind.MISSING_KNOWLEDGE

    def test_knowledge_need_capability_unavailability_is_temporary(self):
        gap = _assess(
            "missing_knowledge",
            knowledge_need={
                "kind": "unsupported_capability",
                "capability": "open_conversation",
                "capability_state": "unavailable",
            },
        )
        assert gap.kind is CapabilityGapKind.TEMPORARILY_BLOCKED
        assert gap.capability == "open_conversation"


# ---------------------------------------------------------------------------
# 2. Fail-closed behaviour
# ---------------------------------------------------------------------------


class TestFailClosed:
    def test_empty_request_is_unknown(self):
        gap = assess_capability_gap("", capability_model=_Model())
        assert gap.kind is CapabilityGapKind.UNKNOWN
        assert gap.is_gap is False

    def test_no_capability_model_is_unknown(self):
        gap = assess_capability_gap("do something", capability_model=None)
        assert gap.kind is CapabilityGapKind.UNKNOWN
        assert "fail-closed" in gap.reason

    def test_unclear_evidence_never_claims_a_gap(self):
        gap = _assess("unclear")
        assert gap.kind is CapabilityGapKind.UNKNOWN
        assert gap.is_gap is False
        assert "fail-closed" in gap.reason

    def test_unrecognised_adjudication_is_unknown(self):
        # an unrecognised base value (never produced by the EXISTING enum) must
        # fail closed rather than fall through to a gap claim
        gap = _assess("something-unrecognised")
        assert gap.kind is CapabilityGapKind.UNKNOWN
        assert gap.is_gap is False

    def test_no_adjudicator_available_is_unknown(self):
        gap = assess_capability_gap(
            "do something",
            capability_model=_Model(),
            development_gap=_Gap("unclear"),
        )
        assert gap.kind is CapabilityGapKind.UNKNOWN

    def test_unfamiliar_wording_alone_is_never_a_gap(self):
        # a request whose subject is unknown (no knowledge) is a knowledge need,
        # never a capability gap
        gap = assess_capability_gap(
            "frobnicate the wibble",
            capability_model=_Model(entries={}),
            knowledge_retriever=_Retriever(items=False),
        )
        assert gap.is_gap is False


# ---------------------------------------------------------------------------
# 3. Reuse of the EXISTING adjudicator
# ---------------------------------------------------------------------------


class TestExistingReuse:
    def test_real_adjudicator_drives_the_base_decision(self):
        # no capability name overlaps and validated knowledge DOES match ->
        # the EXISTING assessor reports missing_capability -> a genuine gap.
        model = _Model(entries={"research": ("available", ())})
        gap = assess_capability_gap(
            "the widget compression format convert operation",
            capability_model=model,
            knowledge_retriever=_Retriever(items=True),
        )
        assert gap.kind is CapabilityGapKind.UNSUPPORTED_CAPABILITY
        assert "development_gap:missing_capability" in gap.evidence

    def test_real_adjudicator_without_knowledge_is_not_a_gap(self):
        model = _Model(entries={"research": ("available", ())})
        gap = assess_capability_gap(
            "frobnicate the wibble",
            capability_model=model,
            knowledge_retriever=_Retriever(items=False),
        )
        assert gap.kind is CapabilityGapKind.MISSING_KNOWLEDGE
        assert "development_gap:missing_knowledge" in gap.evidence

    def test_temporarily_blocked_evidence(self):
        model = _Model(entries={"open_conversation": ("unavailable", ())})
        gap = assess_capability_gap(
            "frobnicate the wibble",
            capability_model=model,
            knowledge_retriever=_Retriever(items=False),
            capability="open_conversation",
        )
        assert gap.kind is CapabilityGapKind.TEMPORARILY_BLOCKED
        assert gap.capability_state == "unavailable"

    def test_detector_binds_the_providers(self):
        detector = CapabilityGapDetector(
            capability_model_provider=lambda: _Model(entries={"research": ("available", ())}),
            knowledge_retriever=_Retriever(items=True),
        )
        gap = detector.assess("the widget compression format convert operation")
        assert gap.kind is CapabilityGapKind.UNSUPPORTED_CAPABILITY
        failing = CapabilityGapDetector(
            capability_model_provider=lambda: (_ for _ in ()).throw(RuntimeError()),
        )
        assert failing.assess("x").kind is CapabilityGapKind.UNKNOWN


# ---------------------------------------------------------------------------
# 4. Determinism, bounds and explainability
# ---------------------------------------------------------------------------


class TestDeterminismAndBounds:
    def test_deterministic_and_serializable(self):
        first = _assess("missing_capability")
        second = _assess("missing_capability")
        assert first == second
        payload = first.to_dict()
        json.dumps(payload)
        assert payload["is_gap"] is True
        assert payload["kind"] == "unsupported_capability"

    def test_reason_and_evidence_are_bounded(self):
        gap = assess_capability_gap("x" * 5000, capability_model=_Model())
        assert len(gap.request) <= 300
        assert len(gap.reason) <= 300
        assert len(gap.evidence) <= 6
        assert len(gap.matched) <= 8

    def test_immutable(self):
        gap = _assess("missing_capability")
        with pytest.raises(Exception):
            gap.kind = CapabilityGapKind.SUPPORTED  # type: ignore[misc]

    def test_capability_names_helper(self):
        assert set(capability_names(_Model())) >= {"research.summarize", "verify"}
        assert capability_names(None) == ()


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


def _seed(storage, claim_id, statement):
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
                ),
            ),
            confidence=0.8,
        )
    )
    storage.store_verification(
        ClaimVerification(
            verification_id=f"verify:{claim_id}",
            claim_id=claim_id,
            status=VerificationStatus.SUPPORTED,
            score=0.75,
            metadata={"outcome": "PLAUSIBLE", "supporting": [uri], "contradicting": []},
        )
    )


class TestRealKernel:
    def test_genuine_gap_from_grounded_evidence(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _seed(
                atlas._research_storage,
                "widget",
                "The widget compression format convert operation is documented.",
            )
            gap = atlas.capability_gap("Convert the widget compression format")
            assert gap.kind is CapabilityGapKind.UNSUPPORTED_CAPABILITY
            assert gap.is_gap is True
            assert "development_gap:missing_capability" in gap.evidence
        finally:
            atlas.shutdown()

    def test_no_evidence_is_not_a_gap(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            gap = atlas.capability_gap("Compress the repository into a zip archive")
            assert gap.is_gap is False
            assert gap.kind in (
                CapabilityGapKind.MISSING_KNOWLEDGE,
                CapabilityGapKind.UNKNOWN,
            )
        finally:
            atlas.shutdown()

    def test_supported_matched_capability(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            gap = atlas.capability_gap("Summarize the Zorblax protocol")
            assert gap.kind is CapabilityGapKind.SUPPORTED
            assert gap.capability_state in ("available", "")
        finally:
            atlas.shutdown()

    def test_unavailable_and_governed_are_not_absence(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            model = atlas.capability_model()
            assert model.find("open_conversation").state == "unavailable"
            blocked = atlas.capability_gap(
                "Have an open-ended chat about anything", capability="open_conversation"
            )
            assert blocked.kind is CapabilityGapKind.TEMPORARILY_BLOCKED
            assert blocked.capability_state == "unavailable"
            assert blocked.is_gap is False

            assert model.find("verify").state == "governed"
            governed = atlas.capability_gap(
                "Verify the development result", capability="verify"
            )
            assert governed.kind is CapabilityGapKind.GOVERNED
            assert governed.is_gap is False
        finally:
            atlas.shutdown()

    def test_ambiguity_and_execution_failure_are_not_gaps(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            ambiguous = atlas.capability_gap("Do it", ambiguous=True)
            assert ambiguous.kind is CapabilityGapKind.AMBIGUOUS
            failed = atlas.capability_gap(
                "Summarize the Zorblax protocol", execution_failed=True
            )
            assert failed.kind is CapabilityGapKind.EXECUTION_FAILURE
            assert failed.is_gap is False
            empty = atlas.capability_gap("")
            assert empty.kind is CapabilityGapKind.UNKNOWN
        finally:
            atlas.shutdown()

    def test_deterministic_and_read_only(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            storage = atlas._research_storage
            _seed(
                storage,
                "widget",
                "The widget compression format convert operation is documented.",
            )
            before = (
                len(storage.load_claims()),
                len(storage.load_verifications()),
                len(storage.load_citations()),
                len(storage.load_reports()),
            )
            first = atlas.capability_gap("Convert the widget compression format")
            second = atlas.capability_gap("Convert the widget compression format")
            assert first.to_dict() == second.to_dict()
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

    def test_conversation_behaviour_is_unchanged(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat("Compress the repository into a zip archive")
            metadata = message.metadata or {}
            # the gap diagnosis is a separate, read-only seam: the conversation
            # outcome is untouched and carries no gap claim
            assert "capability_gap" not in metadata
            assert message.metadata.get("builtin_intent") is not None
        finally:
            atlas.shutdown()

    def test_steps_1_to_21_preserved(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            question = "What is the current release of the Zorblax protocol?"
            assert atlas.knowledge_need(question).kind.value == "missing"
            outcome = atlas.research_knowledge_need(question)
            assert atlas.research_provenance(outcome).claims == ()
            assert atlas.knowledge_retention(outcome).records == ()
            assert atlas.retained_knowledge(question).status.value == "empty"
            assert atlas.temporal_knowledge(question).entries == ()
            assert atlas.refresh_requests(question) == ()
            assert atlas.monitor_knowledge(question).observations == ()
            assert atlas.capability_contract("research")["state"] == "available"
            assert atlas.chat("Is research available?").metadata[
                "builtin_intent"
            ] == "capability_state"
        finally:
            atlas.shutdown()
