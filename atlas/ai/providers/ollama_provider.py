"""
Atlas Ollama Provider

Provides local AI access through Ollama.
"""

import json
from collections.abc import Iterator

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

    def _resolve_model(self, model: str | None) -> str:
        """Return the per-call model override, or the configured default."""
        return model or self._model

    def chat(self, messages, model: str | None = None):
        """Generate a complete chat response."""

        payload = {
            "model": self._resolve_model(model),
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
            model=payload["model"],
        )

    def stream_chat(
        self,
        messages,
        model: str | None = None,
    ) -> Iterator[str]:
        """Stream chat response from Ollama."""

        payload = {
            "model": self._resolve_model(model),
            "messages": messages,
            "stream": True,
        }

        response = requests.post(
            f"{self.BASE_URL}/api/chat",
            json=payload,
            stream=True,
            timeout=self._timeout,
        )

        response.raise_for_status()

        for line in response.iter_lines():

            if not line:
                continue

            data = line.decode("utf-8")

            chunk = json.loads(data)

            if "message" in chunk:
                yield chunk["message"]["content"]

            if chunk.get("done", False):
                break

    def complete(self, prompt, model: str | None = None):
        """Generate a completion."""

        payload = {
            "model": self._resolve_model(model),
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
            model=payload["model"],
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
