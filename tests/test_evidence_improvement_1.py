"""Evidence-driven improvement 1 — self-knowledge depth + conversational
knowledge integration (focused regression).

Exercises the REAL public conversation path (``ConversationService.send`` /
``stream`` on a fully wired ``Atlas`` kernel, default config). Environment note:
all SQLite stores default to one shared file; this module points them at a fresh
temporary database for the module's duration (restored afterwards). Test-harness
only; production behaviour is unchanged.
"""

from __future__ import annotations

import importlib
import pkgutil
import tempfile
from pathlib import Path

import pytest

from atlas.kernel.atlas import Atlas


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
    tmp = Path(tempfile.mkdtemp(prefix="evi1_"))
    saved = _patch_default_db_paths(tmp / "atlas_experience.db")
    fact = tmp / "device.md"
    fact.write_text(
        "# Atlas Evidence Device\n\n"
        "The Atlas Evidence Device operating mode is bounded test mode.\n",
        encoding="utf-8",
    )
    atlas = Atlas()
    atlas.start()
    atlas.acquisition_service.acquire(
        question="atlas evidence device operating mode", sources=[str(fact)]
    )
    try:
        yield atlas
    finally:
        try:
            atlas.shutdown()
        except Exception:  # noqa: BLE001
            pass
        for cls, original in saved:
            setattr(cls, "DEFAULT_DB_PATH", original)


def _service(kernel):
    return kernel.container.get("conversation")


def _send(kernel, text):
    service = _service(kernel)
    service._conversation = service._history.create()
    service._state_manager.clear()
    service._last_investigation_report = None
    return service.send(text)


def _convo(kernel):
    """Fresh conversation that PRESERVES state across turns."""
    service = _service(kernel)
    service._conversation = service._history.create()
    service._state_manager.clear()
    service._last_investigation_report = None
    return service


def _intent(message):
    return (message.metadata or {}).get("builtin_intent")


def _followup(message):
    return (message.metadata or {}).get("knowledge_followup")


def _send_k(kernel, text):
    return _send(kernel, text)


# ---------------------------------------------------------------------------
# A — self-knowledge: component identity / responsibility
# ---------------------------------------------------------------------------


def test_knowledge_decision_component_identified(kernel):
    msg = _send(kernel, "Which component decides whether external knowledge is necessary?")
    assert _intent(msg) == "architecture"
    assert "KnowledgeDecisionService" in msg.content
    assert "atlas/research/knowledge_decision" in msg.content


def test_knowledge_sufficiency_component_identified(kernel):
    msg = _send(kernel, "What component handles knowledge sufficiency decisions?")
    assert _intent(msg) == "architecture"
    assert "KnowledgeDecisionService" in msg.content


def test_work_orchestrator_identified(kernel):
    msg = _send(kernel, "Which component coordinates work execution?")
    assert _intent(msg) == "architecture"
    assert "WorkOrchestrator" in msg.content


def test_development_orchestrator_identified(kernel):
    msg = _send(kernel, "Which component handles development orchestration?")
    assert "DevelopmentOrchestrator" in msg.content


def test_conversation_engine_identified(kernel):
    msg = _send(kernel, "Which component is the conversation engine?")
    assert "ConversationEngine" in msg.content


# ---------------------------------------------------------------------------
# B — self-knowledge: flows / governance (evidence-backed baseline failures)
# ---------------------------------------------------------------------------


def test_request_flow_explained(kernel):
    msg = _send(kernel, "How does a user request travel through your system?")
    assert _intent(msg) == "self_knowledge"
    assert "request flow" in msg.content
    assert "ConversationService" in msg.content
    assert "KnowledgeDecisionService" in msg.content
    assert "SemanticIntake" in msg.content


def test_development_flow_explained(kernel):
    msg = _send(kernel, "How does your development process work?")
    assert _intent(msg) == "self_knowledge"
    assert "development process" in msg.content
    assert "PENDING_APPROVAL" in msg.content
    assert "CodeSandbox" in msg.content
    assert "DevelopmentVerification" in msg.content


def test_owner_approval_explained(kernel):
    msg = _send(kernel, "Where does OWNER approval happen?")
    assert _intent(msg) == "self_knowledge"
    assert "ApprovalManager" in msg.content
    assert "can never approve itself" in msg.content.lower()


def test_sandbox_execution_explained(kernel):
    msg = _send(kernel, "How is sandbox execution enforced?")
    assert _intent(msg) == "self_knowledge"
    assert "CodeSandbox" in msg.content
    assert "live repository is never modified" in msg.content


def test_authorization_boundary_explained(kernel):
    msg = _send(kernel, "What prevents a natural-language request from authorizing itself?")
    assert _intent(msg) == "self_knowledge"
    assert "authority" in msg.content.lower()
    assert "AuthorityService" in msg.content


def test_extension_points_explained(kernel):
    msg = _send(kernel, "If you needed a new capability, where would it fit?")
    assert _intent(msg) == "self_knowledge"
    assert "extension points" in msg.content
    assert "CapabilityRegistry" in msg.content


def test_reuse_existing_components_explained(kernel):
    msg = _send(kernel, "What existing components would you reuse to add a capability?")
    assert _intent(msg) == "self_knowledge"
    assert "extension points" in msg.content
    assert "CapabilityRegistry" in msg.content


def test_verification_strategy_explained(kernel):
    msg = _send(kernel, "How would you verify such a change?")
    assert _intent(msg) == "self_knowledge"
    assert "DevelopmentVerification" in msg.content


