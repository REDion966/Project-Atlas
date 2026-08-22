"""
Atlas Anthropic Provider

Provides AI access through the Anthropic API.
"""

import json
import os
from collections.abc import Iterator

import requests

from atlas.ai.provider import AIProvider
from atlas.models.ai_response import AIResponse


class AnthropicProvider(AIProvider):
    """Anthropic API Provider."""

    BASE_URL = "https://api.anthropic.com/v1"
    API_VERSION = "2023-06-01"

    def __init__(
        self,
        model: str,
        timeout: int,
        api_key: str | None = None,
    ):
        self._model = model
        self._timeout = timeout
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def _require_api_key(self):
        """Raise if no API key is configured."""
        if not self._api_key:
            raise RuntimeError(
                "Anthropic API key is required. "
                "Set ANTHROPIC_API_KEY environment variable or pass api_key."
            )

    def _resolve_model(self, model: str | None) -> str:
        """Return the per-call model override, or the configured default."""
        return model or self._model

    def name(self) -> str:
        """Return provider name."""
        return "Anthropic"

    def _headers(self) -> dict:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": self.API_VERSION,
            "Content-Type": "application/json",
        }

    def chat(self, messages, model: str | None = None):
        """Generate a complete chat response.

        Anthropic uses a /v1/messages endpoint with a 'content'
        field that contains a list of content blocks.
        """

        self._require_api_key()

        payload = {
            "model": self._resolve_model(model),
            "messages": messages,
            "max_tokens": 4096,
            "stream": False,
        }

        response = requests.post(
            f"{self.BASE_URL}/messages",
            headers=self._headers(),
            json=payload,
            timeout=self._timeout,
        )

        response.raise_for_status()

        data = response.json()

        text = "".join(
            block["text"]
            for block in data.get("content", [])
            if block.get("type") == "text"
        )

        return AIResponse(
            text=text,
            provider=self.name(),
            model=payload["model"],
            tokens=(
                data.get("usage", {}).get("input_tokens", 0)
                + data.get("usage", {}).get("output_tokens", 0)
            ),
            finish_reason=data.get("stop_reason"),
            metadata={
                "input_tokens": data.get("usage", {}).get("input_tokens"),
                "output_tokens": data.get("usage", {}).get("output_tokens"),
            },
        )

    def stream_chat(
        self,
        messages,
        model: str | None = None,
    ) -> Iterator[str]:
        """Stream chat response from Anthropic.

        Anthropic SSE events include:
          - message_start, content_block_start, content_block_delta,
            content_block_stop, message_delta, message_stop
        """

        self._require_api_key()

        payload = {
            "model": self._resolve_model(model),
            "messages": messages,
            "max_tokens": 4096,
            "stream": True,
        }

        response = requests.post(
            f"{self.BASE_URL}/messages",
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
                    event_data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                event_type = event_data.get("type")

                if event_type == "content_block_delta":
                    delta = event_data.get("delta", {})
                    text = delta.get("text")
                    if text:
                        yield text

    def complete(self, prompt, model: str | None = None):
        """Generate a completion using the messages endpoint."""

        return self.chat(
            [{"role": "user", "content": prompt}],
            model=model,
        )

    def models(self):
        """Return available Anthropic models.

        Anthropic's /v1/models endpoint returns the list of
        available models.
        """

        self._require_api_key()

        response = requests.get(
            f"{self.BASE_URL}/models",
            headers=self._headers(),
            timeout=self._timeout,
        )

        response.raise_for_status()

        data = response.json()

        return [
            model["id"]
            for model in data.get("data", [])
        ]
