"""
UnderstandingScorer — Phase 8.2.1

Calculates understanding depth instead of measuring knowledge quantity.
Score considers concept connectivity, relationship density, pattern
maturity, evidence quality, and confidence evolution.

Pure logic. No AI. No infrastructure.
"""

from typing import Any


class UnderstandingScorer:
    """
    Scores understanding depth across multiple dimensions.

    Understanding is NOT raw data accumulation. It is measured by:
      - Concept connectivity: how well interconnected concepts are
      - Relationship density: edges per concept ratio
      - Pattern maturity: confirmed patterns with high confidence
      - Evidence quality: average confidence across concepts/patterns
      - Confidence evolution: how much confidence has increased over time

    Score range: 0.0 (no understanding) to 1.0 (deep understanding).
    """

    # Weights for each dimension (sum = 1.0)
    WEIGHTS = {
        "connectivity": 0.25,
        "density": 0.20,
        "maturity": 0.20,
        "evidence_quality": 0.20,
        "confidence_evolution": 0.15,
    }

    def calculate(
        self,
        concepts: list[Any],
        relationships: list[Any],
        patterns: list[Any],
    ) -> dict[str, Any]:
        """
        Calculate the understanding score and return detailed breakdown.

        Args:
            concepts: All stored concepts.
            relationships: All stored relationships.
            patterns: All stored patterns.

        Returns:
            Dict with overall score and per-dimension breakdown.
        """
        if not concepts:
            return self._empty_score()

        n_concepts = len(concepts)
        n_relationships = len(relationships)
        n_patterns = len(patterns)

        # 1. Concept connectivity
        connectivity = self._calc_connectivity(concepts, relationships, n_concepts)

        # 2. Relationship density
        density = self._calc_density(n_relationships, n_concepts)

        # 3. Pattern maturity
        maturity = self._calc_maturity(patterns)

        # 4. Evidence quality
        evidence = self._calc_evidence_quality(concepts, patterns)

        # 5. Confidence evolution
        evolution = self._calc_confidence_evolution(concepts, patterns)

        # Weighted overall score
        overall = (
            connectivity * self.WEIGHTS["connectivity"]
            + density * self.WEIGHTS["density"]
            + maturity * self.WEIGHTS["maturity"]
            + evidence * self.WEIGHTS["evidence_quality"]
            + evolution * self.WEIGHTS["confidence_evolution"]
        )

        return {
            "overall_score": round(min(1.0, overall), 4),
            "connectivity": round(connectivity, 4),
            "density": round(density, 4),
            "maturity": round(maturity, 4),
            "evidence_quality": round(evidence, 4),
            "confidence_evolution": round(evolution, 4),
            "concept_count": n_concepts,
            "relationship_count": n_relationships,
            "pattern_count": n_patterns,
            "weights": dict(self.WEIGHTS),
        }

    # ------------------------------------------------------------------
    # Dimension calculations
    # ------------------------------------------------------------------

    @staticmethod
    def _calc_connectivity(
        concepts: list[Any],
        relationships: list[Any],
        n_concepts: int,
    ) -> float:
        """
        Connectivity: proportion of concepts that are part of at least
        one relationship. Higher = more interconnected understanding.
        """
        if n_concepts == 0:
            return 0.0

        connected_ids: set[str] = set()
        for r in relationships:
            connected_ids.add(getattr(r, "source_id", ""))
            connected_ids.add(getattr(r, "target_id", ""))

        concept_ids = {getattr(c, "concept_id", "") for c in concepts}
        if not concept_ids:
            return 0.0

        connected = len(connected_ids & concept_ids)
        return connected / n_concepts

    @staticmethod
    def _calc_density(n_relationships: int, n_concepts: int) -> float:
        """
        Density: edges per concept ratio normalized to [0, 1].
        A fully connected graph of n nodes has n*(n-1) edges.
        Density = actual_edges / max_possible_edges.
        """
        if n_concepts <= 1:
            return 0.0

        max_edges = n_concepts * (n_concepts - 1)
        if max_edges == 0:
            return 0.0

        return min(1.0, n_relationships / max_edges * 10)  # Scale: 10% of max = 1.0

    @staticmethod
    def _calc_maturity(patterns: list[Any]) -> float:
        """
        Pattern maturity: proportion of patterns with high confidence
        and multiple observations. Mature patterns indicate deep understanding.
        """
        if not patterns:
            return 0.0

        mature_count = 0
        for p in patterns:
            confidence = getattr(p, "confidence", 0)
            frequency = getattr(p, "frequency", 0)
            # Mature = confidence > 0.6 AND observed > 2 times
            if confidence > 0.6 and frequency > 2:
                mature_count += 1

        return mature_count / len(patterns)

    @staticmethod
    def _calc_evidence_quality(
        concepts: list[Any],
        patterns: list[Any],
    ) -> float:
        """
        Evidence quality: average confidence across all concepts and patterns.
        Higher average confidence = higher quality evidence.
        """
        confidences: list[float] = []

        for c in concepts:
            conf = getattr(c, "confidence", 0)
            confidences.append(conf)

        for p in patterns:
            conf = getattr(p, "confidence", 0)
            confidences.append(conf)

        if not confidences:
            return 0.0

        return sum(confidences) / len(confidences)

    @staticmethod
    def _calc_confidence_evolution(
        concepts: list[Any],
        patterns: list[Any],
    ) -> float:
        """
        Confidence evolution: measures how much confidence has grown
        relative to baseline (defined by frequency). More frequently
        observed concepts with high confidence = strong evolution.
        """
        if not concepts:
            return 0.0

        evolution_scores: list[float] = []
        for c in concepts:
            confidence = getattr(c, "confidence", 0)
            frequency = getattr(c, "frequency", 0)
            if frequency > 0 and confidence > 0:
                # Confidence per observation = how efficiently we gain confidence
                efficiency = confidence / (frequency + 1)  # +1 prevents div by zero
                evolution_scores.append(efficiency)

        if not evolution_scores:
            return 0.0

        avg = sum(evolution_scores) / len(evolution_scores)
        return min(1.0, avg * 5)  # Scale up

    @staticmethod
    def _empty_score() -> dict[str, Any]:
        """Return a zero score when no data exists."""
        return {
            "overall_score": 0.0,
            "connectivity": 0.0,
            "density": 0.0,
            "maturity": 0.0,
            "evidence_quality": 0.0,
            "confidence_evolution": 0.0,
            "concept_count": 0,
            "relationship_count": 0,
            "pattern_count": 0,
            "weights": dict(UnderstandingScorer.WEIGHTS),
        }