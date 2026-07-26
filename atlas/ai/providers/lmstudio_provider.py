"""
Atlas LM Studio Provider

Provides local AI access through LM Studio's OpenAI-compatible API.
"""

import json
from collections.abc import Iterator

import requests

from atlas.ai.provider import AIProvider
from atlas.models.ai_response import AIResponse


class LMStudioProvider(AIProvider):
    """LM Studio AI Provider.

    LM Studio exposes an OpenAI-compatible API endpoint.
    """

    BASE_URL = "http://localhost:1234/v1"

    def __init__(
        self,
        model: str,
        timeout: int,
        base_url: str | None = None,
    ):
        self._model = model
        self._timeout = timeout
        self._base_url = (base_url or self.BASE_URL).rstrip("/")

    def name(self) -> str:
        """Return provider name."""
        return "LM Studio"

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
        }

    def chat(self, messages):
        """Generate a complete chat response."""

        payload = {
            "model": self._model,
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
            model=self._model,
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
    ) -> Iterator[str]:
        """Stream chat response from LM Studio."""

        payload = {
            "model": self._model,
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

    def complete(self, prompt):
        """Generate a completion using the chat endpoint."""

        return self.chat(
            [{"role": "user", "content": prompt}]
        )

    def models(self):
        """Return available models from LM Studio."""

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