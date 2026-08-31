"""Atlas Interaction — Per-user preference & correction capture (P3/B3.1).

Pure logic package for capturing per-user preferences and corrections with
immutable provenance, scoped by principal. In-memory scoping first (the
B1.2 precedent); persistence/namespacing is deferred to a later approved
batch.

No infrastructure imports. No AI. No execution. No governance. No schema.
"""

from atlas.interaction.models import (
    CorrectionRecord,
    InteractionKind,
    PreferenceRecord,
    Provenance,
)
from atlas.interaction.repository import InteractionRepository
from atlas.interaction.recorder import InteractionRecorder

__all__ = [
    "CorrectionRecord",
    "InteractionKind",
    "InteractionRecorder",
    "InteractionRepository",
    "PreferenceRecord",
    "Provenance",
]
