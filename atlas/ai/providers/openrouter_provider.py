"""
Atlas OpenRouter Provider

Provides AI access through OpenRouter's OpenAI-compatible API.
"""

import json
import os
from collections.abc import Iterator

import requests

from atlas.ai.provider import AIProvider
from atlas.models.ai_response import AIResponse


class OpenRouterProvider(AIProvider):
    """OpenRouter API Provider.

    OpenRouter exposes an OpenAI-compatible API with a
    different base URL and authentication scheme.
    """

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        model: str,
        timeout: int,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self._model = model
        self._timeout = timeout
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self._base_url = (base_url or self.BASE_URL).rstrip("/")

    def _require_api_key(self):
        """Raise if no API key is configured."""
        if not self._api_key:
            raise RuntimeError(
                "OpenRouter API key is required. "
                "Set OPENROUTER_API_KEY environment variable or pass api_key."
            )

    def _resolve_model(self, model: str | None) -> str:
        """Return the per-call model override, or the configured default."""
        return model or self._model

    def name(self) -> str:
        """Return provider name."""
        return "OpenRouter"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def chat(self, messages, model: str | None = None):
        """Generate a complete chat response."""

        self._require_api_key()

        payload = {
            "model": self._resolve_model(model),
            "messages": messages,
            "stream": False,
        }

        response = requests.post(
            f"{self._base_url}/chat/completions",
            headers=self._headers(),
            json=payload,
            timeout=self._timeout,
        )

        response.raise_for_status()

        data = response.json()

        choice = data["choices"][0]

        return AIResponse(
            text=choice["message"]["content"],
            provider=self.name(),
            model=payload["model"],
            tokens=data.get("usage", {}).get("total_tokens"),
            finish_reason=choice.get("finish_reason"),
            metadata={
                "prompt_tokens": data.get("usage", {}).get("prompt_tokens"),
                "completion_tokens": data.get("usage", {}).get("completion_tokens"),
            },
        )

    def stream_chat(
        self,
        messages,
        model: str | None = None,
    ) -> Iterator[str]:
        """Stream chat response from OpenRouter."""

        self._require_api_key()

        payload = {
            "model": self._resolve_model(model),
            "messages": messages,
            "stream": True,
        }

        response = requests.post(
            f"{self._base_url}/chat/completions",
            headers=self._headers(),
            json=payload,
            stream=True,
            timeout=self._timeout,
        )

        response.raise_for_status()

        for line in response.iter_lines():

            if not line:
                continue

            decoded = line.decode("utf-8")

            if decoded.startswith("data: "):
                data_str = decoded[6:]

                if data_str.strip() == "[DONE]":
                    break

                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                delta = chunk.get("choices", [{}])[0].get("delta", {})

                content = delta.get("content")

                if content:
                    yield content

    def complete(self, prompt, model: str | None = None):
        """Generate a completion using the chat endpoint."""

        return self.chat(
            [{"role": "user", "content": prompt}],
            model=model,
        )

    def models(self):
        """Return available OpenRouter models."""

        self._require_api_key()

        response = requests.get(
            f"{self._base_url}/models",
            headers=self._headers(),
            timeout=self._timeout,
        )

        response.raise_for_status()

        data = response.json()

        return [
            model["id"]
            for model in data.get("data", [])
        ]
