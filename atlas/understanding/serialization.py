"""
Atlas Understanding Serialization — Phase 9.2b

Pure logic conversion between understanding domain models and JSON-safe
dictionaries. This module is the only place that knows both the model shapes
and the storage representation; it is intentionally separate from both
models.py and the SQLite adapter.

No infrastructure imports. No database imports.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from atlas.understanding.models import (
    BehavioralDomain,
    BehavioralSignal,
    Concept,
    ConceptDomain,
    Pattern,
    Relationship,
    RelationshipType,
    UnderstandingCategory,
    UnderstandingInsight,
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _iso(dt: datetime) -> str:
    """Convert a datetime to an ISO 8601 string with timezone-naive fallback."""
    return dt.isoformat()


def _parse_iso(value: Any) -> datetime:
    """Parse an ISO 8601 string into a datetime."""
    if isinstance(value, datetime):
        return value
    if not value:
        return datetime.now()
    return datetime.fromisoformat(str(value))


def _as_enum_name(value: Any, enum_cls: type[Enum]) -> Enum:
    """Return the enum member whose name matches the string value."""
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls[value] if value is not None else list(enum_cls)[0]
    except (KeyError, TypeError):
        return list(enum_cls)[0]


def _as_list(value: Any) -> list[Any]:
    """Ensure a value is a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return [value]


# ----------------------------------------------------------------------
# Concept
# ----------------------------------------------------------------------


def concept_to_dict(concept: Concept) -> dict[str, Any]:
    """Convert a Concept to a JSON-safe dictionary."""
    return {
        "concept_id": concept.concept_id,
        "label": concept.label,
        "domain": concept.domain.name,
        "confidence": concept.confidence,
        "source": concept.source,
        "frequency": concept.frequency,
        "first_seen": _iso(concept.first_seen),
        "last_seen": _iso(concept.last_seen),
        "metadata": dict(concept.metadata),
    }


def dict_to_concept(data: dict[str, Any]) -> Concept:
    """Convert a dictionary back to a Concept."""
    safe = dict(data)
    model_fields = {
        "concept_id",
        "label",
        "domain",
        "confidence",
        "source",
        "frequency",
        "first_seen",
        "last_seen",
        "metadata",
    }

    filtered: dict[str, Any] = {}
    for key in model_fields:
        if key in safe:
            filtered[key] = safe[key]

    filtered["domain"] = _as_enum_name(filtered.get("domain"), ConceptDomain)
    filtered["first_seen"] = _parse_iso(filtered.get("first_seen"))
    filtered["last_seen"] = _parse_iso(filtered.get("last_seen"))
    filtered["metadata"] = dict(filtered.get("metadata") or {})

    return Concept(**filtered)


# ----------------------------------------------------------------------
# Relationship
# ----------------------------------------------------------------------


def relationship_to_dict(relationship: Relationship) -> dict[str, Any]:
    """Convert a Relationship to a JSON-safe dictionary.

    Note: Relationship does NOT have a metadata field.
    """
    return {
        "source_id": relationship.source_id,
        "target_id": relationship.target_id,
        "relationship_type": relationship.relationship_type.name,
        "weight": relationship.weight,
        "confidence": relationship.confidence,
        "observed_count": relationship.observed_count,
        "first_observed": _iso(relationship.first_observed),
        "last_observed": _iso(relationship.last_observed),
    }


def dict_to_relationship(data: dict[str, Any]) -> Relationship:
    """Convert a dictionary back to a Relationship."""
    safe = dict(data)
    model_fields = {
        "source_id",
        "target_id",
        "relationship_type",
        "weight",
        "confidence",
        "observed_count",
        "first_observed",
        "last_observed",
    }

    filtered: dict[str, Any] = {}
    for key in model_fields:
        if key in safe:
            filtered[key] = safe[key]

    filtered["relationship_type"] = _as_enum_name(
        filtered.get("relationship_type"), RelationshipType
    )
    filtered["first_observed"] = _parse_iso(filtered.get("first_observed"))
    filtered["last_observed"] = _parse_iso(filtered.get("last_observed"))

    return Relationship(**filtered)


# ----------------------------------------------------------------------
# Pattern
# ----------------------------------------------------------------------


