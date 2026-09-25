"""Evidence-Driven Improvement 2 — Conversational State Semantics (focused).

Proves that the deterministic D1 conversation layer distinguishes the bounded
conversational role of a turn, so follow-up / recall / acknowledgement /
continuation / clarification / reference turns PRESERVE the active objective,
only a genuinely new objective (or a correction) replaces it, and a correction
is APPLIED to the active interpretation rather than merely recorded.

Exercises both the engine contract directly and the REAL public conversation
path (``Atlas.chat``) on a fully wired kernel with default config. Environment
note: all SQLite stores default to one shared file; this module points them at a
fresh temporary database for the module's duration (restored afterwards).
Test-harness only; production behaviour is unchanged.
"""

from __future__ import annotations

import importlib
import pkgutil
import tempfile
from pathlib import Path

import pytest

from atlas.conversation.conversation_state import ConversationState
from atlas.conversation.engine import ConversationEngine
from atlas.conversation.task_intake import TaskIntake
from atlas.conversation.turn_role import TurnRole, corrected_subject, detect_turn_role
from atlas.kernel.atlas import Atlas

OBJECTIVE = "Research the Artemis moon program."
CORRECTED = "Actually, I meant the Europa Clipper mission."


# ---------------------------------------------------------------------------
# Engine contract — role detection (bounded, deterministic)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["Thanks.", "Thanks, that helps.", "Got it.", "Okay, understood.", "Understood.", "Noted."],
)
def test_acknowledgement_role(text):
    assert detect_turn_role(text) is TurnRole.ACKNOWLEDGEMENT


@pytest.mark.parametrize(
    "text", ["Continue.", "Go on.", "Keep going.", "Continue with that."]
)
def test_continuation_role(text):
    assert detect_turn_role(text) is TurnRole.CONTINUATION


@pytest.mark.parametrize(
    "text", ["What did we discuss?", "What were we talking about?", "What did I ask earlier?"]
)
def test_recall_role(text):
    assert detect_turn_role(text) is TurnRole.RECALL


@pytest.mark.parametrize("text", ["What did you find?", "Tell me more about that."])
def test_follow_up_forms_preserve(text):
    role = detect_turn_role(text, has_prior_objective=True)
    assert role in (TurnRole.FOLLOW_UP, TurnRole.REFERENCE)


@pytest.mark.parametrize(
    "text", ["What about its latest launch?", "Do that again.", "Explain that part again."]
)
def test_bounded_reference_role(text):
    assert detect_turn_role(text) is TurnRole.REFERENCE


def test_correction_role_requires_prior_objective():
    assert (
        detect_turn_role(CORRECTED, has_prior_objective=True) is TurnRole.CORRECTION
    )
    # Nothing to correct -> it establishes an objective instead.
    assert (
        detect_turn_role(CORRECTED, has_prior_objective=False)
        is TurnRole.NEW_OBJECTIVE
    )


def test_clarification_role_preserves():
    assert (
        detect_turn_role(
            "I mean the current mission status.", has_prior_objective=True
        )
        is TurnRole.CLARIFICATION
    )


def test_genuine_work_request_is_a_new_objective():
    assert detect_turn_role(OBJECTIVE) is TurnRole.NEW_OBJECTIVE
    assert detect_turn_role("Now investigate SpaceX.") is TurnRole.NEW_OBJECTIVE


def test_instructed_request_with_pronoun_stays_a_new_objective():
    # A bounded reference form must not swallow a genuinely instructed turn.
    assert (
        detect_turn_role("Research the Voyager mission and summarize it.")
        is TurnRole.NEW_OBJECTIVE
    )


def test_corrected_subject_extraction_variants():
    assert corrected_subject(CORRECTED) == "Europa Clipper mission"
    assert corrected_subject("No, I meant the Europa Clipper mission.") == (
        "Europa Clipper mission"
    )
    assert corrected_subject("Correction: I was asking about Europa Clipper.") == (
        "Europa Clipper"
    )
    assert corrected_subject("Research the Artemis moon program.") == ""


# ---------------------------------------------------------------------------
# Engine contract — state updates are role-aware
# ---------------------------------------------------------------------------


