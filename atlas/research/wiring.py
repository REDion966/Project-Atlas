"""Atlas Research — Component & Service Wiring Metadata (Phase 17.9).

Lightweight integration surface for Track A: a ``ComponentMetadata`` block
describing the research subsystem plus a registration helper that adds it
to the lifecycle ``ComponentRegistry``. Purely observational metadata — no
kernel redesign, no service container changes.
"""

from __future__ import annotations

from atlas.lifecycle.component_definitions import CORE_COMPONENTS
from atlas.lifecycle.models import ComponentMetadata


class _ComponentRegistrar:
    """Duck-typed registration surface (matches lifecycle ComponentRegistry)."""

    def register(self, metadata: ComponentMetadata) -> None: ...


def research_component() -> ComponentMetadata:
    """Return the Track A component metadata (observational only)."""
    return ComponentMetadata(
        name="research",
        package="atlas.research",
        module_path="atlas.research.capability_handlers.ResearchCapabilityFactory",
        description=(
            "Capability Track A: research planner, source adapters, "
            "knowledge extractor, claim verifier, storage, and evolution "
            "ingest bridge."
        ),
        version=1,
        dependencies=[
            "knowledge_manager",
            "evolution_memory",
            "execution_gateway",
        ],
        provided_capabilities=[
            "research.query",
            "research.verify",
            "research.summarize",
            "research.ingest",
        ],
    )


def register_research_component(registry: _ComponentRegistrar) -> None:
    """Add the research component metadata to a ComponentRegistry.

    The registry is expected to expose ``register(metadata)`` following the
    lifecycle ComponentRegistry pattern. Registration is additive.
    """
    metadata = research_component()
    registry.register(metadata)


def research_components() -> list[ComponentMetadata]:
    """Return the core component list extended with the research component.

    Useful for callers (tests / boot introspection) that want the full
    metadata set in one place without mutating ``CORE_COMPONENTS``.
    """
    return [*CORE_COMPONENTS, research_component()]
