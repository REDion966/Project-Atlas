"""Step 15 — autonomous knowledge need detection.

Measured baseline (real Atlas/kernel, before any change): Atlas had NO
knowledge-need detection. Genuinely unseen knowledge questions were reported as
out-of-scope:

  * "What is the current release of the Zorblax protocol?" -> "I could not map
    that request to anything I can do" (unsupported);
  * "Who won the 2147 World Cup?" -> unsupported;
  * "Which component owns memory_search?" style ownership questions were also
    previously misrouted (fixed in Step 14).

The EXISTING D3 sufficiency decision (``KnowledgeSufficiency``) and D2
acquisition status (``ExternalAcquisitionStatus``) already existed but were never
turned into a structured result, never distinguished from a capability gap, and
were unreachable for an unrecognised knowledge question.

Step 15 adds ONE bounded, deterministic, model-free classification over that
already-computed evidence. It detects and represents only: no acquisition, no
research, no storage, no capability-gap detection, no authority.
"""

from __future__ import annotations

import json
import types

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.research.knowledge_need import (
    KnowledgeNeed,
    KnowledgeNeedDetector,
    KnowledgeNeedKind,
    KnowledgeNeedStatus,
    classify_knowledge_need,
    detect_knowledge_need,
)


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _Entry:
    def __init__(self, name, state, reason=""):
        self.name = name
        self.state = state
        self.reason = reason


class _CapabilityModelStub:
    def __init__(self, entries=()):
        self.entries = tuple(entries)
        self._by_name = {e.name: e for e in self.entries}

    def find(self, name):
        return self._by_name.get(name)


class _Answer:
    def __init__(self, status="unknown", acquisition_status="", claims=(), sources=()):
        self.status = types.SimpleNamespace(value=status)
        self.acquisition_status = acquisition_status
        self.claims = tuple(claims)
        self.sources = tuple(sources)


class _KnowledgeResult:
    def __init__(self, status="empty", items=()):
        self.status = types.SimpleNamespace(value=status)
        self.items = tuple(items)
        self.message = ""


def _service(
    *,
    result=None,
    answer=None,
    capability_model=None,
    status_provider=None,
):
    return BuiltinResponseService(
        validated_knowledge_provider=lambda _q: (result if result is not None else _KnowledgeResult()),
        knowledge_decision_provider=lambda _q: (_Answer("sufficient", claims=("x",))),
        knowledge_status_provider=status_provider or (lambda _q: answer),
        capability_model_provider=(
            (lambda: capability_model) if capability_model is not None else None
        ),
    )


# ---------------------------------------------------------------------------
# 1. Deterministic classification (pure, fail-closed)
# ---------------------------------------------------------------------------


