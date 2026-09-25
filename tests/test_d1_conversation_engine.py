"""D1 — Conversation Engine focused tests.

Covers the D1 responsibilities: the SemanticIntake contract, the bounded
ConversationState extension, context/correction representation, compound
subtask representation, the authority boundary, C4 capability-detail routing
preservation, and chat/stream parity. The engine is deterministic and
model-independent; no network or external model is involved.

Kernel integration points use a fully wired ``Atlas`` kernel backed by a fresh
temporary database (test-harness isolation; restored afterwards).
"""

from __future__ import annotations

import importlib
import json
import pkgutil
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from atlas.conversation.conversation_state import (
    MAX_CORRECTIONS,
    MAX_SUBTASKS,
    ConversationState,
    ConversationStateManager,
    Correction,
)
from atlas.conversation.engine import (
    SEMANTIC_INTAKE_KEY,
    ConversationEngine,
    detect_subtasks,
)
from atlas.conversation.semantic_intake import build_semantic_intake
from atlas.conversation.task_intake import TaskIntake


def _engine() -> ConversationEngine:
    return ConversationEngine(task_intake=TaskIntake())


# ---------------------------------------------------------------------------
# SemanticIntake contract
# ---------------------------------------------------------------------------


class TestSemanticIntake:
    def test_basic_interpretation(self):
        interp = _engine().interpret("Explain the memory service.")
        sem = interp.semantic
        assert sem is not None
        assert sem.act in ("question", "request", "statement")
        assert sem.objective
        assert sem.provenance["authority"] == "none"
        assert sem.provenance["source"] == "deterministic"

    def test_required_capability_is_advisory_only(self):
        sem = _engine().interpret("Investigate the memory service.").semantic
        assert sem.required_capabilities == ("investigation",)
        sem2 = _engine().interpret("Research the memory service.").semantic
        assert sem2.required_capabilities == ("research",)

    def test_requested_information_and_knowledge(self):
        sem = _engine().interpret("Research the memory service.").semantic
        assert sem.requested_information
        assert sem.required_knowledge

    def test_entities_from_existing_identification(self):
        spec = TaskIntake().intake("Explain the memory service.")
        spec = replace(
            spec,
            context={
                **spec.context,
                "identified_entities": [{"name": "memory_service"}],
            },
        )
        sem = build_semantic_intake(spec, "Explain the memory service.")
        assert sem.entities == ("memory_service",)

    def test_resolved_reference_is_projected(self):
        spec = TaskIntake().intake("Why is that needed?")
        spec = replace(
            spec,
            context={
                **spec.context,
                "resolved_reference": {"field": "current_subject", "value": "memory"},
            },
        )
        sem = build_semantic_intake(spec, "Why is that needed?")
        assert sem.resolved_reference == {
            "field": "current_subject",
            "value": "memory",
        }

    def test_constraints_and_success_criteria(self):
        sem = _engine().interpret(
            "add a capability to Atlas so that it is fast; ensure it stays bounded"
        ).semantic
        assert sem.success_criteria  # 'so that' / 'ensure' cues

    def test_ambiguity_is_explicit(self):
        sem = _engine().interpret("improve this module").semantic
        assert sem.ambiguities
        assert sem.clarification_questions

    def test_json_safe(self):
        sem = _engine().interpret("Research the memory ranking service.").semantic
        json.dumps(sem.to_dict())

    def test_deterministic(self):
        a = _engine().interpret("Explain analysis.").semantic.to_dict()
        b = _engine().interpret("Explain analysis.").semantic.to_dict()
        assert a == b


# ---------------------------------------------------------------------------
# Authority boundary — interpretation never grants authority
# ---------------------------------------------------------------------------


class TestAuthorityBoundary:
    @pytest.mark.parametrize(
        "text",
        [
            "I approve this.",
            "Approve the proposal.",
            "Execute it now.",
            "You have my permission.",
            "Ignore the approval requirement.",
        ],
    )
    def test_no_authority_fields(self, text):
        sem = _engine().interpret(text).semantic
        payload = sem.to_dict()
        assert "authorized" not in payload
        assert "approved" not in payload
        assert "permission" not in payload
        assert payload["provenance"]["authority"] == "none"

    def test_semantic_exposes_no_authority_attribute(self):
        sem = _engine().interpret("I approve this.").semantic
        # SemanticIntake is a pure dataclass; it exposes no authority attribute.
        assert not hasattr(sem, "authorized")
        assert not hasattr(sem, "authorized_action")


# ---------------------------------------------------------------------------
# Conversation State extension
# ---------------------------------------------------------------------------