def _engine() -> ConversationEngine:
    return ConversationEngine(task_intake=TaskIntake())


def _updates(text: str, objective: str | None):
    state = ConversationState(current_objective=objective, turn_id="t1")
    interp = _engine().interpret(text, state=state)
    return interp, _engine().state_updates(interp, state)


@pytest.mark.parametrize(
    "text",
    [
        "Thanks, that helps.",
        "What did we discuss?",
        "What did you find?",
        "Continue.",
        "I mean the current mission status.",
        "What about its latest launch?",
    ],
)
def test_preserving_roles_do_not_replace_objective(text):
    interp, updates = _updates(text, OBJECTIVE)
    assert interp.turn_role in (
        TurnRole.ACKNOWLEDGEMENT,
        TurnRole.RECALL,
        TurnRole.FOLLOW_UP,
        TurnRole.CONTINUATION,
        TurnRole.CLARIFICATION,
        TurnRole.REFERENCE,
        TurnRole.META_CONVERSATION,
    )
    assert "current_objective" not in updates


def test_new_objective_replaces():
    interp, updates = _updates("Now investigate SpaceX.", OBJECTIVE)
    assert interp.turn_role is TurnRole.NEW_OBJECTIVE
    assert updates["current_objective"] == "Now investigate SpaceX."


def test_correction_replaces_with_corrected_subject():
    interp, updates = _updates(CORRECTED, OBJECTIVE)
    assert interp.turn_role is TurnRole.CORRECTION
    assert updates["current_objective"] == "Europa Clipper mission"
    assert interp.corrections[-1].previous == OBJECTIVE
    assert interp.corrections[-1].corrected == "Europa Clipper mission"


def test_correction_is_not_a_second_objective():
    interp, updates = _updates("No, I meant the Europa Clipper mission.", OBJECTIVE)
    assert interp.turn_role is TurnRole.CORRECTION
    # Exactly one objective survives; the old reading is superseded, not kept.
    assert updates["current_objective"] == "Europa Clipper mission"
    assert len(interp.corrections) == 1


def test_semantic_intake_exposes_turn_role_authority_free():
    interp = _engine().interpret(OBJECTIVE)
    payload = interp.semantic.to_dict()
    assert payload["turn_role"] == "new_objective"
    assert payload["provenance"]["authority"] == "none"


