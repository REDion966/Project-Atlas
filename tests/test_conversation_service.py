"""
Tests for Atlas Conversation Service.
"""

import unittest
from unittest.mock import MagicMock

from atlas.ai.ai_manager import AIManager
from atlas.cognition.api import CognitionAPI
from atlas.cognition.decision import CognitionDecision
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.task_intake import TaskIntake
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
            task_intake=None,
        )

        response = service.send("Hello with cognition")

        # Verify the cognition service was called with all kwargs —
        # the raw user input is propagated as the processing goal
        # (Phase 20, Batch 2: goal/intent propagation), when task intake
        # is explicitly disabled (legacy path).
        mock_cognition_service.process.assert_called_once_with(
            user_input="Hello with cognition",
            memory=None,
            metadata=None,
            goal="Hello with cognition",
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
            task_intake=None,
        )

        response = service.send("Context test")

        # Verify the cognition service was called with the right input —
        # the raw user input is propagated as the processing goal
        # (Phase 20, Batch 2: goal/intent propagation), legacy path.
        mock_cognition_service.process.assert_called_once_with(
            user_input="Context test",
            memory=None,
            metadata=None,
            goal="Context test",
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
            task_intake=None,
        )

        chunks = list(service.stream("Stream test"))

        self.assertGreater(len(chunks), 0)
        # The raw user input is propagated as the processing goal
        # (Phase 20, Batch 2: goal/intent propagation), legacy path.
        mock_cognition_service.process.assert_called_once_with(
            user_input="Stream test",
            memory=None,
            metadata=None,
            goal="Stream test",
        )


class TestConversationServiceWithTaskIntake(unittest.TestCase):
    """B2 — deterministic task intake at the conversation seam."""

    def _make_service(self, cognition_service, task_intake):
        manager = AIManager()
        manager.initialize(
            provider="Mock Provider",
            model="atlas-mock-v1",
            timeout=300,
        )
        cognition_api = CognitionAPI(cognition_service=cognition_service)
        service = ConversationService(
            manager.service,
            cognition_api=cognition_api,
            task_intake=task_intake,
        )
        return service

    def test_structured_goal_propagation(self):
        mock_cognition_service = MagicMock(spec=CognitionService)
        mock_cognition_service.process.return_value = CognitionDecision(
            action="respond",
            reasoning="test",
            data={},
        )
        service = self._make_service(mock_cognition_service, TaskIntake())

        service.send("Create a report so that I can review progress, using local data")

        call = mock_cognition_service.process.call_args
        assert call.kwargs["user_input"] == "Create a report so that I can review progress, using local data"
        goal = call.kwargs["goal"]
        assert goal.startswith("respond: Create a report")
        assert "success:" in goal

    def test_metadata_task_present(self):
        mock_cognition_service = MagicMock(spec=CognitionService)
        mock_cognition_service.process.return_value = CognitionDecision(
            action="respond",
            reasoning="test",
            data={},
        )
        service = self._make_service(mock_cognition_service, TaskIntake())

        service.send("Create a report using local data")

        call = mock_cognition_service.process.call_args
        task = call.kwargs["metadata"]["task"]
        assert task["task_type"] == "action_request"
        assert task["source"] == "deterministic"
        assert task["verified"] is True
        assert task["goal"].startswith("respond: Create a report")

    def test_task_aware_routing(self):
        mock_cognition_service = MagicMock(spec=CognitionService)
        mock_cognition_service.process.return_value = CognitionDecision(
            action="respond",
            reasoning="test",
            data={},
        )
        manager = AIManager()
        manager.initialize(
            provider="Mock Provider",
            model="atlas-mock-v1",
            timeout=300,
        )
        service = ConversationService(
            manager.service,
            cognition_api=CognitionAPI(cognition_service=mock_cognition_service),
            task_intake=TaskIntake(),
        )

        # Replace the AI service with a spy so we can inspect the routing request.
        original_chat = service._ai.chat
        captured = {}

        def spy_chat(prompt, routing_context=None):
            captured["task_type"] = routing_context.task_type
            return original_chat(prompt, routing_context=routing_context)

        service._ai.chat = spy_chat

        service.send("Find the latest research on memory consolidation")

        assert captured["task_type"] == "information_request"

    def test_structured_task_context_rendered(self):
        mock_cognition_service = MagicMock(spec=CognitionService)
        mock_cognition_service.process.return_value = CognitionDecision(
            action="respond",
            reasoning="test",
            data={},
        )
        manager = AIManager()
        manager.initialize(
            provider="Mock Provider",
            model="atlas-mock-v1",
            timeout=300,
        )
        service = ConversationService(
            manager.service,
            cognition_api=CognitionAPI(cognition_service=mock_cognition_service),
            task_intake=TaskIntake(),
        )

        # Capture the context messages before prompt build.
        captured_messages = []
        original_build = service._prompt_builder.build

        def spy_build(context):
            captured_messages.extend(context)
            return original_build(context)

        service._prompt_builder.build = spy_build

        service.send("Create a report using local data")

        cognition_messages = [m for m in captured_messages if getattr(m, "metadata", None) and "cognition" in m.metadata]
        assert cognition_messages
        task = cognition_messages[0].metadata["cognition"]["task"]
        assert task["task_type"] == "action_request"
        assert task["source"] == "deterministic"

    def test_legacy_behavior_when_task_intake_none(self):
        mock_cognition_service = MagicMock(spec=CognitionService)
        mock_cognition_service.process.return_value = CognitionDecision(
            action="respond",
            reasoning="test",
            data={},
        )
        service = self._make_service(mock_cognition_service, task_intake=None)

        service.send("Hello legacy")

        mock_cognition_service.process.assert_called_once_with(
            user_input="Hello legacy",
            memory=None,
            metadata=None,
            goal="Hello legacy",
        )


