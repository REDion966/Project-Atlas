"""Phase 3 — bounded, read-only conversational context tests (no provider)."""

from __future__ import annotations

import dataclasses
import unittest
from unittest.mock import MagicMock

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_context import (
    MAX_CONTEXT_CHARS,
    MAX_CONTEXT_TURNS,
    ConversationContext,
    build_conversation_context,
)
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import ConversationState
from atlas.conversation.message import Message
from atlas.conversation.task_intake import TaskIntake


def _messages(count: int) -> list[Message]:
    messages: list[Message] = []
    for index in range(count):
        role = "user" if index % 2 == 0 else "assistant"
        messages.append(Message(role=role, content=f"{role}-{index}"))
    return messages


class TestConversationContextContract(unittest.TestCase):
    def test_constructed_from_history(self):
        ctx = build_conversation_context(_messages(4))
        self.assertIsInstance(ctx, ConversationContext)
        self.assertTrue(ctx.has_history)
        self.assertEqual(len(ctx.recent_turns), 4)
        self.assertEqual(ctx.recent_turns[0].role, "user")
        self.assertEqual(ctx.recent_turns[0].content, "user-0")
        self.assertEqual(ctx.total_messages, 4)

    def test_bounded_to_recent_window(self):
        messages = _messages(MAX_CONTEXT_TURNS + 7)
        ctx = build_conversation_context(messages)
        self.assertEqual(len(ctx.recent_turns), MAX_CONTEXT_TURNS)
        self.assertEqual(ctx.total_messages, MAX_CONTEXT_TURNS + 7)

    def test_older_messages_excluded(self):
        messages = _messages(MAX_CONTEXT_TURNS + 5)
        ctx = build_conversation_context(messages)
        self.assertEqual(
            [turn.content for turn in ctx.recent_turns],
            [message.content for message in messages[-MAX_CONTEXT_TURNS:]],
        )
        self.assertNotIn(
            messages[0].content, [turn.content for turn in ctx.recent_turns]
        )

    def test_recent_user_and_assistant_turns(self):
        ctx = build_conversation_context(_messages(4))
        self.assertEqual(ctx.recent_user_turns, ("user-0", "user-2"))
        self.assertEqual(ctx.recent_assistant_turns, ("assistant-1", "assistant-3"))

    def test_state_is_projected(self):
        state = ConversationState(
            current_investigation="inv-1", latest_result="done"
        )
        ctx = build_conversation_context(_messages(2), state)
        self.assertEqual(ctx.state.current_investigation, "inv-1")
        self.assertEqual(ctx.state.latest_result, "done")

    def test_empty_history_defaults(self):
        ctx = build_conversation_context([], None)
        self.assertEqual(ctx.recent_turns, ())
        self.assertEqual(ctx.total_messages, 0)
        self.assertFalse(ctx.has_history)
        self.assertIsInstance(ctx.state, ConversationState)

    def test_content_is_bounded(self):
        ctx = build_conversation_context(
            [Message(role="user", content="x" * (MAX_CONTEXT_CHARS + 50))]
        )
        self.assertEqual(len(ctx.recent_turns[0].content), MAX_CONTEXT_CHARS)

    def test_context_is_immutable(self):
        ctx = build_conversation_context(_messages(2))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ctx.total_messages = 999  # type: ignore[misc]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ctx.recent_turns[0].content = "changed"  # type: ignore[misc]

    def test_snapshot_survives_source_mutation(self):
        messages = _messages(3)
        ctx = build_conversation_context(messages)
        before = [turn.content for turn in ctx.recent_turns]
        messages.append(Message(role="user", content="late"))
        messages[0] = Message(role="user", content="mutated")
        self.assertEqual([turn.content for turn in ctx.recent_turns], before)
        self.assertEqual(ctx.total_messages, 3)

    def test_to_dict_is_json_safe(self):
        ctx = build_conversation_context(
            _messages(2), ConversationState(latest_result="r")
        )
        payload = ctx.to_dict()
        self.assertEqual(payload["total_messages"], 2)
        self.assertEqual(payload["state"]["latest_result"], "r")


class _RecordingBuiltin(BuiltinResponseService):
    """Builtin that records the context it receives; output is unchanged."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.contexts: list[ConversationContext | None] = []

    def respond(
        self,
        text,
        spec=None,
        session_context=None,
        message_count=None,
        context=None,
    ):
        self.contexts.append(context)
        return super().respond(
            text,
            spec=spec,
            session_context=session_context,
            message_count=message_count,
            context=context,
        )


class TestContextIntegration(unittest.TestCase):
    def _service(self):
        builtin = _RecordingBuiltin()
        service = ConversationService(
            MagicMock(), task_intake=TaskIntake(), builtin_response=builtin
        )
        return service, builtin

    def test_builtin_receives_bounded_context(self):
        service, builtin = self._service()
        for index in range(MAX_CONTEXT_TURNS + 5):
            service.send(f"hello {index}")
        ctx = builtin.contexts[-1]
        self.assertIsInstance(ctx, ConversationContext)
        self.assertEqual(len(ctx.recent_turns), MAX_CONTEXT_TURNS)
        self.assertGreater(ctx.total_messages, MAX_CONTEXT_TURNS)

    def test_snapshot_not_mutated_by_later_turns(self):
        service, builtin = self._service()
        service.send("hello 0")
        first = builtin.contexts[-1]
        before = [turn.content for turn in first.recent_turns]
        self.assertEqual(before, ["hello 0"])
        service.send("hello 1")
        self.assertEqual([turn.content for turn in first.recent_turns], before)
        self.assertEqual(first.total_messages, 1)

    def test_builtin_output_unchanged_with_context(self):
        builtin = BuiltinResponseService()
        plain = builtin.respond("status", message_count=3)
        with_context = builtin.respond(
            "status",
            message_count=3,
            context=build_conversation_context(_messages(2)),
        )
        self.assertIsNotNone(plain)
        self.assertIsNotNone(with_context)
        self.assertEqual(plain.content, with_context.content)
        self.assertEqual(plain.metadata, with_context.metadata)

    def test_casual_turn_does_not_contact_provider(self):
        ai = MagicMock()
        service = ConversationService(
            ai, task_intake=TaskIntake(), builtin_response=BuiltinResponseService()
        )
        message = service.send("hello")
        self.assertTrue(message.metadata.get("builtin_response"))
        self.assertFalse(message.metadata.get("model_used"))
        ai.chat.assert_not_called()
        ai.stream_chat.assert_not_called()

    def test_builtin_does_not_claim_governed_turn_with_context(self):
        builtin = BuiltinResponseService()
        text = "add a new capability to Atlas for scheduling"
        spec = TaskIntake().intake(text)
        self.assertEqual(spec.task_type.value, "development_request")
        self.assertIsNone(
            builtin.respond(
                text, spec=spec, context=build_conversation_context(_messages(2))
            )
        )


if __name__ == "__main__":
    unittest.main()
