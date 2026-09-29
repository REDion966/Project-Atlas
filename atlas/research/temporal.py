"""Atlas — Temporal & Freshness-Aware Knowledge (Step 19).

A bounded, deterministic, model-free temporal overlay for retained knowledge
(Steps 17-18): it states, from evidence Atlas already holds, WHEN the knowledge
was retrieved/extracted/verified, whether it is current RELATIVE to that
acquisition or historical, and whether temporal information is simply unknown.

It is NOT a new time model and NOT a refresh mechanism. The event timestamps are
the EXISTING ones (``CitationRecord.retrieved_at`` / ``KnowledgeClaim.
extracted_at`` / ``ClaimVerification.verified_at``) and the age judgement is the
EXISTING freshness assessor (``atlas.evolution.freshness``) evaluated over an
EXISTING ``KnowledgeRef`` with its shipped default policy — this module only
projects the assessment onto retained knowledge and adds the missing
content-time dimension.

Two time dimensions are kept strictly apart:

* **content time** (``knowledge_time``) — when the content is *about*. No source
  adapter in Atlas records one, so it is reported as UNKNOWN unless a source
  explicitly attached a bounded content-time metadata value. It is never guessed.
* **event time** (``retrieved_at`` / ``extracted_at`` / ``verified_at``) — when
  Atlas fetched, extracted and verified the claim. This is evidence, not truth.

Guarantees:

* **Absence of temporal evidence is never freshness.** With no event timestamp
  the status is ``undated`` (or the assessor's own non-fresh outcome) — never
  ``current_relative``.
* **No invented dates or validity periods.** No expiration window is invented
  here: age uses the EXISTING default freshness policy, and a missing timestamp
  stays missing.
* **Newer acquisition is not newer truth.** ``current_relative`` means current
  *relative to when Atlas acquired it*, and is documented as exactly that.
* **Provenance and standing survive.** The overlay carries the record id, claim
  id and the Steps 17-18 standing/justification; it changes neither.
* **Deterministic and model-free.** Pure logic over recorded data with an
  injectable clock (the same convention as the existing assessor): no AI, no
  network, no writes, no authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

#: Bounds (a malformed record can never produce unbounded output).
_MAX_ITEMS: int = 40
_MAX_TEXT_CHARS: int = 300
_MAX_FINDINGS: int = 6
_MAX_REASONS: int = 8

#: The only metadata keys read for CONTENT time. A value is used only when a
#: source explicitly recorded it (no adapter does today); an ISO-8601 string is
#: required — anything else stays unknown. ``mtime_epoch`` is deliberately NOT
#: read: the read-side placeholder is a hard-coded ``0.0`` and reading it would
#: invent a 1970 date.
_CONTENT_TIME_KEYS: tuple[str, ...] = (
    "published_at",
    "publication_date",
    "updated_at",
    "content_date",
    "valid_from",
    "as_of",
)


class TemporalStatus(str, Enum):
    """Temporal standing of a retained knowledge record (closed set)."""

    #: Event-time evidence exists and is within the existing freshness window:
    #: current RELATIVE to Atlas's acquisition — never a claim about the world.
    CURRENT_RELATIVE = "current_relative"
    #: Event-time evidence exists but is older than the existing policy window.
    HISTORICAL = "historical"
    #: No event-time evidence at all: the temporal standing cannot be known.
    UNDATED = "undated"
    #: Evidence exists but the standing is not temporally determinable.
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class KnowledgeTemporal:
    """The bounded temporal view of one retained knowledge record (immutable)."""

    record_id: str
    claim_id: str
    status: TemporalStatus
    standing: str = ""
    justified: bool = True
    #: Content time (when the knowledge is ABOUT). Unknown unless a source
    #: explicitly recorded one — never inferred.
    knowledge_time: str = ""
    knowledge_time_known: bool = False
    #: Event times (when Atlas retrieved / extracted / verified it).
    retrieved_at: Any = None
    extracted_at: Any = None
    verified_at: Any = None
    assessed_at: Any = None
    age_days: float | None = None
    #: The EXISTING assessor's own reasons/rationale (preserved verbatim).
    reasons: tuple[str, ...] = ()
    rationale: str = ""
    findings: tuple[str, ...] = ()

    @property
    def has_event_time(self) -> bool:
        """True when at least one event timestamp was recorded."""
        return bool(self.retrieved_at or self.extracted_at or self.verified_at)

    @property
    def is_current_relative(self) -> bool:
        return self.status is TemporalStatus.CURRENT_RELATIVE

    def to_dict(self) -> dict[str, Any]:
        def _iso(value: Any) -> str | None:
            encoder = getattr(value, "isoformat", None)
            return encoder() if callable(encoder) else None

        return {
            "record_id": self.record_id,
            "claim_id": self.claim_id,
            "status": self.status.value,
            "standing": self.standing,
            "justified": self.justified,
            "knowledge_time": self.knowledge_time,
            "knowledge_time_known": self.knowledge_time_known,
            "retrieved_at": _iso(self.retrieved_at),
            "extracted_at": _iso(self.extracted_at),
            "verified_at": _iso(self.verified_at),
            "assessed_at": _iso(self.assessed_at),
            "age_days": self.age_days,
            "reasons": list(self.reasons),
            "rationale": self.rationale,
            "findings": list(self.findings),
            "has_event_time": self.has_event_time,
        }


@dataclass(frozen=True, slots=True)
class TemporalKnowledge:
    """Temporal overlay for one retained-knowledge retrieval (immutable)."""

    status: str
    query: str
    entries: tuple[KnowledgeTemporal, ...] = ()
    message: str = ""

    @property
    def current_relative(self) -> tuple[KnowledgeTemporal, ...]:
        return tuple(e for e in self.entries if e.is_current_relative)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "query": self.query,
            "entries": [e.to_dict() for e in self.entries],
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _name(value: Any) -> str:
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name
    return _clean(value, 64)


def _as_datetime(value: Any) -> Any:
    """Return ``value`` when it is a datetime, else ``None`` (never invented)."""
    try:
        from datetime import datetime

        if isinstance(value, datetime):
            return value
    except Exception:  # pragma: no cover - defensive
        return None
    return None


def _earliest(values: Any) -> Any:
    candidates = [v for v in (_as_datetime(item) for item in values or ()) if v]
    if not candidates:
        return None
    try:
        return min(candidates)
    except TypeError:  # mixed naive/aware: fall back to the recorded order
        return candidates[0]


def _content_time(record: Any) -> str:
    """An explicit content-time value recorded by a source, or ``""``.

    Only the bounded ``_CONTENT_TIME_KEYS`` are read, only from the record's own
    metadata (or its evidence metadata) and only as an ISO-8601 string. Nothing
    is inferred, and no adapter currently records one.
    """
    sources = [getattr(record, "metadata", None)]
    for name in ("evidence", "sources"):
        for item in getattr(record, name, ()) or ():
            sources.append(getattr(item, "metadata", None))
    for metadata in sources:
        if not isinstance(metadata, dict):
            continue
        for key in _CONTENT_TIME_KEYS:
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return _clean(value, 64)
    return ""


def _temporal_status(assessment: Any) -> TemporalStatus:
    """Map the EXISTING freshness assessment onto the bounded temporal status."""
    status = _name(getattr(assessment, "status", "")).upper()
    reasons = tuple(_name(r).upper() for r in (getattr(assessment, "reasons", ()) or ()))
    if status == "FRESH":
        return TemporalStatus.CURRENT_RELATIVE
    if status == "STALE":
        return TemporalStatus.HISTORICAL
    if status == "UNCERTAIN" and "MISSING_PROVENANCE" in reasons:
        return TemporalStatus.UNDATED
    return TemporalStatus.UNKNOWN


# ---------------------------------------------------------------------------
# Assessment
# ---------------------------------------------------------------------------


def record_event_times(record: Any) -> tuple[Any, Any, Any]:
    """The EXISTING event timestamps of a record: (retrieved, extracted, verified).

    ``retrieved_at`` falls back to the earliest evidence retrieval; a missing
    value stays ``None`` (never invented).
    """
    evidence = tuple(getattr(record, "evidence", ()) or ())
    retrieved_at = _as_datetime(getattr(record, "retrieved_at", None)) or _earliest(
        [getattr(item, "retrieved_at", None) for item in evidence]
    )
    extracted_at = _as_datetime(getattr(record, "extracted_at", None))
    verified_at = _as_datetime(getattr(record, "verified_at", None))
    return retrieved_at, extracted_at, verified_at


def record_source_uris(record: Any) -> tuple[str, ...]:
    """The source identity recorded on a record's evidence (attribution)."""
    return tuple(
        uri
        for uri in (
            _clean(getattr(item, "source_uri", ""), 200)
            for item in (getattr(record, "evidence", ()) or ())
        )
        if uri
    )


