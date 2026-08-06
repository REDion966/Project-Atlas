"""Atlas Long-Term Learning — Component & Service Wiring Metadata (Track C).

Lightweight integration surface for Track C: ``ComponentMetadata`` blocks
describing the long-term subsystem plus registration helpers that add them
to the lifecycle ``ComponentRegistry``. Purely observational metadata — no
kernel redesign, no service container changes.

Mirrors the Track A ``atlas/research/wiring.py`` and Track B
``atlas/toolchain/wiring.py`` patterns.
"""

from __future__ import annotations

from atlas.lifecycle.component_definitions import CORE_COMPONENTS
from atlas.lifecycle.models import ComponentMetadata


class _ComponentRegistrar:
    """Duck-typed registration surface (matches lifecycle ComponentRegistry)."""

    def register(self, metadata: ComponentMetadata) -> None: ...


def longterm_component() -> ComponentMetadata:
    """Return the Track C component metadata (observational only)."""
    return ComponentMetadata(
        name="longterm",
        package="atlas.longterm",
        module_path="atlas.longterm.capability_handlers.LongTermCapabilityFactory",
        description=(
            "Capability Track C: episodic recorder, procedure extractor, "
            "consolidator, episodic/procedural repositories, and long-term "
            "storage protocol."
        ),
        version=1,
        dependencies=[
            "experience_repository",
            "memory_service",
        ],
        provided_capabilities=[
            "memory.episodic_query",
            "memory.procedure_query",
            "memory.consolidate",
        ],
    )


def longterm_evolution_component() -> ComponentMetadata:
    """Return the Track C evolution-integration metadata (observational only)."""
    return ComponentMetadata(
        name="longterm_evolution",
        package="atlas.longterm.evolution_integration",
        module_path="atlas.longterm.evolution_integration.LongTermIngestBridge",
        description=(
            "Capability Track C governed consolidation ingest: "
            "LongTermEvolutionTracker + LongTermIngestBridge + GOV-010."
        ),
        version=1,
        dependencies=[
            "evolution_autonomy",
            "memory_service",
        ],
        provided_capabilities=[
            "memory_consolidation_governed_ingest",
        ],
    )


def register_longterm_component(registry: _ComponentRegistrar) -> None:
    """Add the long-term component metadata to a ComponentRegistry.

    The registry is expected to expose ``register(metadata)`` following the
    lifecycle ComponentRegistry pattern. Registration is additive.
    """
    metadata = longterm_component()
    registry.register(metadata)


def register_longterm_evolution_component(registry: _ComponentRegistrar) -> None:
    """Add the long-term evolution component metadata to a ComponentRegistry.

    The registry is expected to expose ``register(metadata)`` following the
    lifecycle ComponentRegistry pattern. Registration is additive.
    """
    metadata = longterm_evolution_component()
    registry.register(metadata)


def longterm_components() -> list[ComponentMetadata]:
    """Return the core component list extended with the long-term components.

    Useful for callers (tests / boot introspection) that want the full
    metadata set in one place without mutating ``CORE_COMPONENTS``.
    """
    return [
        *CORE_COMPONENTS,
        longterm_component(),
        longterm_evolution_component(),
    ]
