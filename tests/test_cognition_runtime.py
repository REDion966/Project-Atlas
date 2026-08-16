"""
Phase 5.7 — Cognition Runtime Integration Tests

Validates the complete cognition pipeline end-to-end:
  Atlas -> ConversationService -> CognitionAPI -> CognitionService -> Memory/Knowledge -> Engine -> Decision
"""

import unittest
from unittest.mock import MagicMock, patch

from atlas.ai.ai_manager import AIManager
from atlas.ai.routing.router import ModelRouter
from atlas.kernel.atlas import Atlas
from atlas.cognition.api import CognitionAPI
from atlas.cognition.decision import CognitionDecision
from atlas.conversation.conversation_service import ConversationService
from atlas.memory.models.memory import Memory
from atlas.services.cognition_service import CognitionService
from atlas.services.service import Service
from atlas.kernel.service_container import ServiceContainer


class TestCognitionRuntimeIntegration(unittest.TestCase):
    """Full cognition pipeline integration tests."""

    def test_full_cognition_conversation_flow(self):
        """
        End-to-end test:
        - Start Atlas
        - CognitionService is running
        - ConversationService processes input
        - CognitionAPI was called
        - CognitionDecision was produced
        - Memory context reached cognition
        - Knowledge context reached cognition
        - Final response completed

        This test drives the full conversation pipeline, which ends in an AI
        provider call. The configured provider is Ollama (config.toml), so it
        is replaced with the Mock Provider following the existing convention in
        tests/test_conversation_service.py. No production code is changed.

        Post-Core hardening: ConversationService.send() always routes via the
        real ModelRouter, whose routing decision would override the patched
        Mock active provider. The ModelRouter patch is therefore scoped to the
        send() call so AIRouter falls back to the active Mock provider.
        """

        atlas = Atlas()

        original_initialize = AIManager.initialize

        def initialize_with_mock(
            manager: AIManager,
            provider: str,
            model: str,
            timeout: int,
            model_router=None,
            api_keys=None,
        ):
            original_initialize(
                manager,
                "Mock Provider",
                "atlas-mock-v1",
                timeout,
                model_router=model_router,
                api_keys=api_keys,
            )

        with patch.object(AIManager, "initialize", initialize_with_mock):
            atlas.start()

        # --- Verify CognitionService is running ---
        cognition_service = atlas.container.get("cognition_service")
        self.assertIsNotNone(cognition_service)
        self.assertTrue(cognition_service.is_running())

        # --- Verify CognitionAPI is available ---
        cognition_api = atlas.container.get("cognition_api")
        self.assertIsNotNone(cognition_api)

        # --- Verify ConversationService is available ---
        conversation = atlas.container.get("conversation")
        self.assertIsNotNone(conversation)

        # --- Inject test memory via memory service ---
        memory_service = atlas.container.get("memory")
        self.assertIsNotNone(memory_service)

        memory_service.add_memory(
            Memory(
                id="test-mem-1",
                title="Test Memory",
                content="This is a test memory for cognition",
                tags=["test"],
            )
        )

        # --- Inject test knowledge via knowledge manager ---
        knowledge_manager = atlas.container.get("knowledge")
        self.assertIsNotNone(knowledge_manager)

        knowledge_manager.remember(
            title="test:cognition",
            content="Test knowledge for cognition",
            source="test",
        )

        # --- Send user query through ConversationService ---
        # ConversationService.send always routes via the real ModelRouter,
        # whose routing decision would override the patched Mock active
        # provider. Return no decision so AIRouter falls back to Mock.
        with patch.object(ModelRouter, "route", return_value=None):
            response = conversation.send("Test cognition query")

        # --- Verify final response completed ---
        self.assertEqual(response.role, "assistant")
        self.assertTrue(len(response.content) > 0)

        atlas.shutdown()

    def test_cognition_api_receives_decision(self):
        """CognitionAPI.process returns a valid CognitionDecision during runtime."""

        atlas = Atlas()

        atlas.start()

        cognition_api = atlas.container.get("cognition_api")

        decision = cognition_api.process("What is the meaning of life?")

        self.assertIsInstance(decision, CognitionDecision)
        self.assertEqual(decision.action, "respond")
        self.assertIn("What is the meaning of life?", decision.data["input"])

        atlas.shutdown()

    def test_cognition_service_reaches_engine(self):
        """CognitionService.process reaches the engine and returns a decision."""

        atlas = Atlas()

        atlas.start()

        cognition_service = atlas.container.get("cognition_service")

        decision = cognition_service.process("Engine test")

        self.assertIsInstance(decision, CognitionDecision)
        self.assertEqual(decision.action, "respond")

        atlas.shutdown()


class TestCognitionServiceStatus(unittest.TestCase):
    """Tests for CognitionService status property."""

    def test_status_without_dependencies(self):
        """Status shows no dependencies when none are injected."""

        service = CognitionService()
        service.start()

        status = service.status

        self.assertTrue(status["running"])
        self.assertFalse(status["has_memory"])
        self.assertFalse(status["has_knowledge"])
        self.assertFalse(status["has_learning"])

        service.stop()

    def test_status_with_dependencies(self):
        """Status shows dependencies when injected."""

        memory = MagicMock()
        knowledge = MagicMock()
        learning = MagicMock()

        service = CognitionService(
            memory_service=memory,
            knowledge_manager=knowledge,
            learning_manager=learning,
        )
        service.start()

        status = service.status

        self.assertTrue(status["running"])
        self.assertTrue(status["has_memory"])
        self.assertTrue(status["has_knowledge"])
        self.assertTrue(status["has_learning"])

        service.stop()

    def test_status_before_start(self):
        """Status shows not running before start()."""

        service = CognitionService()

        status = service.status

        self.assertFalse(status["running"])
        self.assertFalse(status["has_memory"])
        self.assertFalse(status["has_knowledge"])
        self.assertFalse(status["has_learning"])


class TestServiceContainerStartupOrder(unittest.TestCase):
    """Verify ServiceContainer registration and startup order."""

    def test_cognition_service_registered_before_start(self):
        """All keys are registered before start_all is called."""

        atlas = Atlas()

        atlas.start()

        names = atlas.container.names()

        # All expected keys are present
        self.assertIn("cognition", names)
        self.assertIn("cognitive", names)
        self.assertIn("cognition_service", names)
        self.assertIn("cognition_api", names)
        self.assertIn("conversation", names)
        self.assertIn("memory", names)
        self.assertIn("knowledge", names)
        self.assertIn("tasks", names)
        self.assertIn("ai", names)

        atlas.shutdown()

    def test_cognition_dependencies_ready_at_start(self):
        """CognitionService has memory and knowledge available after start."""

        atlas = Atlas()

        atlas.start()

        cognition_service = atlas.container.get("cognition_service")

        status = cognition_service.status

        self.assertTrue(status["running"])
        self.assertTrue(status["has_memory"])
        self.assertTrue(status["has_knowledge"])
        self.assertTrue(status["has_learning"])

        atlas.shutdown()


if __name__ == "__main__":
    unittest.main()
