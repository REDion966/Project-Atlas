"""
Atlas Understanding Layer — Phase 7.1 / 9.2a / 9.2b

The Understanding Layer sits between Memory and Cognition.
It transforms raw observations, memories, conversations, tool results,
knowledge, and structured experiences into structured semantic understanding.

This package contains only pure logic components.
No AI provider dependencies. No infrastructure dependencies.
No autonomous modification. No execution. No code generation.
"""

from atlas.understanding.experience_bridge import (
    BridgeResult,
    ExperienceBridge,
    ExperienceSource,
)
from atlas.understanding.storage_interface import (
    UnderstandingRestoreResult,
    UnderstandingStorage,
)
from atlas.understanding import serialization

__all__ = [
    "BridgeResult",
    "ExperienceBridge",
    "ExperienceSource",
    "UnderstandingRestoreResult",
    "UnderstandingStorage",
    "serialization",
]