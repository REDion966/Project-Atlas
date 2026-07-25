"""
Atlas AI Manager

Initializes and manages Atlas AI providers.
"""

from typing import TYPE_CHECKING

from atlas.ai.providers.mock_provider import MockProvider
from atlas.ai.providers.ollama_provider import OllamaProvider
from atlas.ai.router.ai_router import AIRouter
from atlas.services.ai_service import AIService

if TYPE_CHECKING:
    from atlas.ai.routing.router import ModelRouter


class AIManager:
    """Initializes the Atlas AI subsystem."""

    def __init__(self):
        self._router = AIRouter()
        self._service: AIService | None = None
        self._model_router: "ModelRouter | None" = None

    def initialize(
        self,
        provider: str,
        model: str,
        timeout: int,
        model_router: "ModelRouter | None" = None,
    ):
        """Initialize Atlas AI."""

        self._model_router = model_router

        self._router.registry.register(
            MockProvider()
        )

        self._router.registry.register(
            OllamaProvider(
                model=model,
                timeout=timeout,
            )
        )

        self._router.use(provider)

        self._service = AIService(
            self._router,
            model_router=self._model_router,
        )

        self._service.start()

    @property
    def service(self):
        """Return configured AI service."""
        if self._service is None:
            raise RuntimeError(
                "AIManager has not been initialized."
            )
        return self._service

    @property
    def provider(self):
        """Return the active AI provider."""
        return self._router.provider()