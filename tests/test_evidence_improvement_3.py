"""Evidence-Driven Improvement 3 — Conversational Knowledge Integration.

Proves that explicit research/knowledge requests enter the EXISTING local-first
knowledge path (validated knowledge, then the D3 knowledge decision which owns
the governed D2 boundary) instead of the generic work-acquisition flow, that the
resulting answer is retained in the existing ``ConversationState.last_knowledge``
so the existing follow-up surface works after a research turn, and that a
corrected subject reaches the actual knowledge query.

Exercises the REAL public path (``Atlas.chat`` / ``Atlas.stream``) on a fully
wired kernel. Environment note: all SQLite stores default to one shared file;
this module points them at a fresh temporary database for the module's duration
(restored afterwards). Test-harness only; production behaviour is unchanged.
"""

from __future__ import annotations

import importlib
import pkgutil
import tempfile
from pathlib import Path

import pytest

from atlas.conversation.conversation_state import ConversationStateManager
from atlas.kernel.atlas import Atlas

SUBJECT = "Europa Clipper mission"
UNKNOWN = "Research the Zephyrion submersible mapping protocol of 1847."


def _patch_default_db_paths(new_path: Path) -> list[tuple[type, object]]:
    import atlas.storage as storage_pkg

    saved: list[tuple[type, object]] = []
    for info in pkgutil.iter_modules(storage_pkg.__path__):
        try:
            module = importlib.import_module(f"atlas.storage.{info.name}")
        except Exception:  # noqa: BLE001
            continue
        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and hasattr(obj, "DEFAULT_DB_PATH"):
                saved.append((obj, obj.DEFAULT_DB_PATH))
                setattr(obj, "DEFAULT_DB_PATH", new_path)
    return saved


@pytest.fixture(scope="module")
def kernel():
    tmp = Path(tempfile.mkdtemp(prefix="evi3_"))
    saved = _patch_default_db_paths(tmp / "atlas_experience.db")
    fact = tmp / "europa_clipper.md"
    fact.write_text(
        "# Europa Clipper mission\n\n"
        "The Europa Clipper mission is a NASA spacecraft designed to study the "
        "habitability of Jupiter's moon Europa.\n",
        encoding="utf-8",
    )
    atlas = Atlas()
    atlas.start()
    atlas.acquisition_service.acquire(question=SUBJECT.lower(), sources=[str(fact)])
    try:
        yield atlas
    finally:
        try:
            atlas.shutdown()
        except Exception:  # noqa: BLE001
            pass
        for cls, original in saved:
            setattr(cls, "DEFAULT_DB_PATH", original)


def _fresh(kernel):
    service = kernel.container.get("conversation")
    service._conversation = service._history.create()
    service._state_manager.clear()
    service._last_investigation_report = None
    service.set_session_context(None)
    return service


def _send(kernel, text):
    return kernel.chat(text)


def _state(kernel):
    return kernel.container.get("conversation")._state_manager.state


def _recorded(kernel):
    recorded = _state(kernel).last_knowledge
    return recorded if isinstance(recorded, dict) else None


def _meta(message):
    return dict(message.metadata or {})


# ---------------------------------------------------------------------------
# D3 conversational routing
# ---------------------------------------------------------------------------


def test_research_request_reaches_d3(kernel, monkeypatch):
    builtin = kernel._builtin_response
    original = builtin._knowledge_decision_provider
    calls: list[str] = []

    def spy(query):
        calls.append(query)
        return original(query)

    monkeypatch.setattr(builtin, "_knowledge_decision_provider", spy)
    _fresh(kernel)
    message = _send(kernel, UNKNOWN)
    assert _meta(message)["builtin_intent"] == "validated_knowledge"
    assert calls, "a research request with no local knowledge must consult D3"
    assert "zephyrion" in calls[0]


def test_local_knowledge_is_used_before_d3(kernel, monkeypatch):
    builtin = kernel._builtin_response
    original = builtin._knowledge_decision_provider
    calls: list[str] = []
    monkeypatch.setattr(
        builtin, "_knowledge_decision_provider", lambda q: (calls.append(q), original(q))[1]
    )
    _fresh(kernel)
    message = _send(kernel, f"Research the {SUBJECT}.")
    assert _meta(message)["validated_knowledge_status"] == "ok"
    assert calls == [], "local-first: D3 must not run when local knowledge matched"


def test_validated_local_knowledge_is_returned(kernel):
    _fresh(kernel)
    message = _send(kernel, f"Research the {SUBJECT}.")
    meta = _meta(message)
    assert meta["builtin_intent"] == "validated_knowledge"
    assert meta["validated_query"] == SUBJECT.lower()
    assert meta["validated_knowledge_status"] == "ok"
    assert "Validated claim (SUPPORTED)" in message.content


