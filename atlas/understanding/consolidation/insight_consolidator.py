"""
UnderstandingInsightConsolidator — Phase 8.2.1a

Merges duplicate understanding insights, strengthens confidence,
increases observation count, and preserves history.

Prevents UnderstandingMemory from accumulating duplicate insights.
Pure logic. Deterministic matching on category + summary.
"""

from datetime import datetime, timezone

from atlas.understanding.models import UnderstandingInsight


class InsightConsolidator:
    """
    Merges duplicate understanding insights.

    Two insights are duplicates when they share:
      - Same category
      - Same summary (case-insensitive)
      - OR share > 80% of related concept IDs

    Merging increases confidence and tracks observation count.
    """

    def __init__(self):
        self._merge_counter = 0

    def consolidate(
        self,
        new_insights: list[UnderstandingInsight],
        existing_insights: list[UnderstandingInsight],
    ) -> list[UnderstandingInsight]:
        """
        Merge new insights into existing ones.

        Returns consolidated list — existing matches updated, new ones appended.
        """
        result = list(existing_insights)

        for new_insight in new_insights:
            match_idx = self._find_match(new_insight, result)
            if match_idx is not None:
                result[match_idx] = self._merge(result[match_idx], new_insight)
            else:
                result.append(new_insight)

        return result

    def _find_match(
        self,
        candidate: UnderstandingInsight,
        existing: list[UnderstandingInsight],
    ) -> int | None:
        """Find matching existing insight by index."""
        cand_summary = candidate.summary.lower().strip()
        cand_concepts = set(candidate.related_concept_ids)

        for i, existing_insight in enumerate(existing):
            # Same category and same summary
            if (
                candidate.category == existing_insight.category
                and existing_insight.summary.lower().strip() == cand_summary
            ):
                return i

            # Concept overlap > 80%
            exist_concepts = set(existing_insight.related_concept_ids)
            if cand_concepts and exist_concepts:
                overlap = len(cand_concepts & exist_concepts)
                union = len(cand_concepts | exist_concepts)
                if union > 0 and overlap / union > 0.8:
                    if candidate.category == existing_insight.category:
                        return i

        return None

    def _merge(
        self,
        primary: UnderstandingInsight,
        secondary: UnderstandingInsight,
    ) -> UnderstandingInsight:
        """Merge secondary insight into primary — increase confidence."""
        self._merge_counter += 1

        new_confidence = min(0.98, primary.confidence + (1 - primary.confidence) * 0.3)
        combined_concepts = list(set(
            primary.related_concept_ids + secondary.related_concept_ids
        ))
        combined_patterns = list(set(
            primary.related_pattern_ids + secondary.related_pattern_ids
        ))

        # Track observation count in metadata
        metadata = dict(primary.metadata) if primary.metadata else {}
        metadata["observation_count"] = metadata.get("observation_count", 1) + 1
        metadata["merged_from_id"] = secondary.insight_id
        metadata["last_merged"] = datetime.now(timezone.utc).isoformat()

        # Normalize timestamps to aware UTC for safe comparison
        primary_ts = primary.timestamp
        secondary_ts = secondary.timestamp
        if primary_ts.tzinfo is None:
            primary_ts = primary_ts.replace(tzinfo=timezone.utc)
        if secondary_ts.tzinfo is None:
            secondary_ts = secondary_ts.replace(tzinfo=timezone.utc)

        return UnderstandingInsight(
            insight_id=primary.insight_id,
            category=primary.category,
            summary=primary.summary,
            detail=primary.detail or secondary.detail,
            confidence=round(new_confidence, 4),
            related_concept_ids=combined_concepts,
            related_pattern_ids=combined_patterns,
            source=primary.source,
            timestamp=max(primary_ts, secondary_ts),
            metadata=metadata,
        )

    @property
    def merge_count(self) -> int:
        return self._merge_counter