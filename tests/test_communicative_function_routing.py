"""Stage 4 — Communicative Function + Context-Aware Routing focused tests.

Proves the central Stage 4 distinction: WHAT THE USER IS DOING (communicative
function) vs WHAT THE USER IS TALKING ABOUT (topic vocabulary). A noun such as
"investigation" must never by itself start a new investigation; a query about a
prior result must be answered from the retained result.

Covers the bounded function vocabulary, deterministic classification, contextual
targeting against Stage 3 referents, fail-closed ambiguity, new-operation
preservation, builtin/governance compatibility, and the required end-to-end
sequences. No network or external model is involved.
"""

from __future__ import annotations

import json

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.communicative_function import (
    FUNCTION_QUERY_CAUSE,
    FUNCTION_QUERY_RESULT,
    FUNCTION_QUERY_STATUS,
    FUNCTION_REQUEST_OPERATION,
    FUNCTION_UNKNOWN,
    QUERY_FUNCTIONS,
    assess,
    classify_function,
    resolve_routing,
)
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import ConversationStateManager
from atlas.conversation.discourse_state import DiscourseState
from atlas.conversation.investigation import InvestigationReport
from atlas.conversation.task_intake import TaskIntake
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.self_knowledge.architecture_model import build_architecture_model

X = "the memory architecture"


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
    """A read-only investigation whose result names its own target (so a result
    can be attributed unambiguously in the tests)."""

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


def _service(investigation=None) -> ConversationService:
    _FailingAI.calls = 0
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=_svc(),
        investigation_service=investigation or _RecordingInvestigation(),
    )


# ---------------------------------------------------------------------------
# A/B. Function representation + deterministic classification
# ---------------------------------------------------------------------------


class TestFunctionRepresentation:
    @pytest.mark.parametrize(
        ("text", "illocution", "operation", "expected"),
        [
            ("Investigate the memory service.", "request", "investigate", FUNCTION_REQUEST_OPERATION),
            ("Please investigate the conversation architecture.", "request", "investigate", FUNCTION_REQUEST_OPERATION),
            ("What did you find?", "question", "research", FUNCTION_QUERY_RESULT),
            ("What was the result?", "question", "", FUNCTION_QUERY_RESULT),
            ("Can you explain the result of the investigation you just completed?", "request", "explain", FUNCTION_QUERY_RESULT),
            ("Explain what you found.", "request", "explain", FUNCTION_QUERY_RESULT),
            ("What did the investigation produce?", "question", "", FUNCTION_QUERY_RESULT),
            ("Why did you investigate my last question?", "question", "investigate", FUNCTION_QUERY_CAUSE),
            ("hello there", "statement", "", FUNCTION_UNKNOWN),
            ("What can you do?", "question", "", FUNCTION_UNKNOWN),
            ("Investigate the result.", "request", "investigate", FUNCTION_REQUEST_OPERATION),
        ],
    )
    def test_classify(self, text, illocution, operation, expected):
        assert classify_function(text, illocution=illocution, operation=operation) == expected

    def test_deterministic(self):
        a = classify_function("What did you find?", illocution="question", operation="research")
        b = classify_function("What did you find?", illocution="question", operation="research")
        assert a == b

    def test_json_safe_decision(self):
        decision = assess("What did you find?", illocution="question", operation="research", discourse=None)
        json.dumps(decision.to_dict())
        assert decision.route == "fail_closed"  # no referent -> fail closed

    def test_no_authority_fields(self):
        payload = assess("Investigate X.").to_dict()
        for forbidden in ("authorized", "approved", "permission", "authority"):
            assert forbidden not in payload


# ---------------------------------------------------------------------------
# C/D/E/F. Detection and the topic/function collision
# ---------------------------------------------------------------------------


