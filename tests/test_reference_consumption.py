"""Stage A — consume already-bound contextual evidence (deterministic, no provider).

The deterministic resolver already binds a recognized conversational reference
onto ``TaskSpec.context`` as ``resolved_reference``. This surface proves the
builtin conversational layer now *restates* that already-bound state fact
instead of refusing, while every turn without applicable evidence keeps the
unchanged unsupported behavior.

Nothing here re-resolves, guesses, executes, authorizes, or contacts a model.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from atlas.conversation.builtin_response import (
    BUILTIN_INTENT_REFERENCE,
    _MAX_REFERENCE_CHARS,
    _REFERENCE_LABELS,
    BuiltinResponseService,
)
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationService
from atlas.conversation.task_intake import TaskIntake

RESULT_TEXT = "What about the result?"


class _FailingAI:
    calls = 0

    def chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1
        raise RuntimeError("No AI available")

    def stream_chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1

        def _g():
            raise RuntimeError("No AI available")
            yield ""  # pragma: no cover

        return _g()


def _spec(text: str, reference=None):
    spec = TaskIntake().intake(text)
    if reference is None:
        return spec
    context = dict(spec.context)
    context["resolved_reference"] = reference
    return replace(spec, context=context)


def _service(investigation: bool = False) -> ConversationService:
    _FailingAI.calls = 0
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        investigation_service=InvestigationService() if investigation else None,
    )


class TestReferenceConsumptionUnit(unittest.TestCase):
    """The builtin layer restates only evidence the resolver already bound."""

    def setUp(self) -> None:
        self.svc = BuiltinResponseService()

    def test_resolved_reference_is_restated(self):
        spec = _spec(RESULT_TEXT, {"field": "latest_result", "value": "Finding Alpha"})
        msg = self.svc.respond(RESULT_TEXT, spec=spec)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.metadata["builtin_intent"], BUILTIN_INTENT_REFERENCE)
        self.assertEqual(msg.metadata["reference_field"], "latest_result")
        self.assertFalse(msg.metadata["model_used"])
        self.assertIn("Finding Alpha", msg.content)
        self.assertIn("The most recent result:", msg.content)

    def test_every_consumable_state_field_is_restated(self):
        for field in _REFERENCE_LABELS:
            with self.subTest(field=field):
                spec = _spec(RESULT_TEXT, {"field": field, "value": "value-1"})
                msg = self.svc.respond(RESULT_TEXT, spec=spec)
                self.assertIsNotNone(msg, field)
                self.assertEqual(
                    msg.metadata["builtin_intent"], BUILTIN_INTENT_REFERENCE, field
                )
                self.assertIn("value-1", msg.content, field)

    def test_without_bound_reference_behavior_is_unchanged(self):
        msg = self.svc.respond(RESULT_TEXT, spec=_spec(RESULT_TEXT))
        self.assertIsNotNone(msg)
        self.assertEqual(msg.metadata["builtin_intent"], "unsupported")
        self.assertIn("cannot answer", msg.content)

    def test_contextual_subject_referent_declines(self):
        # ``context_subject`` is a derived contextual referent, not a stored
        # state fact: restating it would assert an identity. Out of scope here.
        spec = _spec("Check that again.", {"field": "context_subject", "value": "x"})
        msg = self.svc.respond("Check that again.", spec=spec)
        self.assertEqual(msg.metadata["builtin_intent"], "unsupported")

    def test_non_content_referent_field_declines(self):
        for field in ("active_proposal_id", "pending_approval_id", "turn_id"):
            with self.subTest(field=field):
                spec = _spec(RESULT_TEXT, {"field": field, "value": "id-1"})
                msg = self.svc.respond(RESULT_TEXT, spec=spec)
                self.assertEqual(msg.metadata["builtin_intent"], "unsupported", field)

    def test_blank_value_declines(self):
        for value in ("", "   ", "\n\t"):
            with self.subTest(value=value):
                spec = _spec(RESULT_TEXT, {"field": "latest_result", "value": value})
                msg = self.svc.respond(RESULT_TEXT, spec=spec)
                self.assertEqual(msg.metadata["builtin_intent"], "unsupported", value)

    def test_non_string_value_declines(self):
        spec = _spec(RESULT_TEXT, {"field": "latest_result", "value": 42})
        msg = self.svc.respond(RESULT_TEXT, spec=spec)
        self.assertEqual(msg.metadata["builtin_intent"], "unsupported")

    def test_malformed_reference_payload_declines(self):
        for payload in ("nope", 7, {"field": "latest_result"}, {"value": "x"}):
            with self.subTest(payload=payload):
                spec = _spec(RESULT_TEXT, payload)
                msg = self.svc.respond(RESULT_TEXT, spec=spec)
                self.assertEqual(msg.metadata["builtin_intent"], "unsupported")

    def test_existing_intents_keep_precedence(self):
        reference = {"field": "latest_result", "value": "Finding Alpha"}
        for text, expected in (
            ("status", "status"),
            ("hello", "greeting"),
            ("What capabilities do you have?", "capabilities"),
            ("who are you", "identity"),
        ):
            with self.subTest(text=text):
                spec = _spec(text, reference)
                msg = self.svc.respond(text, spec=spec)
                self.assertEqual(msg.metadata["builtin_intent"], expected, text)

    def test_governed_turn_is_never_claimed(self):
        spec = _spec(
            "implement the F17 fix for Atlas",
            {"field": "latest_result", "value": "Finding Alpha"},
        )
        self.assertIsNone(
            self.svc.respond("implement the F17 fix for Atlas", spec=spec)
        )

    def test_restatement_is_bounded(self):
        long_value = "x" * (_MAX_REFERENCE_CHARS + 250)
        spec = _spec(RESULT_TEXT, {"field": "latest_result", "value": long_value})
        msg = self.svc.respond(RESULT_TEXT, spec=spec)
        self.assertTrue(msg.content.endswith("..."))
        self.assertLessEqual(len(msg.content), _MAX_REFERENCE_CHARS + 3 + 40)

    def test_restatement_is_deterministic(self):
        spec = _spec(RESULT_TEXT, {"field": "latest_result", "value": "Finding Alpha"})
        first = self.svc.respond(RESULT_TEXT, spec=spec)
        for _ in range(10):
            again = self.svc.respond(RESULT_TEXT, spec=spec)
            self.assertEqual(again.content, first.content)
            self.assertEqual(again.metadata, first.metadata)


class TestReferenceConsumptionEndToEnd(unittest.TestCase):
    """A governed turn's result is consumable by the next casual turn."""

    @staticmethod
    def _after_governed_turn() -> ConversationService:
        service = _service(investigation=True)
        service.send("Investigate the memory architecture.")
        return service

    def test_governed_turn_then_result_reference(self):
        service = self._after_governed_turn()
        recorded = service.state_manager.state.latest_result
        self.assertTrue(recorded)

        message = service.send(RESULT_TEXT)

        self.assertEqual(
            (message.metadata or {}).get("builtin_intent"), BUILTIN_INTENT_REFERENCE
        )
        self.assertEqual(
            (message.metadata or {}).get("reference_field"), "latest_result"
        )
        self.assertIn(recorded, message.content)
        self.assertEqual(_FailingAI.calls, 0, "no provider may be contacted")

    def test_send_and_stream_parity(self):
        sent_service = self._after_governed_turn()
        sent = sent_service.send(RESULT_TEXT)

        streamed_service = self._after_governed_turn()
        chunks = list(streamed_service.stream(RESULT_TEXT))

        self.assertEqual("".join(chunks), sent.content)
        self.assertEqual(
            (streamed_service.conversation.messages[-1].metadata or {}).get(
                "builtin_intent"
            ),
            BUILTIN_INTENT_REFERENCE,
        )

    def test_unsupported_contextual_questions_are_unchanged(self):
        service = self._after_governed_turn()
        for text in (
            "No, I meant the cognition pipeline.",
            "How is the quality of the output?",
            "blorptastic quux",
        ):
            with self.subTest(text=text):
                message = service.send(text)
                self.assertNotEqual(
                    (message.metadata or {}).get("builtin_intent"),
                    BUILTIN_INTENT_REFERENCE,
                    text,
                )
                self.assertIn("cannot answer", message.content, text)

    def test_repeat_uses_read_only_operation_not_subject_restatement(self):
        # Stage C: "Check that again." is a bounded repeat of the most recent
        # governed operation. After a read-only investigation it re-enters the
        # existing handler with the retained operand — it is neither restated
        # as a reference nor left unsupported.
        service = self._after_governed_turn()
        message = service.send("Check that again.")
        self.assertNotEqual(
            (message.metadata or {}).get("builtin_intent"), BUILTIN_INTENT_REFERENCE
        )
        self.assertIsNotNone((message.metadata or {}).get("investigation"))

    def test_reference_answer_grants_no_authority(self):
        service = self._after_governed_turn()
        before = service.state_manager.state
        before_proposals = dict(service._active_proposals)
        before_approvals = dict(service._active_approval_requests)
        self.assertTrue(before_proposals, "the governed turn records its proposal")

        message = service.send(RESULT_TEXT)
        after = service.state_manager.state

        self.assertNotIn("execution", message.metadata)
        self.assertNotIn("approval", message.metadata)
        # Consuming a reference changes nothing governed.
        self.assertEqual(dict(service._active_proposals), before_proposals)
        self.assertEqual(dict(service._active_approval_requests), before_approvals)
        # It restates state; it never rewrites it.
        self.assertEqual(after.latest_result, before.latest_result)
        self.assertEqual(after.current_investigation, before.current_investigation)
        self.assertEqual(after.current_subject, before.current_subject)

    def test_reference_consumption_is_deterministic(self):
        contents = set()
        for _ in range(3):
            service = self._after_governed_turn()
            contents.add(service.send(RESULT_TEXT).content)
        self.assertEqual(len(contents), 1)


