"""Tests for the Atlas conversation core primitives.

Consolidates the previous single-purpose modules for the `atlas/conversation/`
core data/plumbing classes (``Conversation``, ``ContextManager``, ``History``,
``PromptBuilder``) into one focused module. Test cases are preserved verbatim —
this is a structural consolidation only, no assertions were changed.
"""

import unittest

from atlas.conversation.context import ContextManager
from atlas.conversation.conversation import Conversation
from atlas.conversation.history import History
from atlas.conversation.message import Message
from atlas.conversation.prompt_builder import PromptBuilder


class TestConversation(unittest.TestCase):
    """Tests for the Conversation class."""

    def setUp(self):
        self.conversation = Conversation()

    def test_new_conversation_is_empty(self):
        """A new conversation should contain no messages."""
        self.assertEqual(self.conversation.message_count(), 0)

    def test_add_message(self):
        """Adding a message should increase the message count."""

        message = Message(
            role="user",
            content="Hello Atlas"
        )

        self.conversation.add_message(message)

        self.assertEqual(
            self.conversation.message_count(),
            1
        )

        self.assertEqual(
            self.conversation.messages[0].content,
            "Hello Atlas"
        )

    def test_clear(self):
        """Clearing a conversation should remove all messages."""

        self.conversation.add_message(
            Message(
                role="user",
                content="Hello"
            )
        )

        self.conversation.clear()

        self.assertEqual(
            self.conversation.message_count(),
            0
        )


class TestContextManager(unittest.TestCase):
    """Tests for the conversation ContextManager."""

    def test_build_returns_messages(self):
        conversation = Conversation()

        conversation.add_message(
            Message(
                role="user",
                content="Hello Atlas"
            )
        )

        manager = ContextManager()

        context = manager.build(conversation)

        self.assertEqual(len(context), 1)
        self.assertEqual(context[0].content, "Hello Atlas")


class TestHistory(unittest.TestCase):
    """Tests for the History class."""

    def setUp(self):
        self.history = History()

    def test_new_history_is_empty(self):
        self.assertEqual(self.history.count(), 0)
        self.assertIsNone(self.history.active())

    def test_create_conversation(self):
        conversation = self.history.create("Testing")

        self.assertEqual(self.history.count(), 1)
        self.assertEqual(conversation.title, "Testing")
        self.assertEqual(self.history.active(), conversation)


class TestPromptBuilder(unittest.TestCase):
    """Tests for the PromptBuilder."""

    def test_build_prompt(self):
        builder = PromptBuilder()

        messages = [
            Message(
                role="user",
                content="Hello Atlas"
            )
        ]

        prompt = builder.build(messages)

        self.assertEqual(len(prompt), 1)
        self.assertEqual(prompt[0]["role"], "user")
        self.assertEqual(prompt[0]["content"], "Hello Atlas")


if __name__ == "__main__":
    unittest.main()