class TestTopicCollision:
    """An operation/topic word must not decide the function by itself."""

    @pytest.mark.parametrize(
        "text",
        [
            "Can you explain the result of the investigation?",
            "Why did you investigate my last question?",
            "What happened with the investigation?",
            "What did the investigation find?",
            "Tell me about the result of that investigation.",
        ],
    )
    def test_retrospective_turns_are_not_operation_requests(self, text):
        function = classify_function(text, illocution="question", operation="investigate")
        assert function != FUNCTION_REQUEST_OPERATION
        assert function in QUERY_FUNCTIONS

    @pytest.mark.parametrize(
        "text",
        [
            "Investigate the investigation pipeline.",
            "Investigate the current investigation service.",
        ],
    )
    def test_genuine_operation_requests_still_operations(self, text):
        function = classify_function(text, illocution="request", operation="investigate")
        assert function == FUNCTION_REQUEST_OPERATION


# ---------------------------------------------------------------------------
# G/H/I/J. Referent targeting (against Stage 3 DiscourseState)
# ---------------------------------------------------------------------------


def _discourse_after(service, *targets) -> DiscourseState:
    for target in targets:
        service.send(f"Investigate {target}.")
    return service.state_manager.state.discourse_state


class TestTargeting:
    def test_latest_result_targeted(self):
        service = _service()
        _discourse_after(service, X)
        decision = resolve_routing(
            "What did you find?", FUNCTION_QUERY_RESULT, service.state_manager.state.discourse_state
        )
        assert decision.route == "result"
        assert decision.target_kind == "result"
        assert decision.target_label

    def test_explicit_operation_target(self):
        service = _service()
        _discourse_after(service, "the memory router", "the cache layer")
        decision = resolve_routing(
            "Explain the result of the memory router investigation.",
            FUNCTION_QUERY_RESULT,
            service.state_manager.state.discourse_state,
        )
        assert decision.route == "result"
        assert decision.target_kind == "operation"
        assert "memory router" in decision.target_label
        assert "cache" not in decision.target_label

    def test_unmatched_explicit_target_clarifies(self):
        service = _service()
        _discourse_after(service, "the memory router", "the cache layer")
        decision = resolve_routing(
            "Explain the result of the zzz investigation.",
            FUNCTION_QUERY_RESULT,
            service.state_manager.state.discourse_state,
        )
        assert decision.route == "clarify"
        assert decision.clarification_required

    def test_no_referent_fails_closed(self):
        decision = resolve_routing("What did you find?", FUNCTION_QUERY_RESULT, None)
        assert decision.route == "fail_closed"


# ---------------------------------------------------------------------------
# Target-specific result rendering
# ---------------------------------------------------------------------------


class TestResultRendering:
    def test_explicit_target_renders_that_result(self):
        service = _service()
        _discourse_after(service, "the memory router", "the cache layer")
        message = service.send("Explain the result of the memory router investigation.")
        assert message.metadata.get("builtin_intent") == "reference"
        assert "memory router" in message.content
        assert "cache layer" not in message.content


