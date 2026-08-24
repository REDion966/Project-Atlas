"""Atlas Post-Core — Environment & World-State Adaptation Foundation (F1).

Additive, observational foundation for detecting changes in Atlas's external
and runtime environment and normalizing them into the existing
observation/event architecture.

F1 is deliberately NOT the Adaptation Engine: it observes, normalizes,
classifies, and emits changes. It never approves, never modifies, never
executes proposals, and never bypasses governance.

This package reuses — and never duplicates — the existing:

  * ``EventBus``            (event emission)
  * ``SelfObservationEngine`` (bounded observation recording)
  * model / provider / tool / capability / skill registries
  * ``EvolutionScheduler``  (as the future periodic trigger seam)

Pure infrastructure plus deterministic logic. No AI. No kernel access.
No governance imports. No new memory store.
"""

from atlas.evolution.environment.models import (
    EnvironmentChange,
    EnvironmentChangeType,
    EnvironmentDomain,
    EnvironmentEntity,
    EnvironmentObservationResult,
    EnvironmentProviderFailure,
    EnvironmentState,
    ObservationReliability,
)
from atlas.evolution.environment.detector import (
    EnvironmentChangeDetector,
    canonicalize,
)
from atlas.evolution.environment.providers import (
    CapabilityRegistryObserver,
    EnvironmentProvider,
    ModelProfileObserver,
    ProviderAvailabilityObserver,
    RuntimeEnvironmentObserver,
    SkillRegistryObserver,
    ToolRegistryObserver,
)
from atlas.evolution.environment.observer import EnvironmentObserver

__all__ = [
    "CapabilityRegistryObserver",
    "EnvironmentChange",
    "EnvironmentChangeDetector",
    "EnvironmentChangeType",
    "EnvironmentDomain",
    "EnvironmentEntity",
    "EnvironmentObservationResult",
    "EnvironmentObserver",
    "EnvironmentProvider",
    "EnvironmentProviderFailure",
    "EnvironmentState",
    "ModelProfileObserver",
    "ObservationReliability",
    "ProviderAvailabilityObserver",
    "RuntimeEnvironmentObserver",
    "SkillRegistryObserver",
    "ToolRegistryObserver",
    "canonicalize",
]