class TestClassification:
    def test_already_knows_enough(self):
        need = classify_knowledge_need(
            objective="What did you find about X?", sufficiency="sufficient"
        )
        assert need.kind is KnowledgeNeedKind.NONE
        assert need.status is KnowledgeNeedStatus.SATISFIED
        assert need.is_need is False

    def test_has_evidence_implies_satisfied(self):
        need = classify_knowledge_need(objective="X", has_evidence=True)
        assert need.kind is KnowledgeNeedKind.NONE
        assert need.status is KnowledgeNeedStatus.SATISFIED

    def test_genuine_missing_knowledge(self):
        need = classify_knowledge_need(
            objective="What is the current release of the Zorblax protocol?",
            sufficiency="unknown",
            acquisition_status="no_authorized_source",
            freshness_required=True,
        )
        assert need.kind is KnowledgeNeedKind.MISSING
        assert need.status is KnowledgeNeedStatus.UNSATISFIABLE
        assert need.is_need is True
        assert need.is_actionable is False
        assert "deny-by-default" in need.reason.lower()
        assert need.freshness_required is True
        assert "acquisition:no_authorized_source" in need.evidence

    def test_stale_knowledge(self):
        need = classify_knowledge_need(
            objective="What is the latest version of X?",
            sufficiency="stale",
            acquisition_status="acquired",
        )
        assert need.kind is KnowledgeNeedKind.STALE
        assert need.status is KnowledgeNeedStatus.ACTIONABLE
        assert need.is_actionable is True

    def test_insufficient_differs_from_missing(self):
        insufficient = classify_knowledge_need(
            objective="X", sufficiency="insufficient", has_evidence=True
        )
        missing = classify_knowledge_need(objective="X", sufficiency="insufficient")
        assert insufficient.kind is KnowledgeNeedKind.INSUFFICIENT
        assert missing.kind is KnowledgeNeedKind.MISSING

    def test_contradictory_is_preserved(self):
        need = classify_knowledge_need(objective="X", sufficiency="contradictory")
        assert need.kind is KnowledgeNeedKind.CONTRADICTORY
        assert need.status is KnowledgeNeedStatus.UNSATISFIABLE

    def test_unsupported_capability_is_not_a_knowledge_need(self):
        need = classify_knowledge_need(
            objective="Summarize X",
            sufficiency="unknown",
            acquisition_status="no_authorized_source",
            capability="open_conversation",
            capability_state="unavailable",
            capability_reason="no external model is configured",
        )
        assert need.kind is KnowledgeNeedKind.UNSUPPORTED_CAPABILITY
        assert need.status is KnowledgeNeedStatus.UNSATISFIABLE
        assert need.is_need is False
        assert need.capability_state == "unavailable"
        assert "capability" in need.reason.lower()
        assert "no external model is configured" in need.reason

    def test_blocked_capability_is_also_not_a_knowledge_need(self):
        need = classify_knowledge_need(
            objective="Execute the plan",
            capability="execute",
            capability_state="blocked",
        )
        assert need.kind is KnowledgeNeedKind.UNSUPPORTED_CAPABILITY

    def test_ambiguity_beats_every_other_signal(self):
        need = classify_knowledge_need(
            objective="Do it",
            ambiguous=True,
            sufficiency="unknown",
            acquisition_status="no_authorized_source",
            capability="execute",
            capability_state="unavailable",
        )
        assert need.kind is KnowledgeNeedKind.AMBIGUOUS
        assert need.status is KnowledgeNeedStatus.UNKNOWN
        assert need.is_need is False

    def test_actionability_matrix(self):
        actionable = classify_knowledge_need(
            objective="X", sufficiency="insufficient", acquisition_status="acquired"
        )
        existing = classify_knowledge_need(
            objective="X", sufficiency="stale", acquisition_status="existing_knowledge"
        )
        failed = classify_knowledge_need(
            objective="X", sufficiency="insufficient", acquisition_status="failed"
        )
        no_path = classify_knowledge_need(objective="X", sufficiency="insufficient")
        assert actionable.status is KnowledgeNeedStatus.ACTIONABLE
        assert existing.status is KnowledgeNeedStatus.ACTIONABLE
        assert failed.status is KnowledgeNeedStatus.UNSATISFIABLE
        assert no_path.status is KnowledgeNeedStatus.UNSATISFIABLE
        assert "failed closed" in failed.reason

    def test_fail_closed_without_evidence(self):
        need = classify_knowledge_need(objective="frobnicator wibble zorblax")
        assert need.kind is KnowledgeNeedKind.UNKNOWN
        assert need.status is KnowledgeNeedStatus.UNKNOWN
        assert need.is_need is False
        # An unfamiliar-word request alone NEVER establishes a knowledge need.
        assert "fail-closed" in need.reason

    def test_deterministic_and_serializable(self):
        kwargs = dict(
            objective="What is the latest X?",
            sufficiency="unknown",
            acquisition_status="no_authorized_source",
            freshness_required=True,
        )
        first = classify_knowledge_need(**kwargs)
        second = classify_knowledge_need(**kwargs)
        assert first == second
        assert first.to_dict() == second.to_dict()
        json.dumps(first.to_dict())

    def test_immutable_and_bounded(self):
        need = classify_knowledge_need(objective="x" * 5000)
        assert isinstance(need, KnowledgeNeed)
        assert len(need.objective) <= 400
        with pytest.raises(Exception):
            need.kind = KnowledgeNeedKind.MISSING  # type: ignore[misc]

    def test_detect_wrapper_matches_classify(self):
        assert detect_knowledge_need("X", sufficiency="sufficient") == (
            classify_knowledge_need(objective="X", sufficiency="sufficient")
        )


# ---------------------------------------------------------------------------
# 2. Detector composition (existing evidence only)
# ---------------------------------------------------------------------------


