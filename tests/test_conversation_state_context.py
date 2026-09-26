"""Checkpoint 3 — conversation state & context (multi-turn) contracts.

Checkpoint 3 traced the real multi-turn path: ``ConversationState`` (immutable,
single-valued facts) + ``ConversationContext`` (bounded 10-message projection) +
the reference resolver + the cascade. It found:

* one demonstrated, fixed defect — a bare-reference investigation follow-up
  ("Investigate this further.") re-derived its evidence from the literal words
  instead of the retained investigation subject, although
  ``ConversationState.current_investigation`` already held it;
* one demonstrated gap left OPEN with evidence (a resolved *findings* reference
  is not consumed by the information-request route), recorded for Checkpoint 4.

These tests pin the fixed behaviour, the continuation/reset split, the
history-vs-state boundary and the governance non-leak.
"""

from __future__ import annotations

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_context import (
    MAX_CONTEXT_TURNS,
    build_conversation_context,
)
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationReport
from atlas.conversation.task_intake import TaskIntake
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.self_knowledge.architecture_model import build_architecture_model

RETAINED = "Investigate the memory architecture"


class _FailingAI:
    """Any provider contact is a failure: this path is deterministic."""

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
    """Captures the exact call the conversation layer makes."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def investigate(self, target: str, *, objective: str = "") -> InvestigationReport:
        self.calls.append({"target": target, "objective": objective})
        return InvestigationReport(
            target=target,
            objective=objective,
            diagnosis="Identified 1 relevant component(s)",
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


def _retained_service(recording: _RecordingInvestigation) -> ConversationService:
    service = _service(recording)
    service.state_manager.update(current_investigation=RETAINED)
    return service


# ---------------------------------------------------------------------------
# 1. Continuation: a bare-reference follow-up uses the retained subject
# ---------------------------------------------------------------------------


class TestBareReferenceInvestigationFollowUp:
    """The demonstrated Checkpoint 3 defect, now fixed."""

    def test_retained_investigation_subject_reaches_the_investigation(self):
        recording = _RecordingInvestigation()
        service = _retained_service(recording)

        service.send("Investigate this further.")

        assert recording.calls[-1]["objective"] == RETAINED
        # The retained target/state contracts are unchanged.
        assert recording.calls[-1]["target"] == "Investigate this further."
        assert service.state_manager.state.last_operation.kind == (
            "investigation_request"
        )

    def test_no_retained_investigation_fails_closed(self):
        # With nothing retained there is no referent: the existing fail-closed
        # clarification asks for the subject instead of investigating "this".
        recording = _RecordingInvestigation()
        service = _service(recording)

        message = service.send("Investigate this further.")

        assert recording.calls == []
        assert message.metadata.get("frame_clarification") is not None
        assert "Which subject should I use?" in message.content

    def test_new_explicit_subject_is_never_overridden(self):
        recording = _RecordingInvestigation()
        service = _retained_service(recording)

        service.send("Investigate the capability registry.")

        assert recording.calls[-1]["objective"] == "capability registry"

    def test_model_free_and_governance_neutral(self):
        recording = _RecordingInvestigation()
        service = _retained_service(recording)
        message = service.send("Investigate this further.")

        for key in ("execution", "approval", "promotion"):
            assert key not in message.metadata, key
        assert service.state_manager.state.pending_approval_id is None
        assert _FailingAI.calls == 0


# ---------------------------------------------------------------------------
# 2. Reset: retained context is NOT applied to a new topic
# ---------------------------------------------------------------------------


class TestTopicSwitchResetsContext:
    def test_new_topic_does_not_reuse_the_retained_investigation(self):
        recording = _RecordingInvestigation()
        service = _retained_service(recording)

        message = service.send("What is the capability registry responsible for?")

        assert recording.calls == [], "a topic switch must not re-run the investigation"
        assert message.metadata.get("builtin_intent") == "capabilities"

    def test_explicit_new_subject_is_its_own_objective(self):
        recording = _RecordingInvestigation()
        service = _retained_service(recording)

        service.send("Investigate the conversation state manager.")

        assert recording.calls[-1]["objective"] == "conversation state manager"
        assert RETAINED not in recording.calls[-1]["objective"]


# ---------------------------------------------------------------------------
# 3. History vs state: the bounded window rolls over, the facts do not
# ---------------------------------------------------------------------------


class TestHistoryBoundaryIsNotAStateBoundary:
    def test_structured_state_survives_history_rollover(self):
        recording = _RecordingInvestigation()
        service = _service(recording)
        service.send("Investigate the memory architecture.")
        retained = service.state_manager.state.current_investigation
        assert retained

        for _ in range(14):
            service.send("status")

        message = service.send("What about the result?")

        assert message.metadata.get("builtin_intent") == "reference"
        assert message.metadata.get("reference_field") == "latest_result"
        assert service.state_manager.state.current_investigation == retained

    def test_bounded_window_is_smaller_than_the_conversation(self):
        recording = _RecordingInvestigation()
        service = _service(recording)
        service.send("Investigate the memory architecture.")
        for _ in range(14):
            service.send("status")

        context = build_conversation_context(
            service.conversation.messages, service.state_manager.state
        )
        assert context.total_messages > MAX_CONTEXT_TURNS
        assert len(context.recent_turns) == MAX_CONTEXT_TURNS


# ---------------------------------------------------------------------------
# 4. An old governed operation is never reused for a new, unrelated turn
# ---------------------------------------------------------------------------


class TestGovernedStateIsNotReused:
    def test_retained_operation_is_not_reapplied_to_an_unrelated_turn(self):
        recording = _RecordingInvestigation()
        service = _service(recording)
        service.send("Investigate the memory architecture.")
        recorded = service.state_manager.state.last_operation
        assert recorded is not None and recorded.kind == "investigation_request"

        message = service.send("hello")

        assert len(recording.calls) == 1, "the retained operation must not re-run"
        assert service.state_manager.state.last_operation == recorded
        for key in ("approval", "execution", "promotion"):
            assert key not in message.metadata, key
        assert service.state_manager.state.pending_approval_id is None

    @pytest.mark.parametrize(
        "text",
        ["Investigate this further.", "What about the result?", "status"],
    )
    def test_no_state_path_creates_authority(self, text):
        recording = _RecordingInvestigation()
        service = _retained_service(recording)
        message = service.send(text)
        for key in ("authorization", "promotion", "execution"):
            assert key not in message.metadata, key
        assert service.state_manager.state.pending_approval_id is None
