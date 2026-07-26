"""
Atlas Identity Package — Phase 8.0 Cognitive Identity Foundation.

Atlas's own persistent internal identity. This is NOT user identity.
Identity defines who Atlas is, what Atlas believes, what Atlas can do,
and how Atlas makes decisions.

Identity NEVER edits code.
Identity NEVER modifies itself autonomously.
Identity provides stable context to all cognitive subsystems.
Evolution may PROPOSE identity updates — only approved learning changes identity.
"""

from atlas.identity.models import (
    CapabilityProfile,
    CoreBelief,
    CoreIdentity,
    CorePrinciple,
    DecisionStyle,
    EngineeringPreference,
    ImprovementEntry,
    LongTermGoal,
    StrengthProfile,
    WeaknessProfile,
)
from atlas.identity.identity_memory import IdentityMemory
from atlas.identity.belief_manager import BeliefManager
from atlas.identity.capability_profiler import CapabilityProfiler
from atlas.identity.decision_style_manager import DecisionStyleManager
from atlas.identity.identity_engine import IdentityEngine

__all__ = [
    "CoreIdentity",
    "LongTermGoal",
    "CorePrinciple",
    "CoreBelief",
    "EngineeringPreference",
    "CapabilityProfile",
    "StrengthProfile",
    "WeaknessProfile",
    "DecisionStyle",
    "ImprovementEntry",
    "IdentityMemory",
    "BeliefManager",
    "CapabilityProfiler",
    "DecisionStyleManager",
    "IdentityEngine",
]