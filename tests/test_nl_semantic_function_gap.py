"""Deterministic NLU gap fixes — focused full-path regression tests.

Four demonstrated gaps (surface language that was detected and then discarded):

A. "Can you take a look at how the conversation system works?"
   -> the bounded investigation paraphrase now selects the EXISTING investigation.
B. "I want to understand why Atlas is not understanding me properly."
   -> the bounded diagnostic paraphrase selects the EXISTING investigation.
C. "Can you explain that?" (after an investigation)
   -> answered from the RETAINED RESULT, not the active-investigation summary.
D. "Compare this with what you found earlier."
   -> the COMPARE operation is preserved (never downgraded to a single-result
      query); two recorded results are presented, and fewer than two fails closed.

Each case asserts meaning -> function -> routing -> response/state, so the
intended meaning is proven to survive downstream. No model, no network.
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
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.self_knowledge.architecture_model import build_architecture_model

PARAPHRASE = "Can you take a look at how the conversation system works?"
UNDERSTAND = "I want to understand why Atlas is not understanding me properly."
EXPLAIN = "Can you explain that?"
COMPARE = "Compare this with what you found earlier."
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
    model = build_architecture_model(ComponentRegistry())
    service = ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(architecture_model_provider=lambda: model),
        investigation_service=investigation,
    )
    return service, investigation


def _plan(message) -> dict:
    return (message.metadata or {}).get("response_plan") or {}


# ---------------------------------------------------------------------------
# A. Investigation paraphrase
# ---------------------------------------------------------------------------


class TestInvestigationParaphrase:
    def test_surface_language_selects_the_existing_investigation(self):
        assert TaskIntake().intake(PARAPHRASE).task_type is TaskType.INVESTIGATION_REQUEST

    def test_full_path_reaches_the_existing_investigation(self):
        service, investigation = _service()
        message = service.send(PARAPHRASE)
        # routing
        assert investigation.calls == [PARAPHRASE]
        # state/lifecycle (the existing investigation recording)
        state = service.state_manager.state
        assert state.last_operation is not None
        assert state.last_operation.kind == TaskType.INVESTIGATION_REQUEST.value
        assert state.latest_result
        # response
        assert "## Investigation" in message.content

    def test_knowledge_paraphrase_is_unaffected(self):
        assert (
            TaskIntake().intake("Research the memory service.").task_type
            is TaskType.INFORMATION_REQUEST
        )


# ---------------------------------------------------------------------------
# B. "Understand why X is not working"
# ---------------------------------------------------------------------------


class TestUnderstandWhyDiagnostic:
    def test_surface_language_selects_an_existing_operation(self):
        assert TaskIntake().intake(UNDERSTAND).task_type is TaskType.INVESTIGATION_REQUEST

    def test_full_path_produces_an_investigation_not_the_floor(self):
        service, investigation = _service()
        message = service.send(UNDERSTAND)
        assert investigation.calls == [UNDERSTAND]
        assert service.state_manager.state.latest_result
        assert "## Investigation" in message.content
        # not the unsupported floor
        assert "could not map that request" not in message.content.lower()


# ---------------------------------------------------------------------------
# C. Explain + anaphoric target
# ---------------------------------------------------------------------------


class TestExplainAnaphor:
    def test_classifier_keeps_explain_and_returns_a_result_query(self):
        assert (
            classify_function(EXPLAIN, illocution="question", operation="explain")
            is FUNCTION_QUERY_RESULT
        )

    def test_explain_targets_the_retained_result_not_the_active_investigation(self):
        service, _ = _service()
        service.send(f"Investigate {X}.")
        message = service.send(EXPLAIN)

        plan = _plan(message)
        assert plan.get("function") == FUNCTION_QUERY_RESULT
        assert plan.get("target_kind") == "result"
        # the recorded RESULT is presented ...
        assert "Investigation result for" in message.content
        # ... and the operation label is never the answer by itself
        assert "The active investigation:" not in message.content

    def test_explain_fails_closed_without_a_retained_result(self):
        """With no prior context the turn fails closed — never a fabricated result.

        The existing frame-clarification surface ("Which subject should I use?")
        owns a context-free explanation request, which is the honest fail-closed
        outcome; what must NOT happen is a presented result.
        """
        service, _ = _service()
        message = service.send(EXPLAIN)
        plan = _plan(message)
        assert plan.get("shape") in (None, SHAPE_UNAVAILABLE)
        assert "Investigation result for" not in message.content

    def test_plain_explain_request_is_not_captured(self):
        # A named object keeps its existing route (pinned behaviour).
        assert (
            classify_function("Explain the memory service.", illocution="request", operation="explain")
            == "unknown"
        )


# ---------------------------------------------------------------------------
# D. Comparison
# ---------------------------------------------------------------------------


class TestComparison:
    def test_classifier_preserves_compare_over_retrospective_wording(self):
        assert (
            classify_function(COMPARE, illocution="request", operation="compare")
            is FUNCTION_COMPARE
        )

    def test_two_results_produce_a_bounded_comparison(self):
        service, _ = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Investigate {Y}.")
        message = service.send(COMPARE)

        plan = _plan(message)
        assert plan.get("function") == FUNCTION_COMPARE
        assert plan.get("shape") == SHAPE_COMPARISON
        # both RECORDED results are represented, newest first
        discourse = service.state_manager.state.discourse_state
        recorded = [r.label for r in discourse.referents if r.kind == "result"]
        assert len(recorded) == 2
        assert plan.get("candidates") == [recorded[-1], recorded[-2]]
        assert "no relationship between these results is inferred" in message.content

    def test_one_result_fails_closed_instead_of_a_single_summary(self):
        service, _ = _service()
        service.send(f"Investigate {X}.")
        message = service.send(COMPARE)
        plan = _plan(message)
        assert plan.get("function") == FUNCTION_COMPARE
        assert plan.get("shape") == SHAPE_UNAVAILABLE
        assert "Investigation result for" not in message.content


# ---------------------------------------------------------------------------
# P1-3 — reference-shaped investigation idioms
# ---------------------------------------------------------------------------


class TestContextualInvestigationIdiom:
    """A reference-shaped investigation idiom starts a NEW investigation.

    "Look into this.", "Dig into this.", "Dig into the remaining problem." and
    "Check what's going on with this." carry no explicit target; with a retained
    investigation subject they start a NEW read-only investigation of it. With no
    retained subject they decline (fail-closed), so an ordinary status request is
    never captured.
    """

    IDIOMS = (
        "Look into this.",
        "Dig into this.",
        "Dig into the remaining problem.",
        "Check what's going on with this.",
    )

    def test_retained_subject_starts_a_new_investigation(self):
        for text in self.IDIOMS:
            service, investigation = _service()
            service.send(f"Investigate {X}.")
            before = len(investigation.calls)
            message = service.send(text)
            assert len(investigation.calls) == before + 1, text
            assert "## Investigation" in message.content, text

    def test_no_retained_subject_declines(self):
        for text in self.IDIOMS:
            service, investigation = _service()
            message = service.send(text)
            assert investigation.calls == [], text
            assert "## Investigation" not in message.content, text

    def test_ordinary_status_is_not_stolen(self):
        service, investigation = _service()
        message = service.send("What's going on?")
        assert (message.metadata or {}).get("builtin_intent") == "status"
        assert investigation.calls == []


# ---------------------------------------------------------------------------
# send()/stream() parity for the new paths
# ---------------------------------------------------------------------------


class TestSendStreamParity:
    def _run(self, use_stream: bool) -> str:
        service, _ = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Investigate {Y}.")
        if use_stream:
            return "".join(service.stream(COMPARE))
        return service.send(COMPARE).content

    def test_comparison_is_identical_on_both_paths(self):
        assert self._run(False) == self._run(True)
