"""
Atlas AI Manager

Initializes and manages Atlas AI providers.
"""

from atlas.ai.router.ai_router import AIRouter
from atlas.ai.providers.mock_provider import MockProvider
from atlas.ai.providers.ollama_provider import OllamaProvider
from atlas.services.ai_service import AIService


class AIManager:
    """Initializes the Atlas AI subsystem."""

    def __init__(self):
        self._router = AIRouter()
        self._service = AIService(self._router)

    def initialize(self, default_provider: str = "Mock Provider"):
        """Initialize Atlas AI."""

        # Register providers
        self._router.registry.register(MockProvider())
        self._router.registry.register(OllamaProvider())

        # Select provider
        self._router.use(default_provider)

        # Start service
        self._service.start()

    @property
    def service(self):
        """Return configured AI service."""
        return self._service