class TestConversationServiceDevelopmentBridge(unittest.TestCase):
    """B3 — conversational development routing to an injected bridge."""

    def _make_service(self, task_intake, development_bridge, cognition_service=None):
        manager = AIManager()
        manager.initialize(
            provider="Mock Provider",
            model="atlas-mock-v1",
            timeout=300,
        )
        cognition_api = None
        if cognition_service is not None:
            cognition_api = CognitionAPI(cognition_service=cognition_service)
        return ConversationService(
            manager.service,
            cognition_api=cognition_api,
            task_intake=task_intake,
            development_bridge=development_bridge,
        )

    def test_development_request_reaches_bridge(self):
        bridge = MagicMock(return_value="governed prep complete")
        service = self._make_service(TaskIntake(), bridge)

        response = service.send("add a new capability to Atlas for scheduling")

        assert response.role == "assistant"
        assert response.content == "governed prep complete"
        bridge.assert_called_once()
        spec = bridge.call_args[0][0]
        assert spec.task_type.value == "development_request"

    def test_bridge_receives_task_spec(self):
        from atlas.conversation.task_intake import TaskType

        bridge = MagicMock(return_value="ok")
        service = self._make_service(TaskIntake(), bridge)

        service.send("add a new capability to Atlas for scheduling")

        spec = bridge.call_args[0][0]
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST

    def test_clarification_needed_does_not_reach_bridge(self):
        bridge = MagicMock(return_value="should not be called")
        service = self._make_service(TaskIntake(), bridge)

        response = service.send("improve this module")

        bridge.assert_not_called()
        assert response.role == "assistant"
        assert "more detail" in response.content

    def test_non_development_does_not_reach_bridge(self):
        bridge = MagicMock(return_value="should not be called")
        mock_cognition_service = MagicMock(spec=CognitionService)
        mock_cognition_service.process.return_value = CognitionDecision(
            action="respond",
            reasoning="test",
            data={},
        )
        service = self._make_service(TaskIntake(), bridge, mock_cognition_service)

        response = service.send("Hello Atlas")

        bridge.assert_not_called()
        assert response.role == "assistant"

    def test_bridge_none_remains_safe(self):
        mock_cognition_service = MagicMock(spec=CognitionService)
        mock_cognition_service.process.return_value = CognitionDecision(
            action="respond",
            reasoning="test",
            data={},
        )
        service = self._make_service(
            TaskIntake(), None, mock_cognition_service
        )

        response = service.send("add a new capability to Atlas for scheduling")

        assert response.role == "assistant"
        # Without a bridge, the request falls through to the normal AI path.
        mock_cognition_service.process.assert_called_once()

    def test_message_result_preserved(self):
        from atlas.conversation.message import Message

        bridge = MagicMock(return_value=Message(role="assistant", content="msg"))
        service = self._make_service(TaskIntake(), bridge)

        response = service.send("add a new capability to Atlas for scheduling")

        assert response.content == "msg"


if __name__ == "__main__":
    unittest.main()
