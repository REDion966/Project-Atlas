"""
Atlas Belief Manager — Phase 8.0 Cognitive Identity Foundation.

Maintains what Atlas currently believes about itself and its domain.
Beliefs change gradually through accumulated evidence — never instantly.
Pure logic. No AI. No infrastructure.
"""

from datetime import datetime
from typing import Callable

from atlas.identity.models import BeliefConfidence, CoreBelief


class BeliefManager:
    """
    Manages Atlas's core beliefs with gradual confidence evolution.

    Beliefs start TENTATIVE and strengthen through repeated evidence.
    When evidence contradicts a belief, confidence drops gradually.
    Obsolete beliefs are retired rather than deleted.
    """

    def __init__(self, memory: "IdentityMemory | None" = None):
        # Defer import to avoid circular dependency
        if memory is None:
            from atlas.identity.identity_memory import IdentityMemory
            memory = IdentityMemory()

        self._memory = memory
        self._belief_counter = 0

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def add_belief(
        self,
        statement: str,
        category: str = "general",
        confidence: BeliefConfidence = BeliefConfidence.TENTATIVE,
    ) -> CoreBelief:
        """
        Add a new belief. Identity must NOT gain beliefs instantly —
        new beliefs always start at TENTATIVE unless strong evidence exists.
        """
        self._belief_counter += 1
        belief = CoreBelief(
            belief_id=f"BLF-{self._belief_counter:06d}",
            statement=statement,
            category=category,
            confidence=confidence,
            evidence_count=0,
        )
        self._memory.store_belief(belief)
        return belief

    def strengthen_belief(
        self,
        belief_id: str,
        evidence_strength: float = 1.0,
    ) -> CoreBelief | None:
        """
        Increase confidence in an existing belief.

        The more evidence, the higher the confidence. But confidence
        rises gradually — it NEVER jumps from TENTATIVE to ESTABLISHED
        in a single step.
        """
        existing = self._memory.find_belief_by_id(belief_id)
        if existing is None:
            return None

        new_evidence = getattr(existing, "evidence_count", 0) + 1
        new_confidence = self._calculate_confidence(
            getattr(existing, "confidence", BeliefConfidence.TENTATIVE),
            new_evidence,
            evidence_strength,
        )

        updated = CoreBelief(
            belief_id=existing.belief_id,
            statement=existing.statement,
            category=getattr(existing, "category", "general"),
            confidence=new_confidence,
            evidence_count=new_evidence,
            established_at=getattr(existing, "established_at", datetime.now()),
            last_updated=datetime.now(),
            retired_at=getattr(existing, "retired_at", None),
        )

        # Remove old version, store updated version
        self._memory.remove_belief(existing.belief_id)
        self._memory.store_belief(updated)
        return updated

    def weaken_belief(
        self,
        belief_id: str,
        contradiction_strength: float = 1.0,
    ) -> CoreBelief | None:
        """
        Reduce confidence in a belief when contradictory evidence appears.
        A strongly contradicted belief may become RETIRED.
        """
        existing = self._memory.find_belief_by_id(belief_id)
        if existing is None:
            return None

        current_conf = getattr(existing, "confidence", BeliefConfidence.TENTATIVE)
        evidence_count = max(0, getattr(existing, "evidence_count", 0) - int(contradiction_strength * 2))

        new_confidence = self._calculate_weakened_confidence(current_conf)

        retired_at = None
        if new_confidence == BeliefConfidence.RETIRED:
            retired_at = datetime.now()

        updated = CoreBelief(
            belief_id=existing.belief_id,
            statement=existing.statement,
            category=getattr(existing, "category", "general"),
            confidence=new_confidence,
            evidence_count=evidence_count,
            established_at=getattr(existing, "established_at", datetime.now()),
            last_updated=datetime.now(),
            retired_at=retired_at,
        )

        # Remove old version, store updated version
        self._memory.remove_belief(existing.belief_id)
        self._memory.store_belief(updated)
        return updated

    def retire_belief(self, belief_id: str) -> CoreBelief | None:
        """
        Explicitly retire an obsolete belief.
        Retired beliefs are preserved in history, not deleted.
        """
        existing = self._memory.find_belief_by_id(belief_id)
        if existing is None:
            return None

        updated = CoreBelief(
            belief_id=existing.belief_id,
            statement=existing.statement,
            category=getattr(existing, "category", "general"),
            confidence=BeliefConfidence.RETIRED,
            evidence_count=getattr(existing, "evidence_count", 0),
            established_at=getattr(existing, "established_at", datetime.now()),
            last_updated=datetime.now(),
            retired_at=datetime.now(),
        )

        # Remove old version, store updated version
        self._memory.remove_belief(existing.belief_id)
        self._memory.store_belief(updated)
        return updated

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_active_beliefs(self, n: int | None = None) -> list[CoreBelief]:
        """Return beliefs that are not retired."""
        beliefs = self._memory.get_beliefs(n)
        return [b for b in beliefs if getattr(b, "confidence", None) != BeliefConfidence.RETIRED]

    def get_beliefs_by_category(self, category: str, n: int = 50) -> list[CoreBelief]:
        return self._memory.get_beliefs_by_category(category, n)

    def get_beliefs_by_confidence(
        self,
        min_confidence: BeliefConfidence = BeliefConfidence.MODERATE,
        n: int = 50,
    ) -> list[CoreBelief]:
        """Return beliefs at or above a confidence threshold."""
        active = self.get_active_beliefs()
        confidence_order = {
            BeliefConfidence.ESTABLISHED: 5,
            BeliefConfidence.STRONG: 4,
            BeliefConfidence.MODERATE: 3,
            BeliefConfidence.TENTATIVE: 2,
            BeliefConfidence.WEAK: 1,
            BeliefConfidence.RETIRED: 0,
        }
        threshold = confidence_order.get(min_confidence, 0)
        return [
            b for b in active
            if confidence_order.get(getattr(b, "confidence", BeliefConfidence.WEAK), 0) >= threshold
        ][:n]

    def summary(self) -> dict:
        """Return a summary of belief state."""
        all_beliefs = self._memory.get_beliefs()
        active = self.get_active_beliefs()
        by_category: dict[str, int] = {}
        by_confidence: dict[str, int] = {}
        for b in active:
            cat = getattr(b, "category", "general")
            conf = getattr(b, "confidence", BeliefConfidence.TENTATIVE).value
            by_category[cat] = by_category.get(cat, 0) + 1
            by_confidence[conf] = by_confidence.get(conf, 0) + 1

        return {
            "total": len(all_beliefs),
            "active": len(active),
            "retired": len(all_beliefs) - len(active),
            "by_category": by_category,
            "by_confidence": by_confidence,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_confidence(
        current: BeliefConfidence,
        evidence_count: int,
        evidence_strength: float,
    ) -> BeliefConfidence:
        """Confidence rises gradually — no single-step jumps."""
        confidence_order = {
            BeliefConfidence.RETIRED: 0,
            BeliefConfidence.WEAK: 1,
            BeliefConfidence.TENTATIVE: 2,
            BeliefConfidence.MODERATE: 3,
            BeliefConfidence.STRONG: 4,
            BeliefConfidence.ESTABLISHED: 5,
        }
        reverse_order = {v: k for k, v in confidence_order.items()}

        current_level = confidence_order.get(current, 0)
        # Each piece of evidence moves up increments, not levels
        # Requires ~20 evidence to go from TENTATIVE to ESTABLISHED
        increments = evidence_strength * (evidence_count ** 0.5) * 0.3
        new_level = min(5, max(0, current_level + int(increments)))

        return reverse_order.get(new_level, current)

    @staticmethod
    def _calculate_weakened_confidence(current: BeliefConfidence) -> BeliefConfidence:
        """Drop one confidence level per contradiction."""
        order = [
            BeliefConfidence.ESTABLISHED,
            BeliefConfidence.STRONG,
            BeliefConfidence.MODERATE,
            BeliefConfidence.TENTATIVE,
            BeliefConfidence.WEAK,
            BeliefConfidence.RETIRED,
        ]
        try:
            idx = order.index(current)
            return order[min(idx + 1, len(order) - 1)]
        except ValueError:
            return BeliefConfidence.WEAK

    @property
    def memory(self):
        return self._memory