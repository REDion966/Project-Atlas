"""Real-world conversation validation — focused regression tests.

Two material defects found by the multi-turn validation pass, both fixed by
reusing existing mechanisms (no new layer):

  A. A POLITE question form of an operation request ("Can you investigate X?",
     "Investigate the cache layer?") was classified ``unknown`` instead of
     ``request_operation``. The operation executed, but NO dialogue thread /
     subject OCCURRENCE was created, so the retained-conversation contract was
     lost: a following "Go deeper on the previous problem?" failed closed on a
     perfectly valid subject, and a following "What did you find?" could report
     a STALE earlier result after a freshly completed investigation.

  B. The replacement adverb leaked into the operation object:
     "Forget that; investigate this instead." used "instead" as the
     investigation objective.

Deterministic, model-free, no network, no new state/operation/resolver.
"""

from __future__ import annotations

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.communicative_function import (
    FUNCTION_QUERY_RESULT,
    FUNCTION_RELATION,
    FUNCTION_REQUEST_OPERATION,
    classify_function,
)
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationReport
from atlas.conversation.semantic_frame import operation_object
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.self_knowledge.architecture_model import build_architecture_model

X = "the memory service"
Y = "the knowledge router"


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
        self.objectives: list[str] = []

    def investigate(self, target: str, *, objective: str = "") -> InvestigationReport:
        self.calls.append(target)
        self.objectives.append(objective)
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


def _threads(service: ConversationService):
    state = service.state_manager.state
    return tuple(state.thread_state.threads) if state.thread_state else ()


POLITE = (
    "Can you investigate the memory service?",
    "Investigate the memory service?",
)


# ---------------------------------------------------------------------------
# A. the polite request form is a REQUEST_OPERATION
# ---------------------------------------------------------------------------


class TestPoliteRequestIsAnOperationRequest:
    def test_classifier_recognises_the_polite_form(self):
        for text in POLITE:
            assert classify_function(
                text, illocution="question", operation="investigate"
            ) == FUNCTION_REQUEST_OPERATION, text

    def test_a_past_occurrence_question_stays_unknown(self):
        # The guard: a genuine question ABOUT a past occurrence must not start a
        # second investigation.
        for text, operation in (
            ("Did you investigate the cache layer?", "investigate"),
            ("Did you investigate the cache layer?", ""),
            ("Was the memory service investigated?", ""),
        ):
            assert classify_function(text, illocution="question", operation=operation) != (
                FUNCTION_REQUEST_OPERATION
            ), text

    def test_a_past_occurrence_question_is_not_a_function_level_request(self):
        # The bounded classifier never reads "Did you investigate X?" as an
        # operation request. The pre-existing INTAKE route for that turn (an
        # investigation cue) is unchanged by this work and is recorded as a
        # known limitation rather than altered here.
        assert classify_function(
            "Did you investigate the cache layer?", illocution="question",
            operation="investigate",
        ) != FUNCTION_REQUEST_OPERATION


# ---------------------------------------------------------------------------
# A. the polite form keeps the retained-conversation contract
# ---------------------------------------------------------------------------


class TestPoliteFormRetainsTheConversation:
    def test_a_polite_investigation_creates_a_subject_occurrence(self):
        for text in POLITE:
            service, _ = _service()
            service.send(text)
            threads = _threads(service)
            assert len(threads) == 1, (text, threads)
            assert threads[0].operation_referent_id
            assert threads[0].result_referent_id

    def test_deepening_works_after_a_polite_investigation(self):
        service, investigation = _service()
        service.send(f"Can you investigate {X}?")
        # a preceding occurrence, so "the previous issue" has a referent
        service.send("Can you investigate how the conversation system works?")

        message = service.send("Go deeper on the previous issue.")

        # the occurrence exists, so the retained objective continues instead of
        # failing closed on a valid subject
        assert len(investigation.calls) == 3
        assert "no retained conversational subject" not in message.content
        assert "## Investigation" in message.content
        assert investigation.objectives[-1] == f"Can you investigate {X}?"

    def test_a_polite_occurrence_is_reachable_by_the_bare_definite(self):
        service, investigation = _service()
        service.send("Can you investigate how the conversation system works?")

        message = service.send("Go deeper on the issue.")

        assert len(investigation.calls) == 2
        assert "Which one do you mean" not in message.content
        assert "## Investigation" in message.content

    def test_the_previous_problem_still_needs_a_preceding_occurrence(self):
        # unchanged contract: with only ONE retained occurrence there is nothing
        # "the previous problem" can denote, so the turn fails closed.
        service, investigation = _service()
        service.send(f"Investigate {X}.")

        message = service.send("Go deeper on the previous problem.")

        assert len(investigation.calls) == 1
        assert "no retained conversational subject" in message.content

    def test_a_later_result_is_not_masked_by_an_earlier_one(self):
        service, investigation = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Can you investigate {Y}?")

        latest = service.send("What did you find?")

        # the FRESH result, never the stale earlier one
        assert "knowledge router" in latest.content
        assert "memory service" not in latest.content
        assert (latest.metadata or {}).get("builtin_intent") == "reference"

    def test_ordinal_deepening_works_across_polite_and_imperative_forms(self):
        service, investigation = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Can you investigate {Y}?")

        service.send("Can you dig deeper into the second issue?")

        assert investigation.objectives[-1] == f"Can you investigate {Y}?"


