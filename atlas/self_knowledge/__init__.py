"""Atlas Self-Knowledge (C5.1).

Deterministic, read-only projections over Atlas's existing authoritative
runtime sources. No registration, no persistence, no mutation, no model.
"""

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
    "CapabilityAvailability",
    "CapabilityDependency",
    "CapabilityEntry",
    "CapabilityKind",
    "CapabilityModel",
    "CapabilityModelBuilder",
    "CapabilitySource",
    "CapabilitySourceKind",
    "build_capability_model",
]
