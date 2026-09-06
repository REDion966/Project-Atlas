"""
Atlas Understanding Graph

Maintains a graph of concepts and their relationships.
Supports adding concepts, connecting them, and querying the graph.

Phase 7.1 — Understanding Engine.
"""

from collections import defaultdict
from datetime import timezone
from typing import Any

from atlas.understanding.models import (
    Concept,
    Relationship,
    RelationshipType,
)


def _aware_utc(dt: datetime) -> datetime:
    """Normalize a datetime to aware UTC for safe comparison."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class UnderstandingGraph:
    """
    An in-memory graph of concepts and their relationships.

    This is a pure logic component with no infrastructure dependencies.
    It maintains a directed graph where nodes are concepts and edges
    are typed relationships.

    The graph supports:
    - Adding and updating concepts.
    - Creating relationships between concepts.
    - Querying concepts by domain, label, or ID.
    - Finding paths between concepts.
    - Retrieving related concepts.
    """

    def __init__(self) -> None:
        self._concepts: dict[str, Concept] = {}
        self._relationships: list[Relationship] = []
        self._outgoing: dict[str, list[Relationship]] = defaultdict(list)
        self._incoming: dict[str, list[Relationship]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Concept management
    # ------------------------------------------------------------------

    def add_concept(self, concept: Concept) -> None:
        """
        Add a concept to the graph. If a concept with the same ID
        already exists, it is updated (frequency accumulated,
        confidence updated if higher, last_seen refreshed).

        Args:
            concept: The Concept to add or update.
        """
        if concept.concept_id in self._concepts:
            existing = self._concepts[concept.concept_id]
            existing.frequency += concept.frequency
            if concept.confidence > existing.confidence:
                existing.confidence = concept.confidence
            # Normalize timestamps to aware UTC for safe comparison
            if _aware_utc(concept.last_seen) > _aware_utc(existing.last_seen):
                existing.last_seen = concept.last_seen
            if concept.source:
                existing.source = concept.source
        else:
            self._concepts[concept.concept_id] = concept

    def add_concepts(self, concepts: list[Concept]) -> None:
        """Add multiple concepts to the graph."""
        for concept in concepts:
            self.add_concept(concept)

    def get_concept(self, concept_id: str) -> Concept | None:
        """Retrieve a concept by its ID."""
        return self._concepts.get(concept_id)

    def get_concept_by_label(self, label: str) -> Concept | None:
        """Find a concept by its label (case-insensitive)."""
        label_lower = label.lower()
        for concept in self._concepts.values():
            if concept.label.lower() == label_lower:
                return concept
        return None

    def get_all_concepts(self) -> list[Concept]:
        """Return all concepts in the graph."""
        return list(self._concepts.values())

    @property
    def concept_count(self) -> int:
        """Return the number of concepts in the graph."""
        return len(self._concepts)

    def remove_concept(self, concept_id: str) -> bool:
        """
        Remove a concept and all its relationships.

        Args:
            concept_id: The ID of the concept to remove.

        Returns:
            True if the concept was found and removed, False otherwise.
        """
        if concept_id not in self._concepts:
            return False

        del self._concepts[concept_id]

        self._relationships = [
            r for r in self._relationships
            if r.source_id != concept_id and r.target_id != concept_id
        ]

        self._outgoing.pop(concept_id, None)
        self._incoming.pop(concept_id, None)

        return True

    # ------------------------------------------------------------------
    # Relationship management
    # ------------------------------------------------------------------

    def add_relationship(self, relationship: Relationship) -> None:
        """
        Add a relationship between two concepts.

        If a relationship with the same source, target, and type
        already exists, its weight and confidence are updated.

        Args:
            relationship: The Relationship to add.
        """
        existing = self._find_relationship(
            relationship.source_id,
            relationship.target_id,
            relationship.relationship_type,
        )

        if existing is not None:
            existing.observed_count += 1
            existing.weight = max(existing.weight, relationship.weight)
            existing.confidence = max(existing.confidence, relationship.confidence)
            existing.last_observed = relationship.last_observed
        else:
            self._relationships.append(relationship)
            self._outgoing[relationship.source_id].append(relationship)
            self._incoming[relationship.target_id].append(relationship)

    def _find_relationship(
        self,
        source_id: str,
        target_id: str,
        rel_type: RelationshipType,
    ) -> Relationship | None:
        """Find an existing relationship matching source, target, and type."""
        for rel in self._relationships:
            if (rel.source_id == source_id
                    and rel.target_id == target_id
                    and rel.relationship_type == rel_type):
                return rel
        return None

    def get_relationships(
        self,
        concept_id: str | None = None,
    ) -> list[Relationship]:
        """
        Get relationships, optionally filtered by concept.

        Args:
            concept_id: If provided, returns only relationships
                involving this concept. Otherwise returns all.

        Returns:
            A list of Relationship instances.
        """
        if concept_id is None:
            return list(self._relationships)

        return [
            r for r in self._relationships
            if r.source_id == concept_id or r.target_id == concept_id
        ]

    def get_outgoing_relationships(
        self,
        concept_id: str,
    ) -> list[Relationship]:
        """Get relationships where the concept is the source."""
        return list(self._outgoing.get(concept_id, []))

    def get_incoming_relationships(
        self,
        concept_id: str,
    ) -> list[Relationship]:
        """Get relationships where the concept is the target."""
        return list(self._incoming.get(concept_id, []))

    @property
    def relationship_count(self) -> int:
        """Return the number of relationships in the graph."""
        return len(self._relationships)

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def find_related_concepts(
        self,
        concept_id: str,
        max_depth: int = 1,
    ) -> list[Concept]:
        """
        Find concepts related to a given concept up to a maximum depth.

        Args:
            concept_id: The starting concept ID.
            max_depth: Maximum traversal depth (default: 1).

        Returns:
            A list of related Concept instances.
        """
        if concept_id not in self._concepts:
            return []

        visited: set[str] = {concept_id}
        current_level: set[str] = {concept_id}
        results: list[Concept] = []

        for _ in range(max_depth):
            next_level: set[str] = set()

            for cid in current_level:
                for rel in self._outgoing.get(cid, []):
                    if rel.target_id not in visited:
                        next_level.add(rel.target_id)
                        visited.add(rel.target_id)
                for rel in self._incoming.get(cid, []):
                    if rel.source_id not in visited:
                        next_level.add(rel.source_id)
                        visited.add(rel.source_id)

            for nid in next_level:
                concept = self._concepts.get(nid)
                if concept is not None:
                    results.append(concept)

            current_level = next_level

        return results

    def find_path(
        self,
        source_id: str,
        target_id: str,
        max_length: int = 5,
    ) -> list[list[Relationship]]:
        """
        Find all paths between two concepts up to a maximum length.

        Args:
            source_id: The starting concept ID.
            target_id: The target concept ID.
            max_length: Maximum path length.

        Returns:
            A list of paths, where each path is a list of Relationships.
        """
        if source_id not in self._concepts or target_id not in self._concepts:
            return []

        paths: list[list[Relationship]] = []

        def _dfs(
            current: str,
            target: str,
            visited: set[str],
            path: list[Relationship],
        ):
            if len(path) > max_length:
                return

            if current == target and path:
                paths.append(list(path))
                return

            for rel in self._outgoing.get(current, []):
                if rel.target_id not in visited:
                    visited.add(rel.target_id)
                    path.append(rel)
                    _dfs(rel.target_id, target, visited, path)
                    path.pop()
                    visited.discard(rel.target_id)

        _dfs(source_id, target_id, {source_id}, [])
        return paths

    def clear(self) -> None:
        """Remove all concepts and relationships."""
        self._concepts.clear()
        self._relationships.clear()
        self._outgoing.clear()
        self._incoming.clear()