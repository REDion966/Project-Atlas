"""
Atlas AI Manager

Initializes and manages Atlas AI providers.
Agnostic to any specific provider implementation.
"""

from typing import TYPE_CHECKING

from atlas.ai.providers.mock_provider import MockProvider
from atlas.ai.providers.ollama_provider import OllamaProvider
from atlas.ai.providers.openai_provider import OpenAIProvider
from atlas.ai.providers.lmstudio_provider import LMStudioProvider
from atlas.ai.providers.anthropic_provider import AnthropicProvider
from atlas.ai.providers.openrouter_provider import OpenRouterProvider
from atlas.ai.router.ai_router import AIRouter
from atlas.services.ai_service import AIService

if TYPE_CHECKING:
    from atlas.ai.routing.registry import ModelProfileRegistry
    from atlas.ai.routing.router import ModelRouter
    from atlas.config.configuration_models import APIKeySettings


class AIManager:
    """Initializes the Atlas AI subsystem.

    Provider-agnostic: registers all providers and selects
    the active one based on configuration.
    """

    def __init__(
        self,
        model_profile_registry: "ModelProfileRegistry | None" = None,
    ):
        self._router = AIRouter(
            model_profile_registry=model_profile_registry,
        )
        self._service: AIService | None = None
        self._model_router: "ModelRouter | None" = None

    def initialize(
        self,
        provider: str,
        model: str,
        timeout: int,
        model_router: "ModelRouter | None" = None,
        api_keys: "APIKeySettings | None" = None,
    ):
        """Initialize Atlas AI.

        Registers all available providers and activates the
        one specified in the configuration.
        """

        self._model_router = model_router

        # Always register MockProvider for testing
        self._router.registry.register(MockProvider())

        # Extract individual API keys
        openai_key = ""
        anthropic_key = ""
        if api_keys is not None:
            openai_key = api_keys.openai
            anthropic_key = api_keys.anthropic

        # Register Ollama (always available locally, no API key needed)
        self._router.registry.register(
            OllamaProvider(
                model=model,
                timeout=timeout,
            )
        )

        # Register OpenAI
        self._router.registry.register(
            OpenAIProvider(
                model=model,
                timeout=timeout,
                api_key=openai_key or None,
            )
        )

        # Register LM Studio (local, no API key needed)
        self._router.registry.register(
            LMStudioProvider(
                model=model,
                timeout=timeout,
            )
        )

        # Register Anthropic
        self._router.registry.register(
            AnthropicProvider(
                model=model,
                timeout=timeout,
                api_key=anthropic_key or None,
            )
        )

        # Register OpenRouter (optional; requires OPENROUTER_API_KEY at use)
        self._router.registry.register(
            OpenRouterProvider(
                model=model,
                timeout=timeout,
            )
        )

        # Activate the configured provider
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
