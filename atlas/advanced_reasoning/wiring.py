"""Atlas Advanced Reasoning — Component & Service Wiring Metadata (Track D).

Lightweight integration surface for Track D: ``ComponentMetadata`` blocks
describing the advanced-reasoning subsystem plus registration helpers that add
them to the lifecycle ``ComponentRegistry``. Purely observational metadata — no
kernel redesign, no service container changes.

Mirrors the Track A ``atlas/research/wiring.py``, Track B
``atlas/toolchain/wiring.py``, and Track C ``atlas/longterm/wiring.py``
patterns.
"""

from __future__ import annotations

from atlas.lifecycle.component_definitions import CORE_COMPONENTS
from atlas.lifecycle.models import ComponentMetadata


class _ComponentRegistrar:
    """Duck-typed registration surface (matches lifecycle ComponentRegistry)."""

    def register(self, metadata: ComponentMetadata) -> None: ...


#: Capabilities provided by the Track D capability factory.
_REASONING_CAPABILITIES: tuple[str, ...] = (
    "reasoning.trace",
    "reasoning.causal",
    "reasoning.counterfactual",
    "reasoning.hypotheses",
    "reasoning.verify",
    "reasoning.meta",
    "reasoning.ingest",
)


def advanced_reasoning_component() -> ComponentMetadata:
    """Return the Track D component metadata (observational only)."""
    return ComponentMetadata(
        name="advanced_reasoning",
        package="atlas.advanced_reasoning",
        module_path="atlas.advanced_reasoning.capability_handlers.AdvancedReasoningCapabilityFactory",
        description=(
            "Capability Track D: multi-step reasoning, causal/counterfactual "
            "reasoning, hypothesis generation, self-verification, "
            "meta-reasoning, reasoning repository, and capability handlers."
        ),
        version=1,
        dependencies=[
            "reasoning",
            "knowledge_base",
            "world_model",
        ],
        provided_capabilities=list(_REASONING_CAPABILITIES),
    )


def advanced_reasoning_evolution_component() -> ComponentMetadata:
    """Return the Track D evolution-integration metadata (observational only)."""
    return ComponentMetadata(
        name="advanced_reasoning_evolution",
        package="atlas.advanced_reasoning.evolution_integration",
        module_path="atlas.advanced_reasoning.evolution_integration.ReasoningIngestBridge",
        description=(
            "Capability Track D governed reasoning ingest: "
            "ReasoningEvolutionTracker + ReasoningIngestBridge + GOV-011."
        ),
        version=1,
        dependencies=[
            "evolution_autonomy",
            "knowledge_base",
        ],
        provided_capabilities=["reasoning_ingest_governed"],
    )


def register_advanced_reasoning_component(registry: _ComponentRegistrar) -> None:
    """Add the advanced-reasoning component metadata to a ComponentRegistry.

    The registry is expected to expose ``register(metadata)`` following the
    lifecycle ComponentRegistry pattern. Registration is additive.
    """
    registry.register(advanced_reasoning_component())


def register_advanced_reasoning_evolution_component(
    registry: _ComponentRegistrar,
) -> None:
    """Add the advanced-reasoning evolution metadata to a ComponentRegistry.

    The registry is expected to expose ``register(metadata)`` following the
    lifecycle ComponentRegistry pattern. Registration is additive.
    """
    registry.register(advanced_reasoning_evolution_component())


def advanced_reasoning_components() -> list[ComponentMetadata]:
    """Return the core component list extended with the Track D components.

    Useful for callers (tests / boot introspection) that want the full
    metadata set in one place without mutating ``CORE_COMPONENTS``.
    """
    return [
        *CORE_COMPONENTS,
        advanced_reasoning_component(),
        advanced_reasoning_evolution_component(),
    ]