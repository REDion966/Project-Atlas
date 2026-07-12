"""
Atlas Mock AI Provider

Used for testing the AI Router.
"""

from atlas.ai.provider import AIProvider
from atlas.models.ai_response import AIResponse


class MockProvider(AIProvider):
    """Simple testing provider."""

    def name(self) -> str:
        return "Mock Provider"

    def chat(self, messages):

        return AIResponse(
            text="Hello! I am Atlas's first AI provider.",
            provider=self.name(),
            model="atlas-mock-v1",
        )

    def complete(self, prompt):

        return AIResponse(
            text=f"Mock completion: {prompt}",
            provider=self.name(),
            model="atlas-mock-v1",
        )

    def models(self):

        return [
            "atlas-mock-v1"
        ]