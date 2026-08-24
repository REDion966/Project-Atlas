"""Atlas Post-Core F3 — Lifecycle Assessment.

Deterministic lifecycle assessment for capabilities/models/tools/skills.

Reuses existing:
  * F1 ``EnvironmentChange`` signals
  * F2 ``KnowledgeFreshnessAssessment`` signals
  * registry/lifecycle metadata via ``LifecycleTarget`` (built with duck-typed helpers)

Pure recommendation layer. Never mutates, never executes, never researches, never
approves proposals, never invokes governance/authorization/self-development.
"""

from atlas.evolution.lifecycle.models import (
    LifecycleAction,
    LifecycleAssessment,
    LifecycleAssessmentResult,
    LifecycleReason,
    LifecycleTarget,
    LifecycleTargetKind,
)
from atlas.evolution.lifecycle.assessor import CapabilityLifecycleAssessor
from atlas.evolution.lifecycle.targets import (
    target_from_capability,
    target_from_model,
    targets_from_registries,
    target_from_skill,
    target_from_tool,
)

__all__ = [
    "CapabilityLifecycleAssessor",
    "LifecycleAction",
    "LifecycleAssessment",
    "LifecycleAssessmentResult",
    "LifecycleReason",
    "LifecycleTarget",
    "LifecycleTargetKind",
    "target_from_capability",
    "target_from_model",
    "targets_from_registries",
    "target_from_skill",
    "target_from_tool",
]