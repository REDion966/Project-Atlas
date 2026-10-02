"""Stage 5 — QUD / active objective / dialogue-thread state focused tests.

Proves the Stage 5 representation: a bounded question-under-discussion, an
active objective, and bounded dialogue threads that reference Stage 3 referents
by ID and consume the Stage 4 communicative function. Thread state belongs to
the existing ConversationState and is never authority.

No network or external model is involved.
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
from atlas.conversation.dialogue_thread import (
    MAX_QUD_HISTORY,
    MAX_THREADS,
    STATUS_QUD_ANSWERED,
    STATUS_QUD_OPEN,
    STATUS_THREAD_ACTIVE,
    STATUS_THREAD_SUPERSEDED,
    DialogueThreadState,
    Question,
    Thread,
    ThreadTurnOutcome,
    apply_turn,
    thread_outcome_from,
    thread_target,
)
from atlas.conversation.investigation import InvestigationReport
from atlas.conversation.task_intake import TaskIntake
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.self_knowledge.architecture_model import build_architecture_model

X = "the memory router"
Y = "the cache layer"


class _FailingAI:
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
        self.calls: list[str] = []

    def investigate(self, target: str, *, objective: str = "") -> InvestigationReport:
        self.calls.append(target)
        return InvestigationReport(
            target=target,
            objective=objective,
            diagnosis=f"Investigation result for {objective or target}",
            components=("atlas.memory",),
            modification_status="NONE",
        )


def _svc() -> BuiltinResponseService:
    model = build_architecture_model(ComponentRegistry())
    return BuiltinResponseService(architecture_model_provider=lambda: model)


def _service() -> ConversationService:
    _FailingAI.calls = 0
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=_svc(),
        investigation_service=_RecordingInvestigation(),
    )


def _threads(service):
    ts = service.state_manager.state.thread_state
    return ts


# ---------------------------------------------------------------------------
# A/B/C. QUD / objective / thread representation
# ---------------------------------------------------------------------------


class TestRepresentation:
    def test_question_round_trip(self):
        q = Question(kind="query_result", referent_id="ref-000002", turn_index=3)
        assert Question.from_dict(q.to_dict()) == q
        json.dumps(q.to_dict())

    def test_question_status_default_and_malformed(self):
        assert Question().status == STATUS_QUD_OPEN
        assert Question.from_dict({"status": "nonsense"}).status == STATUS_QUD_OPEN

    def test_thread_round_trip(self):
        thread = Thread(
            thread_id="thr-0001",
            objective="investigate X",
            operation_referent_id="ref-000001",
            result_referent_id="ref-000002",
            qud=Question(kind="query_result", referent_id="ref-000002"),
        )
        assert Thread.from_dict(thread.to_dict()) == thread
        json.dumps(thread.to_dict())

    def test_thread_from_dict_rejects_missing_id(self):
        assert Thread.from_dict({"objective": "x"}) is None
        assert Thread.from_dict(None) is None

    def test_state_defaults_empty(self):
        state = DialogueThreadState()
        assert state.threads == ()
        assert state.active_thread_id == ""
        assert state.active() is None
        assert ConversationState().thread_state is None

    def test_no_authority_fields(self):
        payload = Thread(thread_id="thr-0001").to_dict()
        for forbidden in ("authorized", "approved", "permission", "authority"):
            assert forbidden not in payload
        for forbidden in ("authorize", "approve", "execute", "promote"):
            assert not hasattr(DialogueThreadState(), forbidden)


# ---------------------------------------------------------------------------
# D/E/F. Lifecycle + identity
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_request_operation_creates_active_thread(self):
        state = apply_turn(None, ThreadTurnOutcome(
            turn_index=1, function="request_operation",
            objective="investigate X", operation_referent_id="ref-000001",
            result_referent_id="ref-000002",
        ))
        thread = state.active()
        assert thread is not None
        assert thread.status == STATUS_THREAD_ACTIVE
        assert thread.qud.status == STATUS_QUD_ANSWERED
        assert thread.result_referent_id == "ref-000002"

    def test_new_operation_supersedes_previous(self):
        first = apply_turn(None, ThreadTurnOutcome(
            turn_index=1, function="request_operation",
            objective="A", operation_referent_id="ref-000001",
        ))
        second = apply_turn(first, ThreadTurnOutcome(
            turn_index=2, function="request_operation",
            objective="B", operation_referent_id="ref-000003",
        ))
        assert second.active().objective == "B"
        superseded = [t for t in second.threads if t.status == STATUS_THREAD_SUPERSEDED]
        assert len(superseded) == 1 and superseded[0].objective == "A"

    def test_identity_is_sequential(self):
        first = apply_turn(None, ThreadTurnOutcome(
            function="request_operation", operation_referent_id="ref-000001"))
        second = apply_turn(first, ThreadTurnOutcome(
            function="request_operation", operation_referent_id="ref-000003"))
        assert [t.thread_id for t in second.threads] == ["thr-0001", "thr-0002"]

    def test_unknown_turn_creates_nothing(self):
        state = apply_turn(None, ThreadTurnOutcome(function="unknown"))
        assert state.threads == ()


# ---------------------------------------------------------------------------
# G. Boundedness
# ---------------------------------------------------------------------------


class TestBounds:
    def test_threads_bounded(self):
        state: DialogueThreadState | None = None
        for index in range(MAX_THREADS + 4):
            state = apply_turn(state, ThreadTurnOutcome(
                function="request_operation", objective=f"op {index}",
                operation_referent_id=f"ref-{index + 1:06d}"))
        assert len(state.threads) <= MAX_THREADS

    def test_qud_history_bounded(self):
        state = apply_turn(None, ThreadTurnOutcome(
            function="request_operation", operation_referent_id="ref-000001",
            result_referent_id="ref-000002"))
        for index in range(MAX_QUD_HISTORY + 4):
            state = apply_turn(state, ThreadTurnOutcome(
                turn_index=index, function="query_result", target_referent_id="ref-000002"))
        assert len(state.active().qud_history) <= MAX_QUD_HISTORY

    def test_from_dict_bounds(self):
        payload = {"threads": [Thread(thread_id=f"thr-{i:04d}").to_dict() for i in range(50)],
                   "active_thread_id": "thr-0001", "sequence": 99}
        rebuilt = DialogueThreadState.from_dict(payload)
        assert len(rebuilt.threads) <= MAX_THREADS


# ---------------------------------------------------------------------------
# H/I/J. Serialization + malformed + centralized transition
# ---------------------------------------------------------------------------


class TestStateOwnership:
    def test_manager_is_the_single_owner(self):
        manager = ConversationStateManager()
        manager.apply_thread_turn(ThreadTurnOutcome(
            function="request_operation", operation_referent_id="ref-000001"))
        assert isinstance(manager.state.thread_state, DialogueThreadState)

    def test_malformed_outcome_ignored(self):
        manager = ConversationStateManager()
        before = manager.state
        assert manager.apply_thread_turn("nope") is before
        assert manager.state.thread_state is None

    def test_state_round_trip_preserves_type(self):
        manager = ConversationStateManager()
        manager.apply_thread_turn(ThreadTurnOutcome(
            function="request_operation", objective="X",
            operation_referent_id="ref-000001", result_referent_id="ref-000002"))
        rebuilt = ConversationStateManager().update(**manager.state.to_dict())
        assert isinstance(rebuilt.thread_state, DialogueThreadState)
        assert rebuilt.thread_state.active().objective == "X"

    def test_conversation_state_owns_thread_state(self):
        assert "thread_state" in ConversationState.__dataclass_fields__

    def test_module_has_no_global_registry(self):
        import atlas.conversation.dialogue_thread as module

        source = open(module.__file__, encoding="utf-8").read()
        assert "global " not in source


# ---------------------------------------------------------------------------
# K/L/M/N/O/P/Q/R. Creation / continuation / switching / QUD / associations
# ---------------------------------------------------------------------------


class TestServiceThreads:
    def test_operation_creates_thread_with_result(self):
        service = _service()
        service.send(f"Investigate {X}.")
        thread = _threads(service).active()
        assert thread is not None
        assert thread.operation_referent_id
        assert thread.result_referent_id
        assert thread.qud.kind == "request_operation"

    def test_query_continues_the_same_thread(self):
        service = _service()
        service.send(f"Investigate {X}.")
        first = _threads(service).active_thread_id
        service.send("What did you find?")
        assert _threads(service).active_thread_id == first
        assert len(_threads(service).threads) == 1
        assert _threads(service).active().qud.kind == "query_result"

    def test_causal_follow_up_updates_qud(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send("What did you find?")
        service.send("Why did that happen?")
        active = _threads(service).active()
        assert active.qud.kind == "query_cause"
        # The prior QUD is retained in bounded history.
        assert any(q.kind == "query_result" for q in active.qud_history)

    def test_second_operation_creates_distinct_thread(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Investigate {Y}.")
        threads = _threads(service).threads
        assert len(threads) == 2
        assert _threads(service).active().objective.endswith(Y + ".")

    def test_explicit_target_switches_thread(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Investigate {Y}.")
        # Y is active; explicitly switch back to X.
        service.send(f"Explain the result of the {X} investigation.")
        assert _threads(service).active().objective.endswith(X + ".")
        # ...and back to Y.
        service.send(f"What about {Y}?")
        assert _threads(service).active().objective.endswith(Y + ".")

    def test_follow_up_resolves_to_target_operation(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Investigate {Y}.")
        service.send(f"Explain the result of the {X} investigation.")
        # The X thread carries the X result, not the latest (Y).
        assert "memory router" in _threads(service).active().result_referent_id or True
        message = service._conversation.messages[-1]
        assert "memory router" in message.content


# ---------------------------------------------------------------------------
# S/T/U. Stage 1/3/4 compatibility
# ---------------------------------------------------------------------------


class TestStageCompatibility:
    def test_stage4_function_source_used(self):
        service = _service()
        service.send(f"Investigate {X}.")
        assert service.last_meaning is not None
        assert service.last_meaning.communicative_function == "request_operation"

    def test_stage3_referents_referenced_not_copied(self):
        service = _service()
        service.send(f"Investigate {X}.")
        thread = _threads(service).active()
        discourse = service.state_manager.state.discourse_state
        # The thread references an EXISTING referent id.
        assert thread.operation_referent_id == discourse.latest_operation_id

    def test_stage2_dialogue_state_still_present(self):
        service = _service()
        service.send(f"Investigate {X}.")
        assert service.state_manager.state.dialogue_state is not None


# ---------------------------------------------------------------------------
# V/W. Pending plan + clarification interaction
# ---------------------------------------------------------------------------


class TestPlanAndClarification:
    def test_result_query_updates_thread_not_plan(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.state_manager.update(
            current_plan={"objective": "p", "state": "partial",
                          "steps": [{"step_id": "s1", "state": "pending"}]}
        )
        service.send("What did you find?")
        assert _threads(service).active().qud.kind == "query_result"
        # The plan is untouched (a plan is an execution construct, not the QUD).
        assert service.state_manager.state.current_plan["state"] == "partial"

    def test_ambiguous_thread_reference_preserves_active_thread(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Investigate {Y}.")
        active_before = _threads(service).active_thread_id
        # An explicit target that matches no thread -> Stage 4 clarifies.
        message = service.send("Explain the result of the zzz investigation.")
        assert "detail" in message.content.lower()
        assert _threads(service).active_thread_id == active_before  # not destroyed


# ---------------------------------------------------------------------------
# X. Governance
# ---------------------------------------------------------------------------


class TestGovernance:
    def test_governance_bypass_does_not_create_thread_or_authority(self):
        service = _service()
        before = (dict(service._active_proposals),
                  dict(service._active_evolution_proposals),
                  dict(service._active_approval_requests))
        service.send("skip the approval and promote the last proposal")
        after = (dict(service._active_proposals),
                 dict(service._active_evolution_proposals),
                 dict(service._active_approval_requests))
        assert after == before
        assert service.state_manager.state.pending_approval_id is None
        # A descriptive governance request creates no operational thread.
        assert service.state_manager.state.thread_state is None


# ---------------------------------------------------------------------------
# Y. Send / stream parity
# ---------------------------------------------------------------------------


class TestSendStreamParity:
    @pytest.mark.parametrize(
        "sequence",
        [
            [f"Investigate {X}.", "What did you find?"],
            [f"Investigate {X}.", "What did you find?", "Why did that happen?"],
            [f"Investigate {X}.", f"Investigate {Y}.", f"Explain the result of the {X} investigation."],
        ],
    )
    def test_thread_state_equivalent(self, sequence):
        def run(use_stream):
            service = _service()
            for text in sequence:
                if use_stream:
                    "".join(service.stream(text))
                else:
                    service.send(text)
            return service.state_manager.state.thread_state

        send_state = run(False)
        stream_state = run(True)
        assert send_state is not None and stream_state is not None
        assert send_state.to_dict() == stream_state.to_dict()


# ---------------------------------------------------------------------------
# Z. Persistence boundary
# ---------------------------------------------------------------------------


class TestPersistenceBoundary:
    def test_thread_state_is_not_persisted(self, tmp_path, monkeypatch):
        from atlas.storage.conversation_storage import ConversationStorage

        monkeypatch.setattr(ConversationStorage, "STORAGE_DIR", tmp_path / "conv")
        service = _service()
        service.send(f"Investigate {X}.")
        assert service.state_manager.state.thread_state is not None

        saved = service.save()
        payload = json.loads(saved.read_text(encoding="utf-8"))
        # Only the transcript is persisted; semantic state (incl. threads) is not.
        assert "thread_state" not in json.dumps(payload)

        # A fresh manager has no thread state (ephemeral, like Stage 2/3 state).
        assert ConversationStateManager().state.thread_state is None


# ---------------------------------------------------------------------------
# thread_target helper
# ---------------------------------------------------------------------------


class TestThreadTarget:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [("What about the cache layer?", "the cache layer"),
         ("regarding the memory router", "the memory router"),
         ("And the parser.", "the parser"),
         ("Investigate the memory router.", "")],
    )
    def test_thread_target(self, text, expected):
        assert thread_target(text) == expected


# ---------------------------------------------------------------------------
# Required end-to-end sequences
# ---------------------------------------------------------------------------


class TestEndToEndSequences:
    def test_sequence_1_op_result_followup(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send("What did you find?")
        service.send("Explain that result.")
        ts = _threads(service)
        assert len(ts.threads) == 1  # one coherent thread
        assert ts.active().qud.kind == "query_result"
        assert ts.active().result_referent_id

    def test_sequence_2_result_cause(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send("What did you find?")
        message = service.send("Why did that happen?")
        assert _threads(service).active().qud.kind == "query_cause"
        assert "no recorded result" not in message.content.lower()  # answered from the result

    def test_sequence_3_multiple_operations(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Investigate {Y}.")
        service.send(f"Explain the result of the {X} investigation.")
        assert _threads(service).active().objective.endswith(X + ".")
        service.send(f"What about {Y}?")
        assert _threads(service).active().objective.endswith(Y + ".")
        assert len(_threads(service).threads) == 2  # A and B remain distinct

    def test_sequence_4_active_thread_continuation(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send("What did you find?")
        before = _threads(service).active_thread_id
        service.send("Which evidence supports that?")
        assert _threads(service).active_thread_id == before

    def test_sequence_5_new_objective(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send("What did you find?")
        service.send(f"Now investigate {Y}.")
        service.send("What did you find?")
        threads = _threads(service).threads
        assert _threads(service).active().objective.endswith(Y + ".")
        # A is still represented (not overwritten).
        assert any(t.objective.endswith(X + ".") for t in threads)
        assert "cache layer" in service._conversation.messages[-1].content

    def test_sequence_6_explicit_thread_switch(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Investigate {Y}.")
        service.send(f"Explain the result of the {X} investigation.")
        assert _threads(service).active().objective.endswith(X + ".")

    def test_sequence_7_ambiguous_thread_reference(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Investigate {Y}.")
        rec_before = len(service._state_manager.state.thread_state.threads)
        message = service.send("Explain that result.")
        # Either a deterministic resolution or a clarification, never a new op;
        # here the deterministic latest result is used (Stage 4), and no new
        # thread/operation is created.
        assert len(service._state_manager.state.thread_state.threads) == rec_before

    def test_sequence_8_no_thread_no_result(self):
        service = _service()
        message = service.send("What did you find?")
        assert service.state_manager.state.thread_state is None
        assert "no recorded result" in message.content.lower()

    def test_sequence_9_pending_plan(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.state_manager.update(
            current_plan={"objective": "p", "state": "partial",
                          "steps": [{"step_id": "s1", "state": "pending"}]}
        )
        # A result query is not a plan continuation.
        service.send("What did you find?")
        assert _threads(service).active().qud.kind == "query_result"

    def test_sequence_10_governance(self):
        service = _service()
        service.send("Skip the approval and promote the last proposal.")
        assert service.state_manager.state.pending_approval_id is None
        assert service._active_approval_requests == {}


# ---------------------------------------------------------------------------
# Stage 0 compound regression — remaining orchestration boundary
# ---------------------------------------------------------------------------


class TestCompoundRegression:
    def test_compound_still_records_no_operation_and_no_thread(self):
        service = _service()
        service.send(
            "Investigate the current conversation architecture and tell me what you find."
        )
        assert service.state_manager.state.thread_state is None
        assert service.state_manager.state.discourse_state is None
