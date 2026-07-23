"""
Atlas Capability Router

Converts a list of Capability instances into ExecutionRoute instances
for adaptive execution routing (Phase 6.4).

Pure logic only — no AI calls, no memory access, no knowledge access,
and no EventBus or service dependencies.
"""

from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.models import ExecutionRoute
from atlas.reasoning.execution.registry import CapabilityRegistry


class CapabilityRouter:
    """
    Routes capabilities to execution handlers.

    Each capability is validated against the registry to check whether
    a handler exists. If it does, an ExecutionRoute is produced with
    the handler name, parameters, and routing metadata.

    This is a pure logic component with no infrastructure dependencies.
    It does not call AI providers, access memory, query knowledge,
    or interact with any service.

    Attributes:
        registry: The CapabilityRegistry used for handler lookups.
    """

    def __init__(self, registry: CapabilityRegistry) -> None:
        """
        Initialise the router with a registry.

        Args:
            registry: A CapabilityRegistry instance to use for lookups.
        """
        self.registry = registry

    def route(
        self,
        capabilities: list[Capability],
    ) -> list[ExecutionRoute]:
        """
        Convert a list of Capability instances to ExecutionRoute instances.

        Each capability is checked against the registry. If a handler is
        registered, an ExecutionRoute is created with the handler name,
        the capability's metadata as parameters, and a default strategy.

        Capabilities with no registered handler are omitted from the
        result (they cannot be routed).

        Args:
            capabilities: The list of Capability instances to route.

        Returns:
            A list of ExecutionRoute instances for routable capabilities,
            in the same order as the input list.
        """
        routes: list[ExecutionRoute] = []

        for capability in capabilities:
            if not self.registry.has(capability.name):
                # Cannot route — no handler registered
                continue

            route = ExecutionRoute(
                capability=capability.name,
                handler_name=capability.name,
                parameters=dict(capability.metadata),
                strategy="default",
                metadata={
                    "priority": capability.priority,
                    "reason": capability.reason,
                },
            )
            routes.append(route)

        return routes

    def can_route(self, capability: Capability) -> bool:
        """
        Check whether a single capability can be routed.

        Args:
            capability: The Capability instance to check.

        Returns:
            True if a handler is registered for the capability, False otherwise.
        """
        return self.registry.has(capability.name)