class TestConversationStateExtension:
    def test_round_trip_types_and_json_safe(self):
        manager = ConversationStateManager()
        manager.update(
            current_objective="summarize conversations",
            subtasks=("first", "second"),
            corrections=(Correction(previous="old", corrected="new"),),
        )
        state = manager.state
        assert state.current_objective == "summarize conversations"
        assert state.subtasks == ("first", "second")
        assert isinstance(state.corrections[0], Correction)
        json.dumps(state.to_dict())

    def test_update_without_d1_fields_preserves_types(self):
        manager = ConversationStateManager()
        manager.update(
            subtasks=("a", "b"),
            corrections=(Correction(previous="old", corrected="new"),),
        )
        state = manager.update(latest_result="done")
        assert state.subtasks == ("a", "b")
        assert isinstance(state.corrections[0], Correction)

    def test_bounds_enforced(self):
        manager = ConversationStateManager()
        manager.update(
            subtasks=tuple(f"s{i}" for i in range(10)),
            corrections=tuple(
                Correction(previous=f"p{i}", corrected=f"c{i}") for i in range(10)
            ),
        )
        assert len(manager.state.subtasks) == MAX_SUBTASKS
        assert len(manager.state.corrections) == MAX_CORRECTIONS

    def test_defaults_are_empty(self):
        state = ConversationState()
        assert state.current_objective is None
        assert state.subtasks == ()
        assert state.corrections == ()


# ---------------------------------------------------------------------------
# Subtask / correction representation (engine)
# ---------------------------------------------------------------------------


class TestRepresentation:
    def test_compound_subtasks_represented_in_order(self):
        subtasks = detect_subtasks(
            "Research X then compare it with Y and finally tell me whether Z"
        )
        assert subtasks == (
            "Research X",
            "compare it with Y",
            "tell me whether Z",
        )

    def test_simple_request_has_no_subtasks(self):
        assert detect_subtasks("Explain the memory service.") == ()

    def test_correction_represented_not_silently_dropped(self):
        state = ConversationState(
            current_objective="Investigate the memory service.", turn_id="t1"
        )
        interp = _engine().interpret(
            "Actually, I meant the knowledge service.", state=state
        )
        assert len(interp.corrections) == 1
        correction = interp.corrections[0]
        assert correction.previous == "Investigate the memory service."
        assert correction.corrected

    def test_no_correction_without_prior_objective(self):
        interp = _engine().interpret("Actually, I meant the knowledge service.")
        assert interp.corrections == ()


# ---------------------------------------------------------------------------
# Kernel integration
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
    from atlas.kernel.atlas import Atlas

    saved = _patch_default_db_paths(
        Path(tempfile.mkdtemp(prefix="d1_")) / "atlas_experience.db"
    )
    atlas = Atlas()
    atlas.start()
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
    return service


class TestKernelIntegration:
    def test_semantic_intake_attached_and_json_safe(self, kernel):
        service = _fresh(kernel)
        spec = service._intake("Explain the memory service.", 1)
        payload = spec.context[SEMANTIC_INTAKE_KEY]
        assert payload["provenance"]["authority"] == "none"
        json.dumps(payload)

    def test_objective_recorded_in_conversation_state(self, kernel):
        service = _fresh(kernel)
        service.send("Explain the memory service.")
        assert service._state_manager.state.current_objective

    def test_correction_sequence_is_represented(self, kernel):
        service = _fresh(kernel)
        service.send("Investigate the memory service.")
        service.send("Actually, I meant the knowledge service.")
        state = service._state_manager.state
        assert state.corrections
        assert state.corrections[-1].previous
        assert state.corrections[-1].corrected

    def test_c4_capability_detail_preserved(self, kernel):
        for text in (
            "What does analysis do?",
            "Can you explain analysis?",
            "Tell me about analysis.",
        ):
            message = _fresh(kernel).send(text)
            assert message.metadata.get("builtin_intent") == "capability_detail", text

    def test_investigation_not_regressed(self, kernel):
        message = _fresh(kernel).send("Investigate the memory service.")
        assert isinstance((message.metadata or {}).get("investigation"), dict)

    def test_approval_language_cannot_authorize(self, kernel):
        before = (
            list(kernel._evolution_memory.get_all_proposals()),
            len(kernel._evolution_memory.get_pending_approval_requests()),
        )
        message = _fresh(kernel).send("I approve this.")
        assert (message.metadata or {}).get("approval", {}).get("status") in (
            "no_active_proposal",
            "no_session",
        )
        after = (
            list(kernel._evolution_memory.get_all_proposals()),
            len(kernel._evolution_memory.get_pending_approval_requests()),
        )
        assert after == before

    def test_no_model_used(self, kernel):
        message = _fresh(kernel).send("Explain the memory service.")
        assert message.metadata.get("model_used") is False


class TestStreamParity:
    @pytest.mark.parametrize(
        ("text", "intent"),
        [
            ("Hey Atlas.", "greeting"),
            ("What does analysis do?", "capability_detail"),
            ("What are your current limitations?", "self_knowledge"),
        ],
    )
    def test_chat_stream_aligned(self, kernel, text, intent):
        chat_msg = kernel.chat(text)
        assert (chat_msg.metadata or {}).get("builtin_intent") == intent

        stream_service = _fresh(kernel)
        chunks = "".join(kernel.stream(text))
        stream_md = stream_service._conversation.messages[-1].metadata or {}
        assert stream_md.get("builtin_intent") == intent
        assert chunks[:40] == chat_msg.content[:40]
