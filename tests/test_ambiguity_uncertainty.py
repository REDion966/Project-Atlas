"""L6 — ambiguity / uncertainty handling tests (no provider).

Validated limitation: Atlas's deterministic clarifications *are* its
ambiguity/uncertainty handling, but the outstanding question was never
recorded. ``ConversationState.pending_question`` — documented as "Question
Atlas is currently waiting for an answer to" and already consumed by the
bounded reference patterns (``the question`` / ``my question``) — had no
producer, so the uncertainty Atlas surfaced vanished with the reply.

The fix records the questions actually asked as a bounded, deterministic
pending-question value. Nothing is guessed, no answer is invented, no
authority is created, and the clarification replies themselves are unchanged.

All tests are pure/deterministic. No provider network calls are made.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import (
    ConversationService,
    _MAX_PENDING_QUESTION_CHARS,
)
from atlas.conversation.entity_identification import (
    IDENTIFIED_ENTITIES_KEY,
    EntityCatalog,
)
from atlas.conversation.task_intake import AmbiguityReport, TaskIntake, TaskType
from atlas.conversation.turn_meaning import TurnMeaning

CATALOG = EntityCatalog.from_names({"capability": ["code_inspector"]})

CONTINUATION_STATE = {"current_task": "task-1", "current_investigation": "inv-1"}
AMBIGUOUS_TEXT = "continue with that"

REFERENCE_AMBIGUITY = (
    "Multiple plausible continuation referents: current_task, "
    "current_investigation. Clarification required."
)
INTAKE_QUESTIONS = (
    "What does the ambiguous reference refer to?; "
    "What outcome would tell you this is done?"
)
FALLBACK_QUESTION = "What outcome or detail would tell me this is done?"

RUN_PREAMBLE = "I need a bit more detail before I can run this."
DEV_PREAMBLE = (
    "I need a bit more detail before I can prepare this as a governed "
    "development request."
)


class _FailingAI:
    def chat(self, prompt, routing_context=None):
        raise RuntimeError("No AI available")

    def stream_chat(self, prompt, routing_context=None):
        def _g():
            raise RuntimeError("No AI available")
            yield ""  # pragma: no cover

        return _g()


def _service(seed=None, orchestration_resolver=None, catalog=CATALOG):
    service = ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        entity_catalog=catalog,
        orchestration_resolver=orchestration_resolver,
    )
    if seed:
        service.state_manager.update(**seed)
    return service


def _evidence(service: ConversationService, text: str):
    spec = service._intake(text, len(service.conversation.messages))
    spec = service._apply_entity_identification(spec, text)
    out_spec, _ = service._apply_reference_resolution(spec, text)
    return out_spec.context.get("resolved_reference")


class TestPendingQuestionRecording(unittest.TestCase):
    """Deterministic clarifications preserve the uncertainty they surface."""

    def test_reference_ambiguity_records_the_pending_question(self):
        service = _service(CONTINUATION_STATE)
        service.send(AMBIGUOUS_TEXT)
        self.assertEqual(
            service.state_manager.state.pending_question, REFERENCE_AMBIGUITY
        )

    def test_information_request_ambiguity_records_the_pending_question(self):
        """Previously this turn's whole uncertainty block was empty."""
        service = _service({"current_investigation": "inv-1", "latest_result": "res-1"})
        spec = service._intake("what did you find", 0)
        self.assertEqual(spec.ambiguity.to_dict()["ambiguities"], [])
        service.send("what did you find")
        self.assertEqual(
            service.state_manager.state.pending_question,
            "Multiple plausible findings referents: current_investigation, "
            "latest_result. Clarification required.",
        )

    def test_development_clarification_records_the_pending_question(self):
        service = _service()
        service.send("Add a new capability for it")
        self.assertEqual(service.state_manager.state.pending_question, INTAKE_QUESTIONS)

    def test_orchestration_ambiguity_gate_records_the_pending_question(self):
        service = _service(orchestration_resolver=lambda spec, ctx: None)
        service.send("Run it")
        self.assertEqual(service.state_manager.state.pending_question, INTAKE_QUESTIONS)

    def test_unresolved_orchestration_target_records_the_fallback_question(self):
        service = _service(orchestration_resolver=lambda spec, ctx: None)
        message = service.send("Search the repository for the runtime coordinator")
        self.assertIn(RUN_PREAMBLE, message.content)
        self.assertEqual(
            service.state_manager.state.pending_question, FALLBACK_QUESTION
        )

    def test_determined_turn_records_nothing(self):
        service = _service()
        service.send("What does code_inspector do?")
        self.assertIsNone(service.state_manager.state.pending_question)

    def test_insufficient_evidence_records_nothing(self):
        service = _service()
        service.send("Can you check it?")
        self.assertIsNone(service.state_manager.state.pending_question)

    def test_unsupported_turn_records_nothing(self):
        service = _service()
        service.send("asdf qwerty zzz")
        self.assertIsNone(service.state_manager.state.pending_question)

    def test_resolved_reference_records_nothing(self):
        service = _service({"current_task": "task-1"})
        self.assertEqual(
            _evidence(service, AMBIGUOUS_TEXT),
            {"field": "current_task", "value": "task-1"},
        )
        self.assertIsNone(service.state_manager.state.pending_question)

    def test_recorded_value_is_bounded(self):
        long_question = "why " * 400
        spec = replace(
            TaskIntake().intake("Add a new capability for it"),
            ambiguity=AmbiguityReport(clarification_questions=(long_question,)),
        )
        service = _service()
        service._intake = lambda text, history_length=0: spec
        service.send("Add a new capability for it")
        pending = service.state_manager.state.pending_question
        self.assertTrue(pending.endswith("..."))
        self.assertLessEqual(len(pending), _MAX_PENDING_QUESTION_CHARS + 3)
        self.assertTrue(long_question.startswith(pending[:-3]))

    def test_recording_is_deterministic(self):
        values = set()
        for _ in range(10):
            service = _service(CONTINUATION_STATE)
            service.send(AMBIGUOUS_TEXT)
            values.add(service.state_manager.state.pending_question)
        self.assertEqual(values, {REFERENCE_AMBIGUITY})

    def test_send_and_stream_record_the_same_value(self):
        sent_service = _service(CONTINUATION_STATE)
        sent = sent_service.send(AMBIGUOUS_TEXT).content
        streamed_service = _service(CONTINUATION_STATE)
        chunks = list(streamed_service.stream(AMBIGUOUS_TEXT))
        self.assertEqual("".join(chunks), sent)
        self.assertEqual(
            streamed_service.state_manager.state.pending_question,
            sent_service.state_manager.state.pending_question,
        )

    def test_recording_preserves_other_state_fields(self):
        service = _service(CONTINUATION_STATE)
        before = service.state_manager.state
        service.send(AMBIGUOUS_TEXT)
        after = service.state_manager.state
        self.assertIsNot(after, before)
        self.assertEqual(after.current_task, "task-1")
        self.assertEqual(after.current_investigation, "inv-1")
        self.assertEqual(after.current_subject, before.current_subject)
        self.assertEqual(after.turn_id, before.turn_id)


