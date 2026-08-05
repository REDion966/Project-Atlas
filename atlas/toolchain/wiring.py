"""Atlas Toolchain — Component & Service Wiring Metadata (Phase 18.x).

Lightweight integration surface for Track B: a ``ComponentMetadata`` block
describing the toolchain subsystem plus a registration helper that adds it
to the lifecycle ``ComponentRegistry``. Purely observational metadata — no
kernel redesign, no service container changes.

Mirrors the Track A ``atlas/research/wiring.py`` pattern.
"""

from __future__ import annotations

from atlas.evolution.governance.constraint_registry import ConstraintRegistry
from atlas.lifecycle.component_definitions import CORE_COMPONENTS
from atlas.lifecycle.models import ComponentMetadata
from atlas.toolchain.evolution_integration import (
    GOV_009_RULE_ID,
    ToolchainIngestBridge,
    ToolchainIngestSink,
    register_gov_009,
)


def toolchain_evolution_component() -> ComponentMetadata:
    """Return the Track B evolution-integration metadata (observational only)."""
    return ComponentMetadata(
        name="toolchain_evolution",
        package="atlas.toolchain.evolution_integration",
        module_path="atlas.toolchain.evolution_integration.ToolchainIngestBridge",
        description=(
            "Capability Track B governed skill-activation ingest: "
            "ToolchainEvolutionTracker + ToolchainIngestBridge + GOV-009."
        ),
        version=1,
        dependencies=[
            "evolution_autonomy",
            "skill_registry",
        ],
        provided_capabilities=[
            "skill_activation_governed_ingest",
        ],
    )


def register_toolchain_evolution_component(registry: _ComponentRegistrar) -> None:
    """Add the toolchain evolution component metadata to a ComponentRegistry.

    The registry is expected to expose ``register(metadata)`` following the
    lifecycle ComponentRegistry pattern. Registration is additive.
    """
    metadata = toolchain_evolution_component()
    registry.register(metadata)
    def register(self, metadata: ComponentMetadata) -> None: ...


class _ComponentRegistrar:
    """Duck-typed registration surface (matches lifecycle ComponentRegistry)."""

    def register(self, metadata: ComponentMetadata) -> None: ...


def toolchain_component() -> ComponentMetadata:
    """Return the Track B component metadata (observational only)."""
    return ComponentMetadata(
        name="toolchain",
        package="atlas.toolchain",
        module_path="atlas.toolchain.registry.SkillRegistry",
        description=(
            "Capability Track B: skill registry, tool chain planner, "
            "tool effectiveness tracker, and toolchain data models."
        ),
        version=1,
        dependencies=[
            "tool_engine",
        ],
        provided_capabilities=[
            "skill_registration",
            "skill_lookup",
            "tool_chain_planning",
            "tool_effectiveness_tracking",
        ],
    )


def register_toolchain_component(registry: _ComponentRegistrar) -> None:
    """Add the toolchain component metadata to a ComponentRegistry.

    The registry is expected to expose ``register(metadata)`` following the
    lifecycle ComponentRegistry pattern. Registration is additive.
    """
    metadata = toolchain_component()
    registry.register(metadata)


def toolchain_components() -> list[ComponentMetadata]:
    """Return the core component list extended with the toolchain component.

    Useful for callers (tests / boot introspection) that want the full
    metadata set in one place without mutating ``CORE_COMPONENTS``.
    """
    return [*CORE_COMPONENTS, toolchain_component()]
