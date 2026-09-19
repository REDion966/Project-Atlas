"""L10 — evidence-driven expansion tests (no provider contacted).

L9 (the completed end-to-end validation) reported a bounded set of
FUTURE/L10 candidates. Each was re-reproduced against the current source and
classified (see the L10 report). Exactly three passed the evidence gate and
are implemented here — all as *additions to existing deterministic
vocabularies*, with no new language framework and no provider:

1. Capability/status synonym recognition (phrases for capabilities Atlas
   already answers): "Can you tell me what you're able to do?",
   "what's going on right now".
2. Conversation-topic recall phrased through "remember"
   ("Do you remember what we discussed?"), which previously fell through to a
   knowledge-store search for the literal string "what discussed".
3. A bounded, whole-turn casual acknowledgement surface
   ("thanks", "thanks, that helps", "ok", "perfect, cheers",
   "nice one, thank you very much", "sorry, my mistake") which previously
   received the "I cannot answer that conversationally" refusal.

Every expansion is negative-tested for overmatch: an acknowledgement that
carries an instruction, a mention of the same words inside a request, and the
previously supported surfaces must all keep their existing behavior.
"""

from __future__ import annotations

import unittest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.kernel.atlas import Atlas


class _FailingAI:
    """Any provider contact is a failure."""

    def chat(self, prompt, routing_context=None):
        raise RuntimeError("provider must not be contacted")

    def stream_chat(self, prompt, routing_context=None):
        def _generator():
            raise RuntimeError("provider must not be contacted")
            yield ""  # pragma: no cover

        return _generator()


def _service(seed: dict | None = None) -> ConversationService:
    service = ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
    )
    if seed:
        service.state_manager.update(**seed)
    return service


def _intent(message) -> object:
    return (message.metadata or {}).get("builtin_intent")


ACKNOWLEDGEMENT_PHRASES = (
    ("thanks!", "thanks"),
    ("thanks, that helps", "thanks"),
    ("perfect, cheers", "thanks"),
    ("nice one, thank you very much", "thanks"),
    ("thank you very much", "thanks"),
    ("ok", "acknowledged"),
    ("got it", "acknowledged"),
    ("sorry, my mistake", "acknowledged"),
)

# Turns that merely *contain* acknowledgement words, or add an instruction.
NOT_ACKNOWLEDGEMENTS = (
    ("ok, now investigate the memory architecture", TaskType.INVESTIGATION_REQUEST),
    ("perfect, please investigate the memory architecture", TaskType.INVESTIGATION_REQUEST),
    ("thanks, what can you do?", TaskType.QUESTION),
    ("okay so what's the status?", TaskType.QUESTION),
    ("noted, approve it", TaskType.APPROVAL),
    ("I want to thank the team for their work", TaskType.CONVERSATION),
)


class TestEvidencedRecognitionExpansions(unittest.TestCase):
    """Synonym recognition for capabilities Atlas already answers."""

    def test_capability_synonym_reaches_capabilities(self):
        for text in (
            "Can you tell me what you're able to do?",
            "what you're able to do",
            "what you are able to do",
        ):
            with self.subTest(text=text):
                message = _service().send(text)
                self.assertEqual(_intent(message), "capabilities")

    def test_status_synonym_reaches_status(self):
        for text in ("what's going on right now", "what's going on"):
            with self.subTest(text=text):
                message = _service().send(text)
                self.assertEqual(_intent(message), "status")

    def test_topic_recall_through_remember(self):
        message = _service(
            seed={"current_investigation": "Investigate the memory architecture"}
        ).send("Do you remember what we discussed?")
        self.assertEqual(_intent(message), "conversation_recall")
        self.assertEqual((message.metadata or {}).get("recall_source"), "topic")
        self.assertIn("Investigate the memory architecture", message.content)

    def test_topic_recall_without_candidate_stays_fail_closed(self):
        # No prior subject: the bounded topic recall declines and the existing
        # store-recall path applies unchanged (no invented answer).
        message = _service().send("Do you remember what we discussed?")
        self.assertNotEqual(_intent(message), "conversation_recall")

    def test_canonical_surfaces_are_unchanged(self):
        expectations = {
            "hello": "greeting",
            "help": "help",
            "who are you?": "identity",
            "what capabilities do you have": "capabilities",
            "status": "status",
            "what commands can I use": "commands",
            "what can you do?": "help",
            # Status phrasings must stay status: this is why the
            # investigation-verb paraphrase candidate was rejected.
            "look into the status": "status",
            "take a look at the status": "status",
        }
        for text, intent in expectations.items():
            with self.subTest(text=text):
                self.assertEqual(_intent(_service().send(text)), intent)

    def test_new_recognition_does_not_contact_provider(self):
        service = _service(
            seed={"current_investigation": "Investigate the memory architecture"}
        )
        for text in (
            "Can you tell me what you're able to do?",
            "what's going on right now",
            "Do you remember what we discussed?",
            "thanks!",
            "ok",
        ):
            with self.subTest(text=text):
                message = service.send(text)
                self.assertIs((message.metadata or {}).get("model_used"), False)


