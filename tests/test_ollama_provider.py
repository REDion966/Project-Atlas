import unittest

from atlas.ai.providers.ollama_provider import OllamaProvider


class TestOllamaProvider(unittest.TestCase):

    def setUp(self):
        self.provider = OllamaProvider()

    def test_name(self):
        self.assertEqual(
            self.provider.name(),
            "Ollama"
        )

    def test_models(self):
        models = self.provider.models()

        self.assertIn(
            "qwen3:8b",
            models
        )

    def test_complete(self):
        response = self.provider.complete(
            "Say hello."
        )

        self.assertTrue(
            len(response.text) > 0
        )

        self.assertEqual(
            response.provider,
            "Ollama"
        )


if __name__ == "__main__":
    unittest.main()