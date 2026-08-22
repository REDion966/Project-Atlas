"""Production ``StateReader`` / ``StateWriter`` adapter for the CAPABILITY scope.

Wraps the real :class:`~atlas.reasoning.execution.registry.CapabilityRegistry`
and implements the Phase 16 protocols from
:mod:`atlas.evolution.autonomy.applier`.

Namespace (deterministic): ``capability.<name>``.

Write semantics: a value must be a callable ``CapabilityHandler``. The
registry's own ``register`` raises ``ValueError`` on duplicate names — the
adapter preserves that governance control rather than creating an
alternate registration path. Repeated registration of the same name
therefore fails closed, which is the correct behavior for capability
governance (enhance/deprecate flows are handled by higher layers).

Remove semantics: ``unregister`` raises ``KeyError`` when the name is
missing; the adapter converts a missing-name removal into ``False`` so the
protocol's ``remove() -> bool`` contract is honored without swallowing
real registry errors.

Pure adapter layer: no governance, no AI, no async, no new persistence.
"""

from __future__ import annotations

from typing import Any, cast

from atlas.evolution.autonomy.applier import StateReader, StateWriter
from atlas.reasoning.execution.models import CapabilityHandler
from atlas.reasoning.execution.registry import CapabilityRegistry

#: Deterministic namespace prefix for CAPABILITY-scope state keys.
CAPABILITY_NAMESPACE = "capability."


class CapabilityStateAdapter(StateReader, StateWriter):
    """Production capability-scope adapter over ``CapabilityRegistry``."""

    def __init__(self, capability_registry: CapabilityRegistry) -> None:
        if capability_registry is None:
            raise ValueError("CapabilityRegistry is required")
        self._registry = capability_registry

    # ------------------------------------------------------------------
    # Key normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(key: str) -> str:
        """Strip the optional ``capability.`` namespace prefix.

        Accepts both ``capability.<name>`` and ``<name>``.
        """
        if key.startswith(CAPABILITY_NAMESPACE):
            return key[len(CAPABILITY_NAMESPACE):]
        return key

    # ------------------------------------------------------------------
    # StateReader
    # ------------------------------------------------------------------

    def read(self, key: str, default: Any = None) -> Any:
        """Return the registered handler for ``key``, or ``default``."""
        name = self._normalize(key)
        handler = self._registry.get(name)
        if handler is None:
            return default
        return handler

    def has(self, key: str) -> bool:
        """Return True when a handler is registered for ``key``."""
        return self._registry.has(self._normalize(key))

    # ------------------------------------------------------------------
    # StateWriter
    # ------------------------------------------------------------------

    def write(self, key: str, value: Any) -> None:
        """Register ``value`` as the handler for ``key``.

        ``value`` must be a callable ``CapabilityHandler``. Duplicate
        registration raises ``ValueError`` (the registry's own governance
        control). Dict-shaped upgrade payloads (the ``CapabilityApplier``
        entry shape) are NOT accepted here: capability changes must flow
        through the governed applier/registry path, not a raw adapter.
        """
        name = self._normalize(key)
        if not callable(value):
            raise TypeError(
                "CapabilityStateAdapter.write expects a callable "
                f"CapabilityHandler, got {type(value).__name__}"
            )
        handler = cast(CapabilityHandler, value)
        self._registry.register(name, handler)

    def remove(self, key: str) -> bool:
        """Unregister the handler for ``key``.

        Returns True if a handler existed and was removed; False when the
        name is not registered (converted from the registry's KeyError so
        the protocol contract holds).
        """
        name = self._normalize(key)
        if not self._registry.has(name):
            return False
        self._registry.unregister(name)
        return True