class TestResultQualifierAliasesEndToEnd(unittest.TestCase):
    """Bounded result-qualifier aliases ride the existing Stage A path.

    Atlas retains exactly ONE result (``latest_result``), so "previous/last/
    prior result" are bounded aliases to that single value — reference
    coverage, not result-history semantics. When no result is retained the
    qualifier forms fail closed exactly like any other unsupported turn.
    """

    QUALIFIERS = (
        "What about the previous result?",
        "What about the last result?",
        "What about the prior result?",
    )

    def test_qualifier_forms_consumed_after_governed_turn(self):
        service = TestReferenceConsumptionEndToEnd._after_governed_turn()
        recorded = service.state_manager.state.latest_result
        self.assertTrue(recorded)
        for text in self.QUALIFIERS:
            with self.subTest(text=text):
                message = service.send(text)
                self.assertEqual(
                    (message.metadata or {}).get("builtin_intent"),
                    BUILTIN_INTENT_REFERENCE,
                )
                self.assertEqual(
                    (message.metadata or {}).get("reference_field"), "latest_result"
                )
                self.assertIn(recorded, message.content)
        self.assertEqual(_FailingAI.calls, 0, "no provider may be contacted")

    def test_qualifier_forms_fail_closed_without_result(self):
        for text in self.QUALIFIERS:
            with self.subTest(text=text):
                service = _service()  # no governed turn -> no latest_result
                message = service.send(text)
                self.assertNotEqual(
                    (message.metadata or {}).get("builtin_intent"),
                    BUILTIN_INTENT_REFERENCE,
                )
                self.assertIn("cannot answer", message.content)
        self.assertEqual(_FailingAI.calls, 0, "no provider may be contacted")

    def test_qualifier_stream_parity(self):
        sent_service = TestReferenceConsumptionEndToEnd._after_governed_turn()
        streamed_service = TestReferenceConsumptionEndToEnd._after_governed_turn()
        for text in self.QUALIFIERS:
            with self.subTest(text=text):
                sent = sent_service.send(text)
                self.assertEqual("".join(streamed_service.stream(text)), sent.content)

    def test_qualifier_alias_grants_no_authority(self):
        service = TestReferenceConsumptionEndToEnd._after_governed_turn()
        before = service.state_manager.state
        before_proposals = dict(service._active_proposals)
        before_approvals = dict(service._active_approval_requests)
        message = service.send("What about the previous result?")
        self.assertNotIn("execution", message.metadata)
        self.assertNotIn("approval", message.metadata)
        self.assertEqual(dict(service._active_proposals), before_proposals)
        self.assertEqual(dict(service._active_approval_requests), before_approvals)
        after = service.state_manager.state
        self.assertEqual(after.latest_result, before.latest_result)
        self.assertEqual(after.current_investigation, before.current_investigation)


if __name__ == "__main__":
    unittest.main()
