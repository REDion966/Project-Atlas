"""Atlas Self-Knowledge (C5.1 capability model + Phase 1.2 architecture model).

Deterministic, read-only projections over Atlas's existing authoritative
runtime sources. No registration, no persistence, no mutation, no model.
"""

from atlas.self_knowledge.architecture_model import (
    ArchitectureModel,
    ArchitectureModelBuilder,
    ArchitectureSource,
    ArchitectureSourceKind,
    ComponentArchitectureEntry,
    LocateResult,
    SubsystemEntry,
    build_architecture_model,
)
from atlas.self_knowledge.capability_model import (
    CapabilityAvailability,
    CapabilityDependency,
    CapabilityEntry,
    CapabilityKind,
    CapabilityModel,
    CapabilityModelBuilder,
    CapabilitySource,
    CapabilitySourceKind,
    build_capability_model,
)

__all__ = [
    "ArchitectureModel",
    "ArchitectureModelBuilder",
    "ArchitectureSource",
    "ArchitectureSourceKind",
    "CapabilityAvailability",
    "CapabilityDependency",
    "CapabilityEntry",
    "CapabilityKind",
    "CapabilityModel",
    "CapabilityModelBuilder",
    "CapabilitySource",
    "CapabilitySourceKind",
    "ComponentArchitectureEntry",
    "LocateResult",
    "SubsystemEntry",
    "build_architecture_model",
    "build_capability_model",
]