def knowledge_ref_for(record: Any) -> Any | None:
    """The EXISTING ``KnowledgeRef`` for a retained record, or ``None``.

    Shared by the temporal overlay (Step 19) and knowledge refresh (Step 20) so
    both evaluate the SAME projection with the EXISTING freshness assessor.
    Deterministic and read-only; ``None`` when the freshness model is
    unavailable (fail-closed).
    """
    try:
        from atlas.evolution.freshness.models import KnowledgeRef
    except Exception:  # pragma: no cover - defensive
        return None
    record_id = _clean(getattr(record, "record_id", ""), 120)
    claim_id = _clean(getattr(record, "claim_id", ""), 120)
    retrieved_at, _extracted_at, verified_at = record_event_times(record)
    try:
        return KnowledgeRef(
            knowledge_id=record_id or claim_id,
            source_uris=record_source_uris(record),
            claim_id=claim_id,
            # a recorded verification exists whenever a status was recorded
            verification_id=(
                f"verify:{claim_id}"
                if getattr(record, "verification_status", "")
                else ""
            ),
            retrieved_at=retrieved_at,
            verified_at=verified_at,
            confidence=getattr(record, "confidence", None),
        )
    except Exception:  # pragma: no cover - defensive
        return None


def assess_record_temporal(
    record: Any,
    *,
    assessor: Any | None = None,
    now: Any = None,
) -> KnowledgeTemporal:
    """Temporal view of one retained record (pure; never raises).

    ``assessor`` is the EXISTING ``KnowledgeFreshnessAssessor`` (a default one is
    built when omitted) and ``now`` is the injectable clock, exactly as the
    existing assessor convention requires.
    """
    record_id = _clean(getattr(record, "record_id", ""), 120)
    claim_id = _clean(getattr(record, "claim_id", ""), 120)
    standing = _clean(getattr(record, "standing", ""), 32)
    justified = bool(getattr(record, "justified", True))

    retrieved_at, extracted_at, verified_at = record_event_times(record)

    knowledge_time = ""
    knowledge_time_known = False
    recorded = _clean(getattr(record, "knowledge_time", ""), 64)
    if recorded:
        knowledge_time = recorded
        knowledge_time_known = True
    else:
        candidate = _content_time(record)
        if candidate:
            knowledge_time = candidate
            knowledge_time_known = True

    assessment: Any = None
    assessed_at: Any = None
    reasons: tuple[str, ...] = ()
    rationale = ""
    status = TemporalStatus.UNDATED
    age_days: float | None = None
    try:
        engine = assessor
        if engine is None:
            from atlas.evolution.freshness.assessor import (
                KnowledgeFreshnessAssessor,
            )

            engine = KnowledgeFreshnessAssessor()
        reference = knowledge_ref_for(record)
        if reference is None:
            raise ValueError("no freshness reference could be built")
        assessment = engine.assess(reference, now=now)
        status = _temporal_status(assessment)
        assessed_at = getattr(assessment, "assessed_at", None)
        reasons = tuple(
            _name(r) for r in (getattr(assessment, "reasons", ()) or ())
        )[:_MAX_REASONS]
        rationale = _clean(getattr(assessment, "rationale", ""), 120)
        if retrieved_at is not None and assessed_at is not None:
            try:
                age_days = round((assessed_at - retrieved_at).total_seconds() / 86400, 3)
            except Exception:
                age_days = None
    except Exception:  # fail-closed: no assessment, no invented freshness
        status = TemporalStatus.UNDATED if not retrieved_at else TemporalStatus.UNKNOWN

    findings: list[str] = []
    if knowledge_time_known:
        findings.append(
            "a source recorded a content time; it is kept distinct from when "
            "Atlas acquired the claim"
        )
    else:
        findings.append(
            "no content-time evidence was recorded; only when Atlas "
            "retrieved/extracted/verified the claim is known (knowledge_time is "
            "unknown, never inferred)"
        )
    if not (retrieved_at or extracted_at or verified_at):
        findings.append(
            "no acquisition/verification timestamp was recorded, so temporal "
            "standing is unknown (never assumed current)"
        )
    if status is TemporalStatus.CURRENT_RELATIVE:
        findings.append(
            "current relative to when Atlas acquired it, not a statement that the "
            "content is true now"
        )
    if status is TemporalStatus.HISTORICAL:
        findings.append(
            "the recorded evidence is older than the existing freshness window"
        )

    return KnowledgeTemporal(
        record_id=record_id,
        claim_id=claim_id,
        status=status,
        standing=standing,
        justified=justified,
        knowledge_time=knowledge_time,
        knowledge_time_known=knowledge_time_known,
        retrieved_at=retrieved_at,
        extracted_at=extracted_at,
        verified_at=verified_at,
        assessed_at=assessed_at,
        age_days=age_days,
        reasons=reasons,
        rationale=rationale,
        findings=tuple(findings[:_MAX_FINDINGS]),
    )


