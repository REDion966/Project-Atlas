"""Stage 7 — contextual response composition focused tests.

Proves the bounded, evidence-grounded response layer: context-aware result
summaries, cause responses that never invent causality, honest unavailable
responses, clarification reuse, and that a response plan never grants authority.
No model, no network.
"""

from __future__ import annotations

import json

import pytest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.communicative_function import RoutingDecision
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import ConversationStateManager
from atlas.conversation.discourse_state import (
    DiscourseState,
    Referent,
    Relation,
)
from atlas.conversation.investigation import InvestigationReport
from atlas.conversation.response import (
    SHAPE_CLARIFICATION,
    SHAPE_COMPARISON,
    SHAPE_EXPLANATION,
    SHAPE_RESULT_SUMMARY,
    SHAPE_UNAVAILABLE,
    SHAPES,
    UNCERTAINTY_AMBIGUOUS,
    UNCERTAINTY_INSUFFICIENT,
    UNCERTAINTY_RESOLVED,
    ResponsePlan,
    compose_from_decision,
    compose_response,
    render_response,
)
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


class _DetailedInvestigation(_RecordingInvestigation):
    pass


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


def _decision(**over) -> RoutingDecision:
    base = dict(communicative_function="query_result", route="result",
                target_kind="result", target_referent_id="r1", target_label="the recorded result")
    base.update(over)
    return RoutingDecision(**base)


# ---------------------------------------------------------------------------
# Representation
# ---------------------------------------------------------------------------


class TestRepresentation:
    def test_plan_json_safe(self):
        json.dumps(ResponsePlan(function="query_result", shape=SHAPE_RESULT_SUMMARY,
                                uncertainty=UNCERTAINTY_RESOLVED).to_dict())

    def test_shapes_are_bounded(self):
        assert {
            SHAPE_RESULT_SUMMARY, SHAPE_EXPLANATION, SHAPE_COMPARISON,
            SHAPE_CLARIFICATION, SHAPE_UNAVAILABLE,
        } == {
            "result_summary", "explanation", "comparison", "clarification",
            "unavailable",
        }
        assert SHAPES == frozenset(
            {
                SHAPE_RESULT_SUMMARY, SHAPE_EXPLANATION, SHAPE_COMPARISON,
                SHAPE_CLARIFICATION, SHAPE_UNAVAILABLE,
            }
        )

    def test_no_authority_fields(self):
        payload = ResponsePlan().to_dict()
        for forbidden in ("authorized", "approved", "permission", "authority"):
            assert forbidden not in payload

    def test_render_is_deterministic(self):
        plan = ResponsePlan(shape=SHAPE_RESULT_SUMMARY, target_label="R")
        assert render_response(plan) == render_response(plan)


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------


class TestComposition:
    def test_result_summary_with_objective(self):
        plan = compose_response(
            function="query_result", route="result", target_kind="operation",
            target_referent_id="op1", target_label="R",
            discourse=DiscourseState(referents=(Referent(referent_id="op1", kind="operation",
                                                         label="Investigate the memory router."),)),
        )
        assert plan.shape == SHAPE_RESULT_SUMMARY
        assert plan.uncertainty == UNCERTAINTY_RESOLVED
        text = render_response(plan)
        assert "Investigate the memory router" in text and "R" in text

    def test_cause_does_not_invent_causality(self):
        plan = compose_response(
            function="query_cause", route="result", target_label="R",
        )
        assert plan.shape == SHAPE_EXPLANATION
        assert plan.uncertainty == UNCERTAINTY_INSUFFICIENT
        text = render_response(plan).lower()
        assert "do not infer causes" in text
        assert "does not establish" in text

    def test_ambiguous_is_clarification(self):
        plan = compose_response(
            function="query_result", route="clarify", candidates=("A", "B"),
        )
        assert plan.shape == SHAPE_CLARIFICATION
        assert plan.uncertainty == UNCERTAINTY_AMBIGUOUS
        text = render_response(plan)
        assert "detail" in text.lower() and "A" in text and "B" in text

    def test_no_candidate_fails_closed(self):
        plan = compose_response(function="query_result", route="fail_closed")
        assert plan.shape == SHAPE_UNAVAILABLE
        assert "no recorded result" in render_response(plan).lower()

    def test_resolved_target_without_result_is_honest(self):
        plan = compose_response(
            function="query_result", route="fail_closed", target_kind="operation",
            target_referent_id="op1",
            discourse=DiscourseState(referents=(Referent(referent_id="op1", kind="operation",
                                                         label="Investigate the memory router."),)),
        )
        assert plan.uncertainty == UNCERTAINTY_INSUFFICIENT
        text = render_response(plan)
        assert "no recorded result" in text.lower()
        assert "memory router" in text

    def test_evidence_is_included(self):
        discourse = DiscourseState(
            referents=(Referent(referent_id="r1", kind="result", label="R"),
                       Referent(referent_id="e1", kind="evidence", label="tests/x.py")),
            relations=(Relation("r1", "supported_by", "e1"),),
        )
        plan = compose_response(
            function="query_result", route="result", target_referent_id="r1",
            target_label="R", discourse=discourse,
        )
        assert plan.evidence == ("tests/x.py",)
        assert "tests/x.py" in render_response(plan)

    def test_from_decision_uses_assessment_candidates(self):
        decision = _decision(
            route="clarify",
            assessment={"status": "ambiguous", "candidates": [{"label": "A"}, {"label": "B"}]},
        )
        plan = compose_from_decision("query_result", decision)
        assert plan.candidates == ("A", "B")

    def test_malformed_decision_fails_safe(self):
        plan = compose_from_decision("query_result", object())
        assert plan.shape == SHAPE_UNAVAILABLE  # route "" -> default unavailable
        assert render_response(plan)