class TestDetector:
    def test_composes_sufficiency_and_capability(self):
        detector = KnowledgeNeedDetector(
            capability_model_provider=lambda: _CapabilityModelStub(
                [_Entry("research", "available", "its backing route is wired")]
            ),
            knowledge_status_provider=lambda _q: _Answer(
                "unknown", "no_authorized_source"
            ),
        )
        need = detector.detect("What is the latest X?", capability="research")
        assert need.kind is KnowledgeNeedKind.MISSING
        assert need.capability_state == "available"
        assert need.acquisition_status == "no_authorized_source"

    def test_answer_with_claims_is_satisfied(self):
        detector = KnowledgeNeedDetector(
            capability_model_provider=None,
            knowledge_status_provider=lambda _q: _Answer("sufficient", claims=({"a": 1},)),
        )
        need = detector.detect("X")
        assert need.kind is KnowledgeNeedKind.NONE
        assert need.status is KnowledgeNeedStatus.SATISFIED

    def test_failing_providers_fail_closed(self):
        def _boom(_q):
            raise RuntimeError("nope")

        detector = KnowledgeNeedDetector(
            capability_model_provider=lambda: (_ for _ in ()).throw(RuntimeError("no")),
            knowledge_status_provider=_boom,
        )
        need = detector.detect("X", capability="research")
        assert need.kind is KnowledgeNeedKind.UNKNOWN
        assert need.status is KnowledgeNeedStatus.UNKNOWN

    def test_no_providers_fail_closed(self):
        need = KnowledgeNeedDetector().detect("X")
        assert need.kind is KnowledgeNeedKind.UNKNOWN


# ---------------------------------------------------------------------------
# 3. Conversation recognition (bounded, non-hijacking)
# ---------------------------------------------------------------------------


def _conversation_service(*, open_conversation_state=None):
    model = None
    if open_conversation_state is not None:
        model = _CapabilityModelStub(
            [
                _Entry("open_conversation", open_conversation_state),
                _Entry("research", "available", "its backing route is wired"),
            ]
        )
    svc = _service(answer=_Answer("unknown", "no_authorized_source"), capability_model=model)
    spec = types.SimpleNamespace(task_type=types.SimpleNamespace(value="question"))
    return svc, spec


class TestConversationRecognition:
    def test_freshness_form_is_recognised_as_a_knowledge_need(self):
        svc, spec = _conversation_service(open_conversation_state="unavailable")
        message = svc.respond(
            "What is the current release of the Zorblax protocol?", spec=spec
        )
        assert message is not None
        assert message.metadata["builtin_intent"] == "validated_knowledge"
        need = message.metadata["knowledge_need"]
        assert need["kind"] == "missing"
        assert need["status"] == "unsatisfiable"
        assert need["is_need"] is True

    def test_attribution_form_is_recognised(self):
        svc, spec = _conversation_service(open_conversation_state="unavailable")
        message = svc.respond("Who won the 2147 World Cup?", spec=spec)
        assert message.metadata["builtin_intent"] == "validated_knowledge"
        assert message.metadata["knowledge_need"]["kind"] == "missing"

    def test_existing_knowledge_answer_also_carries_the_need(self):
        svc, spec = _conversation_service(open_conversation_state="unavailable")
        message = svc.respond(
            "What did you find about the Frobnitz standard?", spec=spec
        )
        assert message.metadata["builtin_intent"] == "validated_knowledge"
        assert message.metadata["knowledge_need"]["kind"] == "missing"

    def test_no_capability_model_preserves_existing_behaviour(self):
        svc, spec = _conversation_service(open_conversation_state=None)
        message = svc.respond("What is the current release of the Zorblax protocol?", spec=spec)
        assert message.metadata["builtin_intent"] == "unsupported"

    def test_open_conversation_available_is_never_hijacked(self):
        svc, spec = _conversation_service(open_conversation_state="available")
        message = svc.respond("What is the current release of the Zorblax protocol?", spec=spec)
        assert message.metadata["builtin_intent"] == "unsupported"

    def test_unusable_or_self_subject_declines(self):
        svc, spec = _conversation_service(open_conversation_state="unavailable")
        for text in ("Who created you?", "Who wrote this?", "What is the latest?"):
            message = svc.respond(text, spec=spec)
            assert message.metadata["builtin_intent"] != "validated_knowledge", text

    def test_ordinary_turns_are_unaffected(self):
        svc, spec = _conversation_service(open_conversation_state="unavailable")
        for text, expected in (
            ("Do the thing.", "unsupported"),
            ("Thanks, that makes sense.", "acknowledgement"),
            ("hello", "greeting"),
        ):
            message = svc.respond(text, spec=spec)
            assert message.metadata["builtin_intent"] == expected, text


