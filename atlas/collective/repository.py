"""Atlas Collective — CollectiveRepository (P4).

Bounded, in-memory store for:
  * CANDIDATE records (pending Owner review)
  * APPROVED collective knowledge
  * REJECTED candidates (retained for deduplication / audit)

No persistence — schema v11, B1.2 in-memory scoping precedent. Every record
is frozen; the repository never mutates one. Bounds prevent unbounded growth;
fail-closed on malformed input (never raises). Candidate → collective
promotion changes STATUS, never provenance.

No infrastructure, no kernel, no runtime, no AI, no governance.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from atlas.collective.models import (
    CollectiveCandidate,
    CollectiveKnowledge,
    CollectiveStatus,
)


class CollectiveRepository:
    """Bounded, in-memory collective-learning store."""

    def __init__(
        self,
        max_candidates: int = 1_000,
        max_collective: int = 1_000,
    ) -> None:
        if max_candidates <= 0 or max_collective <= 0:
            raise ValueError("All bounds must be positive integers (fail-closed)")
        self._max_candidates = max_candidates
        self._max_collective = max_collective
        self._candidates: deque[CollectiveCandidate] = deque(maxlen=max_candidates)
        self._collective: deque[CollectiveKnowledge] = deque(maxlen=max_collective)
        self._rejected: deque[CollectiveCandidate] = deque(maxlen=max_candidates)

    # ------------------------------------------------------------------
    # Candidates
    # ------------------------------------------------------------------

    def store_candidate(self, record: CollectiveCandidate) -> None:
        """Store a candidate (bounded append)."""
        if not isinstance(record, CollectiveCandidate):
            return
        if record.status is not CollectiveStatus.CANDIDATE:
            return
        self._candidates.append(record)

    def get_candidates(self, n: int = 100) -> list[CollectiveCandidate]:
        """Return the most recent candidates (newest first)."""
        if n <= 0:
            return []
        return list(reversed(self._candidates))[:n]

    def get_candidate(self, candidate_id: str) -> CollectiveCandidate | None:
        """Return a single candidate by id, or None."""
        if not isinstance(candidate_id, str):
            return None
        for r in self._candidates:
            if r.candidate_id == candidate_id:
                return r
        return None

    def remove_candidate(self, candidate_id: str) -> CollectiveCandidate | None:
        """Remove and return a candidate by id, or None when unknown."""
        if not isinstance(candidate_id, str):
            return None
        for r in list(self._candidates):
            if r.candidate_id == candidate_id:
                try:
                    self._candidates.remove(r)
                except ValueError:
                    return r
                return r
        return None

    @property
    def candidate_count(self) -> int:
        return len(self._candidates)

    # ------------------------------------------------------------------
    # Collective (APPROVED) knowledge
    # ------------------------------------------------------------------

    def store_collective(self, record: CollectiveKnowledge) -> None:
        """Store an approved collective record (bounded append)."""
        if not isinstance(record, CollectiveKnowledge):
            return
        if record.status is not CollectiveStatus.APPROVED:
            return
        self._collective.append(record)

    def get_collective(self, n: int = 100) -> list[CollectiveKnowledge]:
        """Return the most recent approved records (newest first)."""
        if n <= 0:
            return []
        return list(reversed(self._collective))[:n]

    def get_collective_by_id(self, knowledge_id: str) -> CollectiveKnowledge | None:
        """Return a single collective record by id, or None."""
        if not isinstance(knowledge_id, str):
            return None
        for r in self._collective:
            if r.knowledge_id == knowledge_id:
                return r
        return None

    @property
    def collective_count(self) -> int:
        return len(self._collective)

    # ------------------------------------------------------------------
    # Rejected
    # ------------------------------------------------------------------

    def store_rejected(self, record: CollectiveCandidate) -> None:
        """Store a rejected candidate (bounded append, for audit/deduplication)."""
        if not isinstance(record, CollectiveCandidate):
            return
        if record.status is not CollectiveStatus.REJECTED:
            return
        self._rejected.append(record)

    def get_rejected(self, n: int = 100) -> list[CollectiveCandidate]:
        """Return the most recent rejected candidates (newest first)."""
        if n <= 0:
            return []
        return list(reversed(self._rejected))[:n]

    @property
    def rejected_count(self) -> int:
        return len(self._rejected)

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return a bounded summary of repository state."""
        return {
            "candidate_count": self.candidate_count,
            "collective_count": self.collective_count,
            "rejected_count": self.rejected_count,
            "max_candidates": self._max_candidates,
            "max_collective": self._max_collective,
            "scoped_by": "collective (approved only)",
            "persisted": False,
        }

    def clear(self) -> None:
        """Clear all stored records."""
        self._candidates.clear()
        self._collective.clear()
        self._rejected.clear()