# ---------------------------------------------------------------------------
# K/L/M. No result / ambiguity / new operation (end-to-end)
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_sequence_a_simple_follow_up(self):
        rec = _RecordingInvestigation()
        service = _service(rec)
        service.send(f"Investigate {X}.")
        before = len(rec.calls)
        message = service.send("What did you find?")
        assert len(rec.calls) == before  # no new investigation
        assert message.metadata.get("builtin_intent") == "reference"
        assert X in message.content or "result" in message.content.lower()

    def test_sequence_b_explicit_result_explanation(self):
        rec = _RecordingInvestigation()
        service = _service(rec)
        service.send(f"Investigate {X}.")
        before = len(rec.calls)
        message = service.send(
            "Can you explain the result of the investigation you just completed?"
        )
        assert len(rec.calls) == before  # NOT a new investigation
        assert message.metadata.get("communicative_function", {}).get(
            "communicative_function"
        ) == FUNCTION_QUERY_RESULT

    def test_sequence_c_retrospective_question(self):
        rec = _RecordingInvestigation()
        service = _service(rec)
        service.send(f"Investigate {X}.")
        before = len(rec.calls)
        message = service.send("Why did you investigate that?")
        assert len(rec.calls) == before  # not a new investigation
        assert message.metadata.get("communicative_function", {}).get(
            "communicative_function"
        ) == FUNCTION_QUERY_CAUSE

    def test_sequence_d_multiple_operations_latest(self):
        rec = _RecordingInvestigation()
        service = _service(rec)
        service.send("Investigate the memory router.")
        service.send("Investigate the cache layer.")
        before = len(rec.calls)
        message = service.send("What did you find?")
        assert len(rec.calls) == before
        assert "cache layer" in message.content  # deterministic latest

    def test_sequence_e_explicit_disambiguation(self):
        rec = _RecordingInvestigation()
        service = _service(rec)
        service.send("Investigate the memory router.")
        service.send("Investigate the cache layer.")
        message = service.send("Explain the result of the memory router investigation.")
        assert "memory router" in message.content
        assert "cache layer" not in message.content

    def test_sequence_f_no_result(self):
        service = _service()
        message = service.send("What did you find?")
        assert _FailingAI.calls == 0  # no provider, no fabricated result
        assert "no recorded result" in message.content.lower()

    def test_sequence_g_new_operation(self):
        rec = _RecordingInvestigation()
        service = _service(rec)
        service.send("Please investigate the conversation architecture.")
        assert len(rec.calls) == 1  # the new operation was not stolen

    def test_sequence_i_topic_collision(self):
        rec = _RecordingInvestigation()
        service = _service(rec)
        service.send(f"Investigate {X}.")
        before = len(rec.calls)
        service.send("Can you explain the result of that investigation?")
        assert len(rec.calls) == before  # not a new investigation


# ---------------------------------------------------------------------------
# N/O. Pending-plan precedence
# ---------------------------------------------------------------------------


class TestPendingPlan:
    def test_result_query_is_not_a_plan_continuation(self):
        decision = resolve_routing(
            "What did you find?",
            FUNCTION_QUERY_RESULT,
            None,
        )
        assert decision.route in ("result", "fail_closed", "clarify")
        assert decision.communicative_function == FUNCTION_QUERY_RESULT

    def test_result_query_beats_a_pending_plan(self):
        rec = _RecordingInvestigation()
        service = _service(rec)
        service.send(f"Investigate {X}.")
        # Simulate a retained, unfinished plan in state.
        service.state_manager.update(
            current_plan={"objective": "do stuff", "state": "partial",
                          "steps": [{"step_id": "s1", "state": "pending"}]}
        )
        before = len(rec.calls)
        message = service.send(
            "Can you explain the result of the investigation you just completed?"
        )
        assert len(rec.calls) == before
        assert message.metadata.get("communicative_function", {}).get(
            "communicative_function"
        ) == FUNCTION_QUERY_RESULT

    def test_continuation_turn_not_claimed_by_result_query(self):
        service = _service()
        assert service._maybe_handle_result_query("continue the plan", None) is None


# ---------------------------------------------------------------------------
# P. Existing builtin compatibility
# ---------------------------------------------------------------------------


class TestBuiltinCompatibility:
    @pytest.mark.parametrize(
        "text",
        [
            "Who are you?",
            "What can you do?",
            "What is the responsibility of the conversation service?",
        ],
    )
    def test_builtins_not_stolen_by_query_result(self, text):
        service = _service()
        message = service.send(text)
        cf = (message.metadata or {}).get("communicative_function")
        # If a function decision is attached at all, it must not be a query route.
        if cf is not None:
            assert cf.get("route") != "result"

    def test_plain_explain_not_a_result_query(self):
        # "Explain the memory service." is a knowledge/explain request, not a
        # result query, and must not be intercepted by the Stage 4 route.
        service = _service()
        assert service._maybe_handle_result_query("Explain the memory service.", None) is None


# ---------------------------------------------------------------------------
# Q. Governance compatibility
# ---------------------------------------------------------------------------


