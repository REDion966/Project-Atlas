"""
Atlas Model Router

Selects the best AI model for a given request without executing providers.
"""

from atlas.ai.routing.models import RoutingDecision, RoutingRequest
from atlas.ai.routing.policy import RoutingPolicy
from atlas.ai.routing.registry import ModelProfileRegistry


class ModelRouter:
    """
    Routes requests to the most appropriate model profile.

    The router is a pure decision component. It reads registered model
    profiles and delegates to a RoutingPolicy to produce a
    RoutingDecision. It never calls providers or accesses infrastructure.
    """

    def __init__(
        self,
        registry: ModelProfileRegistry,
        policy: RoutingPolicy | None = None,
    ):
        """
        Initialize the model router.

        Args:
            registry: Registry of available model profiles.
            policy: Optional routing policy. Defaults to RoutingPolicy.
        """

        self._registry = registry
        self._policy = policy or RoutingPolicy()

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
        """

        profiles = self._registry.list_profiles()
        return self._policy.select(request, profiles)

    @property
    def registry(self) -> ModelProfileRegistry:
        """Return the model profile registry."""

        return self._registry

    @property
    def policy(self) -> RoutingPolicy:
        """Return the routing policy."""

        return self._policy
