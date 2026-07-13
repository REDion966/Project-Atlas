"""
Atlas AI Service

Provides the public interface for Atlas AI.
"""

from atlas.services.service import Service
from atlas.ai.router.ai_router import AIRouter


class AIService(Service):
    """Atlas AI service."""

    def __init__(self, router: AIRouter):
        super().__init__("AI Service")
        self._router = router

    def start(self):
        """Start the AI service."""

        self.mark_running()

    def stop(self):
        """Stop the AI service."""

        super().stop()

    def chat(self, messages):
        """Chat with the active AI provider."""

        return self._router.chat(messages)

    def complete(self, prompt):
        """Generate a completion."""

        return self._router.complete(prompt)

    def models(self):
        """Return available models."""

        return self._router.models()