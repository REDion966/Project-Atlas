"""Bounded investigation deepening — focused full-path regression tests.

Approved contract: "deeper / further / more deeply" is NOT a depth or effort
parameter and NOT a new operation. It CONTINUES the retained investigation
objective by issuing a new investigation occurrence against the resolved target,
through the EXISTING investigation handler and lifecycle. The modifier must never
become the objective, and the phrases excluded by the contract must keep their own
routes.

Deterministic, model-free, no network, no new state/operation/resolver.
"""

from __future__ import annotations

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.communicative_function import FUNCTION_COMPARE, FUNCTION_RELATION
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationReport
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.self_knowledge.architecture_model import build_architecture_model

X = "the conversation architecture"
Y = "the memory service"
Z = "the cache layer"


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


def _episodes(service: ConversationService, count: int):
    for subject in (X, Y, Z)[:count]:
        service.send(f"Investigate {subject}.")
    return tuple(service.state_manager.state.thread_state.threads)


# ---------------------------------------------------------------------------
# 1. The shipped continuation is unchanged
# ---------------------------------------------------------------------------


class TestExistingContinuation:
    def test_investigate_this_further_still_continues(self):
        service, investigation = _service()
        service.send(f"Investigate {X}.")
        threads_before = len(service.state_manager.state.thread_state.threads)

        message = service.send("Investigate this further.")

        assert investigation.objectives[-1] == f"Investigate {X}."
        assert len(investigation.calls) == 2
        # a NEW occurrence is created (the previous one superseded)
        state = service.state_manager.state
        assert len(state.thread_state.threads) == threads_before + 1
        assert state.thread_state.active() is not None
        assert "## Investigation" in message.content

    def test_lifecycle_records_a_new_occurrence_and_result(self):
        service, investigation = _service()
        service.send(f"Investigate {X}.")
        discourse_before = len(service.state_manager.state.discourse_state.referents)

        service.send("Can you investigate this more deeply?")

        state = service.state_manager.state
        # the authoritative handler produced a NEW operation/result pair
        assert (
            len(state.discourse_state.referents) == discourse_before + 2
        ), "a deepening request must create its own operation/result referents"
        assert state.last_operation.kind == "investigation_request"
        assert state.latest_result
        # the follow-up resolves through the existing machinery
        follow_up = service.send("What did you find?")
        assert (follow_up.metadata or {}).get("builtin_intent") == "reference"
        assert "Investigation result for" in follow_up.content
        assert len(investigation.calls) == 2  # no extra investigation


# ---------------------------------------------------------------------------
# 2/5. Bare reference + modifier
# ---------------------------------------------------------------------------


class TestBareReferenceDeepening:
    def test_more_deeply_uses_the_retained_target_not_the_adverb(self):
        service, investigation = _service()
        service.send(f"Investigate {X}.")

        message = service.send("Can you investigate this more deeply?")

        assert TaskIntake().intake("Can you investigate this more deeply?").task_type is (
            TaskType.INVESTIGATION_REQUEST
        )
        assert len(investigation.calls) == 2
        # the MODIFIER is never the objective
        assert investigation.objectives[-1] == f"Investigate {X}."
        assert not any("deeply" in objective.lower() for objective in investigation.objectives)
        assert "**Objective:**" in message.content
        objective_line = [
            line for line in message.content.splitlines() if "**Objective:**" in line
        ][0]
        assert "deeply" not in objective_line.lower()
        assert service.state_manager.state.last_operation is not None

    def test_look_further_into_that_keeps_the_investigation_path(self):
        service, investigation = _service()
        service.send(f"Investigate {X}.")

        message = service.send("Can you look further into that?")

        assert len(investigation.calls) == 2
        assert investigation.objectives[-1] == f"Investigate {X}."
        assert "## Investigation" in message.content
        # never the reference surface
        assert "The active investigation:" not in message.content


# ---------------------------------------------------------------------------
# 3/4. Subject-occurrence targets
# ---------------------------------------------------------------------------


class TestSubjectOccurrenceDeepening:
    def test_dig_deeper_ordinal_subject_uses_canonical_order(self):
        service, investigation = _service()
        episodes = _episodes(service, 2)
        retained = [thread.objective for thread in episodes]
        calls_before = len(investigation.calls)

        message = service.send("Can you dig deeper into the second issue?")

        assert len(investigation.calls) == calls_before + 1
        # the SECOND retained occurrence, oldest-first
        assert investigation.objectives[-1] == retained[1]
        assert "## Investigation" in message.content

    def test_go_deeper_previous_subject_is_the_preceding_occurrence(self):
        service, investigation = _service()
        episodes = _episodes(service, 2)
        retained = [thread.objective for thread in episodes]

        service.send("Go deeper on the previous problem.")

        # the occurrence immediately PRECEDING the active one — never a salience pick
        assert investigation.objectives[-1] == retained[0]
        assert investigation.objectives[-1] != retained[1]


