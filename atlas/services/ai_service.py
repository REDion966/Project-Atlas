"""
Atlas AI Service

Provides the public interface for Atlas AI.
"""

from atlas.services.service import Service
from atlas.ai.router.ai_router import AIRouter
from atlas.ai.providers.mock_provider import MockProvider


class AIService(Service):
    """Atlas AI service."""

    def __init__(self):
        self._router = AIRouter()

    def start(self):
        """Start the AI service."""

        self._router.registry.register(MockProvider())
        self._router.use("Mock Provider")

    def stop(self):
        """Stop the AI service."""
        pass

    def chat(self, messages):
        """Chat with the active AI provider."""
        return self._router.chat(messages)

    def complete(self, prompt):
        """Generate a completion."""
        return self._router.complete(prompt)

    def models(self):
        """Return available models."""
        return self._router.models()