"""Atlas Toolchain — Component & Service Wiring Metadata (Phase 18.x).

Lightweight integration surface for Track B: a ``ComponentMetadata`` block
describing the toolchain subsystem plus a registration helper that adds it
to the lifecycle ``ComponentRegistry``. Purely observational metadata — no
kernel redesign, no service container changes.

Mirrors the Track A ``atlas/research/wiring.py`` pattern.
"""

from __future__ import annotations

from atlas.lifecycle.component_definitions import CORE_COMPONENTS
from atlas.lifecycle.models import ComponentMetadata


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