class TestAcknowledgementSurface(unittest.TestCase):
    def test_evidenced_acknowledgements_are_answered(self):
        for text, detail in ACKNOWLEDGEMENT_PHRASES:
            with self.subTest(text=text):
                message = _service().send(text)
                self.assertEqual(_intent(message), "acknowledgement")
                self.assertIs((message.metadata or {}).get("model_used"), False)
                self.assertTrue(message.content)
                self.assertNotIn("cannot answer that conversationally", message.content)
                if detail == "thanks":
                    self.assertIn("You're welcome", message.content)
                else:
                    self.assertIn("no action taken", message.content)

    def test_acknowledgement_is_whole_turn_only(self):
        for text, expected in NOT_ACKNOWLEDGEMENTS:
            with self.subTest(text=text):
                spec = TaskIntake().intake(text)
                self.assertEqual(spec.task_type, expected)
                self.assertNotEqual(_intent(_service().send(text)), "acknowledgement")

    def test_acknowledgement_does_not_trigger_any_action(self):
        service = _service()
        before = service.state_manager.state
        message = service.send("thanks, that helps")
        self.assertEqual(_intent(message), "acknowledgement")
        self.assertIs(service.state_manager.state, before)
        self.assertEqual(len(service.conversation.messages), 2)

    def test_acknowledgement_is_deterministic(self):
        first = _service().send("ok").content
        for _ in range(3):
            self.assertEqual(_service().send("ok").content, first)

    def test_acknowledgement_matches_on_send_and_stream(self):
        sent = _service().send("thanks!")
        stream_service = _service()
        chunks = list(stream_service.stream("thanks!"))
        self.assertEqual("".join(chunks), sent.content)
        self.assertEqual(
            _intent(stream_service.conversation.messages[-1]), "acknowledgement"
        )

    def test_acknowledgement_does_not_hijack_governed_task_types(self):
        # The responder only answers casual task types; a governed spec is
        # never claimed even when the text looks like an acknowledgement.
        spec = TaskIntake().intake("approve it")
        self.assertEqual(spec.task_type, TaskType.APPROVAL)
        self.assertIsNone(
            BuiltinResponseService().respond("thanks", spec=spec)
        )


class TestGovernanceSafetyOfTheExpansion(unittest.TestCase):
    """The expansion must not authorize, reject, execute, or consume state."""

    def test_acknowledgement_does_not_authorize_a_pending_proposal(self):
        atlas = Atlas()
        atlas.start()
        try:
            atlas.chat("Investigate the memory architecture.")
            atlas.chat("Prepare a proposal.")
            pending = atlas._conversation.state_manager.state.pending_approval_id
            self.assertIsNotNone(pending)

            for text in ("ok", "thanks", "got it"):
                with self.subTest(text=text):
                    response = atlas.chat(text)
                    self.assertNotIn("approval", response.metadata or {})
                    self.assertEqual(
                        atlas._conversation.state_manager.state.pending_approval_id,
                        pending,
                    )
        finally:
            atlas.shutdown()

    def test_acknowledgement_does_not_trigger_development(self):
        atlas = Atlas()
        atlas.start()
        try:
            atlas.chat("Summarize the tradeoffs of caching.")
            for text in ("ok", "thanks"):
                with self.subTest(text=text):
                    response = atlas.chat(text)
                    metadata = response.metadata or {}
                    self.assertNotIn("execution", metadata)
                    self.assertNotIn("approval", metadata)
            self.assertIsNone(
                atlas._conversation.state_manager.state.pending_approval_id
            )
        finally:
            atlas.shutdown()

    def test_acknowledgement_does_not_approve_or_reject(self):
        atlas = Atlas()
        atlas.start()
        try:
            atlas.chat("Investigate the memory architecture.")
            atlas.chat("Prepare a proposal.")
            pending = atlas._conversation.state_manager.state.pending_approval_id
            atlas.chat("noted, approve it")  # explicit instruction, not an ack
            after = atlas._conversation.state_manager.state
            self.assertIsNone(after.pending_approval_id)
            self.assertIsNotNone(pending)
        finally:
            atlas.shutdown()

    def test_investigation_wording_still_cannot_authorize(self):
        atlas = Atlas()
        atlas.start()
        try:
            atlas.chat("Investigate the memory architecture.")
            atlas.chat("Prepare a proposal.")
            pending = atlas._conversation.state_manager.state.pending_approval_id
            atlas.chat("Investigate the approval flow.")
            self.assertEqual(
                atlas._conversation.state_manager.state.pending_approval_id, pending
            )
        finally:
            atlas.shutdown()

    def test_previously_rejected_candidates_remain_unsupported(self):
        # Documented non-implemented candidates must not have been "solved"
        # by accident, and must not perform any action.
        service = _service()
        for text in ("Do the thing.", "Fix that.", "handle it"):
            with self.subTest(text=text):
                message = service.send(text)
                self.assertEqual(_intent(message), "unsupported")
                self.assertNotIn("execution", message.metadata or {})
                self.assertNotIn("approval", message.metadata or {})


if __name__ == "__main__":
    unittest.main()
