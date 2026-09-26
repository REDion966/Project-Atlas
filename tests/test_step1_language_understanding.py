"""Step 1 — Language & cognitive understanding (evidence contract).

Covers the bounded Step 1 additions on top of the existing G1 NLU architecture:

* the extended :class:`SemanticFrame` structured meaning (arguments/reference);
* the assistance-framing fix (a capability verb bound to an object is a request
  for help, not a capability-inventory question);
* the punctuation/formatting classification-invariance contract;
* frame/floor acknowledgement consistency;
* the OPTIONAL model-assisted intent parser (untrusted, fail-closed, governed);
* deterministic fallback and governance preservation.

No provider is contacted anywhere in this module.
"""

from __future__ import annotations

import json

import pytest

from atlas.conversation import semantic_frame as sf
from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.model_intent_parser import ModelIntentParser
from atlas.conversation.task_intake import (
    MODEL_PROPOSABLE_TASK_TYPES,
    TaskIntake,
    TaskType,
)


def _intent(text: str) -> object:
    builtin = BuiltinResponseService()
    classified = builtin._classify(text, TaskIntake().intake(text), None)
    return classified[0] if isinstance(classified, tuple) else classified


# ---------------------------------------------------------------------------
# 1. Structured meaning
# ---------------------------------------------------------------------------


class TestStructuredMeaning:
    def test_arguments_and_reference_are_attached(self):
        frame = sf.interpret("Tell me more about the memory architecture.")
        assert frame.subject  # bounded entity slot
        assert ("subject", frame.subject) in frame.arguments
        assert frame.reference == "that" or frame.reference == ""

    def test_reference_cue_is_recorded_for_a_bounded_reference(self):
        frame = sf.interpret("Tell me more about that.")
        assert frame.reference in ("that", "this", "it")

    def test_concept_is_exposed_as_an_argument(self):
        frame = sf.interpret("How does your memory architecture work?")
        assert frame.concept == "architecture"
        assert ("concept", "architecture") in frame.arguments

    def test_to_dict_is_json_safe_and_carries_the_new_fields(self):
        frame = sf.interpret("Can you help me with scheduling?")
        payload = frame.to_dict()
        json.dumps(payload)
        assert "arguments" in payload and "reference" in payload

    def test_structured_meaning_is_deterministic(self):
        first = sf.interpret("What about the previous result?")
        second = sf.interpret("What about the previous result?")
        assert first == second


# ---------------------------------------------------------------------------
# 2. Assistance framing (no capability-inventory over-match)
# ---------------------------------------------------------------------------


class TestAssistanceFraming:
    @pytest.mark.parametrize(
        "text",
        (
            "Can you help me with scheduling?",
            "Could you help me with the memory architecture?",
            "Can you support the loader?",
        ),
    )
    def test_assistance_request_is_not_capability_inventory(self, text):
        frame = sf.interpret(text)
        assert frame.domain is not sf.SemanticDomain.CAPABILITIES
        assert _intent(text) != "capabilities"

    @pytest.mark.parametrize(
        "text",
        (
            "What can you do?",
            "What can you help with?",
            "What's within your capabilities?",
            "Tell me what you're able to handle.",
        ),
    )
    def test_genuine_capability_questions_are_preserved(self, text):
        assert _intent(text) in ("help", "capabilities")


# ---------------------------------------------------------------------------
# 3. Punctuation / formatting invariance
# ---------------------------------------------------------------------------


class TestPunctuationInvariance:
    @pytest.mark.parametrize(
        "variant",
        (
            "What, can you do?",
            "What can you do?!",
            "What  can  you  do?",
            "what can you do???",
        ),
    )
    def test_capability_usage_question_variants_are_consistent(self, variant):
        baseline = _intent("What can you do?")
        assert baseline == "help"
        assert _intent(variant) == baseline

    @pytest.mark.parametrize(
        "variant",
        ("What, can you do?", "What can you do?!"),
    )
    def test_frame_domain_is_punctuation_insensitive(self, variant):
        assert sf.interpret(variant).domain is sf.SemanticDomain.CAPABILITIES

    def test_punctuation_insensitive_helper_is_deterministic(self):
        from atlas.conversation.builtin_response import _punctuation_insensitive

        assert _punctuation_insensitive("What, can you do?") == "what can you do"
        assert _punctuation_insensitive("What, can you do?") == _punctuation_insensitive(
            "what  can  you  do"
        )


# ---------------------------------------------------------------------------
# 4. Acknowledgement consistency (frame vs deterministic floor)
# ---------------------------------------------------------------------------


