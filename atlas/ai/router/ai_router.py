"""
Atlas AI Router

Routes AI requests through the Provider Registry.
"""

from collections.abc import Iterator

from atlas.ai.registry import AIProviderRegistry


class AIRouter:
    """Routes requests to registered AI providers."""

    def __init__(self):
        self._registry = AIProviderRegistry()
        self._active_provider = None

    @property
    def registry(self):
        """Return the provider registry."""
        return self._registry

    def use(self, provider_name: str):
        """Select the active provider."""

        provider = self._registry.get(provider_name)

        if provider is None:
            raise RuntimeError(
                f"Provider '{provider_name}' is not registered."
            )

        self._active_provider = provider

    def provider(self):
        """Return the active provider."""
        return self._active_provider

    def chat(self, messages):
        """Route chat requests."""

        if self._active_provider is None:
            raise RuntimeError(
                "No active AI provider selected."
            )

        return self._active_provider.chat(messages)

    def stream_chat(
        self,
        messages,
    ) -> Iterator[str]:
        """Route streaming chat requests."""

        if self._active_provider is None:
            raise RuntimeError(
                "No active AI provider selected."
            )

        return self._active_provider.stream_chat(
            messages
        )

    def complete(self, prompt):
        """Route completion requests."""

        if self._active_provider is None:
            raise RuntimeError(
                "No active AI provider selected."
            )

        return self._active_provider.complete(
            prompt
        )

    def models(self):
        """Return models from the active provider."""

        if self._active_provider is None:
            raise RuntimeError(
                "No active AI provider selected."
            )

        return self._active_provider.models()