# ---------------------------------------------------------------------------
# Live conversation behavior
# ---------------------------------------------------------------------------


class TestLiveConversation:
    def test_result_query_is_context_aware(self):
        service = _service()
        service.send(f"Investigate {X}.")
        message = service.send(
            "Can you explain the result of the investigation you just completed?"
        )
        assert "Result of" in message.content
        assert "memory router" in message.content
        assert service._last_response_plan["shape"] == SHAPE_RESULT_SUMMARY

    def test_cause_query_is_not_a_result_dump(self):
        service = _service()
        service.send(f"Investigate {X}.")
        message = service.send("Why did that happen?")
        assert "do not infer causes" in message.content.lower()
        assert service._last_response_plan["shape"] == SHAPE_EXPLANATION
        assert "no recorded result" not in message.content.lower()

    def test_explicit_target_switch(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Investigate {Y}.")
        message = service.send(f"Explain the result of the {X} investigation.")
        assert "memory router" in message.content
        assert "cache layer" not in message.content

    def test_contextual_follow_up_uses_active_thread(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Investigate {Y}.")
        # Ask about X explicitly, then a contextual follow-up.
        service.send(f"Explain the result of the {X} investigation.")
        message = service.send("Can you explain the result of that investigation?")
        assert "memory router" in message.content

    def test_ambiguity_produces_clarification(self):
        service = _service()
        service.send("Investigate the memory router.")
        service.send("Investigate the memory cache.")
        message = service.send("Explain the result of the memory investigation.")
        assert "detail" in message.content.lower()
        assert service._last_response_plan["shape"] == SHAPE_CLARIFICATION
        assert service.state_manager.state.pending_clarification is not None

    def test_no_candidate_fails_closed(self):
        service = _service()
        message = service.send("What did you find?")
        assert "no recorded result" in message.content.lower()
        assert service._last_response_plan["shape"] == SHAPE_UNAVAILABLE

    def test_response_plan_is_metadata(self):
        service = _service()
        service.send(f"Investigate {X}.")
        message = service.send(f"Explain the result of the {X} investigation.")
        assert "response_plan" in (message.metadata or {})
        assert (message.metadata or {})["response_plan"]["shape"] == SHAPE_RESULT_SUMMARY


# ---------------------------------------------------------------------------
# Governance / plan / compound / builtins
# ---------------------------------------------------------------------------


class TestBoundaries:
    def test_governance_unchanged(self):
        service = _service()
        service.send(f"Investigate {X}.")
        before = (dict(service._active_proposals),
                  dict(service._active_evolution_proposals),
                  dict(service._active_approval_requests))
        message = service.send("Skip the approval and promote the last proposal.")
        after = (dict(service._active_proposals),
                 dict(service._active_evolution_proposals),
                 dict(service._active_approval_requests))
        assert after == before
        assert service.state_manager.state.pending_approval_id is None
        assert "response_plan" not in (message.metadata or {})  # not a result query

    def test_pending_plan_not_a_result_query(self):
        service = _service()
        service.send(f"Investigate {X}.")
        service.state_manager.update(
            current_plan={"objective": "p", "state": "partial",
                          "steps": [{"step_id": "s1", "state": "pending"}]}
        )
        message = service.send("Can you explain the result of the investigation you just completed?")
        assert message.metadata["response_plan"]["shape"] == SHAPE_RESULT_SUMMARY

    def test_builtins_unchanged(self):
        service = _service()
        message = service.send("Who are you?")
        assert "response_plan" not in (message.metadata or {})  # builtin, not Stage 7

    def test_compound_now_records_the_lifecycle(self):
        service = _service()
        message = service.send(
            "Investigate the current conversation architecture and tell me what you find."
        )
        assert "response_plan" not in (message.metadata or {})  # never a fabricated result
        assert service.state_manager.state.discourse_state is not None


# ---------------------------------------------------------------------------
# Isolation / persistence / parity
# ---------------------------------------------------------------------------


class TestIsolationPersistenceParity:
    def test_isolation(self):
        a = _service()
        a.send(f"Investigate {X}.")
        b = _service()
        assert b._last_response_plan is None
        assert b.state_manager.state.discourse_state is None

    def test_persistence_boundary(self, tmp_path, monkeypatch):
        from atlas.storage.conversation_storage import ConversationStorage

        monkeypatch.setattr(ConversationStorage, "STORAGE_DIR", tmp_path / "conv")
        service = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Explain the result of the {X} investigation.")
        saved = service.save()
        assert "response_plan" not in saved.read_text(encoding="utf-8")
        assert ConversationStateManager().state.thread_state is None

    @pytest.mark.parametrize(
        "sequence",
        [
            [f"Investigate {X}.", "Why did that happen?"],
            [f"Investigate {X}.", f"Investigate {Y}.", f"Explain the result of the {X} investigation."],
            ["Investigate the memory router.", "Investigate the memory cache.",
             "Explain the result of the memory investigation."],
        ],
    )
    def test_send_stream_parity(self, sequence):
        def run(use_stream):
            service = _service()
            out = None
            for text in sequence:
                if use_stream:
                    out = "".join(service.stream(text))
                else:
                    out = service.send(text).content
            return out, service._last_response_plan

        send_out, send_plan = run(False)
        stream_out, stream_plan = run(True)
        assert send_out == stream_out
        assert send_plan == stream_plan