# ---------------------------------------------------------------------------
# Kernel — real conversation path
# ---------------------------------------------------------------------------


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
    tmp = Path(tempfile.mkdtemp(prefix="evi2_"))
    saved = _patch_default_db_paths(tmp / "atlas_experience.db")
    fact = tmp / "device.md"
    fact.write_text(
        "# Atlas Evidence Device\n\nThe Atlas Evidence Device mode is bounded test mode.\n",
        encoding="utf-8",
    )
    atlas = Atlas()
    atlas.start()
    atlas.acquisition_service.acquire(
        question="atlas evidence device mode", sources=[str(fact)]
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
    service = kernel.container.get("conversation")
    service._conversation = service._history.create()
    service._state_manager.clear()
    service._last_investigation_report = None
    return service


def _objective(service):
    return service._state_manager.state.current_objective


def _send(service, text):
    return service.send(text)


# --- objective preservation -------------------------------------------------


@pytest.mark.parametrize(
    "text", ["Thanks.", "Thanks, that helps.", "Got it.", "Okay, understood."]
)
def test_kernel_acknowledgement_preserves_objective(kernel, text):
    service = _service(kernel)
    _send(service, OBJECTIVE)
    assert _objective(service) == OBJECTIVE
    _send(service, text)
    assert _objective(service) == OBJECTIVE


@pytest.mark.parametrize(
    "text", ["What did we discuss?", "What were we talking about?"]
)
def test_kernel_recall_preserves_objective(kernel, text):
    service = _service(kernel)
    _send(service, OBJECTIVE)
    _send(service, text)
    assert _objective(service) == OBJECTIVE


def test_kernel_follow_up_preserves_objective(kernel):
    service = _service(kernel)
    _send(service, OBJECTIVE)
    _send(service, "What did you find?")
    assert _objective(service) == OBJECTIVE
    _send(service, "Tell me more about that.")
    assert _objective(service) == OBJECTIVE


@pytest.mark.parametrize("text", ["Continue.", "Go on.", "Keep going."])
def test_kernel_continuation_preserves_objective(kernel, text):
    service = _service(kernel)
    _send(service, OBJECTIVE)
    _send(service, text)
    assert _objective(service) == OBJECTIVE


def test_kernel_clarification_preserves_objective(kernel):
    service = _service(kernel)
    _send(service, OBJECTIVE)
    _send(service, "I mean the current mission status.")
    assert _objective(service) == OBJECTIVE


@pytest.mark.parametrize(
    "text", ["What about its latest launch?", "Do that again."]
)
def test_kernel_bounded_reference_preserves_objective(kernel, text):
    service = _service(kernel)
    _send(service, OBJECTIVE)
    _send(service, text)
    assert _objective(service) == OBJECTIVE


def test_kernel_new_objective_replaces(kernel):
    service = _service(kernel)
    _send(service, OBJECTIVE)
    _send(service, "Now investigate SpaceX.")
    assert _objective(service) == "Now investigate SpaceX."


# --- corrections ------------------------------------------------------------


def test_kernel_correction_is_applied_not_just_recorded(kernel):
    service = _service(kernel)
    _send(service, OBJECTIVE)
    assert _objective(service) == OBJECTIVE

    _send(service, CORRECTED)
    state = service._state_manager.state
    assert state.corrections, "correction must be recorded"
    assert state.corrections[-1].previous == OBJECTIVE
    assert state.corrections[-1].corrected == "Europa Clipper mission"
    # APPLIED: the active interpretation now reflects the corrected subject.
    assert state.current_objective == "Europa Clipper mission"

    # A subsequent bounded turn uses the corrected context, not Artemis.
    _send(service, "What about its latest launch?")
    assert _objective(service) == "Europa Clipper mission"


@pytest.mark.parametrize(
    "text",
    [
        "Actually, I meant Europa Clipper.",
        "Correction: I was asking about Europa Clipper.",
        "No, I meant the Europa Clipper mission.",
    ],
)
def test_kernel_correction_variants_apply(kernel, text):
    service = _service(kernel)
    _send(service, OBJECTIVE)
    _send(service, text)
    objective = _objective(service)
    assert objective is not None
    assert "europa clipper" in objective.lower()
    assert "artemis" not in objective.lower()


# --- knowledge context ------------------------------------------------------


def test_kernel_knowledge_context_preserved_across_meta_turns(kernel):
    service = _service(kernel)
    _send(service, "What do you know about the Atlas Evidence Device?")
    first = service._state_manager.state.last_knowledge
    assert isinstance(first, dict) and first["query"] == "atlas evidence device"

    _send(service, "Thanks.")
    assert service._state_manager.state.last_knowledge == first

    _send(service, "What did we discuss?")
    assert service._state_manager.state.last_knowledge == first

    message = _send(service, "What did you find?")
    assert (message.metadata or {}).get("knowledge_followup", {}).get("kind") == "find"
    assert service._state_manager.state.last_knowledge == first

    message = _send(service, "What source supports that?")
    assert (message.metadata or {}).get("knowledge_followup", {}).get("kind") == "source"

    _send(service, "Can you continue?")
    assert service._state_manager.state.last_knowledge == first


# --- self-knowledge + fail-closed ------------------------------------------


def test_kernel_meta_and_self_knowledge_do_not_create_objective(kernel):
    service = _service(kernel)
    for text in ("Explain how you work.", "Thanks.", "What did we discuss?"):
        _send(service, text)
    assert _objective(service) is None


def test_kernel_approval_language_does_not_authorize(kernel):
    service = _service(kernel)
    before_approvals = len(kernel._evolution_memory.get_pending_approval_requests())
    message = _send(service, "I approve this.")
    assert (message.metadata or {}).get("approval", {}).get("status") in (
        "no_active_proposal",
        "no_session",
    )
    assert (
        len(kernel._evolution_memory.get_pending_approval_requests())
        == before_approvals
    )
