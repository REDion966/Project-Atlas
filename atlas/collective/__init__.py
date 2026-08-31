"""Atlas Collective — Governed Collective Learning (P4).

Reuses existing governance (ApprovalManager) + knowledge/experience seams.
Never duplicates a second approval/memory/identity/experience subsystem.

The collective layer has three explicit states:

  * CANDIDATE  — extracted, pending Owner review
  * APPROVED   — approved collective knowledge (bounded, advisory)
  * REJECTED   — rejected candidate (retained for deduplication/audit)

Collective knowledge is advisory context only — it never executes anything.
"""

from atlas.collective.models import (
    CollectiveCandidate,
    CollectiveKind,
    CollectiveKnowledge,
    CollectiveProvenance,
    CollectiveStatus,
)
from atlas.collective.repository import CollectiveRepository
from atlas.collective.governance import CollectiveGovernance

__all__ = [
    "CollectiveCandidate",
    "CollectiveGovernance",
    "CollectiveKind",
    "CollectiveKnowledge",
    "CollectiveProvenance",
    "CollectiveRepository",
    "CollectiveStatus",
]