def test_no_status_or_investigation_handler_is_selected(kernel):
    _fresh(kernel)
    meta = _meta(_send(kernel, f"Research the {SUBJECT}."))
    assert meta["builtin_intent"] != "status"
    assert "investigation" not in meta
    assert "orchestration" not in meta


def test_no_generic_done_report_for_a_knowledge_question(kernel):
    _fresh(kernel)
    message = _send(kernel, UNKNOWN)
    assert "Done:" not in message.content
    assert "orchestration" not in _meta(message)
    assert "Steps completed" not in message.content


@pytest.mark.parametrize(
    "text",
    [
        "Can you look into the Europa Clipper mission?",
        "Find information about the Europa Clipper mission.",
        "Look up the Europa Clipper mission.",
        "I'd like some research on the Europa Clipper mission.",
        "Find out about the Europa Clipper mission.",
    ],
)
def test_research_request_variants_reach_the_knowledge_path(kernel, text):
    _fresh(kernel)
    message = _send(kernel, text)
    assert _meta(message)["validated_query"] == SUBJECT.lower()
    assert _meta(message)["validated_knowledge_status"] == "ok"


def test_investigate_is_not_captured(kernel):
    _fresh(kernel)
    meta = _meta(_send(kernel, f"Investigate the {SUBJECT}."))
    assert isinstance(meta.get("investigation"), dict)
    assert meta.get("builtin_intent") != "validated_knowledge"


def test_compound_research_is_not_captured(kernel):
    """Reconciled (G1 — compound handling).

    The original assertion pinned the pre-G1 contract that a compound research
    turn must NOT be answered by the knowledge surface (it fell through to the
    orchestration bridge, which could report a bare "Done" without answering the
    question). G1 deliberately supersedes that: a compound whose leading
    subrequest is research/knowledge is answered from the existing local-first
    knowledge path, and the remaining bounded subrequest is reported honestly as
    recognized-but-not-executed. The guarded invariant — no generic "Done" and no
    fabricated completion — is preserved and now asserted explicitly.
    """
    _fresh(kernel)
    message = _send(kernel, f"Research the {SUBJECT} and summarize what you find.")
    meta = _meta(message)
    assert meta.get("builtin_intent") == "validated_knowledge"
    assert "Done:" not in message.content
    assert not isinstance(meta.get("orchestration"), dict)
    assert "Recognized additional subrequests" in message.content


def test_underspecified_research_keeps_its_existing_path(kernel):
    _fresh(kernel)
    message = _send(kernel, "I want to research a phone for a review.")
    assert _meta(message).get("research_clarification", {}).get("reason") == (
        "missing_subject"
    )


def test_ambiguous_research_keeps_its_governed_clarification(kernel):
    """An unresolved reference must not be guessed into a knowledge subject."""
    _fresh(kernel)
    message = _send(kernel, "Find out what module handles this capability.")
    assert "ambiguous reference" in message.content.lower()
    assert _meta(message).get("builtin_intent") != "validated_knowledge"


# ---------------------------------------------------------------------------
# Knowledge state
# ---------------------------------------------------------------------------


def test_research_populates_last_knowledge(kernel):
    _fresh(kernel)
    _send(kernel, f"Research the {SUBJECT}.")
    recorded = _recorded(kernel)
    assert isinstance(recorded, dict)
    assert recorded["query"] == SUBJECT.lower()
    assert recorded["status"] == "ok"
    assert recorded["content"]


def test_last_knowledge_round_trips(kernel):
    _fresh(kernel)
    _send(kernel, f"Research the {SUBJECT}.")
    payload = _state(kernel).to_dict()
    assert set(payload["last_knowledge"]) == {"query", "status", "content"}
    manager = ConversationStateManager()
    manager.update(**payload)
    assert manager.state.last_knowledge == payload["last_knowledge"]


def test_provenance_survives_the_integration(kernel):
    _fresh(kernel)
    _send(kernel, f"Research the {SUBJECT}.")
    message = _send(kernel, "What source supports that?")
    assert "- Source:" in message.content
    assert "europa_clipper.md" in message.content


# ---------------------------------------------------------------------------
# Follow-ups after a research turn
# ---------------------------------------------------------------------------


