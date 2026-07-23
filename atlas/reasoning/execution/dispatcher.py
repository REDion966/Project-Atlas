"""
Atlas Capability Dispatcher

Dispatches capability execution by looking up handlers in the registry.
Contains no AI calls, no memory access, no knowledge access,
and no EventBus or service dependencies.
"""

from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry


class CapabilityDispatcher:
    """
    Dispatches a list of Capability instances to registered handlers.

    Each capability is looked up in the registry and executed in
    priority order. Results are collected and returned.

    This is a pure logic component with no infrastructure dependencies.
    It does not call AI providers, access memory, query knowledge,
    or interact with any service.

    Attributes:
        registry: The CapabilityRegistry to look up handlers from.
    """

    def __init__(self, registry: CapabilityRegistry) -> None:
        """
        Initialise the dispatcher with a registry.

        Args:
            registry: A CapabilityRegistry instance to use for lookups.
        """
        self.registry = registry

    def dispatch(
        self,
        capabilities: list[Capability],
    ) -> list[ExecutionResult]:
        """
        Execute a list of capabilities through their registered handlers.

        Capabilities are executed in the order provided. Each capability
        is looked up in the registry. If a handler is found, it is called
        with the capability's metadata as parameters. If no handler is
        found, a failed ExecutionResult is returned.

        Args:
            capabilities: The list of Capability instances to dispatch.

        Returns:
            A list of ExecutionResult instances, one per capability,
            in the same order as the input capabilities.
        """
        results: list[ExecutionResult] = []

        for capability in capabilities:
            result = self._execute_single(capability)
            results.append(result)

        return results

    def _execute_single(
        self,
        capability: Capability,
    ) -> ExecutionResult:
        """
        Execute a single capability.

        Looks up the handler in the registry and calls it with the
        capability's metadata as parameters.

        Args:
            capability: The Capability instance to execute.

        Returns:
            An ExecutionResult indicating success or failure.
        """
        handler = self.registry.get(capability.name)

        if handler is None:
            return ExecutionResult(
                capability=capability.name,
                success=False,
                error=(
                    f"No handler registered for capability: "
                    f"{capability.name}"
                ),
                metadata={
                    "priority": capability.priority,
                    "reason": capability.reason,
                },
            )

        try:
            result = handler(capability.metadata)
            return result
        except Exception as exc:
            return ExecutionResult(
                capability=capability.name,
                success=False,
                error=str(exc),
                metadata={
                    "priority": capability.priority,
                    "reason": capability.reason,
                },
            )