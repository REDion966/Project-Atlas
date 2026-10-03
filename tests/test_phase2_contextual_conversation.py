"""Phase 2 — contextual meaning & natural conversation (focused regressions).

Four bounded capabilities, all built on the EXISTING conversation architecture
(no new state/dialogue/memory/reference/execution authority, no model):

  * P2-1 — work/completion recall grounded in EXISTING retained state;
  * P2-2 — result-grounded elaboration/simplification requests;
  * P2-3 — bounded conversational stance/constraints (representation only);
  * P2-4 — bounded contextual comparison resolved against recorded referents.

Deterministic, model-free, no network.
"""

from __future__ import annotations

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.communicative_function import (
    FUNCTION_COMPARE,
    FUNCTION_QUERY_RESULT,
    classify_function,
)
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationReport
from atlas.conversation.response import SHAPE_COMPARISON, SHAPE_UNAVAILABLE
from atlas.conversation.task_intake import TaskIntake

X = "the conversation architecture"
Y = "the memory service"


class _FailingAI:
    def chat(self, prompt, routing_context=None):
        raise RuntimeError("provider must not be contacted")

    def stream_chat(self, prompt, routing_context=None):
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
            modification_status="NONE",
        )


def _service() -> tuple[ConversationService, _RecordingInvestigation]:
    investigation = _RecordingInvestigation()
    service = ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        investigation_service=investigation,
    )
    return service, investigation


def _after_two() -> tuple[ConversationService, _RecordingInvestigation]:
    service, investigation = _service()
    service.send(f"Investigate {X}.")
    service.send(f"Investigate {Y}.")
    return service, investigation


def _plan(message) -> dict:
    return (message.metadata or {}).get("response_plan") or {}


# ---------------------------------------------------------------------------
# P2-1 — work / completion recall
# ---------------------------------------------------------------------------


class TestWorkRecall:
    def test_completion_recall_lists_retained_work(self):
        service, _ = _service()
        service.send(f"Investigate {X}.")
        message = service.send("What have we done?")
        metadata = message.metadata or {}
        assert metadata.get("work_recall", {}).get("kind") == "completion"
        assert metadata["work_recall"]["count"] >= 1
        assert X.split()[-1] in message.content
        assert "Nothing was executed or authorized." in message.content

    def test_remind_completed_recall(self):
        service, _ = _service()
        service.send(f"Investigate {X}.")
        message = service.send("Can you remind me what we completed?")
        assert (message.metadata or {}).get("work_recall", {}).get("kind") == (
            "completion"
        )

    def test_activity_recall(self):
        service, _ = _service()
        service.send(f"Investigate {X}.")
        message = service.send("What were we working on?")
        metadata = message.metadata or {}
        assert metadata.get("work_recall", {}).get("kind") == "activity"
        assert metadata["work_recall"]["count"] >= 1

    def test_recall_does_not_report_itself_as_work(self):
        service, _ = _service()
        service.send(f"Investigate {X}.")
        message = service.send("What have we done?")
        # Only the investigation is retained work — never the recall question.
        assert (message.metadata or {}).get("work_recall", {}).get("count") == 1
        assert "what have we done" not in message.content.lower()

    def test_empty_conversation_is_honest(self):
        service, _ = _service()
        message = service.send("What have we done?")
        assert (message.metadata or {}).get("work_recall", {}).get("count") == 0
        assert "no record of completed or recent work" in message.content

    def test_temporal_precision_is_honest_and_not_fabricated(self):
        service, _ = _service()
        service.send(f"Investigate {X}.")
        message = service.send("What were we working on yesterday?")
        metadata = message.metadata or {}
        assert metadata.get("work_recall", {}).get("temporal_supported") is False
        assert "do not retain trustworthy per-work timestamps" in message.content
        # It still offers only the work Atlas actually retains.
        assert X.split()[-1] in message.content


# ---------------------------------------------------------------------------
# P2-2 — result-grounded elaboration / simplification
# ---------------------------------------------------------------------------


class TestElaboration:
    FORMS = (
        "Can you explain that more simply?",
        "Explain that in simpler terms.",
        "Can you clarify that?",
        "What does that mean?",
        "Can you elaborate on that?",
    )

    def test_forms_are_result_grounded(self):
        for text in self.FORMS:
            assert classify_function(text) == FUNCTION_QUERY_RESULT, text

    def test_each_form_resolves_to_the_retained_result(self):
        for text in self.FORMS:
            service, _ = _service()
            service.send(f"Investigate {X}.")
            message = service.send(text)
            metadata = message.metadata or {}
            assert metadata.get("reference_field") == "latest_result", text
            assert "Investigation result for" in message.content, text

    def test_fails_closed_without_a_retained_result(self):
        for text in self.FORMS:
            service, _ = _service()
            message = service.send(text)
            assert "Investigation result for" not in message.content, text
            assert (message.metadata or {}).get("reference_field") != "latest_result"

    def test_named_explain_is_not_captured(self):
        # A named object keeps its existing route (pinned behaviour).
        service, _ = _service()
        service.send(f"Investigate {X}.")
        message = service.send("Explain the memory service.")
        assert (message.metadata or {}).get("reference_field") != "latest_result"