class TestUncertaintyReachability(unittest.TestCase):
    """The recorded uncertainty is reachable through existing machinery."""

    def test_pending_question_becomes_referenceable(self):
        service = _service(CONTINUATION_STATE)
        service.send(AMBIGUOUS_TEXT)
        self.assertEqual(
            _evidence(service, "the question"),
            {"field": "pending_question", "value": REFERENCE_AMBIGUITY},
        )

    def test_my_question_also_resolves(self):
        service = _service()
        service.send("Add a new capability for it")
        self.assertEqual(
            _evidence(service, "my question"),
            {"field": "pending_question", "value": INTAKE_QUESTIONS},
        )

    def test_reachability_is_fail_closed_without_a_clarification(self):
        service = _service(CONTINUATION_STATE)
        self.assertIsNone(_evidence(service, "the question"))
        service.send("What does code_inspector do?")
        self.assertIsNone(_evidence(service, "the question"))

    def test_reference_resolution_stays_evidence_only(self):
        service = _service(CONTINUATION_STATE)
        service.send(AMBIGUOUS_TEXT)
        text = "the question"
        spec = service._intake(text, len(service.conversation.messages))
        spec = service._apply_entity_identification(spec, text)
        out_spec, response = service._apply_reference_resolution(spec, text)
        self.assertIs(out_spec.task_type, spec.task_type)
        self.assertEqual(out_spec.needs_clarification, spec.needs_clarification)
        self.assertEqual(out_spec.confidence, spec.confidence)
        self.assertIsNone(response)
        self.assertEqual(
            out_spec.context["resolved_reference"],
            {"field": "pending_question", "value": REFERENCE_AMBIGUITY},
        )