# ---------------------------------------------------------------------------
# 6/7. Missing and ambiguous targets
# ---------------------------------------------------------------------------


class TestTargetFailure:
    def test_missing_target_fails_closed_without_investigating(self):
        service, investigation = _service()
        message = service.send("Go deeper on the previous problem.")
        assert investigation.calls == []
        assert "## Investigation" not in message.content
        # honest, and never an invented objective
        assert "Which subject" in message.content

    def test_ambiguous_subject_clarifies_and_never_investigates(self):
        service, investigation = _service()
        episodes = _episodes(service, 2)
        retained = [thread.objective for thread in episodes]
        calls_before = len(investigation.calls)

        message = service.send("Go deeper on the issue.")

        assert len(investigation.calls) == calls_before  # nothing executed
        assert "Which one do you mean" in message.content
        for objective in retained:
            assert objective in message.content
        assert service.state_manager.state.pending_clarification is not None


# ---------------------------------------------------------------------------
# 8-15. Excluded interpretations keep their routes
# ---------------------------------------------------------------------------


class TestExcludedInterpretations:
    def test_evidence_gap_analysis_is_not_hijacked(self):
        service, investigation = _service()
        _episodes(service, 2)
        message = service.send("Can you analyze the findings further?")
        assert "Evidence Gap Analysis" in message.content
        assert investigation.calls == [f"Investigate {X}.", f"Investigate {Y}."]

    def test_explanation_is_not_hijacked(self):
        service, investigation = _service()
        _episodes(service, 2)
        message = service.send("Explain this in more detail.")
        assert "## Investigation" not in message.content
        assert len(investigation.calls) == 2

    def test_verification_and_result_query_are_not_hijacked(self):
        service, investigation = _service()
        _episodes(service, 2)
        verified = service.send("Can you verify that result?")
        found = service.send("What did you find?")
        for message in (verified, found):
            assert "## Investigation" not in message.content
        assert (found.metadata or {}).get("builtin_intent") == "reference"
        assert len(investigation.calls) == 2

    def test_knowledge_and_research_are_not_hijacked(self):
        service, investigation = _service()
        _episodes(service, 2)
        knowledge = service.send("Tell me more about the memory service.")
        research = service.send("Research more about the memory service.")
        for message in (knowledge, research):
            assert "## Investigation" not in message.content
        assert len(investigation.calls) == 2

    def test_relation_query_is_not_hijacked(self):
        service, investigation = _service()
        _episodes(service, 2)
        message = service.send("Does this relate to the previous problem?")
        metadata = message.metadata or {}
        assert metadata.get("relation_query") is not None
        assert "relation_query" in metadata
        assert len(investigation.calls) == 2

    def test_comparison_is_not_hijacked(self):
        service, investigation = _service()
        _episodes(service, 2)
        message = service.send("Compare this with what you found earlier.")
        plan = (message.metadata or {}).get("response_plan") or {}
        assert plan.get("function") == FUNCTION_COMPARE
        assert len(investigation.calls) == 2

    def test_explicit_investigation_target_is_unchanged(self):
        service, investigation = _service()
        message = service.send(f"Investigate {X}.")
        assert investigation.calls == [f"Investigate {X}."]
        assert "## Investigation" in message.content


# ---------------------------------------------------------------------------
# 16. send()/stream() parity
# ---------------------------------------------------------------------------


class TestSendStreamParity:
    def _run(self, use_stream: bool, text: str, warmups: tuple[str, ...]):
        service, investigation = _service()
        for warmup in warmups:
            service.send(warmup)
        if use_stream:
            content = "".join(service.stream(text))
        else:
            content = service.send(text).content
        return content, tuple(investigation.objectives)

    def test_successful_deepening_is_equivalent(self):
        warmups = (f"Investigate {X}.",)
        text = "Can you investigate this more deeply?"
        sent, sent_objectives = self._run(False, text, warmups)
        streamed, stream_objectives = self._run(True, text, warmups)
        assert sent == streamed
        assert sent_objectives == stream_objectives

    def test_fail_closed_deepening_is_equivalent(self):
        text = "Go deeper on the previous problem."
        sent, sent_objectives = self._run(False, text, ())
        streamed, stream_objectives = self._run(True, text, ())
        assert sent == streamed
        assert sent_objectives == stream_objectives == ()
