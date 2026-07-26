"""
Atlas Understanding Memory

Stores concepts, relationships, patterns, and understanding insights.
Maintains bounded histories for each data type.

Phase 7.1 — Understanding Engine.
"""

from collections import deque
from datetime import datetime
from typing import Any

from atlas.understanding.models import (
    Concept,
    Pattern,
    Relationship,
    BehavioralSignal,
    UnderstandingInsight,
)


class UnderstandingMemory:
    """
    Persistent (in-memory) store for understanding data.

    Maintains bounded histories of concepts, relationships, patterns,
    insights, and behavioral signals. This is a pure logic component
    with no infrastructure dependencies.

    Attributes:
        max_concepts: Maximum number of concepts to retain.
        max_relationships: Maximum number of relationships to retain.
        max_patterns: Maximum number of patterns to retain.
        max_insights: Maximum number of insights to retain.
        max_signals: Maximum number of behavioral signals to retain.
    """

    def __init__(
        self,
        max_concepts: int = 5000,
        max_relationships: int = 5000,
        max_patterns: int = 1000,
        max_insights: int = 2000,
        max_signals: int = 1000,
    ) -> None:
        if any(v <= 0 for v in (max_concepts, max_relationships, max_patterns, max_insights, max_signals)):
            raise ValueError("All limits must be positive integers")

        self._max_concepts = max_concepts
        self._max_relationships = max_relationships
        self._max_patterns = max_patterns
        self._max_insights = max_insights
        self._max_signals = max_signals

        self._concepts: dict[str, Concept] = {}
        self._relationships: deque[Relationship] = deque(maxlen=max_relationships)
        self._patterns: deque[Pattern] = deque(maxlen=max_patterns)
        self._insights: deque[UnderstandingInsight] = deque(maxlen=max_insights)
        self._signals: deque[BehavioralSignal] = deque(maxlen=max_signals)

    # ------------------------------------------------------------------
    # Concepts
    # ------------------------------------------------------------------

    def store_concept(self, concept: Concept) -> None:
        """Store or update a concept."""
        if len(self._concepts) >= self._max_concepts and concept.concept_id not in self._concepts:
            return
        self._concepts[concept.concept_id] = concept

    def get_concept(self, concept_id: str) -> Concept | None:
        """Retrieve a concept by ID."""
        return self._concepts.get(concept_id)

    def get_all_concepts(self) -> list[Concept]:
        """Return all stored concepts."""
        return list(self._concepts.values())

    def remove_concept(self, concept_id: str) -> bool:
        """Remove a concept by ID. Returns True if found."""
        return self._concepts.pop(concept_id, None) is not None

    @property
    def concept_count(self) -> int:
        return len(self._concepts)

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------

    def store_relationship(self, relationship: Relationship) -> None:
        """Store a relationship."""
        self._relationships.append(relationship)

    def get_relationships(self, n: int = 100) -> list[Relationship]:
        """Return the most recent n relationships."""
        if n <= 0:
            return []
        return list(reversed(self._relationships))[:n]

    def clear_relationships(self) -> None:
        """Clear all stored relationships."""
        self._relationships.clear()

    @property
    def relationship_count(self) -> int:
        return len(self._relationships)

    # ------------------------------------------------------------------
    # Patterns
    # ------------------------------------------------------------------

    def store_pattern(self, pattern: Pattern) -> None:
        """Store a pattern."""
        self._patterns.append(pattern)

    def get_pattern_by_id(self, pattern_id: str) -> Pattern | None:
        """Retrieve a pattern by ID."""
        for p in self._patterns:
            if p.pattern_id == pattern_id:
                return p
        return None

    def get_patterns(self, n: int = 50) -> list[Pattern]:
        """Return the most recent n patterns."""
        if n <= 0:
            return []
        return list(reversed(self._patterns))[:n]

    def clear_patterns(self) -> None:
        """Clear all stored patterns."""
        self._patterns.clear()

    @property
    def pattern_count(self) -> int:
        return len(self._patterns)

    # ------------------------------------------------------------------
    # Insights
    # ------------------------------------------------------------------

    def store_insight(self, insight: UnderstandingInsight) -> None:
        """Store an understanding insight."""
        self._insights.append(insight)

    def get_insights(
        self,
        n: int = 50,
        category: Any | None = None,
    ) -> list[UnderstandingInsight]:
        """Return the most recent n insights, optionally filtered by category."""
        if n <= 0:
            return []

        if category is None:
            return list(reversed(self._insights))[:n]

        filtered = [
            i for i in reversed(self._insights)
            if i.category == category
        ]
        return filtered[:n]

    def clear_insights(self) -> None:
        """Clear all stored insights."""
        self._insights.clear()

    @property
    def insight_count(self) -> int:
        return len(self._insights)

    # ------------------------------------------------------------------
    # Behavioral signals
    # ------------------------------------------------------------------

    def store_signal(self, signal: BehavioralSignal) -> None:
        """Store a behavioral signal."""
        self._signals.append(signal)

    def get_signals(self, n: int = 50) -> list[BehavioralSignal]:
        """Return the most recent n behavioral signals."""
        if n <= 0:
            return []
        return list(reversed(self._signals))[:n]

    @property
    def signal_count(self) -> int:
        return len(self._signals)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return a summary of all stored understanding data."""
        return {
            "concept_count": self.concept_count,
            "relationship_count": self.relationship_count,
            "pattern_count": self.pattern_count,
            "insight_count": self.insight_count,
            "signal_count": self.signal_count,
        }

    def clear(self) -> None:
        """Clear all stored understanding data."""
        self._concepts.clear()
        self._relationships.clear()
        self._patterns.clear()
        self._insights.clear()
        self._signals.clear()