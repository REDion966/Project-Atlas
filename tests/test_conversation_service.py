"""
Tests for Atlas Conversation Service.
"""

import unittest

from atlas.ai.ai_manager import AIManager
from atlas.conversation.conversation_service import ConversationService


class TestConversationService(unittest.TestCase):

    def test_send_returns_message(self):
        """Conversation service should return an assistant message."""

        # Initialize AI
        manager = AIManager()

        manager.initialize(
            provider="Mock Provider",
            model="atlas-mock-v1",
            timeout=300,
        )

        # Create conversation service
        service = ConversationService(
            manager.service
        )

        # Send message
        response = service.send("Hello Atlas")

        # Verify response
        self.assertEqual(
            response.role,
            "assistant",
        )

        self.assertTrue(
            len(response.content) > 0
        )


if __name__ == "__main__":
    unittest.main()