# ---------------------------------------------------------------------------
# P2-3 — stance / constraints
# ---------------------------------------------------------------------------


class TestStanceConstraints:
    def test_no_modification_is_recorded_and_acknowledged(self):
        service, investigation = _service()
        message = service.send("Don't change anything yet.")
        assert (message.metadata or {}).get("stance", {}).get("kind") == (
            "no_modification"
        )
        assert service.state_manager.state.active_stance == "no_modification"
        assert investigation.calls == []
        assert "will not change anything" in message.content

    def test_read_only_only_form_is_recorded_without_investigating(self):
        service, investigation = _service()
        message = service.send("Only investigate for now.")
        assert (message.metadata or {}).get("stance", {}).get("kind") == "read_only"
        assert service.state_manager.state.active_stance == "read_only"
        assert investigation.calls == []

    def test_constraint_grants_no_authority(self):
        service, _ = _service()
        message = service.send("Don't make any changes.")
        for key in ("execution", "approval", "promotion"):
            assert key not in (message.metadata or {})
        assert service.state_manager.state.pending_approval_id is None

    def test_explicit_objective_supersedes_the_constraint(self):
        service, investigation = _service()
        service.send("Don't change anything yet.")
        assert service.state_manager.state.active_stance is not None
        service.send(f"Investigate {X}.")
        assert service.state_manager.state.active_stance is None
        assert investigation.calls  # the explicit objective still ran

    def test_constraint_attached_to_an_objective_defers_and_records(self):
        service, investigation = _service()
        service.send(f"Investigate {X}. Don't modify anything yet.")
        # the explicit investigation still runs ...
        assert investigation.calls
        # ... and the read-only constraint is retained as bounded stance.
        assert service.state_manager.state.active_stance == "no_modification"

    def test_unrelated_turn_records_no_stance(self):
        service, _ = _service()
        service.send("Handle it carefully.")
        assert service.state_manager.state.active_stance is None


# ---------------------------------------------------------------------------
# P2-4 — contextual comparison
# ---------------------------------------------------------------------------


class TestContextualComparison:
    def test_compare_against_context(self):
        service, _ = _after_two()
        message = service.send("Compare that with what we had before.")
        plan = _plan(message)
        assert plan.get("function") == FUNCTION_COMPARE
        assert plan.get("shape") == SHAPE_COMPARISON
        assert len(plan.get("candidates") or []) == 2
        assert "no relationship between these results is inferred" in message.content

    def test_difference_form_is_a_comparison(self):
        assert (
            classify_function("What's different from what we had before?")
            == FUNCTION_COMPARE
        )
        service, _ = _after_two()
        message = service.send("What's different from what we had before?")
        assert _plan(message).get("shape") == SHAPE_COMPARISON

    def test_how_does_this_compare(self):
        service, _ = _after_two()
        message = service.send("How does this compare with the previous result?")
        assert _plan(message).get("function") == FUNCTION_COMPARE

    def test_comparison_insufficient_fails_closed(self):
        service, _ = _service()
        service.send(f"Investigate {X}.")
        message = service.send("Compare that with what we had before.")
        plan = _plan(message)
        assert plan.get("function") == FUNCTION_COMPARE
        assert plan.get("shape") == SHAPE_UNAVAILABLE
        assert "Investigation result for" not in message.content

    def test_named_external_comparison_is_unchanged(self):
        # With no recorded results, a comparison naming external subjects is not
        # contextually resolvable: it fails closed and never fabricates a
        # comparison (existing route preserved).
        service, _ = _service()
        message = service.send("Compare the Samsung Galaxy S26 Ultra and the iPhone.")
        assert _plan(message).get("shape") != SHAPE_COMPARISON


# ---------------------------------------------------------------------------
# Multi-turn + send/stream parity
# ---------------------------------------------------------------------------


class TestMultiTurnAndParity:
    def test_sequence_investigate_find_explain(self):
        service, _ = _service()
        service.send(f"Investigate {X}.")
        found = service.send("What did you find?")
        assert (found.metadata or {}).get("reference_field") == "latest_result"
        simpler = service.send("Can you explain that more simply?")
        assert (simpler.metadata or {}).get("reference_field") == "latest_result"
        assert "Investigation result for" in simpler.content

    def test_constraint_then_continue_keeps_the_stance_meaningful(self):
        service, _ = _service()
        service.send(f"Investigate {X}.")
        service.send("Only investigate for now.")
        assert service.state_manager.state.active_stance == "read_only"
        message = service.send("What did you find?")
        # the stance never became an execution authority; the recall still works
        assert (message.metadata or {}).get("reference_field") == "latest_result"

    def test_send_stream_parity_for_new_paths(self):
        def _run(use_stream: bool) -> list[str]:
            service, _ = _service()
            service.send(f"Investigate {X}.")
            outputs: list[str] = []
            for turn in (
                "What have we done?",
                "Can you explain that more simply?",
                "Don't change anything yet.",
                "Investigate the storage layer.",
                "Compare that with what we had before.",
            ):
                if use_stream:
                    outputs.append("".join(service.stream(turn)))
                else:
                    outputs.append(service.send(turn).content)
            return outputs

        assert _run(False) == _run(True)
