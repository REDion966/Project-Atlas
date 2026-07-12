"""
Tests for the Atlas Mock AI Provider.
"""

import unittest

from atlas.ai.providers.mock_provider import MockProvider
from atlas.models.ai_response import AIResponse


class TestMockProvider(unittest.TestCase):
    """Tests for MockProvider."""

    def setUp(self):
        self.provider = MockProvider()

    def test_provider_name(self):
        """Provider should return the correct name."""
        self.assertEqual(
            self.provider.name(),
            "Mock Provider"
        )

    def test_chat_returns_ai_response(self):
        """Chat should return an AIResponse object."""

        response = self.provider.chat([])

        self.assertIsInstance(response, AIResponse)

        self.assertEqual(
            response.provider,
            "Mock Provider"
        )

    def test_models_returns_list(self):
        """Models should return a list."""

        models = self.provider.models()

        self.assertIsInstance(models, list)

        self.assertGreater(len(models), 0)


if __name__ == "__main__":
    unittest.main()