"""
Tests for the Atlas AI Router.
"""

import unittest

from atlas.ai.router.ai_router import AIRouter
from atlas.ai.providers.mock_provider import MockProvider
from atlas.ai.routing.models import RoutingDecision
from atlas.models.ai_response import AIResponse


class TestAIRouter(unittest.TestCase):
    """Tests for AIRouter."""

    def setUp(self):
        self.router = AIRouter()
        self.provider = MockProvider()

        self.router.registry.register(self.provider)
        self.router.use("Mock Provider")

    def test_active_provider(self):
        """Router should return the active provider."""

        self.assertEqual(
            self.router.provider().name(),
            "Mock Provider"
        )

    def test_chat(self):
        """Router should return an AIResponse."""

        response = self.router.chat([])

        self.assertIsInstance(
            response,
            AIResponse
        )

    def test_complete(self):
        """Router should generate a completion."""

        response = self.router.complete("Hello")

        self.assertIsInstance(
            response,
            AIResponse
        )

    def test_models(self):
        """Router should return available models."""

        models = self.router.models()

        self.assertEqual(
            models,
            ["atlas-mock-v1"]
        )

    def test_chat_with_routing_decision(self):
        """Router should use provider from routing decision."""

        decision = RoutingDecision(
            provider_name="Mock Provider",
            model_name="atlas-mock-v1",
        )

        response = self.router.chat([], routing_decision=decision)

        self.assertIsInstance(response, AIResponse)
        self.assertEqual(response.provider, "Mock Provider")

    def test_stream_chat_with_routing_decision(self):
        """Router should stream from provider in routing decision."""

        decision = RoutingDecision(
            provider_name="Mock Provider",
            model_name="atlas-mock-v1",
        )

        chunks = list(self.router.stream_chat([], routing_decision=decision))

        self.assertGreater(len(chunks), 0)

    def test_chat_without_routing_decision_uses_active_provider(self):
        """Router should keep existing behavior when no decision provided."""

        response = self.router.chat([])

        self.assertIsInstance(response, AIResponse)
        self.assertEqual(response.provider, "Mock Provider")

    def test_routing_decision_unknown_provider_raises(self):
        """Router should raise when routing decision references unknown provider."""

        decision = RoutingDecision(
            provider_name="Unknown Provider",
            model_name="unknown-model",
        )

        with self.assertRaises(RuntimeError):
            self.router.chat([], routing_decision=decision)


if __name__ == "__main__":
    unittest.main()
