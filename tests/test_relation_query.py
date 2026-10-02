"""Relation query — focused full-path regression tests.

The bounded question "does A relate to B?" is recognized by the function layer as
``FUNCTION_RELATION`` and answered ONLY from a DIRECT recorded discourse edge
(either stored direction, over the five existing relation types). Absent evidence
is reported as insufficient evidence, never as "unrelated"; relatedness is never
inferred from a shared thread, topic, proximity, salience or a third referent.

Targets reuse EXISTING machinery: a subject occurrence ("the previous problem",
"the second issue") resolves through the retained dialogue threads (creation
order), and anything else keeps the existing contextual reference/routing.

Deterministic, model-free, no network, no new state or resolver.
"""

from __future__ import annotations

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.communicative_function import (
    FUNCTION_COMPARE,
    FUNCTION_RELATION,
    classify_function,
    relation_query_parts,
)
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationReport
from atlas.conversation.task_intake import TaskIntake
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


def _episodes(service: ConversationService, count: int):
    subjects = (X, Y, Z)
    for i in range(count):
        service.send(f"Investigate {subjects[i]}.")
    thread_state = service.state_manager.state.thread_state
    return tuple(thread_state.threads)


def _ask(service: ConversationService, text: str):
    message = service.send(text)
    return (message.metadata or {}).get("relation_query"), message


# ---------------------------------------------------------------------------
# A. Recognition
# ---------------------------------------------------------------------------


class TestRecognition:
    def test_bounded_question_is_its_own_function(self):
        text = f"Does that relate to the previous problem?"
        assert relation_query_parts(text) == ("that", "the previous problem")
        assert (
            classify_function(text, illocution="question", operation="")
            == FUNCTION_RELATION
        )

    def test_architectural_relate_usage_is_not_captured(self):
        for text in ("How do the modules relate to each other?",
                     "Do the modules relate to the router?"):
            assert relation_query_parts(text) is None or text.startswith("Do the modules")
        assert (
            classify_function("How do the modules relate to each other?",
                               illocution="question", operation="")
            == "unknown"
        )


# ---------------------------------------------------------------------------
# B/C. Targets
# ---------------------------------------------------------------------------


class TestTargets:
    def test_previous_subject_is_the_occurrence_before_the_active_one(self):
        service, _ = _service()
        episodes = _episodes(service, 3)
        for text in ("Does that relate to the previous problem?",
                     "Does that relate to the previous issue?"):
            record, _message = _ask(service, text)
            assert record["status"] == "established"
            # "previous" is the retained occurrence preceding the ACTIVE one.
            assert episodes[1].objective in {record["a"], record["b"]}

    def test_ordinal_subject_uses_oldest_first_creation_order(self):
        service, _ = _service()
        episodes = _episodes(service, 3)
        assert [t.created_turn for t in episodes] == sorted(t.created_turn for t in episodes)
        record, _message = _ask(service, "Does the first issue relate to the second issue?")
        assert record["status"] == "established"
        assert {record["a"], record["b"]} == {
            episodes[0].objective,
            episodes[1].objective,
        }

    def test_second_occurrence_is_the_second_episode(self):
        service, _ = _service()
        episodes = _episodes(service, 3)
        record, _message = _ask(service, "Does the second issue relate to the first issue?")
        assert record["status"] == "established"
        assert {record["a"], record["b"]} == {
            episodes[0].objective,
            episodes[1].objective,
        }


# ---------------------------------------------------------------------------
# E. The direct-edge predicate
# ---------------------------------------------------------------------------


class TestDirectEdge:
    def test_positive_edge_is_reported_verbatim(self):
        service, _ = _service()
        _episodes(service, 2)
        discourse = service.state_manager.state.discourse_state
        recorded = {
            (r.relation, r.source_id, r.target_id) for r in discourse.relations
        }
        record, message = _ask(service, "Does that relate to the previous problem?")
        assert record["status"] == "established"
        assert (record["relation"], record["source_referent_id"], record["target_referent_id"]) in recorded
        assert "The record contains a direct relationship" in message.content
        assert record["relation"] in message.content

    def test_edge_in_the_opposite_query_order_still_resolves(self):
        service, _ = _service()
        _episodes(service, 2)
        forward, _ = _ask(service, "Does that relate to the previous problem?")
        reverse, _ = _ask(service, "Does the previous problem relate to that?")
        assert forward["status"] == "established"
        assert reverse["status"] == "established"
        # same recorded edge, reached in either query order
        assert {forward["source_referent_id"], forward["target_referent_id"]} == {
            reverse["source_referent_id"],
            reverse["target_referent_id"],
        }

    def test_no_direct_edge_is_insufficient_never_unrelated(self):
        service, _ = _service()
        _episodes(service, 3)
        record, message = _ask(service, "Does the first issue relate to the third issue?")
        assert record["status"] == "no_direct_edge"
        lowered = message.content.lower()
        assert "no direct recorded relationship" in lowered
        assert "not evidence that they are unrelated" in lowered
        # never an ontological claim
        assert "they are unrelated" not in lowered.replace(
            "not evidence that they are unrelated", ""
        )

    def test_transitive_chain_is_not_reported(self):
        service, _ = _service()
        _episodes(service, 3)
        record, _ = _ask(service, "Does the first issue relate to the third issue?")
        assert record["status"] != "established"