# ---------------------------------------------------------------------------
# B. the replacement adverb is not the objective
# ---------------------------------------------------------------------------


class TestReplacementAdverbIsNotTheObjective:
    def test_operation_object_drops_the_replacement_adverb(self):
        assert operation_object("Forget that; investigate this instead.") == ""
        assert operation_object("Investigate the memory service instead.") == (
            "memory service"
        )

    def test_a_genuine_subject_word_is_still_extracted(self):
        assert operation_object("Investigate the instead policy.") == "policy"

    def test_a_replacement_turn_does_not_report_the_adverb_as_its_objective(
        self,
    ):
        service, investigation = _service()
        service.send(f"Investigate {X}.")

        message = service.send("Forget that; investigate this instead.")

        assert len(investigation.calls) == 2
        assert investigation.objectives[-1] != "instead"
        # the reported objective is never the bare adverb, whatever it renders as
        objective_lines = [
            line for line in message.content.splitlines() if "**Objective:**" in line
        ]
        assert all(line.strip().lower() != "**objective:** instead" for line in objective_lines)


# ---------------------------------------------------------------------------
# Interaction guards — the fixes must not steal these routes
# ---------------------------------------------------------------------------


class TestGuards:
    def test_explanation_cause_and_comparison_routes_are_untouched(self):
        service, investigation = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Investigate {Y}.")
        calls = len(investigation.calls)

        explanation = service.send("Can you explain that?")
        cause = service.send("Why does that happen?")
        comparison = service.send("Compare this with what you found earlier.")

        assert (explanation.metadata or {}).get("builtin_intent") == "reference"
        assert (cause.metadata or {}).get("response_plan", {}).get("function") == (
            "query_cause"
        )
        assert (comparison.metadata or {}).get("response_plan", {}).get("function") == (
            "query_comparison"
        )
        assert len(investigation.calls) == calls

    def test_relation_and_knowledge_routes_are_untouched(self):
        service, investigation = _service()
        service.send(f"Investigate {X}.")
        service.send(f"Investigate {Y}.")
        calls = len(investigation.calls)

        relation = service.send("Does this relate to the previous problem?")
        knowledge = service.send("Tell me more about the memory service.")

        assert "relation_query" in (relation.metadata or {})
        assert (knowledge.metadata or {}).get("builtin_intent") is not None
        assert len(investigation.calls) == calls

    def test_a_question_about_a_result_is_still_a_result_query(self):
        assert classify_function(
            "What did you find?", illocution="question", operation="research"
        ) == FUNCTION_QUERY_RESULT
        assert (
            classify_function(
                "Does this relate to the previous problem?",
                illocution="question",
                operation="",
            )
            == FUNCTION_RELATION
        )

    def test_intake_contract_is_unchanged_for_an_explicit_request(self):
        spec = TaskIntake().intake("Investigate the memory service.")
        assert spec.task_type is TaskType.INVESTIGATION_REQUEST


# ---------------------------------------------------------------------------
# send()/stream() parity for the fixed behaviour
# ---------------------------------------------------------------------------


class TestSendStreamParity:
    def _run(self, use_stream: bool):
        service, investigation = _service()
        first = (
            "".join(service.stream("Can you investigate the memory service?"))
            if use_stream
            else service.send("Can you investigate the memory service?").content
        )
        second = (
            "".join(service.stream("Go deeper on the issue."))
            if use_stream
            else service.send("Go deeper on the issue.").content
        )
        return (first, second, tuple(investigation.objectives))

    def test_polite_investigation_and_deepening_are_equivalent(self):
        assert self._run(False) == self._run(True)