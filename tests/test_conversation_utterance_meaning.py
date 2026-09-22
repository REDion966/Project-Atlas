"""L3 — minimal structured utterance meaning tests.

Covers the ``UtteranceMeaning`` value object, the deterministic illocution /
leading-operation / target interpretation, and the two authorized routing
effects (F1 question-vs-approval, F4 leading operation vs later cue).

The frozen lexical contracts (ACTION accepted forms, DEVELOPMENT accepted
forms, objective extraction, ambiguity, reference resolution) are covered by
their own existing suites and are only exercised here where an interaction is
possible.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.conversation.utterance_meaning import (
    MAX_TARGET_CHARS,
    UTTERANCE_MEANING_KEY,
    Illocution,
    Operation,
    UtteranceMeaning,
)


def _meaning(text: str) -> UtteranceMeaning:
    spec = TaskIntake().intake(text)
    payload = spec.context[UTTERANCE_MEANING_KEY]
    meaning = UtteranceMeaning.from_dict(payload)
    assert meaning is not None
    return meaning


def _spec(text: str):
    return TaskIntake().intake(text)


class TestUtteranceMeaningValueObject:
    def test_fields_and_domains(self):
        meaning = UtteranceMeaning(
            illocution=Illocution.REQUEST,
            operation=Operation.DEVELOP,
            target="an email notification capability",
        )
        assert meaning.illocution is Illocution.REQUEST
        assert meaning.operation is Operation.DEVELOP
        assert meaning.target == "an email notification capability"

    def test_defaults_are_bounded(self):
        meaning = UtteranceMeaning()
        assert meaning.illocution is Illocution.STATEMENT
        assert meaning.operation is None
        assert meaning.target is None

    def test_value_semantics_and_immutability(self):
        a = UtteranceMeaning(illocution=Illocution.QUESTION)
        b = UtteranceMeaning(illocution=Illocution.QUESTION)
        assert a == b
        with pytest.raises(dataclasses.FrozenInstanceError):
            a.target = "changed"  # type: ignore[misc]

    def test_to_dict_is_json_safe_and_none_preserving(self):
        meaning = UtteranceMeaning(
            illocution=Illocution.REQUEST, operation=None, target=None
        )
        payload = meaning.to_dict()
        assert payload == {
            "illocution": "request",
            "operation": None,
            "target": None,
        }
        json.dumps(payload)

    def test_from_dict_round_trips(self):
        meaning = UtteranceMeaning(
            illocution=Illocution.REQUEST,
            operation=Operation.ACT,
            target="the verification",
        )
        assert UtteranceMeaning.from_dict(meaning.to_dict()) == meaning

    def test_from_dict_fails_closed(self):
        assert UtteranceMeaning.from_dict("not-a-dict") is None
        assert UtteranceMeaning.from_dict({}) is None
        assert UtteranceMeaning.from_dict({"illocution": "nonsense"}) is None
        # An unknown operation falls back to None rather than raising.
        rebuilt = UtteranceMeaning.from_dict(
            {"illocution": "statement", "operation": "nonsense", "target": None}
        )
        assert rebuilt is not None
        assert rebuilt.operation is None

    def test_from_dict_bounds_the_target(self):
        rebuilt = UtteranceMeaning.from_dict(
            {"illocution": "statement", "operation": None, "target": "y" * 1000}
        )
        assert rebuilt is not None
        assert rebuilt.target is not None
        assert len(rebuilt.target) == MAX_TARGET_CHARS


class TestIllocution:
    @pytest.mark.parametrize(
        "text",
        [
            "Why does Atlas need a development approval step?",
            "How would that capability work?",
            "What is Project Atlas?",
            "Can you explain how your architecture works?",
        ],
    )
    def test_questions_stay_questions(self, text):
        assert _meaning(text).illocution is Illocution.QUESTION

    @pytest.mark.parametrize(
        "text",
        [
            "Add an email notification capability for long-running tasks.",
            "Develop an email notification capability for long-running tasks.",
            "I want Atlas to notify me by email whenever a task takes too long.",
            "I'd like Atlas to support email notifications.",
            "It would be useful to receive an email when a task runs for a long time.",
        ],
    )
    def test_requests_are_requests_regardless_of_frame(self, text):
        # There is no separate "desire" illocution: a non-imperative desire is
        # a request.
        assert _meaning(text).illocution is Illocution.REQUEST

    @pytest.mark.parametrize(
        "text",
        [
            "The email notification capability is still missing.",
            "The analysis is complete.",
            "The verification is running.",
            "The project is long-running.",
        ],
    )
    def test_statements_are_statements(self, text):
        assert _meaning(text).illocution is Illocution.STATEMENT


class TestLeadingOperation:
    @pytest.mark.parametrize(
        ("text", "operation"),
        [
            ("Research how Atlas could improve its language understanding.", Operation.RESEARCH),
            ("Investigate why Atlas cannot answer this question.", Operation.INVESTIGATE),
            ("Develop an email notification capability.", Operation.DEVELOP),
            ("Add an email notification capability.", Operation.DEVELOP),
            ("Run the verification.", Operation.ACT),
            ("Explain how the architecture works.", Operation.EXPLAIN),
            ("Create a report.", Operation.ACT),
            ("Build the module.", Operation.DEVELOP),
        ],
    )
    def test_leading_operation(self, text, operation):
        assert _meaning(text).operation is operation

    def test_statement_has_no_operation(self):
        assert _meaning("The verification is running.").operation is None
        assert _meaning("The analysis is complete.").operation is None


class TestTarget:
    def test_question_target_drops_the_question_frame(self):
        assert _meaning("What is Project Atlas?").target == "Project Atlas"
        assert (
            _meaning("What are your current limitations?").target
            == "your current limitations"
        )

    def test_request_target_drops_the_leading_imperative(self):
        assert (
            _meaning("Add an email notification capability.").target
            == "an email notification capability."
        )
        assert _meaning("Run the verification.").target == "the verification."

    def test_statement_keeps_the_subject(self):
        assert (
            _meaning("The email notification capability is still missing.").target
            == "The email notification capability is still missing."
        )

    def test_target_is_bounded(self):
        spec = _spec("Add " + ("y" * 5_000))
        meaning = UtteranceMeaning.from_dict(spec.context[UTTERANCE_MEANING_KEY])
        assert meaning is not None
        assert meaning.target is not None
        assert len(meaning.target) <= MAX_TARGET_CHARS


class TestF1QuestionVersusApproval:
    def test_question_about_approval_stays_a_question(self):
        spec = _spec("Why does Atlas need a development approval step?")
        assert spec.task_type is TaskType.QUESTION

    def test_question_about_rejection_stays_a_question(self):
        spec = _spec("Why did you reject the proposal?")
        assert spec.task_type is TaskType.QUESTION

    @pytest.mark.parametrize(
        "text",
        [
            "Approve this development proposal.",
            "Authorize the proposed change.",
            "Examine the proposal and approve it.",
            "Approve the proposal that came from the investigation.",
            "approve this proposal",
            "approve it",
            "noted, approve it",
            "approve",
        ],
    )
    def test_explicit_approval_instructions_are_unchanged(self, text):
        assert _spec(text).task_type is TaskType.APPROVAL

    def test_explicit_rejection_instruction_is_unchanged(self):
        assert _spec("reject the proposal").task_type is TaskType.REJECTION_REQUEST


class TestF4LeadingOperationVersusLaterCue:
    def test_research_is_not_development(self):
        spec = _spec("Research how Atlas could improve its language understanding.")
        assert spec.task_type is TaskType.INFORMATION_REQUEST

    def test_investigation_remains_investigation(self):
        spec = _spec("Investigate why Atlas cannot answer this question.")
        assert spec.task_type is TaskType.INVESTIGATION_REQUEST

    @pytest.mark.parametrize(
        "text",
        [
            "Add a capability for scheduled follow-ups.",
            "Develop the capability.",
            "Rebuild the module.",
            "Build a module that tracks long-running tasks.",
            "Improve Atlas's ability to understand follow-up questions.",
            "Create a module for scheduled follow-ups.",
            "Modify the module.",
            "I want Atlas to add an email notification capability for long-running tasks.",
        ],
    )
    def test_explicit_development_is_unchanged(self, text):
        assert _spec(text).task_type is TaskType.DEVELOPMENT_REQUEST


class TestL3Attachment:
    def test_meaning_travels_on_the_bounded_context_channel(self):
        spec = _spec("Add an email notification capability.")
        payload = spec.context[UTTERANCE_MEANING_KEY]
        assert payload["illocution"] == "request"
        assert payload["operation"] == "develop"

    def test_task_spec_serialization_stays_json_safe(self):
        spec = _spec("Research how Atlas could improve its language understanding.")
        json.dumps(spec.to_dict())

    def test_meaning_is_present_for_every_deterministic_spec(self):
        # Degenerate and casual turns still produce a bounded meaning.
        for text in ("", "...", "Hello Atlas."):
            spec = _spec(text)
            assert UTTERANCE_MEANING_KEY in spec.context

    def test_determinism(self):
        for text in (
            "Research how Atlas could improve its language understanding.",
            "Why does Atlas need a development approval step?",
            "Add an email notification capability for long-running tasks.",
        ):
            a = _spec(text)
            b = _spec(text)
            assert a.context[UTTERANCE_MEANING_KEY] == b.context[UTTERANCE_MEANING_KEY]
            assert a.task_type is b.task_type


class _FailingAI:
    """No provider: the deterministic path must stand alone."""

    def chat(self, prompt, routing_context=None):
        raise RuntimeError("No AI available")

    def stream_chat(self, prompt, routing_context=None):
        def _gen():
            raise RuntimeError("No AI available")
            yield ""  # pragma: no cover

        return _gen()


def _service():
    from atlas.conversation.builtin_response import BuiltinResponseService
    from atlas.conversation.conversation_service import ConversationService

    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
    )


_APPROVAL_HANDLER_MARKER = "no development proposal awaiting approval"


class TestF1ThroughTheConversationPath:
    """The classification gate is the only thing keeping a question out of
    approval handling, so assert the behaviour end to end as well. The approval
    handler marks its own turns with ``metadata["approval"]``."""

    def test_question_about_approval_never_reaches_approval_handling(self):
        message = _service().send("Why does Atlas need a development approval step?")
        assert message.metadata.get("approval") is None
        assert _APPROVAL_HANDLER_MARKER not in message.content.lower()

    def test_explicit_approval_still_reaches_approval_handling(self):
        message = _service().send("approve this proposal")
        # The approval handler owns this turn (it refuses for its own reasons).
        assert isinstance(message.metadata.get("approval"), dict)
