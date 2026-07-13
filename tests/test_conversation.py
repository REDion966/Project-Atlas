"""
Tests for Atlas Conversation.
"""

import unittest

from atlas.conversation.conversation import Conversation
from atlas.conversation.message import Message


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


if __name__ == "__main__":
    unittest.main()