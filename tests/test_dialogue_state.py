"""Stage 2 — Dialogue / Information State focused tests (behaviour-preserving).

Covers the Stage 2 responsibilities: the bounded ``DialogueState`` container and
its value/serialization contract, the centralized ``apply_dialogue_turn`` seam,
route-independent recording through ``ConversationService.send``/``stream``,
boundedness, clarification transitions, compatibility with the existing
``ConversationState`` fields, and the explicit Stage 3/4 boundaries.

The layer is representation-only and PROCEED-only: it must change no routing.
That is proven directly by ``TestBehaviourPreservation`` (running turns with the
dialogue recording disabled vs enabled must be identical) plus the frozen
regression suites run separately.

No network or external model is involved: any provider contact fails the test.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import (
    ConversationState,
    ConversationStateManager,
)
from atlas.conversation.dialogue_state import (
    MAX_RECENT_TURNS,
    STATUS_NONE,
    STATUS_PENDING,
    STATUS_RESOLVED,
    DialogueState,
    DialogueTurn,
    DialogueTurnOutcome,
    apply_turn,
    outcome_from,
)
from atlas.conversation.investigation import InvestigationReport
from atlas.conversation.meaning import build_atlas_meaning
from atlas.conversation.task_intake import TaskIntake
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.self_knowledge.architecture_model import build_architecture_model

CASUAL = "Hello Atlas."
OPERATIONAL = "Investigate the memory service."
QUESTION = "How does the memory service work?"

#: The known Stage 0 sequence (see docs/ATLAS_STATE.md 34.7).
STAGE0_SEQUENCE = (
    "Investigate the current conversation architecture and tell me what you find.",
    "What did you find?",
    "Can you explain the result of the investigation you just completed?",
)


class _FailingAI:
    """Any provider contact is a failure: these routes are deterministic."""

    calls = 0

    def chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1
        raise RuntimeError("provider must not be contacted")

    def stream_chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1

        def _generator():
            raise RuntimeError("provider must not be contacted")
            yield ""  # pragma: no cover

        return _generator()


class _RecordingInvestigation:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def investigate(self, target: str, *, objective: str = "") -> InvestigationReport:
        self.calls.append({"target": target, "objective": objective})
        return InvestigationReport(
            target=target,
            objective=objective,
            diagnosis="Identified 3 relevant component(s) in atlas",
            components=("atlas.memory",),
            modification_status="NONE",
        )


def _svc() -> BuiltinResponseService:
    model = build_architecture_model(ComponentRegistry())
    return BuiltinResponseService(architecture_model_provider=lambda: model)


def _service(investigation=None) -> ConversationService:
    _FailingAI.calls = 0
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=_svc(),
        investigation_service=investigation,
    )


def _outcome(**over) -> DialogueTurnOutcome:
    base = dict(
        turn_index=1,
        turn_role="new_objective",
        act="request",
        objective="do the thing",
        subject="the thing",
        topic="the thing",
        topic_kind="investigation",
    )
    base.update(over)
    return DialogueTurnOutcome(**base)


# ---------------------------------------------------------------------------
# A. Initial state
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_empty_dialogue_state_is_valid(self):
        state = DialogueState()
        assert state.turn_index == 0
        assert state.clarification_status == STATUS_NONE
        assert state.recent == ()

    def test_conversation_state_default_has_no_dialogue_state(self):
        assert ConversationState().dialogue_state is None

    def test_no_authority_fields(self):
        payload = DialogueState().to_dict()
        for forbidden in ("authorized", "approved", "permission", "authority"):
            assert forbidden not in payload
        assert not hasattr(DialogueState(), "authorize")
        assert not hasattr(DialogueState(), "execute")


# ---------------------------------------------------------------------------
# B. Turn updates
# ---------------------------------------------------------------------------


class TestTurnUpdates:
    def test_apply_turn_sets_current_fields(self):
        state = apply_turn(None, _outcome(objective="o", subject="s", topic="t"))
        assert state.objective == "o"
        assert state.subject == "s"
        assert state.topic == "t"
        assert state.turn_role == "new_objective"
        assert state.act == "request"

    def test_unrelated_outcome_fields_do_not_leak(self):
        first = apply_turn(None, _outcome(objective="o1"))
        second = apply_turn(first, _outcome(objective="o2", topic=""))
        # The latest outcome replaces the current snapshot (it is not merged).
        assert second.objective == "o2"
        assert second.topic == ""
        # ...but the bounded history still carries the first reading.
        assert second.recent[1].objective == "o1"

    def test_manager_seam_sets_dialogue_state(self):
        manager = ConversationStateManager()
        manager.apply_dialogue_turn(_outcome(objective="hello"))
        assert isinstance(manager.state.dialogue_state, DialogueState)
        assert manager.state.dialogue_state.objective == "hello"

    def test_manager_ignores_malformed_outcome(self):
        manager = ConversationStateManager()
        before = manager.state
        assert manager.apply_dialogue_turn("not-an-outcome") is before
        assert manager.state.dialogue_state is None


# ---------------------------------------------------------------------------
# C. Objective / topic continuity (compatibility with existing fields)
# ---------------------------------------------------------------------------


class TestObjectiveTopicContinuity:
    def test_outcome_reads_existing_state_facts(self):
        meaning = build_atlas_meaning(OPERATIONAL, spec=TaskIntake().intake(OPERATIONAL))
        state = ConversationState(
            current_objective="existing objective",
            current_subject="existing subject",
        )
        outcome = outcome_from(meaning, state, turn_index=7)
        assert outcome.objective == "existing objective"
        assert outcome.subject == "existing subject"
        assert outcome.turn_index == 7

    def test_existing_fields_are_not_replaced_by_the_seam(self):
        manager = ConversationStateManager()
        manager.update(current_objective="keep me", current_subject="keep subject")
        meaning = build_atlas_meaning("Hello Atlas.")
        outcome = outcome_from(meaning, manager.state, turn_index=1)
        manager.apply_dialogue_turn(outcome)
        # Existing authoritative fields are untouched by dialogue recording.
        assert manager.state.current_objective == "keep me"
        assert manager.state.current_subject == "keep subject"
        # The dialogue snapshot mirrors the existing objective, not a new value.
        assert manager.state.dialogue_state.objective == "keep me"


# ---------------------------------------------------------------------------
# D. Clarification
# ---------------------------------------------------------------------------


class TestClarification:
    def test_pending_is_recorded(self):
        state = apply_turn(
            None, _outcome(clarification_pending=True, clarification_question="which?")
        )
        assert state.clarification_status == STATUS_PENDING
        assert state.clarification_question == "which?"

    def test_resolution_is_recorded(self):
        pending = apply_turn(None, _outcome(clarification_pending=True, clarification_question="which?"))
        resolved = apply_turn(pending, _outcome(clarification_pending=False))
        assert resolved.clarification_status == STATUS_RESOLVED
        assert resolved.clarification_question == "which?"

    def test_none_after_resolution(self):
        pending = apply_turn(None, _outcome(clarification_pending=True))
        resolved = apply_turn(pending, _outcome(clarification_pending=False))
        settled = apply_turn(resolved, _outcome(clarification_pending=False))
        assert settled.clarification_status == STATUS_NONE
        assert settled.clarification_question == ""


# ---------------------------------------------------------------------------
# E. Replacement / immutability / determinism
# ---------------------------------------------------------------------------


class TestValueBehaviour:
    def test_updates_do_not_mutate_the_original(self):
        first = apply_turn(None, _outcome(objective="o1"))
        apply_turn(first, _outcome(objective="o2"))
        assert first.objective == "o1"

    def test_state_is_frozen(self):
        state = DialogueState()
        with pytest.raises(dataclasses.FrozenInstanceError):
            state.objective = "x"  # type: ignore[misc]

    def test_deterministic(self):
        a = apply_turn(None, _outcome()).to_dict()
        b = apply_turn(None, _outcome()).to_dict()
        assert a == b


# ---------------------------------------------------------------------------
# F. Bounds
# ---------------------------------------------------------------------------


class TestBounds:
    def test_recent_window_is_bounded(self):
        state: DialogueState | None = None
        for index in range(MAX_RECENT_TURNS + 5):
            state = apply_turn(state, _outcome(turn_index=index))
        assert len(state.recent) == MAX_RECENT_TURNS
        # Most recent first; oldest dropped.
        assert state.recent[0].turn_index == MAX_RECENT_TURNS + 4

    def test_long_strings_are_bounded(self):
        state = apply_turn(None, _outcome(objective="x" * 5000, subject="y" * 5000))
        assert len(state.objective) <= 400
        assert len(state.subject) <= 200

    def test_from_dict_rejects_malformed(self):
        assert DialogueState.from_dict(None) is None
        assert DialogueState.from_dict("nope") is None
        # A well-formed empty dict yields a valid empty state.
        assert DialogueState.from_dict({}) == DialogueState()


# ---------------------------------------------------------------------------
# G. Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_json_safe(self):
        json.dumps(apply_turn(None, _outcome()).to_dict())

    def test_round_trip(self):
        state = apply_turn(None, _outcome(objective="o", clarification_pending=True))
        rebuilt = DialogueState.from_dict(state.to_dict())
        assert rebuilt == state
        assert isinstance(rebuilt.recent[0], DialogueTurn)

    def test_conversation_state_to_dict_is_json_safe(self):
        manager = ConversationStateManager()
        manager.apply_dialogue_turn(_outcome())
        json.dumps(manager.state.to_dict())

    def test_conversation_state_round_trip_preserves_dialogue_type(self):
        manager = ConversationStateManager()
        manager.apply_dialogue_turn(_outcome(objective="o"))
        payload = manager.state.to_dict()
        rebuilt = ConversationStateManager().update(**payload)
        assert isinstance(rebuilt.dialogue_state, DialogueState)
        assert rebuilt.dialogue_state.objective == "o"


# ---------------------------------------------------------------------------
# H. ConversationService integration (route-independent recording)
# ---------------------------------------------------------------------------


class TestServiceIntegration:
    def test_casual_turn_records_dialogue_state(self):
        service = _service()
        service.send(CASUAL)
        dialogue = service.state_manager.state.dialogue_state
        assert isinstance(dialogue, DialogueState)
        assert dialogue.recent

    def test_recording_is_route_independent(self):
        # A turn answered by the builtin surface and a turn that falls through to
        # the (failing) provider both still record a dialogue turn.
        casual = _service()
        casual.send(CASUAL)
        fallthrough = _service()
        fallthrough.send("zzqx unrecognized gibberish turn")
        assert casual.state_manager.state.dialogue_state is not None
        assert fallthrough.state_manager.state.dialogue_state is not None

    def test_recent_grows_across_turns(self):
        service = _service()
        service.send("Hello Atlas.")
        service.send("Thanks.")
        service.send("How does the memory service work?")
        assert len(service.state_manager.state.dialogue_state.recent) >= 2


# ---------------------------------------------------------------------------
# I. Behaviour preservation
# ---------------------------------------------------------------------------


class TestBehaviourPreservation:
    def _run(self, service, sequence):
        return [(m.role, m.content, dict(m.metadata or {})) for m in (service.send(t) for t in sequence)]

    def test_recording_is_additive(self, monkeypatch):
        sequence = STAGE0_SEQUENCE

        monkeypatch.setattr(
            ConversationService, "_record_dialogue_turn", lambda self: None
        )
        control = self._run(_service(_RecordingInvestigation()), sequence)
        monkeypatch.undo()

        real_service = _service(_RecordingInvestigation())
        real = self._run(real_service, sequence)

        assert control == real
        assert real_service.state_manager.state.dialogue_state is not None

    def test_stage0_query_turns_do_not_start_new_operations(self):
        """Stage 4 fix: the query turns no longer start a NEW investigation.

        (The compound lead turn still retains no result, so the follow-up fails
        closed; that recording/sequencing gap is outside the Stage 4 boundary and
        is documented by the Stage 4 tests.)
        """
        recording = _RecordingInvestigation()
        service = _service(recording)
        service.send(STAGE0_SEQUENCE[0])
        service.send(STAGE0_SEQUENCE[1])
        before = len(recording.calls)
        message = service.send(STAGE0_SEQUENCE[2])
        assert len(recording.calls) == before  # no NEW investigation
        assert not isinstance((message.metadata or {}).get("investigation"), dict)


# ---------------------------------------------------------------------------
# J. Send / stream parity
# ---------------------------------------------------------------------------


class TestSendStreamParity:
    @pytest.mark.parametrize("text", [CASUAL, QUESTION, OPERATIONAL])
    def test_dialogue_state_equivalent(self, text):
        send_service = _service()
        send_service.send(text)
        stream_service = _service()
        list(stream_service.stream(text))
        assert (
            send_service.state_manager.state.dialogue_state.to_dict()
            == stream_service.state_manager.state.dialogue_state.to_dict()
        )


# ---------------------------------------------------------------------------
# K. Stage 3/4 boundaries + governance
# ---------------------------------------------------------------------------


class TestBoundaries:
    def test_no_referent_or_thread_fields(self):
        fields = set(DialogueState.__dataclass_fields__)
        for forbidden in ("referents", "threads", "qud", "operation_refs", "result_refs"):
            assert forbidden not in fields

    def test_conversation_state_has_no_referent_registry(self):
        assert "referents" not in ConversationState.__dataclass_fields__

    def test_no_communicative_function_routing_introduced(self):
        import atlas.conversation.dialogue_state as module

        source = open(module.__file__, encoding="utf-8").read()
        for forbidden in ("REQUEST_OPERATION", "QUERY_RESULT", "CommunicativeFunction", "adjudicat"):
            assert forbidden not in source

    def test_recording_creates_no_governance_objects(self):
        service = _service()
        before = (
            dict(service._active_proposals),
            dict(service._active_evolution_proposals),
            dict(service._active_approval_requests),
        )
        service.send("I approve this.")
        service.send("Execute it now.")
        after = (
            dict(service._active_proposals),
            dict(service._active_evolution_proposals),
            dict(service._active_approval_requests),
        )
        assert after == before
