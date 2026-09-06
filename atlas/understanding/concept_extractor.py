"""
Atlas Concept Extractor

Extracts concepts from input data including observations, memories,
conversations, tool results, and knowledge. Produces structured concepts
with confidence scores.

Phase 7.1 — Understanding Engine.
"""

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from atlas.understanding.models import (
    Concept,
    ConceptDomain,
)


def _aware_utc(dt: datetime) -> datetime:
    """Normalize a datetime to aware UTC for safe comparison."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class ConceptExtractor:
    """
    Extracts concepts from unstructured or semi-structured input data.

    This is a pure logic component with no infrastructure dependencies.
    It uses deterministic keyword extraction and pattern matching to
    identify concepts, their domains, and confidence levels.

    The extractor maintains an internal vocabulary of known concept
    patterns organized by domain. This vocabulary can be expanded
    without modifying the extraction logic.
    """

    def __init__(self) -> None:
        self._concept_counter = 0

        # Domain keyword mappings for deterministic concept detection
        self._domain_keywords: dict[ConceptDomain, set[str]] = {
            ConceptDomain.TECHNICAL: {
                "function", "class", "method", "api", "interface",
                "implementation", "module", "package", "dependency",
                "algorithm", "data", "config", "pipeline", "service",
                "repository", "handler", "router", "registry",
            },
            ConceptDomain.BEHAVIORAL: {
                "user", "prefer", "want", "need", "like", "request",
                "ask", "suggest", "recommend", "approve", "decide",
            },
            ConceptDomain.SYSTEM_METRIC: {
                "time", "latency", "error", "rate", "count",
                "duration", "memory", "cpu", "usage", "performance",
            },
            ConceptDomain.USER_PREFERENCE: {
                "prefer", "favorite", "better", "worse", "good",
                "bad", "easy", "hard", "simple", "useful",
            },
        }

    def _next_concept_id(self) -> str:
        """Generate a unique concept identifier."""
        self._concept_counter += 1
        return f"CON-{self._concept_counter:06d}"

    # ------------------------------------------------------------------
    # Core extraction
    # ------------------------------------------------------------------

    def extract_from_text(
        self,
        text: str,
        source: str = "",
    ) -> list[Concept]:
        """
        Extract concepts from a text string.

        Splits text into words, identifies meaningful terms, and
        classifies them by domain. Returns deduplicated concepts.

        Args:
            text: The input text to analyze.
            source: Source identifier for provenance.

        Returns:
            A list of Concept instances extracted from the text.
        """
        if not text or not text.strip():
            return []

        words = self._tokenize(text)
        word_frequencies = Counter(words)

        concepts: list[Concept] = []
        seen_labels: set[str] = set()

        for word, count in word_frequencies.most_common():
            normalized = word.lower()

            if len(normalized) < 3:
                continue

            if normalized in seen_labels:
                continue

            domain = self._classify_domain(normalized)
            confidence = self._compute_confidence(normalized, count, len(words))

            if confidence < 0.1:
                continue

            concept = Concept(
                concept_id=self._next_concept_id(),
                label=normalized,
                domain=domain,
                confidence=confidence,
                source=source,
                frequency=count,
            )
            concepts.append(concept)
            seen_labels.add(normalized)

        return concepts

    def extract_from_observation(
        self,
        observation: Any,
        source: str = "",
    ) -> list[Concept]:
        """
        Extract concepts from an observation object.

        Extracts concepts from the observation's description, metric name,
        and any string values in its metadata.

        Args:
            observation: An observation object with a 'description' or
                'metric_name' attribute.
            source: Optional source override.

        Returns:
            A list of Concept instances.
        """
        concepts: list[Concept] = []

        texts: list[str] = []

        if hasattr(observation, "description") and observation.description:
            texts.append(str(observation.description))

        if hasattr(observation, "metric_name") and observation.metric_name:
            texts.append(str(observation.metric_name))

        if hasattr(observation, "source") and observation.source:
            texts.append(str(observation.source))

        effective_source = source or (
            getattr(observation, "source", "") or ""
        )

        for text in texts:
            extracted = self.extract_from_text(text, source=effective_source)
            concepts.extend(extracted)

        return self._deduplicate(concepts)

    def extract_from_data(
        self,
        data: dict[str, Any],
        source: str = "",
    ) -> list[Concept]:
        """
        Extract concepts from a dictionary of data.

        Processes all string values in the dictionary for concept
        extraction. Nested dictionaries are flattened.

        Args:
            data: A dictionary of data to analyze.
            source: Source identifier.

        Returns:
            A list of Concept instances.
        """
        texts: list[str] = []

        for key, value in data.items():
            if isinstance(value, str):
                texts.append(value)
            elif isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, str):
                        texts.append(sub_value)

        concepts: list[Concept] = []
        for text in texts:
            concepts.extend(self.extract_from_text(text, source=source))

        return self._deduplicate(concepts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _tokenize(self, text: str) -> list[str]:
        """
        Split text into normalized tokens.

        Handles camelCase, snake_case, and punctuation removal.
        """
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        words = re.findall(r'[a-zA-Z][a-zA-Z0-9]*', text)
        return [w.lower() for w in words if len(w) >= 2]

    def _classify_domain(self, word: str) -> ConceptDomain:
        """Classify a word into a concept domain based on keywords."""
        for domain, keywords in self._domain_keywords.items():
            if word in keywords:
                return domain
        return ConceptDomain.GENERAL

    def _compute_confidence(
        self,
        word: str,
        frequency: int,
        total_words: int,
    ) -> float:
        """
        Compute a confidence score for an extracted concept.

        Factors:
        - Frequency relative to total words.
        - Word length (longer words tend to be more meaningful).
        - Domain match (domain keywords get a boost).
        """
        if total_words == 0:
            return 0.0

        freq_score = min(frequency / max(total_words * 0.1, 1), 1.0)
        length_score = min(len(word) / 15.0, 1.0)
        domain_score = 0.3 if self._classify_domain(word) != ConceptDomain.GENERAL else 0.0

        raw = (freq_score * 0.4) + (length_score * 0.3) + (domain_score * 0.3)
        return round(min(raw, 1.0), 4)

    def _deduplicate(
        self,
        concepts: list[Concept],
    ) -> list[Concept]:
        """
        Remove duplicate concepts by label, keeping the highest
        confidence and accumulating frequency.
        """
        by_label: dict[str, Concept] = {}
        for concept in concepts:
            if concept.label in by_label:
                existing = by_label[concept.label]
                if concept.confidence > existing.confidence:
                    existing.confidence = concept.confidence
                existing.frequency += concept.frequency
                # Normalize timestamps to aware UTC for safe comparison
                if _aware_utc(concept.last_seen) > _aware_utc(existing.last_seen):
                    existing.last_seen = concept.last_seen
            else:
                by_label[concept.label] = concept
        return list(by_label.values())