class TestAcknowledgementConsistency:
    @pytest.mark.parametrize(
        "text", ("That makes sense.", "Got it, thanks.", "Thanks, that helps.")
    )
    def test_frame_and_floor_agree_on_acknowledgement(self, text):
        assert sf.interpret(text).role is sf.SemanticRole.ACKNOWLEDGEMENT
        assert _intent(text) == "acknowledgement"

    def test_instruction_after_acknowledgement_is_not_an_acknowledgement(self):
        text = "ok, now investigate the memory architecture"
        assert sf.interpret(text).role is not sf.SemanticRole.ACKNOWLEDGEMENT


# ---------------------------------------------------------------------------
# 5. Model-assisted intent parser (optional, untrusted, fail-closed)
# ---------------------------------------------------------------------------


def _model_returning(payload_text):
    return lambda prompt: payload_text


class TestModelIntentParser:
    def test_disabled_by_default(self):
        assert ModelIntentParser().parse("please sort out the backlog", {}) is None

    def test_only_consulted_for_deterministically_untyped_turns(self):
        parser = ModelIntentParser(model=_model_returning('{"task_type": "action_request"}'))
        # Deterministically typed turns are never re-litigated.
        assert parser.parse("make it so", {}) is None
        assert parser.parse("Can you help me with scheduling?", {}) is None
        # A bare greeting is too small to be worth a model call.
        assert parser.parse("hello there", {}) is None

    def test_fires_for_a_substantive_untyped_turn(self):
        parser = ModelIntentParser(
            model=_model_returning(
                '{"task_type": "action_request", "intent": "tidy the backlog", '
                '"goal": "tidy the backlog"}'
            )
        )
        parsed = parser.parse("please sort out the scheduling mess", {})
        assert parsed == {
            "task_type": "action_request",
            "intent": "tidy the backlog",
            "goal": "tidy the backlog",
        }

    def test_accepts_ai_response_shape(self):
        class _Resp:
            text = '{"task_type": "information_request", "intent": "x"}'

        parser = ModelIntentParser(model=lambda prompt: _Resp())
        assert parser.parse("please get me the current figures", {})["task_type"] == (
            "information_request"
        )

    @pytest.mark.parametrize(
        "raw",
        (
            "sure! here you go: {\"task_type\": \"action_request\"}",  # prose-wrapped
            "```json\n{\"task_type\": \"action_request\"}\n```",  # markdown fence
            "not json at all",
            '["action_request"]',
            '{"task_type": "action_request", "code": "os.system(...)"}',  # extra key
        ),
    )
    def test_malformed_or_extra_keys_fail_closed(self, raw):
        parser = ModelIntentParser(model=_model_returning(raw))
        assert parser.parse("please sort out the scheduling mess", {}) is None

    def test_model_exception_fails_closed(self):
        def boom(prompt):
            raise RuntimeError("no model")

        assert ModelIntentParser(model=boom).parse("please sort out the mess", {}) is None

    @pytest.mark.parametrize(
        "governed_type",
        ("approval", "execution_request", "rejection_request", "planning_request",
         "recovery_request", "autonomy_request"),
    )
    def test_model_may_not_propose_governance_task_types(self, governed_type):
        parser = ModelIntentParser(
            model=_model_returning(
                '{"task_type": "' + governed_type + '", "intent": "do it"}'
            )
        )
        # The adapter refuses the governed type...
        parsed = parser.parse("please sort out the scheduling mess", {})
        assert parsed is None or "task_type" not in parsed
        # ...and the sanitizer independently refuses it.
        spec = TaskIntake(parser=parser).intake("please sort out the scheduling mess")
        assert spec.task_type is not TaskType.APPROVAL
        assert spec.task_type.value not in (
            "approval",
            "execution_request",
            "rejection_request",
            "planning_request",
            "recovery_request",
            "autonomy_request",
        )

    def test_allowlist_contains_no_governance_types(self):
        assert "approval" not in MODEL_PROPOSABLE_TASK_TYPES
        assert "execution_request" not in MODEL_PROPOSABLE_TASK_TYPES
        assert "autonomy_request" not in MODEL_PROPOSABLE_TASK_TYPES


# ---------------------------------------------------------------------------
# 6. Deterministic fallback / model independence
# ---------------------------------------------------------------------------


class TestDeterministicFallback:
    def test_default_intake_is_deterministic_and_verified(self):
        spec = TaskIntake().intake("please sort out the scheduling mess")
        assert spec.source == "deterministic"
        assert spec.verified is True
        assert spec.model_metadata == {}

    def test_disabled_parser_keeps_deterministic_provenance(self):
        spec = TaskIntake(parser=ModelIntentParser()).intake("please sort out the mess")
        assert spec.source == "deterministic"
        assert spec.verified is True

    def test_model_fields_are_untrusted_and_bounded(self):
        parser = ModelIntentParser(
            model=_model_returning(
                '{"task_type": "action_request", "intent": "  tidy  the backlog  "}'
            )
        )
        spec = TaskIntake(parser=parser).intake("please sort out the scheduling mess")
        assert spec.source == "model_assisted"
        assert spec.verified is False
        assert len(spec.intent) <= 400
