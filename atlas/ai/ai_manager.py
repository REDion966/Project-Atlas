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
        self._initialized = False

    def initialize(self, default_provider: str = "Mock Provider"):
        """Initialize the Atlas AI subsystem."""

        if self._initialized:
            return

        # Register providers
        self._router.registry.register(MockProvider())
        self._router.registry.register(OllamaProvider())

        # Select active provider
        self._router.use(default_provider)

        # Start AI service
        self._service.start()

        self._initialized = True

    @property
    def service(self) -> AIService:
        """Return the configured AI service."""
        return self._service

    @property
    def initialized(self) -> bool:
        """Return True if the AI subsystem has been initialized."""
        return self._initialized