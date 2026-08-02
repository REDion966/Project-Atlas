"""
Atlas Evolution Autonomy — Applier Registry — Phase 16.5

Registers and resolves ``Applier`` instances by ``ScopeType``.

The registry is a pure, deterministic lookup component. It does not
authorize, schedule, or execute. ``ApplicationEngine`` uses it to find
the correct applier for an already-authorized ``EvolutionRequest``.

New scopes/appliers are added by constructor injection; there is no
mutable register-at-runtime surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from atlas.evolution.autonomy.applier import Applier
from atlas.evolution.governance.models import ScopeType


class NoApplierError(Exception):
    """Raised when no applier is registered for a scope."""


@dataclass(frozen=True, slots=True)
class ApplierRegistry:
    """Immutable registry of scope-to-applier mappings."""

    _appliers: dict[ScopeType, Applier] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validate that each applier advertises the scope it is registered under.
        for scope, applier in self._appliers.items():
            if not applier.supports(scope):
                raise ValueError(
                    f"Applier {type(applier).__name__} does not support {scope.name}"
                )

    @classmethod
    def default(cls) -> "ApplierRegistry":
        """Return a registry with the four Phase 16.5 appliers pre-registered."""
        from atlas.evolution.autonomy.capability_applier import CapabilityApplier
        from atlas.evolution.autonomy.config_applier import ConfigApplier
        from atlas.evolution.autonomy.information_applier import (
            KnowledgeApplier,
            MemoryApplier,
        )

        return cls({
            ScopeType.CONFIG: ConfigApplier(),
            ScopeType.MEMORY: MemoryApplier(),
            ScopeType.KNOWLEDGE: KnowledgeApplier(),
            ScopeType.CAPABILITY: CapabilityApplier(),
        })

    def register(self, scope: ScopeType, applier: Applier) -> "ApplierRegistry":
        """Return a new registry with ``applier`` registered for ``scope``."""
        if not applier.supports(scope):
            raise ValueError(
                f"Applier {type(applier).__name__} does not support {scope.name}"
            )
        updated = dict(self._appliers)
        updated[scope] = applier
        return ApplierRegistry(updated)

    def resolve(self, scope: ScopeType) -> Applier:
        """Return the applier for ``scope``.

        Raises ``NoApplierError`` for unknown scopes (including UNKNOWN).
        This is the architecture's fail-closed path for unclassified requests.
        """
        applier = self._appliers.get(scope)
        if applier is None:
            raise NoApplierError(f"No applier registered for scope {scope.name}")
        return applier

    def supports(self, scope: ScopeType) -> bool:
        """Return True when an applier is registered for ``scope``."""
        return scope in self._appliers

    @property
    def scopes(self) -> set[ScopeType]:
        """Return the set of registered scopes."""
        return set(self._appliers.keys())
