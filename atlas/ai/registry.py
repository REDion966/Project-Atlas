"""
Atlas AI Provider Registry

Maintains all registered AI providers.
"""

from atlas.ai.provider import AIProvider


class AIProviderRegistry:
    """Stores and manages AI providers."""

    def __init__(self):
        self._providers: dict[str, AIProvider] = {}

    def register(self, provider: AIProvider):
        """Register an AI provider."""
        self._providers[provider.name()] = provider

    def get(self, name: str) -> AIProvider | None:
        """Return a provider by name."""
        return self._providers.get(name)

    def providers(self) -> list[str]:
        """Return registered provider names."""
        return sorted(self._providers.keys())

    def exists(self, name: str) -> bool:
        """Check if a provider exists."""
        return name in self._providers

    def unregister(self, name: str):
        """Remove a provider."""
        self._providers.pop(name, None)