"""
Atlas Model Router

Selects the best AI model for a given request without executing providers.
"""

from atlas.ai.routing.models import (
    LOCAL_PROVIDER_NAMES,
    RoutingDecision,
    RoutingRequest,
)
from atlas.ai.routing.policy import RoutingPolicy
from atlas.ai.routing.registry import ModelProfileRegistry


class ModelRouter:
    """
    Routes requests to the most appropriate model profile.

    The router is a pure decision component. It reads registered model
    profiles and delegates to a RoutingPolicy to produce a
    RoutingDecision. It never calls providers or accesses infrastructure.

    External providers are explicit opt-in augmentations: when
    ``external_providers`` is False (the default), only explicitly
    recognized local no-network profiles (``LOCAL_PROVIDER_NAMES``) are
    eligible for selection — every other name, known external or unknown,
    is excluded — so a RoutingDecision can never silently resolve to an
    external or unrecognized provider.
    """

    def __init__(
        self,
        registry: ModelProfileRegistry,
        policy: RoutingPolicy | None = None,
        external_providers: bool = False,
    ):
        """
        Initialize the model router.

        Args:
            registry: Registry of available model profiles.
            policy: Optional routing policy. Defaults to RoutingPolicy.
            external_providers: Explicit opt-in for external (HTTP)
                providers. When False (default), only ``LOCAL_PROVIDER_NAMES``
                profiles are eligible; all other names are excluded.
        """

        self._registry = registry
        self._policy = policy or RoutingPolicy()
        self._external_providers = bool(external_providers)

    @property
    def external_providers(self) -> bool:
        """Return whether external provider selection is opted in."""
        return self._external_providers

    def route(
        self,
        request: RoutingRequest,
    ) -> RoutingDecision | None:
        """
        Produce a routing decision for the given request.

        Args:
            request: The routing request describing request needs.

        Returns:
            A RoutingDecision, or None if no profiles are registered.
            Without the external-providers opt-in, the decision resolves
            only to an explicitly recognized local no-network profile.
        """

        profiles = self._registry.list_profiles()
        if not self._external_providers:
            profiles = [
                profile
                for profile in profiles
                if profile.provider_name in LOCAL_PROVIDER_NAMES
            ]
        return self._policy.select(request, profiles)

    @property
    def registry(self) -> ModelProfileRegistry:
        """Return the model profile registry."""

        return self._registry

    @property
    def policy(self) -> RoutingPolicy:
        """Return the routing policy."""

        return self._policy
