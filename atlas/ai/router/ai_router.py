"""
Atlas AI Router

Routes AI requests through the Provider Registry.
"""

from collections.abc import Iterator
from typing import TYPE_CHECKING

from atlas.ai.registry import AIProviderRegistry
from atlas.ai.routing.models import RoutingDecision

if TYPE_CHECKING:
    from atlas.ai.routing.registry import ModelProfileRegistry


class AIRouter:
    """Routes requests to registered AI providers."""

    def __init__(
        self,
        model_profile_registry: "ModelProfileRegistry | None" = None,
    ):
        self._registry = AIProviderRegistry()
        self._active_provider = None
        self._model_profile_registry = model_profile_registry

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

    def chat(
        self,
        messages,
        routing_decision: RoutingDecision | None = None,
    ):
        """Route chat requests."""

        provider = self._resolve_provider(routing_decision)

        if provider is None:
            raise RuntimeError(
                "No active AI provider selected."
            )

        return provider.chat(
            messages,
            model=self._resolve_model(routing_decision),
        )

    def stream_chat(
        self,
        messages,
        routing_decision: RoutingDecision | None = None,
    ) -> Iterator[str]:
        """Route streaming chat requests."""

        provider = self._resolve_provider(routing_decision)

        if provider is None:
            raise RuntimeError(
                "No active AI provider selected."
            )

        return provider.stream_chat(
            messages,
            model=self._resolve_model(routing_decision),
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

    def _resolve_provider(
        self,
        routing_decision: RoutingDecision | None,
    ):
        """
        Resolve the provider to use for a request.

        If a routing decision is provided, look up the requested provider
        in the registry. Otherwise, return the active provider.
        """

        if routing_decision is None:
            return self._active_provider

        provider = self._registry.get(
            routing_decision.provider_name
        )

        if provider is None:
            raise RuntimeError(
                f"Provider '{routing_decision.provider_name}' "
                f"requested by routing decision is not registered."
            )

        return provider

    def _resolve_model(
        self,
        routing_decision: RoutingDecision | None,
    ):
        """
        Resolve the model to request from the provider.

        If a routing decision carries a model_name and the model is valid
        for the selected provider according to the ModelProfileRegistry
        (when one is available), return it. Otherwise return None so the
        provider uses its configured default model.
        """

        if routing_decision is None:
            return None

        model = routing_decision.model_name

        if not model:
            return None

        if (
            self._model_profile_registry is not None
            and self._model_profile_registry.get(
                routing_decision.provider_name,
                model,
            )
            is None
        ):
            raise RuntimeError(
                f"Model '{model}' requested by routing decision is not "
                f"a registered profile for provider "
                f"'{routing_decision.provider_name}'."
            )

        return model
