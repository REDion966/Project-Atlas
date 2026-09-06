"""
ConceptConsolidator — Phase 8.2.1a

Storage-aware concept deduplication. When memory and graph references
are provided, merged concepts immediately update storage — the caller
does NOT need to manually synchronize.

Pure logic. No AI. Deterministic label/domain matching.
"""

from datetime import datetime, timezone
from typing import Any

from atlas.understanding.models import Concept, ConceptDomain


class ConceptConsolidator:
    """
    Storage-aware concept merger.

    When memory and graph are injected, consolidation automatically
    updates storage — replacing old concepts with merged versions.

    Without storage references (backward compatible): returns merged
    list, caller handles storage.
    """

    def __init__(
        self,
        memory: Any = None,
        graph: Any = None,
    ):
        self._memory = memory
        self._graph = graph
        self._merge_counter = 0
        self._merge_history: list[dict[str, str]] = []

    def consolidate(
        self,
        concepts: list[Concept],
        existing_concepts: list[Concept] | None = None,
    ) -> list[Concept]:
        """
        Consolidate new concepts against themselves and existing ones.
        If storage is available, updates memory/graph automatically.
        """
        if existing_concepts is None:
            existing_concepts = self._get_all_concepts()

        all_concepts = list(existing_concepts) + list(concepts)
        merged: dict[str, Concept] = {}

        for concept in all_concepts:
            key = concept.label.lower().strip()
            if key in merged:
                merged[key] = self._merge(merged[key], concept)
            else:
                merged[key] = concept

        result = list(merged.values())

        # Sync storage with merged concepts
        if self._memory is not None:
            for c in result:
                self._memory.store_concept(c)
        if self._graph is not None:
            for c in result:
                self._graph.add_concepts([c])

        return result

    def try_merge_with_existing(
        self,
        new_concept: Concept,
        existing_concepts: list[Concept],
    ) -> Concept | None:
        """Try to merge a single new concept into existing ones. Returns merged or None."""
        new_label = new_concept.label.lower().strip()

        for existing in existing_concepts:
            existing_label = existing.label.lower().strip()

            if new_label == existing_label:
                return self._merge(existing, new_concept)
            if new_label in existing_label or existing_label in new_label:
                if new_concept.domain == existing.domain:
                    return self._merge(existing, new_concept)
            if self._normalize(new_label) == self._normalize(existing_label):
                return self._merge(existing, new_concept)

        return None

    def _merge(self, primary: Concept, secondary: Concept) -> Concept:
        self._merge_counter += 1
        new_confidence = self._calc_merged_confidence(
            primary.confidence, secondary.confidence, primary.frequency
        )
        new_frequency = primary.frequency + secondary.frequency

        self._merge_history.append({
            "primary_id": primary.concept_id,
            "secondary_id": secondary.concept_id,
            "timestamp": datetime.now().isoformat(),
        })

        metadata = dict(primary.metadata)
        sources = metadata.setdefault("merged_from", [])
        if secondary.source and secondary.source not in sources:
            sources.append(secondary.source)
        metadata["merge_count"] = metadata.get("merge_count", 0) + 1

        # Normalize timestamps to aware UTC for safe comparison
        primary_first = primary.first_seen
        primary_last = primary.last_seen
        secondary_first = secondary.first_seen
        secondary_last = secondary.last_seen
        if primary_first.tzinfo is None:
            primary_first = primary_first.replace(tzinfo=timezone.utc)
        if primary_last.tzinfo is None:
            primary_last = primary_last.replace(tzinfo=timezone.utc)
        if secondary_first.tzinfo is None:
            secondary_first = secondary_first.replace(tzinfo=timezone.utc)
        if secondary_last.tzinfo is None:
            secondary_last = secondary_last.replace(tzinfo=timezone.utc)

        merged = Concept(
            concept_id=primary.concept_id,
            label=primary.label,
            domain=primary.domain,
            confidence=round(new_confidence, 4),
            source=primary.source,
            frequency=new_frequency,
            first_seen=min(primary_first, secondary_first),
            last_seen=max(primary_last, secondary_last),
            metadata=metadata,
        )

        # Update storage immediately if available
        if self._memory is not None:
            self._memory.remove_concept(primary.concept_id)
            self._memory.store_concept(merged)

        return merged

    def _get_all_concepts(self) -> list[Concept]:
        if self._graph is not None:
            return self._graph.get_all_concepts()
        if self._memory is not None:
            return self._memory.get_concepts()
        return []

    @staticmethod
    def _calc_merged_confidence(
        primary_confidence: float,
        secondary_confidence: float,
        primary_frequency: int,
    ) -> float:
        weight_existing = primary_frequency / (primary_frequency + 1)
        weight_new = 1 / (primary_frequency + 1)
        blended = (primary_confidence * weight_existing) + (secondary_confidence * weight_new)
        return min(0.98, max(secondary_confidence, blended))

    @staticmethod
    def _normalize(label: str) -> str:
        normalized = label.lower().strip()
        for suffix in ["s", "es", "ing", "ed", "ly", "tion", "ment"]:
            if normalized.endswith(suffix) and len(normalized) > len(suffix) + 3:
                normalized = normalized[:-len(suffix)]
        return normalized

    @property
    def merge_count(self) -> int:
        return self._merge_counter

    @property
    def merge_history(self) -> list[dict[str, str]]:
        return list(self._merge_history)