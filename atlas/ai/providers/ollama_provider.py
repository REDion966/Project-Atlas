"""
Atlas Ollama Provider

Provides local AI access through Ollama.
"""

import requests

from atlas.ai.provider import AIProvider
from atlas.models.ai_response import AIResponse


class OllamaProvider(AIProvider):
    """Ollama AI Provider."""

    BASE_URL = "http://localhost:11434"

    def __init__(
        self,
        model: str,
        timeout: int,
    ):
        self._model = model
        self._timeout = timeout

    def name(self) -> str:
        """Return provider name."""
        return "Ollama"

    def chat(self, messages):
        """Generate a chat response."""

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }

        response = requests.post(
            f"{self.BASE_URL}/api/chat",
            json=payload,
            timeout=self._timeout,
        )

        response.raise_for_status()

        data = response.json()

        return AIResponse(
            text=data["message"]["content"],
            provider=self.name(),
            model=self._model,
        )

    def complete(self, prompt):
        """Generate a completion."""

        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }

        response = requests.post(
            f"{self.BASE_URL}/api/generate",
            json=payload,
            timeout=self._timeout,
        )

        response.raise_for_status()

        data = response.json()

        return AIResponse(
            text=data["response"],
            provider=self.name(),
            model=self._model,
        )

    def models(self):
        """Return installed Ollama models."""

        response = requests.get(
            f"{self.BASE_URL}/api/tags",
            timeout=self._timeout,
        )

        response.raise_for_status()

        data = response.json()

        return [
            model["name"]
            for model in data["models"]
        ]