class TestClarificationContractPreserved(unittest.TestCase):
    """Existing clarification behaviour is unchanged."""

    def test_reference_ambiguity_message_unchanged(self):
        service = _service(CONTINUATION_STATE)
        message = service.send(AMBIGUOUS_TEXT)
        self.assertEqual(
            message.content, f"{RUN_PREAMBLE}\n- {REFERENCE_AMBIGUITY}"
        )

    def test_development_clarification_message_unchanged(self):
        service = _service()
        message = service.send("Add a new capability for it")
        self.assertEqual(
            message.content,
            f"{DEV_PREAMBLE}\n"
            "- What does the ambiguous reference refer to?\n"
            "- What outcome would tell you this is done?",
        )

    def test_routing_spec_is_preserved_on_clarification(self):
        """The routing spec stays untouched; the uncertainty is recorded in state."""
        service = _service(CONTINUATION_STATE)
        spec = service._intake(AMBIGUOUS_TEXT, 0)
        out_spec, message = service._apply_reference_resolution(spec, AMBIGUOUS_TEXT)
        self.assertIsNotNone(message)
        self.assertIs(out_spec, spec)
        self.assertFalse(out_spec.needs_clarification)
        self.assertEqual(
            service.state_manager.state.pending_question, REFERENCE_AMBIGUITY
        )

    def test_clarification_grants_no_authority(self):
        service = _service(CONTINUATION_STATE)
        message = service.send(AMBIGUOUS_TEXT)
        self.assertNotIn("execution", message.metadata or {})
        self.assertNotIn("approval", message.metadata or {})
        self.assertEqual(service._active_approval_requests, {})
        self.assertEqual(service._active_proposals, {})

    def test_no_provider_is_used(self):
        service = _service(CONTINUATION_STATE)
        message = service.send(AMBIGUOUS_TEXT)
        self.assertFalse(message.metadata.get("model_used", False))
        self.assertFalse(service.state_manager.state.active_proposal_id)


class TestL0L5Preservation(unittest.TestCase):
    """L0–L5 contracts and behaviour are unaffected."""

    def test_turn_meaning_shape_unchanged(self):
        self.assertEqual(
            set(TurnMeaning.__dataclass_fields__),
            {"intent", "uncertainty", "reference", "source_text", "provenance"},
        )

    def test_l5_subject_carry_forward_unaffected(self):
        service = _service()
        service.send("What does code_inspector do?")
        self.assertEqual(service.state_manager.state.current_subject, "code_inspector")
        self.assertEqual(
            _evidence(service, "Tell me more about it."),
            {"field": "current_subject", "value": "code_inspector"},
        )
        self.assertIsNone(service.state_manager.state.pending_question)

    def test_l4_entity_evidence_unchanged(self):
        service = _service()
        text = "What does code_inspector do?"
        spec = service._intake(text, 0)
        out_spec = service._apply_entity_identification(spec, text)
        self.assertEqual(
            out_spec.context[IDENTIFIED_ENTITIES_KEY],
            [{"name": "code_inspector", "kind": "capability"}],
        )

    def test_l2_whitespace_variant_records_equivalently(self):
        canonical = _service(CONTINUATION_STATE)
        canonical.send(AMBIGUOUS_TEXT)
        variant = _service(CONTINUATION_STATE)
        variant.send("continue   with\tthat")
        self.assertEqual(
            variant.state_manager.state.pending_question,
            canonical.state_manager.state.pending_question,
        )

    def test_l3_classification_unchanged(self):
        service = _service()
        spec = service._intake("Add a new capability for it", 0)
        self.assertIs(spec.task_type, TaskType.DEVELOPMENT_REQUEST)
        self.assertTrue(spec.needs_clarification)
        message = service.send("Add a new capability for it")
        self.assertIn(DEV_PREAMBLE, message.content)
        self.assertIsNone(service.state_manager.state.active_proposal_id)
        self.assertIsNone(service.state_manager.state.current_task)


if __name__ == "__main__":
    unittest.main()
