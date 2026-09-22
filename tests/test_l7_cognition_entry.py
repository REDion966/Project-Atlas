"""L7 (entry) — bounded cognition-entry eligibility signal.

The deterministic floor's "no answer" outcome (``BUILTIN_INTENT_UNSUPPORTED``)
is the only existing signal that separates "answered deterministically" from
"declined". These tests pin the bounded signal derived from it, and prove that
the signal is DATA only: no turn is delegated to cognition, and every
user-visible value is unchanged.
"""

from __future__ import annotations

from dataclasses import replace

from atlas.conversation.builtin_response import (
    BUILTIN_INTENT_UNSUPPORTED,
    BuiltinResponseService,
)
from atlas.conversation.conversation_service import (
    REASONING_ELIGIBILITY_KEY,
    ConversationService,
    reasoning_eligibility,
)
from atlas.conversation.task_intake import TaskIntake, TaskType


class _FailingAI:
    def chat(self, prompt, routing_context=None):
        raise RuntimeError("no ai")

    def stream_chat(self, prompt, routing_context=None):
        def _gen():
            raise RuntimeError("no ai")
            yield ""  # pragma: no cover

        return _gen()


class _RecordingCognition:
    """Records every cognition call so delegation can be observed."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def process(self, user_input, memory=None, metadata=None, goal=None, turn_meaning=None):
        from atlas.cognition.decision import CognitionDecision

        self.calls.append(user_input)
        return CognitionDecision(action="respond", reasoning="stub", data={})


def _service(cognition=None) -> ConversationService:
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        cognition_api=cognition,
    )


def _signal(service: ConversationService, text: str):
    message = service.send(text)
    return message, (message.metadata or {}).get(REASONING_ELIGIBILITY_KEY)


class TestSignalIsEmittedForUndirectedCasualTurns:
    def test_open_ended_question_is_eligible(self):
        message, signal = _signal(_service(), "What should I work on next?")
        assert signal == {
            "eligible": True,
            "task_type": "question",
            "illocution": "question",
            "operation": None,
        }

    def test_factual_question_is_eligible(self):
        _message, signal = _signal(_service(), "What is Project Atlas?")
        assert signal is not None and signal["eligible"] is True

    def test_capability_desire_request_is_eligible(self):
        _message, signal = _signal(_service(), "I'd like Atlas to support email notifications.")
        assert signal == {
            "eligible": True,
            "task_type": "conversation",
            "illocution": "request",
            "operation": None,
        }

    def test_signal_is_json_safe_and_bounded(self):
        import json

        _message, signal = _signal(_service(), "What should I work on next?")
        assert json.dumps(signal)
        assert set(signal) == {"eligible", "task_type", "illocution", "operation"}


class TestSignalIsAbsentWhenTheFloorAnswered:
    def test_greeting_has_no_signal(self):
        message, signal = _signal(_service(), "Hello Atlas.")
        assert message.metadata.get("builtin_intent") == "greeting"
        assert signal is None

    def test_canned_answer_has_no_signal(self):
        for text, intent in (
            ("What can you do?", "help"),
            ("How are you?", "status"),
            ("who are you", "identity"),
        ):
            message, signal = _signal(_service(), text)
            assert message.metadata.get("builtin_intent") == intent, text
            assert signal is None, text

    def test_statement_is_not_eligible(self):
        # L3 says the user stated something rather than asking for anything.
        message, signal = _signal(_service(), "The project is long-running.")
        assert message.metadata.get("builtin_intent") == BUILTIN_INTENT_UNSUPPORTED
        assert signal is None


class TestSignalIsAbsentForGovernedAndPhaseOwnedTurns:
    def test_governed_types_never_reach_the_floor_or_the_signal(self):
        for text in (
            "Add a capability for scheduled follow-ups.",          # Phase 4
            "Investigate why Atlas cannot answer this question.",  # Phase 3
            "Summarize the tradeoffs of caching.",                 # orchestration
            "Research how Atlas currently handles references.",    # Phase 3
            "approve this proposal",                               # Phase 4/5
        ):
            message, signal = _signal(_service(), text)
            assert REASONING_ELIGIBILITY_KEY not in (message.metadata or {}), text
            assert signal is None, text

    def test_clarification_pending_turn_has_no_signal(self):
        message, signal = _signal(_service(), "Build it.")
        assert REASONING_ELIGIBILITY_KEY not in (message.metadata or {})
        assert signal is None


class TestDelegationRequiresTheSignalAndABoundary:
    """L8-c consumes this signal, so the L7 contract is now: the signal is the
    only thing that can permit delegation, and delegation additionally needs a
    wired cognition boundary."""

    def test_without_a_cognition_boundary_the_floor_stays_terminal(self):
        service = _service(cognition=None)
        message = service.send("What should I work on next?")
        assert message.metadata.get("builtin_intent") == "unsupported"
        assert (message.metadata or {}).get(REASONING_ELIGIBILITY_KEY) is not None

    def test_eligible_turn_is_delegated_when_cognition_is_wired(self):
        cognition = _RecordingCognition()
        service = _service(cognition=cognition)
        service.send("What should I work on next?")
        assert cognition.calls == ["What should I work on next?"]

    def test_ineligible_turn_is_never_delegated(self):
        cognition = _RecordingCognition()
        service = _service(cognition=cognition)
        service.send("Hello Atlas.")
        assert cognition.calls == []


class TestBehaviourIsUnchanged:
    def test_reply_text_is_identical_to_the_bare_floor(self):
        text = "What should I work on next?"
        spec = TaskIntake().intake(text)
        baseline = BuiltinResponseService().respond(
            text, spec=spec, message_count=0, context=None
        )
        message, signal = _signal(_service(), text)
        assert message.content == baseline.content
        assert signal is not None

    def test_existing_metadata_keys_are_untouched(self):
        message, _signal_value = _signal(_service(), "What should I work on next?")
        for key, value in (
            ("builtin_response", True),
            ("builtin_intent", BUILTIN_INTENT_UNSUPPORTED),
            ("model_used", False),
        ):
            assert message.metadata[key] == value

    def test_task_type_and_routing_are_unchanged(self):
        Intake = TaskIntake()
        for text, expected in (
            ("What should I work on next?", TaskType.QUESTION),
            ("I'd like Atlas to support email notifications.", TaskType.CONVERSATION),
            ("Add a capability for scheduled follow-ups.", TaskType.DEVELOPMENT_REQUEST),
            ("Build it.", TaskType.ACTION_REQUEST),
        ):
            assert Intake.intake(text).task_type is expected, text

    def test_signal_is_deterministic_across_services(self):
        first = _signal(_service(), "What should I work on next?")[1]
        second = _signal(_service(), "What should I work on next?")[1]
        assert first == second


class TestPredicateFailClosed:
    def test_absent_spec_has_no_signal(self):
        assert reasoning_eligibility(None, BUILTIN_INTENT_UNSUPPORTED) is None

    def test_answered_outcome_has_no_signal(self):
        spec = TaskIntake().intake("Hello Atlas.")
        assert reasoning_eligibility(spec, "greeting") is None

    def test_clarification_veto_has_no_signal(self):
        spec = TaskIntake().intake("What should I work on next?")
        assert reasoning_eligibility(spec, BUILTIN_INTENT_UNSUPPORTED) is not None
        vetoed = replace(spec, needs_clarification=True)
        assert reasoning_eligibility(vetoed, BUILTIN_INTENT_UNSUPPORTED) is None

    def test_governed_task_type_has_no_signal(self):
        for text in (
            "Add a capability for scheduled follow-ups.",
            "Investigate why Atlas cannot answer this question.",
            "Summarize the tradeoffs of caching.",
        ):
            spec = TaskIntake().intake(text)
            assert reasoning_eligibility(spec, BUILTIN_INTENT_UNSUPPORTED) is None, text

    def test_statement_illocution_has_no_signal(self):
        spec = TaskIntake().intake("The project is long-running.")
        assert reasoning_eligibility(spec, BUILTIN_INTENT_UNSUPPORTED) is None

    def test_absent_or_malformed_l3_block_has_no_signal(self):
        spec = TaskIntake().intake("What should I work on next?")
        without_l3 = replace(
            spec,
            context={
                k: v for k, v in spec.context.items() if k != "utterance_meaning"
            },
        )
        assert reasoning_eligibility(without_l3, BUILTIN_INTENT_UNSUPPORTED) is None
        malformed = replace(
            spec, context={**spec.context, "utterance_meaning": "not-a-dict"}
        )
        assert reasoning_eligibility(malformed, BUILTIN_INTENT_UNSUPPORTED) is None
        unknown_illocution = replace(
            spec,
            context={
                **spec.context,
                "utterance_meaning": {"illocution": "speculation", "operation": None},
            },
        )
        assert (
            reasoning_eligibility(unknown_illocution, BUILTIN_INTENT_UNSUPPORTED)
            is None
        )

    def test_operation_is_preserved_when_present(self):
        spec = TaskIntake().intake("Research how Atlas currently handles references.")
        forced = replace(spec, task_type=TaskType.QUESTION)
        signal = reasoning_eligibility(forced, BUILTIN_INTENT_UNSUPPORTED)
        assert signal is not None
        assert signal["operation"] == "research"