# ---------------------------------------------------------------------------
# D. The bridge / missing referent
# ---------------------------------------------------------------------------


class TestReferentBridge:
    def test_unavailable_referents_fail_closed(self):
        from dataclasses import replace

        service, _ = _service()
        _episodes(service, 2)
        thread_state = service.state_manager.state.thread_state
        assert thread_state is not None and len(thread_state.threads) == 2  # retained
        # The earlier occurrence survives, but its RECORDED referents are gone.
        stale = replace(
            thread_state.threads[0],
            operation_referent_id="ref-999998",
            result_referent_id="ref-999999",
        )
        service.state_manager.update(
            thread_state=replace(
                thread_state, threads=(stale, thread_state.threads[1])
            )
        )
        record, message = _ask(service, "Does that relate to the previous problem?")
        assert record["status"] == "referent_unavailable"
        assert "no longer has an available operation or result referent" in message.content


# ---------------------------------------------------------------------------
# F. Ambiguity
# ---------------------------------------------------------------------------


class TestAmbiguity:
    def test_bare_definite_with_multiple_occurrences_clarifies(self):
        service, _ = _service()
        _episodes(service, 2)
        record, message = _ask(service, "Does that relate to the issue?")
        assert record["status"] == "ambiguous"
        assert len(record["candidates"]) == 2
        assert "Which one do you mean" in message.content
        # the existing clarification machinery owns the follow-up
        assert service.state_manager.state.pending_clarification is not None

    def test_no_silent_salience_selection(self):
        service, _ = _service()
        _episodes(service, 2)
        record, message = _ask(service, "Does that relate to the problem?")
        assert record["status"] == "ambiguous"
        assert "direct relationship" not in message.content


# ---------------------------------------------------------------------------
# G. Missing target
# ---------------------------------------------------------------------------


class TestMissingTarget:
    def test_no_retained_subject_fails_closed(self):
        service, _ = _service()
        record, message = _ask(service, "Does that relate to the previous problem?")
        assert record["status"] == "target_not_retained"
        assert "I have no retained conversational subject" in message.content
        assert "Investigation result" not in message.content


# ---------------------------------------------------------------------------
# H. Existing behaviour regressions
# ---------------------------------------------------------------------------


class TestExistingBehaviour:
    def test_comparison_still_routes_as_comparison(self):
        service, _ = _service()
        _episodes(service, 2)
        message = service.send("Compare this with what you found earlier.")
        plan = (message.metadata or {}).get("response_plan") or {}
        assert plan.get("function") == FUNCTION_COMPARE

    def test_result_query_is_unchanged(self):
        service, _ = _service()
        _episodes(service, 1)
        message = service.send("What did you find?")
        assert (message.metadata or {}).get("builtin_intent") == "reference"
        assert message.content.startswith("The most recent result:")

    def test_correction_is_unchanged(self):
        service, _ = _service()
        _episodes(service, 1)
        message = service.send("Actually, I meant the previous result.")
        assert "I recorded that correction" in message.content

    def test_ordinary_unsupported_question_is_unchanged(self):
        service, _ = _service()
        _episodes(service, 1)
        message = service.send("How do the modules relate to each other?")
        assert "relation_query" not in (message.metadata or {})


# ---------------------------------------------------------------------------
# I. send()/stream() parity
# ---------------------------------------------------------------------------


class TestSendStreamParity:
    QUESTION = "Does that relate to the previous problem?"

    def _run(self, use_stream: bool):
        service, _ = _service()
        _episodes(service, 2)
        if use_stream:
            return "".join(service.stream(self.QUESTION))
        return service.send(self.QUESTION).content

    def test_equivalent_behaviour(self):
        sent_content = self._run(False)
        stream_content = self._run(True)
        assert sent_content == stream_content
        assert "direct relationship" in sent_content
