"""
Tests for the Atlas AI Provider Registry.
"""

import unittest

from atlas.ai.registry import AIProviderRegistry
from atlas.ai.providers.mock_provider import MockProvider


class TestAIProviderRegistry(unittest.TestCase):
    """Tests for AIProviderRegistry."""

    def setUp(self):
        self.registry = AIProviderRegistry()
        self.provider = MockProvider()

    def test_register_provider(self):
        """A provider should be registered successfully."""

        self.registry.register(self.provider)

        self.assertTrue(
            self.registry.exists("Mock Provider")
        )

    def test_get_provider(self):
        """Should return the registered provider."""

        self.registry.register(self.provider)

        provider = self.registry.get("Mock Provider")

        self.assertIs(provider, self.provider)

    def test_list_providers(self):
        """Should list all registered providers."""

        self.registry.register(self.provider)

        providers = self.registry.providers()

        self.assertEqual(
            providers,
            ["Mock Provider"]
        )

    def test_unregister_provider(self):
        """Should remove a provider."""

        self.registry.register(self.provider)

        self.registry.unregister("Mock Provider")

        self.assertFalse(
            self.registry.exists("Mock Provider")
        )


if __name__ == "__main__":
    unittest.main()