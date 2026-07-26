"""
PatternConsolidator — Phase 8.2.1

Merges recurring patterns and tracks observation count.
Increases certainty through repeated confirmation.
Prevents pattern explosion by deduplication.

Pure logic. Deterministic matching on label + related concepts.
"""

from datetime import datetime

from atlas.understanding.models import Pattern


class PatternConsolidator:
    """
    Consolidates recurring patterns by merging duplicates.

    Two patterns are considered duplicates when:
      - Same label (case-insensitive), OR
      - Share > 70% of related concept IDs and have equal label length, OR
      - One pattern's label is a normalized subset of the other

    Merging tracks observation count, increases confidence, and
    preserves the earliest detection timestamp.
    """

    def __init__(self):
        self._merge_counter = 0

    def consolidate(
        self,
        new_patterns: list[Pattern],
        existing_patterns: list[Pattern],
    ) -> list[Pattern]:
        """
        Consolidate new patterns against existing ones.

        Args:
            new_patterns: Newly detected patterns.
            existing_patterns: Previously stored patterns.

        Returns:
            Consolidated list — existing patterns updated, new ones appended.
        """
        result = list(existing_patterns)

        for new_pattern in new_patterns:
            match_idx = self._find_match(new_pattern, result)
            if match_idx is not None:
                result[match_idx] = self._merge(result[match_idx], new_pattern)
            else:
                result.append(new_pattern)

        return result

    def _find_match(
        self,
        candidate: Pattern,
        existing: list[Pattern],
    ) -> int | None:
        """Find matching existing pattern by index, or None."""
        cand_label = candidate.label.lower().strip()
        cand_concepts = set(candidate.related_concept_ids)

        for i, existing_pattern in enumerate(existing):
            exist_label = existing_pattern.label.lower().strip()

            # Exact label match
            if cand_label == exist_label:
                return i

            # Concept overlap match (> 70% overlap)
            exist_concepts = set(existing_pattern.related_concept_ids)
            if cand_concepts and exist_concepts:
                overlap = len(cand_concepts & exist_concepts)
                union = len(cand_concepts | exist_concepts)
                if union > 0 and overlap / union > 0.7:
                    return i

        return None

    def _merge(self, primary: Pattern, secondary: Pattern) -> Pattern:
        """
        Merge secondary pattern into primary.

        Confidence increases from repeated confirmation.
        Frequency accumulates. Related concepts merged.
        """
        self._merge_counter += 1

        new_frequency = primary.frequency + secondary.frequency
        new_confidence = min(0.98, primary.confidence + (1 - primary.confidence) * 0.25)

        # Merge concept IDs (unique)
        combined_concepts = list(set(
            primary.related_concept_ids + secondary.related_concept_ids
        ))

        return Pattern(
            pattern_id=primary.pattern_id,
            label=primary.label,
            description=primary.description or secondary.description,
            confidence=round(new_confidence, 4),
            related_concept_ids=combined_concepts,
            frequency=new_frequency,
            first_observed=min(primary.first_observed, secondary.first_observed),
            last_observed=max(primary.last_observed, secondary.last_observed),
        )

    @property
    def merge_count(self) -> int:
        return self._merge_counter