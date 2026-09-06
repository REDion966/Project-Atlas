"""
Atlas Understanding — Data Models

Pure data models for the Understanding Layer.
Phase 7.1 — Understanding Engine.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any


# ---------------------------------------------------------------------------
# Concept types
# ---------------------------------------------------------------------------


class ConceptDomain(Enum):
    """Domain of a concept extracted from input data."""

    GENERAL = auto()
    BEHAVIORAL = auto()
    TECHNICAL = auto()
    DOMAIN_KNOWLEDGE = auto()
    SYSTEM_METRIC = auto()
    USER_PREFERENCE = auto()


@dataclass(slots=True)
class Concept:
    """
    A single extracted concept.

    Attributes:
        concept_id: Unique identifier for this concept.
        label: Human-readable label for the concept.
        domain: The domain this concept belongs to.
        confidence: Confidence in this extraction (0.0 to 1.0).
        source: Where this concept was extracted from.
        frequency: How often this concept has been observed.
        first_seen: When this concept was first observed.
        last_seen: When this concept was last observed.
        metadata: Optional additional context.
    """

    concept_id: str
    label: str
    domain: ConceptDomain = ConceptDomain.GENERAL
    confidence: float = 0.5
    source: str = ""
    frequency: int = 1
    first_seen: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_seen: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Relationship types
# ---------------------------------------------------------------------------


class RelationshipType(Enum):
    """Type of relationship between two concepts."""

    ASSOCIATED_WITH = auto()
    CAUSES = auto()
    DEPENDS_ON = auto()
    CONTRADICTS = auto()
    GENERALIZES = auto()
    SPECIALIZES = auto()
    SEQUENCES_WITH = auto()
    SIMILAR_TO = auto()


@dataclass(slots=True)
class Relationship:
    """
    A directed relationship between two concepts.

    Attributes:
        source_id: The concept_id of the source concept.
        target_id: The concept_id of the target concept.
        relationship_type: The type of relationship.
        weight: Strength of the relationship (0.0 to 1.0).
        confidence: Confidence in this relationship (0.0 to 1.0).
        observed_count: How many times this relationship was observed.
        first_observed: When this relationship was first noted.
        last_observed: When this relationship was last noted.
    """

    source_id: str
    target_id: str
    relationship_type: RelationshipType
    weight: float = 0.5
    confidence: float = 0.5
    observed_count: int = 1
    first_observed: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_observed: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Pattern types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Pattern:
    """
    A detected pattern across concepts or understanding insights.

    Attributes:
        pattern_id: Unique identifier for this pattern.
        label: Human-readable label for the pattern.
        description: Detailed description of what the pattern means.
        confidence: Confidence in this pattern (0.0 to 1.0).
        related_concept_ids: Concept IDs that form this pattern.
        frequency: How often this pattern has been observed.
        first_observed: When this pattern was first detected.
        last_observed: When this pattern was last detected.
    """

    pattern_id: str
    label: str
    description: str
    confidence: float = 0.5
    related_concept_ids: list[str] = field(default_factory=list)
    frequency: int = 1
    first_observed: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_observed: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Understanding insight types
# ---------------------------------------------------------------------------


class UnderstandingCategory(Enum):
    """Category of an understanding insight."""

    CONCEPT_INSIGHT = auto()
    RELATIONSHIP_INSIGHT = auto()
    PATTERN_INSIGHT = auto()
    BEHAVIORAL_INSIGHT = auto()
    TREND_INSIGHT = auto()
    ANOMALY_INSIGHT = auto()


@dataclass(slots=True)
class UnderstandingInsight:
    """
    A structured understanding insight produced by the Understanding Engine.

    This is the primary output of the Understanding Layer. Future reasoning
    components should consume UnderstandingInsight instances instead of
    raw memories whenever possible.

    Attributes:
        insight_id: Unique identifier for this insight.
        category: The category of understanding.
        summary: Human-readable summary of the insight.
        detail: Detailed explanation.
        confidence: Confidence in this insight (0.0 to 1.0).
        related_concept_ids: Concepts involved in this insight.
        related_pattern_ids: Patterns involved in this insight.
        source: Where the input data came from.
        timestamp: When the insight was generated.
        metadata: Optional additional context.
    """

    insight_id: str
    category: UnderstandingCategory
    summary: str
    detail: str
    confidence: float = 0.5
    related_concept_ids: list[str] = field(default_factory=list)
    related_pattern_ids: list[str] = field(default_factory=list)
    source: str = ""
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Behavioral signal types
# ---------------------------------------------------------------------------


class BehavioralDomain(Enum):
    """Domain of behavioral understanding."""

    COMMUNICATION = auto()
    DECISION_MAKING = auto()
    PROBLEM_SOLVING = auto()
    LEARNING = auto()
    COLLABORATION = auto()


@dataclass(slots=True)
class BehavioralSignal:
    """
    A structured signal about observed human behavior.

    This is the foundation for future behavior models. It captures
    observable behavioral patterns without implementing psychology.

    Attributes:
        signal_id: Unique identifier for this signal.
        domain: The behavioral domain this signal relates to.
        description: Human-readable description of the observed behavior.
        confidence: Confidence in this signal (0.0 to 1.0).
        related_concept_ids: Concepts related to this behavioral signal.
        source: Where the behavior was observed.
        timestamp: When the behavior was observed.
    """

    signal_id: str
    domain: BehavioralDomain
    description: str
    confidence: float = 0.5
    related_concept_ids: list[str] = field(default_factory=list)
    source: str = ""
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Behavior extractor interface (pluggable)
# ---------------------------------------------------------------------------


class BehaviorExtractor:
    """
    Abstract interface for pluggable behavior extraction.

    Future implementations will extract behavioral signals from
    conversation data, user interactions, and tool usage patterns.
    This establishes the architecture so future models can plug into
    the UnderstandingEngine without modifying it.

    Current implementation returns empty results as a no-op default.
    """

    def extract_signals(
        self,
        text: str,
        source: str = "",
    ) -> list[BehavioralSignal]:
        """
        Extract behavioral signals from input text.

        Override this method in subclasses to implement specific
        behavioral extraction logic.

        Args:
            text: The input text to analyze.
            source: Source identifier for the input.

        Returns:
            A list of BehavioralSignal instances. The default
            implementation returns an empty list.
        """
        return []

    def extract_signals_from_observations(
        self,
        observations: list[Any],
    ) -> list[BehavioralSignal]:
        """
        Extract behavioral signals from observation data.

        Args:
            observations: A list of observation objects.

        Returns:
            A list of BehavioralSignal instances. The default
            implementation returns an empty list.
        """
        return []