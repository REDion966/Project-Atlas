"""
Tests for Atlas Context Manager.
"""

import unittest

from atlas.conversation.context import ContextManager
from atlas.conversation.conversation import Conversation
from atlas.conversation.message import Message


class TestContextManager(unittest.TestCase):

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


if __name__ == "__main__":
    unittest.main()