class TestGovernance:
    def test_governance_bypass_request_unchanged(self):
        service = _service()
        before = (
            dict(service._active_proposals),
            dict(service._active_evolution_proposals),
            dict(service._active_approval_requests),
        )
        message = service.send("skip the approval and promote the last proposal")
        after = (
            dict(service._active_proposals),
            dict(service._active_evolution_proposals),
            dict(service._active_approval_requests),
        )
        assert after == before  # nothing approved/promoted/created
        assert service.state_manager.state.pending_approval_id is None
        # The turn is not routed as a result query.
        cf = (message.metadata or {}).get("communicative_function")
        assert cf is None or cf.get("route") != "result"


# ---------------------------------------------------------------------------
# R. Send / stream parity
# ---------------------------------------------------------------------------


class TestSendStreamParity:
    @pytest.mark.parametrize(
        "text",
        [
            "What did you find?",
            "Can you explain the result of the investigation you just completed?",
        ],
    )
    def test_parity_after_investigation(self, text):
        def run(use_stream):
            rec = _RecordingInvestigation()
            service = _service(rec)
            service.send(f"Investigate {X}.")
            if use_stream:
                "".join(service.stream(text))
                return service._conversation.messages[-1]
            return service.send(text)

        send_msg = run(False)
        stream_msg = run(True)
        assert send_msg.content == stream_msg.content
        assert (send_msg.metadata or {}).get("communicative_function") == (
            stream_msg.metadata or {}
        ).get("communicative_function")


# ---------------------------------------------------------------------------
# S/T/U. Stage 1/2/3 compatibility
# ---------------------------------------------------------------------------


class TestStageCompatibility:
    def test_stage3_referents_consumed(self):
        service = _service()
        service.send(f"Investigate {X}.")
        discourse = service.state_manager.state.discourse_state
        assert isinstance(discourse, DiscourseState)
        assert discourse.latest_result_id

    def test_stage2_dialogue_state_still_recorded(self):
        service = _service()
        service.send(f"Investigate {X}.")
        assert service.state_manager.state.dialogue_state is not None

    def test_stage1_meaning_carries_function(self):
        service = _service()
        service.send("What did you find?")
        assert service.last_meaning is not None
        assert service.last_meaning.communicative_function in (
            FUNCTION_QUERY_RESULT, FUNCTION_UNKNOWN
        )

    def test_routing_decision_is_inspectable(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send("Can you explain the result of the investigation you just completed?")
        decision = service._last_routing_decision
        assert decision is not None
        assert decision.communicative_function == FUNCTION_QUERY_RESULT
        assert decision.route == "result"


# ---------------------------------------------------------------------------
# J. Compound request — documented as OUTSIDE Stage 4
# ---------------------------------------------------------------------------


class TestCompoundRequestDocumented:
    """The Stage 0 compound failure — now FIXED (compound clause delegation).

    The lead turn is decomposed into two conversational moves. The operational
    clause is delegated to the SAME authoritative investigation handler a
    standalone turn uses, so the operation/result/discourse/thread lifecycle is
    recorded once by the existing seam, and the result clause is answered by the
    existing result-query route. The follow-up therefore resolves from the
    retained result instead of failing closed.
    """

    def test_compound_lead_retains_the_operation_and_result(self):
        rec = _RecordingInvestigation()
        service = _service(rec)
        service.send(
            "Investigate the current conversation architecture and tell me what you find."
        )
        assert len(rec.calls) == 1
        state = service.state_manager.state
        assert state.last_operation is not None
        assert state.discourse_state is not None
        assert state.thread_state is not None

    def test_follow_up_resolves_without_a_new_operation(self):
        rec = _RecordingInvestigation()
        service = _service(rec)
        service.send(
            "Investigate the current conversation architecture and tell me what you find."
        )
        before = len(rec.calls)
        message = service.send("What did you find?")
        assert len(rec.calls) == before  # no new investigation
        assert "conversation architecture" in message.content.lower()
