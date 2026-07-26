"""
RelationshipConsolidator — Phase 8.2.1

Merges duplicate relationships and strengthens confidence through
repeated evidence. Prevents graph explosion by deduplicating edges.

Pure logic. Deterministic matching on source_id + target_id + type.
"""

from datetime import datetime

from atlas.understanding.models import Relationship, RelationshipType


class RelationshipConsolidator:
    """
    Consolidates duplicate relationships in the understanding graph.

    Two relationships are considered duplicates when they share:
      - Same source concept ID
      - Same target concept ID
      - Same relationship type

    When merged, confidence and weight increase toward 1.0 from
    repeated evidence. Observation counts accumulate.
    """

    def __init__(self):
        self._merge_counter = 0

    def consolidate(
        self,
        new_relationships: list[Relationship],
        existing_relationships: list[Relationship],
    ) -> list[Relationship]:
        """
        Merge new relationships into existing ones, deduplicating.

        Returns the consolidated list of relationships. For each new
        relationship that matches an existing one, the existing one is
        strengthened. For genuinely new relationships, they pass through.

        Args:
            new_relationships: Newly detected relationships.
            existing_relationships: Previously stored relationships.

        Returns:
            Consolidated list — existing matches updated, new ones appended.
        """
        result: list[Relationship] = []
        # Build index of existing relationships by composite key
        existing_index: dict[str, int] = {}
        for i, rel in enumerate(existing_relationships):
            key = self._key(rel)
            existing_index[key] = i

        # Start with existing relationships (will be mutated)
        result = list(existing_relationships)

        for new_rel in new_relationships:
            key = self._key(new_rel)
            if key in existing_index:
                # Merge into existing
                idx = existing_index[key]
                result[idx] = self._merge(result[idx], new_rel)
            else:
                # New unique relationship
                result.append(new_rel)
                existing_index[key] = len(result) - 1

        return result

    def try_merge_with_existing(
        self,
        new_relationship: Relationship,
        existing_relationships: list[Relationship],
    ) -> Relationship | None:
        """
        Try to merge a single new relationship into existing ones.

        Returns the merged relationship if found, None otherwise.
        """
        new_key = self._key(new_relationship)
        for existing in existing_relationships:
            if self._key(existing) == new_key:
                return self._merge(existing, new_relationship)
        return None

    @staticmethod
    def _key(rel: Relationship) -> str:
        """Generate a composite key for deduplication."""
        return f"{rel.source_id}|{rel.target_id}|{rel.relationship_type.name}"

    def _merge(self, primary: Relationship, secondary: Relationship) -> Relationship:
        """
        Merge secondary relationship into primary.

        Confidence and weight increase gradually from repeated evidence.
        Observation count accumulates.
        """
        self._merge_counter += 1

        new_observed = primary.observed_count + secondary.observed_count
        # Weight increases toward 1.0 from repeated observations
        new_weight = min(0.98, primary.weight + (1 - primary.weight) * 0.3)
        # Confidence increases from repeated confirmation
        new_confidence = min(0.98, primary.confidence + (1 - primary.confidence) * 0.2)

        return Relationship(
            source_id=primary.source_id,
            target_id=primary.target_id,
            relationship_type=primary.relationship_type,
            weight=round(new_weight, 4),
            confidence=round(new_confidence, 4),
            observed_count=new_observed,
            first_observed=min(primary.first_observed, secondary.first_observed),
            last_observed=max(primary.last_observed, secondary.last_observed),
        )

    @property
    def merge_count(self) -> int:
        return self._merge_counter