def pattern_to_dict(pattern: Pattern) -> dict[str, Any]:
    """Convert a Pattern to a JSON-safe dictionary.

    Note: Pattern does NOT have a metadata field.
    """
    return {
        "pattern_id": pattern.pattern_id,
        "label": pattern.label,
        "description": pattern.description,
        "confidence": pattern.confidence,
        "related_concept_ids": list(pattern.related_concept_ids),
        "frequency": pattern.frequency,
        "first_observed": _iso(pattern.first_observed),
        "last_observed": _iso(pattern.last_observed),
    }


def dict_to_pattern(data: dict[str, Any]) -> Pattern:
    """Convert a dictionary back to a Pattern."""
    safe = dict(data)
    model_fields = {
        "pattern_id",
        "label",
        "description",
        "confidence",
        "related_concept_ids",
        "frequency",
        "first_observed",
        "last_observed",
    }

    filtered: dict[str, Any] = {}
    for key in model_fields:
        if key in safe:
            filtered[key] = safe[key]

    filtered["related_concept_ids"] = _as_list(filtered.get("related_concept_ids"))
    filtered["first_observed"] = _parse_iso(filtered.get("first_observed"))
    filtered["last_observed"] = _parse_iso(filtered.get("last_observed"))

    return Pattern(**filtered)


# ----------------------------------------------------------------------
# UnderstandingInsight
# ----------------------------------------------------------------------


def insight_to_dict(insight: UnderstandingInsight) -> dict[str, Any]:
    """Convert a UnderstandingInsight to a JSON-safe dictionary."""
    return {
        "insight_id": insight.insight_id,
        "category": insight.category.name,
        "summary": insight.summary,
        "detail": insight.detail,
        "confidence": insight.confidence,
        "related_concept_ids": list(insight.related_concept_ids),
        "related_pattern_ids": list(insight.related_pattern_ids),
        "source": insight.source,
        "timestamp": _iso(insight.timestamp),
        "metadata": dict(insight.metadata),
    }


def dict_to_insight(data: dict[str, Any]) -> UnderstandingInsight:
    """Convert a dictionary back to a UnderstandingInsight."""
    safe = dict(data)
    model_fields = {
        "insight_id",
        "category",
        "summary",
        "detail",
        "confidence",
        "related_concept_ids",
        "related_pattern_ids",
        "source",
        "timestamp",
        "metadata",
    }

    filtered: dict[str, Any] = {}
    for key in model_fields:
        if key in safe:
            filtered[key] = safe[key]

    filtered["category"] = _as_enum_name(
        filtered.get("category"), UnderstandingCategory
    )
    filtered["related_concept_ids"] = _as_list(filtered.get("related_concept_ids"))
    filtered["related_pattern_ids"] = _as_list(filtered.get("related_pattern_ids"))
    filtered["timestamp"] = _parse_iso(filtered.get("timestamp"))
    filtered["metadata"] = dict(filtered.get("metadata") or {})

    return UnderstandingInsight(**filtered)


# ----------------------------------------------------------------------
# BehavioralSignal
# ----------------------------------------------------------------------


def signal_to_dict(signal: BehavioralSignal) -> dict[str, Any]:
    """Convert a BehavioralSignal to a JSON-safe dictionary.

    Note: BehavioralSignal does NOT have a metadata field.
    """
    return {
        "signal_id": signal.signal_id,
        "domain": signal.domain.name,
        "description": signal.description,
        "confidence": signal.confidence,
        "related_concept_ids": list(signal.related_concept_ids),
        "source": signal.source,
        "timestamp": _iso(signal.timestamp),
    }


def dict_to_signal(data: dict[str, Any]) -> BehavioralSignal:
    """Convert a dictionary back to a BehavioralSignal."""
    safe = dict(data)
    model_fields = {
        "signal_id",
        "domain",
        "description",
        "confidence",
        "related_concept_ids",
        "source",
        "timestamp",
    }

    filtered: dict[str, Any] = {}
    for key in model_fields:
        if key in safe:
            filtered[key] = safe[key]

    filtered["domain"] = _as_enum_name(filtered.get("domain"), BehavioralDomain)
    filtered["related_concept_ids"] = _as_list(filtered.get("related_concept_ids"))
    filtered["timestamp"] = _parse_iso(filtered.get("timestamp"))

    return BehavioralSignal(**filtered)