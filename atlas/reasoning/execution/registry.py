"""
Atlas Capability Registry

Stores and manages capability handler registrations.
Contains no AI calls, no memory access, no knowledge access,
and no EventBus or service dependencies.
"""

from atlas.reasoning.execution.models import CapabilityHandler, ExecutionResult


class CapabilityRegistry:
    """
    Registry for capability handler functions.

    Handlers are registered by capability name and can be looked up
    for execution. This is a pure logic component with no
    infrastructure dependencies.

    Attributes:
        _handlers: Internal dict mapping capability names to handlers.
    """

    def __init__(self) -> None:
        """Initialise an empty registry."""
        self._handlers: dict[str, CapabilityHandler] = {}

    def register(
        self,
        name: str,
        handler: CapabilityHandler,
    ) -> None:
        """
        Register a handler for a capability.

        Args:
            name: The capability name to register.
            handler: The handler function to associate.

        Raises:
            ValueError: If a handler is already registered for this name.
        """
        if name in self._handlers:
            raise ValueError(
                f"Handler already registered for capability: {name}"
            )

        self._handlers[name] = handler

    def unregister(self, name: str) -> None:
        """
        Remove a registered handler.

        Args:
            name: The capability name to unregister.

        Raises:
            KeyError: If no handler is registered for this name.
        """
        if name not in self._handlers:
            raise KeyError(
                f"No handler registered for capability: {name}"
            )

        del self._handlers[name]

    def get(self, name: str) -> CapabilityHandler | None:
        """
        Look up a handler by capability name.

        Args:
            name: The capability name to look up.

        Returns:
            The registered handler, or None if not found.
        """
        return self._handlers.get(name)

    def has(self, name: str) -> bool:
        """
        Check if a handler is registered for a capability.

        Args:
            name: The capability name to check.

        Returns:
            True if a handler is registered, False otherwise.
        """
        return name in self._handlers

    @property
    def registered_names(self) -> list[str]:
        """
        Get the list of all registered capability names.

        Returns:
            A sorted list of registered capability names.
        """
        return sorted(self._handlers.keys())

    @property
    def count(self) -> int:
        """
        Get the number of registered handlers.

        Returns:
            The number of registered handlers.
        """
        return len(self._handlers)

    def clear(self) -> None:
        """Remove all registered handlers."""
        self._handlers.clear()