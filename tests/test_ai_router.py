"""
Tests for the Atlas AI Router.
"""

import unittest

from atlas.ai.router.ai_router import AIRouter
from atlas.ai.providers.mock_provider import MockProvider
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


if __name__ == "__main__":
    unittest.main()