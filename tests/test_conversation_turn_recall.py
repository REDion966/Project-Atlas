"""Phase 5 — bounded deterministic conversational-turn recall tests (no provider)."""

from __future__ import annotations

import unittest

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_context import build_conversation_context
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import ConversationState
from atlas.conversation.message import Message
from atlas.conversation.task_intake import TaskIntake, TaskType

# Distinctive history so tests prove content came from context, not a fixture.
HISTORY = (
    ("user", "Investigate the conversation system."),
    ("assistant", "Finding Alpha"),
    ("user", "Investigate the memory architecture."),
    ("assistant", "Finding Beta"),
)


def _ctx(history, current, state=None):
    messages = [Message(role=role, content=content) for role, content in history]
    messages.append(Message(role="user", content=current))
    return build_conversation_context(messages, state)


class _FailingAI:
    def chat(self, prompt, routing_context=None):
        raise RuntimeError("No AI available")

    def stream_chat(self, prompt, routing_context=None):
        def _g():
            raise RuntimeError("No AI available")
            yield ""  # pragma: no cover

        return _g()


class TestConversationTurnRecall(unittest.TestCase):
    def setUp(self):
        self.svc = BuiltinResponseService()

    def _respond(self, text, state=None, history=HISTORY):
        return self.svc.respond(text, context=_ctx(history, text, state))

    def test_previous_user_request_recalled(self):
        for text in (
            "What did I ask earlier?",
            "What did I ask you?",
            "What was my last question?",
            "What did I say previously?",
        ):
            with self.subTest(text=text):
                msg = self._respond(text)
                self.assertEqual(msg.metadata["builtin_intent"], "conversation_recall")
                self.assertEqual(msg.metadata["recall_source"], "user")
                self.assertIn("Investigate the memory architecture.", msg.content)

    def test_recent_assistant_response_recalled(self):
        for text in (
            "What did you just tell me?",
            "What did you say?",
            "What was your previous response?",
        ):
            with self.subTest(text=text):
                msg = self._respond(text)
                self.assertEqual(msg.metadata["builtin_intent"], "conversation_recall")
                self.assertEqual(msg.metadata["recall_source"], "assistant")
                self.assertIn("Finding Beta", msg.content)

    def test_recent_topic_recalled(self):
        for text in ("What did we discuss?", "What were we talking about?"):
            with self.subTest(text=text):
                msg = self._respond(text)
                self.assertEqual(msg.metadata["builtin_intent"], "conversation_recall")
                self.assertEqual(msg.metadata["recall_source"], "topic")
                self.assertIn("Investigate the memory architecture.", msg.content)

    def test_finding_recalled_only_when_deterministically_available(self):
        msg = self._respond(
            "What did we find?", state=ConversationState(latest_result="Finding Alpha")
        )
        self.assertEqual(msg.metadata["builtin_intent"], "conversation_recall")
        self.assertEqual(msg.metadata["recall_source"], "finding")
        self.assertIn("Finding Alpha", msg.content)

        without = self._respond("What did we find?")
        self.assertNotEqual(
            without.metadata.get("builtin_intent"), "conversation_recall"
        )
        self.assertNotIn("Finding", without.content)

    def test_no_history_fails_honestly(self):
        for text in (
            "What did we discuss?",
            "What did I ask earlier?",
            "What did you just tell me?",
        ):
            with self.subTest(text=text):
                msg = self._respond(text, history=())
                self.assertNotEqual(
                    msg.metadata.get("builtin_intent"), "conversation_recall"
                )
                self.assertNotIn("Investigate", msg.content)

    def test_older_than_bound_not_recalled(self):
        messages = [
            Message(role="user", content="Investigate the early distinctive system."),
            Message(role="assistant", content="Early Finding"),
        ]
        messages.extend(
            Message(role="user", content=f"filler {index}") for index in range(12)
        )
        messages.append(Message(role="user", content="What did I ask earlier?"))
        context = build_conversation_context(messages)
        msg = self.svc.respond("What did I ask earlier?", context=context)
        self.assertEqual(msg.metadata["builtin_intent"], "conversation_recall")
        self.assertNotIn("early distinctive", msg.content)

    def test_recall_does_not_mutate_context(self):
        context = _ctx(HISTORY, "What did I ask earlier?")
        before = context.to_dict()
        self.svc.respond("What did I ask earlier?", context=context)
        self.assertEqual(context.to_dict(), before)

    def test_recall_result_is_immutable_and_data_only(self):
        msg = self._respond("What did I ask earlier?")
        self.assertFalse(msg.metadata.get("model_used"))
        self.assertNotIn("execution", msg.metadata)
        self.assertNotIn("approval", msg.metadata)

    def test_recall_does_not_steal_existing_intents(self):
        checks = (
            ("What can you currently do?", "capabilities"),
            ("status", "status"),
            ("Who are you?", "identity"),
            ("help", "help"),
        )
        for text, intent in checks:
            with self.subTest(text=text):
                msg = self._respond(text)
                self.assertEqual(msg.metadata["builtin_intent"], intent)

    def test_store_recall_remains_distinct_and_unchanged(self):
        for text in (
            "do you remember IsoDate",
            "What did we discover about the investigation system?",
            "Can you remind me what we found?",
        ):
            with self.subTest(text=text):
                msg = self.svc.respond(text)
                self.assertEqual(msg.metadata["builtin_intent"], "recall")
                self.assertNotEqual(msg.metadata.get("recall_source"), "assistant")

    def test_false_positive_near_misses_unsupported(self):
        for text in (
            "What happened yesterday?",
            "Can you check it?",
            "How is the quality of the output?",
        ):
            with self.subTest(text=text):
                msg = self._respond(text)
                self.assertEqual(msg.metadata["builtin_intent"], "unsupported")