def test_unknown_component_fails_honestly(kernel):
    msg = _send(kernel, "Which component handles quantum tea brewing?")
    # Falls back to the deterministic architecture summary; never invents a
    # component/class for an unknown subject.
    assert "KnowledgeDecisionService" not in msg.content
    assert "WorkOrchestrator" not in msg.content
    assert "TeaBrewer" not in msg.content


def test_self_knowledge_is_read_only(kernel):
    before_approvals = len(kernel._evolution_memory.get_pending_approval_requests())
    before_promotions = len(kernel.pending_promotion_reviews())
    for q in (
        "How does a user request travel through your system?",
        "How does your development process work?",
        "Where does OWNER approval happen?",
        "What would you change to add a new capability?",
        "If you needed a new capability, where would it fit?",
    ):
        msg = _send(kernel, q)
        assert "proposal" not in msg.content.lower() or "proposal" in msg.content.lower()
    assert len(kernel._evolution_memory.get_pending_approval_requests()) == before_approvals
    assert len(kernel.pending_promotion_reviews()) == before_promotions


# ---------------------------------------------------------------------------
# C — conversational knowledge: subject disambiguation
# ---------------------------------------------------------------------------


def test_external_status_is_not_atlas_status(kernel):
    msg = _send(kernel, "What is the current status of the Artemis moon program?")
    assert _intent(msg) == "validated_knowledge"
    assert "Atlas status" not in msg.content
    assert "artemis moon program" in msg.content.lower()


def test_external_happening_with_is_knowledge(kernel):
    msg = _send(kernel, "What is happening with the Artemis moon program?")
    assert _intent(msg) == "validated_knowledge"


def test_can_you_find_latest_knowledge(kernel):
    msg = _send(kernel, "Can you find the latest information about the Atlas Evidence Device?")
    assert _intent(msg) == "validated_knowledge"


def test_atlas_self_status_is_still_status(kernel):
    for q in ("What is your status?", "How is Atlas?"):
        msg = _send(kernel, q)
        assert _intent(msg) == "status", q


def test_general_knowledge_reaches_d3(kernel):
    # The D3 knowledge-decision provider is consulted on the conversational path.
    assert kernel.knowledge_decision is not None
    msg = _send(kernel, "What do you know about the Atlas Evidence Device?")
    assert _intent(msg) == "validated_knowledge"
    assert (msg.metadata or {}).get("validated_knowledge_status") == "ok"


def test_research_request_keeps_its_existing_path(kernel):
    msg = _send(kernel, "Research the Artemis moon program for me.")
    assert _intent(msg) != "status"
    assert "Atlas status" not in msg.content


# ---------------------------------------------------------------------------
# D — knowledge result continuity + provenance follow-ups
# ---------------------------------------------------------------------------


def test_knowledge_result_preserved_in_context(kernel):
    service = _convo(kernel)
    service.send("What do you know about the Atlas Evidence Device?")
    recorded = service._state_manager.state.last_knowledge
    assert isinstance(recorded, dict)
    assert recorded["query"] == "atlas evidence device"
    assert recorded["status"] == "ok"


def test_find_followup_resolves_to_previous_result(kernel):
    service = _convo(kernel)
    service.send("What do you know about the Atlas Evidence Device?")
    msg = service.send("What did you find?")
    assert _followup(msg) == {"kind": "find", "query": "atlas evidence device", "status": "ok"}
    assert "Atlas Evidence Device".lower() in msg.content.lower()


def test_source_followup_resolves_to_provenance(kernel):
    service = _convo(kernel)
    service.send("What do you know about the Atlas Evidence Device?")
    msg = service.send("What source supports that?")
    assert _followup(msg)["kind"] == "source"
    assert "- source:" in msg.content.lower()


def test_continue_followup_resolves_to_current_context(kernel):
    service = _convo(kernel)
    service.send("What do you know about the Atlas Evidence Device?")
    msg = service.send("Can you continue?")
    assert _followup(msg)["kind"] == "continue"
    assert "atlas evidence device" in msg.content.lower()


def test_missing_provenance_is_honest(kernel):
    service = _convo(kernel)
    service.send("What is the current status of the Artemis moon program?")
    msg = service.send("What source supports that?")
    assert _followup(msg)["kind"] == "source"
    assert "no authorized source provenance" in msg.content.lower()


def test_ambiguous_followup_without_context_is_not_fabricated(kernel):
    msg = _send(kernel, "What source supports that?")
    assert _followup(msg) is None
    assert _intent(msg) != "validated_knowledge"


def test_followup_does_not_capture_topic_bearing_request(kernel):
    service = _convo(kernel)
    service.send("What do you know about the Atlas Evidence Device?")
    msg = service.send("What did you find about the Atlas Evidence Device?")
    assert _followup(msg) is None


def test_stream_matches_send_for_followup(kernel):
    service = _convo(kernel)
    service.send("What do you know about the Atlas Evidence Device?")
    chunks = list(service.stream("Can you continue?"))
    assert any("most recent knowledge result" in c for c in chunks)


# ---------------------------------------------------------------------------
# E — governance + no second store
# ---------------------------------------------------------------------------


def test_acquisition_remains_governed(kernel):
    assert kernel._config.get("research", "web_allowed_hosts", default=()) == ()
    _send(kernel, "What is the current status of the Artemis moon program?")
    assert len(kernel._evolution_memory.get_pending_approval_requests()) == 0
    assert len(kernel.pending_promotion_reviews()) == 0


def test_no_second_knowledge_store(kernel):
    service = _convo(kernel)
    service.send("What do you know about the Atlas Evidence Device?")
    payload = service._state_manager.state.to_dict()
    assert isinstance(payload["last_knowledge"], dict)
    assert len(payload["last_knowledge"]["content"]) <= 600
    assert set(payload["last_knowledge"]) == {"query", "status", "content"}
