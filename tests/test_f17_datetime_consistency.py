"""P11.2 — F17 datetime consistency tests.

Proves the F17 invariant: all datetime values created or normalized in the
understanding/experience path are timezone-aware UTC, and mixed-awareness
comparisons cannot raise TypeError.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from atlas.understanding.models import Concept, Pattern, Relationship
from atlas.understanding.serialization import (
    _parse_iso,
    concept_to_dict,
    dict_to_concept,
)
from atlas.experience.serialization import _parse_iso as _parse_iso_exp


class TestConceptDefaults:
    """Concept timestamp defaults must be aware UTC."""

    def test_first_seen_is_aware(self):
        c = Concept(concept_id="C1", label="test")
        assert c.first_seen.tzinfo is not None

    def test_last_seen_is_aware(self):
        c = Concept(concept_id="C1", label="test")
        assert c.last_seen.tzinfo is not None

    def test_first_seen_is_utc(self):
        c = Concept(concept_id="C1", label="test")
        assert c.first_seen.utcoffset() == timedelta(0)

    def test_last_seen_is_utc(self):
        c = Concept(concept_id="C1", label="test")
        assert c.last_seen.utcoffset() == timedelta(0)


class TestComparisonSafety:
    """min()/max() over Concept timestamps must not raise TypeError."""

    def test_min_first_seen(self):
        a = Concept(concept_id="C1", label="a", first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))
        b = Concept(concept_id="C2", label="b", first_seen=datetime(2026, 1, 2, tzinfo=timezone.utc))
        result = min(a.first_seen, b.first_seen)
        assert result == datetime(2026, 1, 1, tzinfo=timezone.utc)

    def test_max_last_seen(self):
        a = Concept(concept_id="C1", label="a", last_seen=datetime(2026, 1, 1, tzinfo=timezone.utc))
        b = Concept(concept_id="C2", label="b", last_seen=datetime(2026, 1, 2, tzinfo=timezone.utc))
        result = max(a.last_seen, b.last_seen)
        assert result == datetime(2026, 1, 2, tzinfo=timezone.utc)

    def test_mixed_naive_aware_comparison_via_normalization(self):
        """A naive datetime normalized via _parse_iso becomes aware and comparable."""
        naive = datetime(2026, 1, 1, 12, 0, 0)
        aware = datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
        normalized = _parse_iso(naive)
        # After normalization, both are aware and comparable
        assert normalized.tzinfo is not None
        result = min(normalized, aware)
        assert result == normalized


class TestSerializationRoundTrip:
    """Serialization must preserve awareness."""

    def test_aware_round_trip(self):
        aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        c = Concept(concept_id="C1", label="test", first_seen=aware, last_seen=aware)
        d = concept_to_dict(c)
        restored = dict_to_concept(d)
        assert restored.first_seen.tzinfo is not None
        assert restored.last_seen.tzinfo is not None

    def test_legacy_naive_string_normalized(self):
        """A naive ISO string from legacy storage is normalized to aware UTC."""
        data = {
            "concept_id": "C1",
            "label": "test",
            "domain": "GENERAL",
            "confidence": 0.5,
            "source": "",
            "frequency": 1,
            "first_seen": "2026-01-01T12:00:00",  # naive
            "last_seen": "2026-01-02T12:00:00",   # naive
            "metadata": {},
        }
        c = dict_to_concept(data)
        assert c.first_seen.tzinfo is not None
        assert c.last_seen.tzinfo is not None
        assert c.first_seen.utcoffset() == timedelta(0)

    def test_timezone_bearing_string_preserved(self):
        """A timezone-bearing ISO string preserves its awareness."""
        data = {
            "concept_id": "C1",
            "label": "test",
            "domain": "GENERAL",
            "confidence": 0.5,
            "source": "",
            "frequency": 1,
            "first_seen": "2026-01-01T12:00:00+00:00",
            "last_seen": "2026-01-02T12:00:00+00:00",
            "metadata": {},
        }
        c = dict_to_concept(data)
        assert c.first_seen.tzinfo is not None
        assert c.last_seen.tzinfo is not None


class TestParseIso:
    """_parse_iso normalizes all inputs to aware UTC."""

    def test_none_returns_aware(self):
        result = _parse_iso(None)
        assert result.tzinfo is not None

    def test_empty_string_returns_aware(self):
        result = _parse_iso("")
        assert result.tzinfo is not None

    def test_naive_datetime_made_aware(self):
        naive = datetime(2026, 1, 1, 12, 0, 0)
        result = _parse_iso(naive)
        assert result.tzinfo is not None
        assert result.utcoffset() == timedelta(0)

    def test_aware_datetime_preserved(self):
        aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = _parse_iso(aware)
        assert result.tzinfo is not None

    def test_naive_iso_string_normalized(self):
        result = _parse_iso("2026-01-01T12:00:00")
        assert result.tzinfo is not None
        assert result.utcoffset() == timedelta(0)

    def test_aware_iso_string_preserved(self):
        result = _parse_iso("2026-01-01T12:00:00+00:00")
        assert result.tzinfo is not None


class TestExperienceParseIso:
    """Experience serialization _parse_iso also normalizes."""

    def test_naive_datetime_made_aware(self):
        naive = datetime(2026, 1, 1, 12, 0, 0)
        result = _parse_iso_exp(naive)
        assert result.tzinfo is not None

    def test_aware_datetime_preserved(self):
        aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = _parse_iso_exp(aware)
        assert result.tzinfo is not None