# ---------------------------------------------------------------------------
# 4. Real Atlas/kernel validation
# ---------------------------------------------------------------------------


def _started_atlas(monkeypatch, tmp_path):
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage

    class TmpSQLiteEvolutionStorage(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "evolution.db")

    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage", TmpSQLiteEvolutionStorage
    )
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    return atlas


class TestRealKernel:
    def test_unseen_knowledge_request_is_a_genuine_need(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            need = atlas.knowledge_need("What is the current release of the Zorblax protocol?")
            assert need.kind is KnowledgeNeedKind.MISSING
            assert need.status is KnowledgeNeedStatus.UNSATISFIABLE
            assert need.freshness_required is True
            assert need.evidence
        finally:
            atlas.shutdown()

    def test_need_agrees_with_the_existing_decision(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            text = "Who won the 2147 World Cup?"
            answer = atlas.answer_knowledge_question(text)
            need = atlas.knowledge_need(text)
            assert need.sufficiency == answer.status.value
            assert need.acquisition_status == answer.acquisition_status
        finally:
            atlas.shutdown()

    def test_unavailable_capability_is_not_a_knowledge_need(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            # open_conversation is external-model dependent -> unavailable here.
            assert atlas.capability_contract("open_conversation")["state"] == "unavailable"
            need = atlas.knowledge_need("Tell me about X.", capability="open_conversation")
            assert need.kind is KnowledgeNeedKind.UNSUPPORTED_CAPABILITY
            assert need.is_need is False
        finally:
            atlas.shutdown()

    def test_conversation_and_kernel_agree(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            text = "What is the current release of the Zorblax protocol?"
            message = atlas.chat(text)
            recorded = message.metadata["knowledge_need"]
            kernel_need = atlas.knowledge_need(atlas.chat(text).metadata["validated_query"])
            assert recorded["kind"] == "missing"
            assert recorded["kind"] == kernel_need.kind.value
            assert recorded["status"] == kernel_need.status.value
        finally:
            atlas.shutdown()

    def test_send_stream_parity(self, monkeypatch, tmp_path):
        text = "What is the current release of the Zorblax protocol?"
        a = _started_atlas(monkeypatch, tmp_path)
        try:
            sent = a.chat(text).content
        finally:
            a.shutdown()
        b = _started_atlas(monkeypatch, tmp_path)
        try:
            streamed = "".join(b.stream(text))
        finally:
            b.shutdown()
        assert sent == streamed

    def test_no_authority_or_mutation(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            before = atlas.component_registry.component_count
            for text in (
                "What is the current release of the Zorblax protocol?",
                "Who won the 2147 World Cup?",
                "Tell me about quantum flux capacitors.",
            ):
                message = atlas.chat(text)
                for key in ("approval", "execution", "promotion", "authorization"):
                    assert key not in (message.metadata or {}), key
            assert atlas.component_registry.component_count == before
            assert atlas.pending_promotion_reviews() == []
        finally:
            atlas.shutdown()

    def test_deny_by_default_acquires_nothing(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            need = atlas.knowledge_need("Summarize the Frobnitz standard in depth.")
            assert need.acquisition_status in ("", "no_authorized_source")
            assert need.status is not KnowledgeNeedStatus.ACTIONABLE
        finally:
            atlas.shutdown()

    def test_existing_knowledge_and_other_surfaces_preserved(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            # Step 14 ownership question still answered by the architecture surface.
            assert atlas.chat("Which component owns memory_search?").metadata[
                "architecture"
            ]["kind"] == "ownership"
            # Step 13 capability-state question still answered.
            assert atlas.chat("Is research available?").metadata[
                "builtin_intent"
            ] == "capability_state"
            # Investigation still routes to a read-only investigation.
            investigated = atlas.chat("Investigate the memory architecture.")
            assert investigated.metadata.get("investigation") is not None
            # The existing explicit knowledge route still reports its own outcome.
            found = atlas.chat("What did you find about quantum flux capacitors?")
            assert found.metadata["builtin_intent"] == "validated_knowledge"
            assert found.metadata["validated_knowledge_status"] == "empty"
        finally:
            atlas.shutdown()