class TestTurnRecallClassificationPrecedence(unittest.TestCase):
    def test_recall_with_investigation_noun_not_investigation(self):
        for text in (
            "Do you remember our investigation?",
            "What did I ask earlier?",
        ):
            with self.subTest(text=text):
                self.assertIsNot(
                    TaskIntake().intake(text).task_type,
                    TaskType.INVESTIGATION_REQUEST,
                )

    def test_genuine_investigation_preserved(self):
        for text in (
            "Investigate the conversation system.",
            "Please investigate this problem.",
        ):
            with self.subTest(text=text):
                self.assertIs(
                    TaskIntake().intake(text).task_type,
                    TaskType.INVESTIGATION_REQUEST,
                )


class TestTurnRecallIntegration(unittest.TestCase):
    def _service(self) -> ConversationService:
        return ConversationService(
            _FailingAI(),
            task_intake=TaskIntake(),
            builtin_response=BuiltinResponseService(),
        )

    def test_send_recalls_previous_assistant_turn(self):
        service = self._service()
        service.send("hello")
        message = service.send("What did you just tell me?")
        self.assertEqual(message.metadata.get("builtin_intent"), "conversation_recall")
        self.assertIn("model-independent operating framework", message.content)

    def test_send_and_stream_share_recall(self):
        service = self._service()
        service.send("hello")
        sent = service.send("What did I ask earlier?")
        self.assertEqual(sent.metadata.get("builtin_intent"), "conversation_recall")
        self.assertIn("hello", sent.content)
        chunks = list(service.stream("What did I ask earlier?"))
        self.assertTrue(chunks)
        self.assertIn("hello", chunks[0])

    def test_recall_does_not_mutate_state_manager(self):
        service = self._service()
        service.state_manager.update(current_investigation="inv-1")
        before = service.state_manager.state
        service.send("What did we discuss?")
        self.assertIs(service.state_manager.state, before)

    def test_recall_does_not_trigger_governed_handlers(self):
        service = self._service()
        service.send("hello")
        calls: list[int] = []
        service._maybe_handle_investigation_request = lambda *a, **k: calls.append(1)
        message = service.send("What did I ask earlier?")
        self.assertEqual(calls, [])
        self.assertEqual(message.metadata.get("builtin_intent"), "conversation_recall")
        self.assertNotIn("execution", message.metadata)
        self.assertNotIn("approval", message.metadata)

    def test_recall_is_deterministic(self):
        first_service = self._service()
        first_service.send("hello")
        second_service = self._service()
        second_service.send("hello")
        self.assertEqual(
            first_service.send("What did you just tell me?").content,
            second_service.send("What did you just tell me?").content,
        )

    def test_casual_recall_does_not_contact_provider(self):
        service = self._service()
        service.send("hello")
        service.send("What did I ask earlier?")
        self.assertTrue(True)  # _FailingAI would raise on any provider call


if __name__ == "__main__":
    unittest.main()