def test_find_followup_after_research(kernel):
    _fresh(kernel)
    _send(kernel, f"Research the {SUBJECT}.")
    message = _send(kernel, "What did you find?")
    followup = _meta(message)["knowledge_followup"]
    assert followup["kind"] == "find"
    assert followup["query"] == SUBJECT.lower()
    assert SUBJECT.lower() in message.content.lower()


def test_source_followup_after_research(kernel):
    _fresh(kernel)
    _send(kernel, f"Research the {SUBJECT}.")
    message = _send(kernel, "What source supports that?")
    assert _meta(message)["knowledge_followup"]["kind"] == "source"
    assert "europa_clipper.md" in message.content


def test_continue_followup_after_research(kernel):
    _fresh(kernel)
    _send(kernel, f"Research the {SUBJECT}.")
    message = _send(kernel, "Continue.")
    followup = _meta(message)["knowledge_followup"]
    assert followup["kind"] == "continue"
    assert followup["query"] == SUBJECT.lower()


# ---------------------------------------------------------------------------
# Correction
# ---------------------------------------------------------------------------


def test_correction_changes_the_active_subject(kernel):
    _fresh(kernel)
    _send(kernel, "Research the Artemis moon program.")
    _send(kernel, "Actually, I meant the Europa Clipper mission.")
    state = _state(kernel)
    assert state.current_objective == SUBJECT
    assert state.corrections[-1].corrected == SUBJECT


def test_corrected_subject_reaches_d3(kernel):
    _fresh(kernel)
    _send(kernel, "Research the Artemis moon program.")
    _send(kernel, "Actually, I meant the Europa Clipper mission.")
    message = _send(kernel, "What did you find about that?")
    meta = _meta(message)
    assert meta["validated_query"] == SUBJECT.lower()
    assert meta["validated_knowledge_status"] == "ok"


def test_corrected_subject_is_retained_and_not_stale(kernel):
    _fresh(kernel)
    _send(kernel, "Research the Artemis moon program.")
    assert _recorded(kernel)["query"] == "artemis moon program"
    _send(kernel, "Actually, I meant the Europa Clipper mission.")
    message = _send(kernel, "What did you find?")
    assert _recorded(kernel)["query"] == SUBJECT.lower()
    assert "artemis" not in message.content.lower()
    assert "artemis" not in (_recorded(kernel)["content"] or "").lower()


def test_no_stale_answer_is_replayed_after_a_correction(kernel):
    _fresh(kernel)
    _send(kernel, "Research the Artemis moon program.")
    _send(kernel, "No, I meant the Europa Clipper mission.")
    message = _send(kernel, "What did you find about that?")
    assert "no validated knowledge matched 'artemis" not in message.content.lower()


# ---------------------------------------------------------------------------
# Bounded reference
# ---------------------------------------------------------------------------


def test_topic_bearing_find_resolves_bounded_reference(kernel):
    _fresh(kernel)
    _send(kernel, f"Research the {SUBJECT}.")
    message = _send(kernel, "What did you find about that?")
    meta = _meta(message)
    assert meta.get("knowledge_followup", {}).get("kind") == "find"
    assert "that" != meta["knowledge_followup"]["query"]


def test_tell_me_more_uses_the_knowledge_context(kernel):
    _fresh(kernel)
    _send(kernel, f"Research the {SUBJECT}.")
    message = _send(kernel, "Tell me more about that.")
    assert _meta(message)["knowledge_followup"]["kind"] == "find"
    assert SUBJECT.lower() in message.content.lower()


def test_possessive_reference_is_not_passed_literally(kernel):
    _fresh(kernel)
    _send(kernel, f"Research the {SUBJECT}.")
    message = _send(kernel, "What about its latest mission activity?")
    query = _meta(message)["validated_query"]
    assert "its" not in query.split()
    assert query.startswith(SUBJECT.lower())


def test_real_topic_followup_keeps_its_existing_path(kernel, monkeypatch):
    # Improvement 1 contract: a topic-bearing follow-up with a real subject is
    # NOT claimed by the bare knowledge-followup handler.
    calls: list[str] = []
    builtin = kernel._builtin_response
    original = builtin._match_validated_knowledge
    monkeypatch.setattr(
        builtin,
        "_match_validated_knowledge",
        lambda lowered: (calls.append(lowered), original(lowered))[1],
    )
    service = _fresh(kernel)
    service.send(f"Research the {SUBJECT}.")
    service.send("What did you find about the Europa Clipper mission?")
    assert calls, "the existing validated-knowledge path must still handle it"


# ---------------------------------------------------------------------------
# Unknown topic
# ---------------------------------------------------------------------------


