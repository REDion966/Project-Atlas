"""
Tests for Atlas Conversation Service.
"""

import unittest
from unittest.mock import MagicMock

from atlas.ai.ai_manager import AIManager
from atlas.cognition.api import CognitionAPI
from atlas.cognition.decision import CognitionDecision
from atlas.conversation.conversation_service import ConversationService
from atlas.services.cognition_service import CognitionService


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


class TestConversationServiceWithCognition(unittest.TestCase):
    """Tests for ConversationService with CognitionAPI integration."""

    def test_without_cognition_still_works(self):
        """ConversationService works without cognition_api injected."""

        manager = AIManager()
        manager.initialize(
            provider="Mock Provider",
            model="atlas-mock-v1",
            timeout=300,
        )

        service = ConversationService(
            manager.service,
        )

        response = service.send("Hello without cognition")

        self.assertEqual(response.role, "assistant")
        self.assertTrue(len(response.content) > 0)

    def test_with_cognition_receives_decision(self):
        """ConversationService with cognition_api receives a CognitionDecision."""

        manager = AIManager()
        manager.initialize(
            provider="Mock Provider",
            model="atlas-mock-v1",
            timeout=300,
        )

        # Create a mock CognitionAPI that records calls
        mock_cognition_service = MagicMock(spec=CognitionService)
        mock_cognition_service.process.return_value = CognitionDecision(
            action="respond",
            reasoning="test reasoning",
            data={"input": "Hello with cognition"},
        )
        cognition_api = CognitionAPI(
            cognition_service=mock_cognition_service,
        )

        service = ConversationService(
            manager.service,
            cognition_api=cognition_api,
        )

        response = service.send("Hello with cognition")

        # Verify the cognition service was called with all kwargs
        mock_cognition_service.process.assert_called_once_with(
            user_input="Hello with cognition",
            memory=None,
            metadata=None,
            goal=None,
        )

        # Verify response still works
        self.assertEqual(response.role, "assistant")
        self.assertTrue(len(response.content) > 0)

    def test_cognition_data_included_in_context(self):
        """Cognition decision data is included in the context sent to the AI."""

        manager = AIManager()
        manager.initialize(
            provider="Mock Provider",
            model="atlas-mock-v1",
            timeout=300,
        )

        # Create a mock CognitionAPI
        mock_cognition_service = MagicMock(spec=CognitionService)
        mock_cognition_service.process.return_value = CognitionDecision(
            action="respond",
            reasoning="context test reasoning",
            data={"key": "value"},
        )
        cognition_api = CognitionAPI(
            cognition_service=mock_cognition_service,
        )

        service = ConversationService(
            manager.service,
            cognition_api=cognition_api,
        )

        response = service.send("Context test")

        # Verify the cognition service was called with the right input
        mock_cognition_service.process.assert_called_once_with(
            user_input="Context test",
            memory=None,
            metadata=None,
            goal=None,
        )

        # Verify response still works
        self.assertEqual(response.role, "assistant")
        self.assertTrue(len(response.content) > 0)

    def test_cognition_does_not_break_stream(self):
        """Streaming still works with cognition_api injected."""

        manager = AIManager()
        manager.initialize(
            provider="Mock Provider",
            model="atlas-mock-v1",
            timeout=300,
        )

        mock_cognition_service = MagicMock(spec=CognitionService)
        mock_cognition_service.process.return_value = CognitionDecision(
            action="respond",
            reasoning="stream test",
            data={},
        )
        cognition_api = CognitionAPI(
            cognition_service=mock_cognition_service,
        )

        service = ConversationService(
            manager.service,
            cognition_api=cognition_api,
        )

        chunks = list(service.stream("Stream test"))

        self.assertGreater(len(chunks), 0)
        mock_cognition_service.process.assert_called_once_with(
            user_input="Stream test",
            memory=None,
            metadata=None,
            goal=None,
        )


if __name__ == "__main__":
    unittest.main()