def assess_temporal(
    records: Any,
    *,
    assessor: Any | None = None,
    now: Any = None,
) -> tuple[KnowledgeTemporal, ...]:
    """Temporal views for many retained records (deterministic order)."""
    ordered = sorted(
        (r for r in records or ()),
        key=lambda r: _clean(getattr(r, "claim_id", ""), 120),
    )
    return tuple(
        assess_record_temporal(record, assessor=assessor, now=now)
        for record in ordered[:_MAX_ITEMS]
    )


def temporal_from_retained(
    retained: Any,
    *,
    assessor: Any | None = None,
    now: Any = None,
) -> TemporalKnowledge:
    """Temporal overlay for a Step 18 ``RetainedKnowledge`` result (never raises).

    The overlay only ADDS temporal information: the retrieval status, the query
    and the retained records themselves are unchanged, and the Steps 17-18
    standing/justification is carried through verbatim.
    """
    raw_status = getattr(retained, "status", "")
    status = _clean(getattr(raw_status, "value", raw_status), 32)
    return TemporalKnowledge(
        status=status,
        query=_clean(getattr(retained, "query", ""), 200),
        entries=assess_temporal(
            getattr(retained, "records", ()) or (), assessor=assessor, now=now
        ),
        message=_clean(getattr(retained, "message", ""), _MAX_TEXT_CHARS),
    )


__all__ = [
    "KnowledgeTemporal",
    "TemporalKnowledge",
    "TemporalStatus",
    "assess_record_temporal",
    "assess_temporal",
    "knowledge_ref_for",
    "record_event_times",
    "record_source_uris",
    "temporal_from_retained",
]