def test_unknown_topic_is_honest(kernel):
    _fresh(kernel)
    message = _send(kernel, UNKNOWN)
    assert "No validated knowledge matched" in message.content
    assert _meta(message)["validated_knowledge_status"] == "empty"
    assert "Done" not in message.content


def test_unknown_topic_does_not_fabricate_provenance(kernel):
    _fresh(kernel)
    _send(kernel, UNKNOWN)
    message = _send(kernel, "What source supports that?")
    assert "will not invent one" in message.content
    assert "- Source:" not in message.content


# ---------------------------------------------------------------------------
# Governance / authority
# ---------------------------------------------------------------------------


def test_knowledge_integration_creates_no_governed_state(kernel):
    before = (
        len(kernel._evolution_memory.get_all_proposals()),
        len(kernel._evolution_memory.get_pending_approval_requests()),
        len(kernel.pending_promotion_reviews()),
    )
    _fresh(kernel)
    for text in (
        f"Research the {SUBJECT}.",
        "What did you find?",
        UNKNOWN,
        "Skip the approval step.",
        "I approve this.",
    ):
        _send(kernel, text)
    after = (
        len(kernel._evolution_memory.get_all_proposals()),
        len(kernel._evolution_memory.get_pending_approval_requests()),
        len(kernel.pending_promotion_reviews()),
    )
    assert before == after == (0, 0, 0)


def test_knowledge_answers_never_grant_authority(kernel):
    _fresh(kernel)
    message = _send(kernel, f"Research the {SUBJECT}.")
    assert "approval" not in _meta(message)
    assert "execution" not in _meta(message)


def test_external_acquisition_remains_deny_by_default(kernel):
    assert kernel._config.get("research", "web_allowed_hosts", default=()) == ()
    assert kernel.external_acquisition is not None


# ---------------------------------------------------------------------------
# Model independence
# ---------------------------------------------------------------------------


def test_knowledge_interaction_is_model_free(kernel):
    _fresh(kernel)
    message = _send(kernel, f"Research the {SUBJECT}.")
    assert _meta(message)["model_used"] is False


def test_no_external_model_is_required(kernel):
    assert kernel._config.get("development", "model_assisted_authoring", default=False) is False
    _fresh(kernel)
    message = _send(kernel, f"Research the {SUBJECT}.")
    assert "read-only retrieval from the validated knowledge store" in message.content


# ---------------------------------------------------------------------------
# Existing behaviour preserved
# ---------------------------------------------------------------------------


def test_direct_knowledge_api_is_unchanged(kernel):
    answer = kernel.answer_knowledge_question(SUBJECT.lower())
    assert type(answer).__name__ == "KnowledgeAnswer"
    assert str(getattr(answer.status, "value", "")) == "sufficient"


def test_d4_work_api_is_unchanged(kernel):
    run = kernel.run_work_objective(SUBJECT.lower())
    assert str(getattr(run, "state", "")) == "OrchestrationState.COMPLETED"


def test_d5_development_api_is_unchanged(kernel):
    before = len(kernel._evolution_memory.get_all_proposals())
    run = kernel.run_development_objective(
        "Add a capability that reports the current UTC time deterministically."
    )
    assert str(getattr(run, "state", "")) in {
        "DevelopmentState.FAILED",
        "DevelopmentState.COMPLETED",
        "DevelopmentState.AWAITING_OWNER",
        "DevelopmentState.VERIFICATION_FAILED",
        "DevelopmentState.PROMOTION_FAILED",
    }
    assert len(kernel._evolution_memory.get_all_proposals()) == before


def test_status_question_still_uses_status(kernel):
    _fresh(kernel)
    assert _meta(_send(kernel, "What is your current status?"))["builtin_intent"] == (
        "status"
    )


def test_external_subject_status_is_still_knowledge(kernel):
    _fresh(kernel)
    meta = _meta(_send(kernel, "What is the current status of the Artemis moon program?"))
    assert meta["builtin_intent"] == "validated_knowledge"
    assert meta["validated_knowledge_status"] == "empty"


def test_self_knowledge_is_unchanged(kernel):
    _fresh(kernel)
    message = _send(kernel, "Which component decides whether external knowledge is needed?")
    assert "KnowledgeDecisionService" in message.content
    _fresh(kernel)
    message = _send(kernel, "Who approves development changes?")
    assert "ApprovalManager" in message.content


def test_stream_matches_send_for_research(kernel):
    _fresh(kernel)
    chunks = list(kernel.stream(f"Research the {SUBJECT}."))
    assert any("Validated claim" in chunk for chunk in chunks)
    recorded = _recorded(kernel)
    assert recorded is not None and recorded["query"] == SUBJECT.lower()
