"""
Atlas World Graph

Entity → Relation → Entity graph for the world model.
Supports causal relations, entity relationships, and graph queries.

Phase 7.4 — World Model Foundation.
"""

from collections import defaultdict
from datetime import datetime
from typing import Any

from atlas.world_model.models import (
    CausalRelation,
    Entity,
    RelationType,
)


class WorldGraph:
    """
    Maintains a graph of entities and their causal/relational connections.

    Pure logic component. No infrastructure dependencies.
    Supports adding/updating entities, creating relations, and
    querying the graph for causal chains.
    """

    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}
        self._relations: list[CausalRelation] = []
        self._outgoing: dict[str, list[CausalRelation]] = defaultdict(list)
        self._incoming: dict[str, list[CausalRelation]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Entity management
    # ------------------------------------------------------------------

    def add_entity(self, entity: Entity) -> None:
        """Add or update an entity."""
        if entity.entity_id in self._entities:
            existing = self._entities[entity.entity_id]
            existing.status = entity.status
            existing.confidence = max(existing.confidence, entity.confidence)
            existing.last_updated = datetime.now()
            if entity.description:
                existing.description = entity.description
        else:
            self._entities[entity.entity_id] = entity

    def get_entity(self, entity_id: str) -> Entity | None:
        """Retrieve an entity by ID."""
        return self._entities.get(entity_id)

    def get_all_entities(self) -> list[Entity]:
        """Return all entities."""
        return list(self._entities.values())

    @property
    def entity_count(self) -> int:
        return len(self._entities)

    # ------------------------------------------------------------------
    # Relation management
    # ------------------------------------------------------------------

    def add_relation(self, relation: CausalRelation) -> None:
        """Add a causal relation between two entities."""
        for existing in self._relations:
            if (existing.source_id == relation.source_id
                    and existing.target_id == relation.target_id
                    and existing.relation_type == relation.relation_type):
                existing.observed_count += 1
                existing.confidence = min(existing.confidence + 0.05, 1.0)
                existing.last_observed = datetime.now()
                return

        self._relations.append(relation)
        self._outgoing[relation.source_id].append(relation)
        self._incoming[relation.target_id].append(relation)

    def get_relations(
        self,
        entity_id: str | None = None,
    ) -> list[CausalRelation]:
        """Get all relations, optionally filtered by entity."""
        if entity_id is None:
            return list(self._relations)
        return [
            r for r in self._relations
            if r.source_id == entity_id or r.target_id == entity_id
        ]

    @property
    def relation_count(self) -> int:
        return len(self._relations)

    # ------------------------------------------------------------------
    # Causal chain queries
    # ------------------------------------------------------------------

    def find_causes_of(self, entity_id: str) -> list[CausalRelation]:
        """Find all relations where this entity is the effect (target)."""
        return list(self._incoming.get(entity_id, []))

    def find_effects_of(self, entity_id: str) -> list[CausalRelation]:
        """Find all relations where this entity is the cause (source)."""
        return list(self._outgoing.get(entity_id, []))

    def find_causal_chain(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
    ) -> list[list[CausalRelation]]:
        """
        Find all causal paths between two entities.
        """
        if source_id not in self._entities or target_id not in self._entities:
            return []

        paths: list[list[CausalRelation]] = []

        def _dfs(current: str, target: str, visited: set[str], path: list[CausalRelation]):
            if len(path) > max_depth:
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
        """Remove all entities and relations."""
        self._entities.clear()
        self._relations.clear()
        self._outgoing.clear()
        self._incoming.clear()