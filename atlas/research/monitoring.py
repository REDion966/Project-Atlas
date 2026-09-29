"""Atlas — Continuous Information Monitoring (Step 21).

A bounded, deterministic, model-free monitoring pass over retained knowledge
(Steps 18-20): it represents bounded monitoring targets, determines which of them
require attention using the EXISTING temporal/freshness machinery, and emits
deterministic observations plus actionable refresh candidates.

It is NOT a scheduler, NOT a second freshness or refresh pipeline, and NOT an
alerting system: attention is decided by the EXISTING Step 19 temporal overlay and
the EXISTING Step 20 refresh plan, execution is the EXISTING Step 20 refresh, and
observations are returned data — nothing is published, queued, persisted, fetched,
replaced or promoted here. Continuity is provided by the caller: the monitoring
pass is a bounded, explicitly callable unit that the existing externally-driven
``Atlas.tick()``/runtime loop (or a CLI/host) can invoke; it is deliberately NOT
wired into ``Atlas.tick()``, so nothing happens automatically.

Guarantees:

* **Observe, never mutate.** ``monitor`` reads the EXISTING store, the EXISTING
  temporal overlay and the EXISTING refresh plan. It performs no acquisition, no
  I/O, no write, no promotion and no authorization, and it never modifies the
  monitored knowledge.
* **Idempotent.** An observation id is derived deterministically from the record
  and its attention kind, observations are de-duplicated within a pass, and the
  output is stable across repeated passes with the same clock.
* **Attention from evidence only.** ``fresh`` / ``stale`` / ``uncertain`` /
  ``temporally_unknown`` come from the EXISTING assessor through the Step 19
  status and the Step 20 request; a missing signal reports ``unknown`` rather
  than assuming freshness.
* **Refresh only when asked.** ``monitor_and_refresh`` is the ONLY path that
  touches the acquisition boundary and it reuses the Step 20 ``KnowledgeRefresher``
  unchanged — no second refresh path exists.
* **Bounded, deterministic, model-free, fail-closed.** Every collection is
  capped, the clock is injectable (the existing assessor convention), no model is
  consulted, and an unavailable store fails closed with an explicit status.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from atlas.research.knowledge_representation import RetainedKnowledgeRetriever
from atlas.research.refresh import (
    KnowledgeRefresh,
    KnowledgeRefresher,
    RefreshRequest,
    build_refresh_request,
)
from atlas.research.temporal import TemporalStatus, assess_record_temporal

#: Bounds (a malformed or huge store can never produce unbounded output).
_MAX_TARGETS: int = 8
_MAX_OBSERVATIONS: int = 8
_MAX_SOURCES: int = 8
_MAX_FINDINGS: int = 6
_MAX_TEXT_CHARS: int = 300
_MAX_REASON_CHARS: int = 300

#: The monitoring rule, stated once so callers can report it verbatim.
MONITORING_RULE: str = (
    "Monitoring observes retained knowledge and reports bounded attention "
    "observations using the existing temporal/freshness and refresh machinery. "
    "It never fetches, replaces, promotes or authorizes anything: refresh happens "
    "only through an explicit call that reuses the existing governed refresh path."
)

#: The store statuses of the EXISTING retained-knowledge retrieval.
_RETRIEVAL_OK = "ok"
_RETRIEVAL_EMPTY = "empty"
_RETRIEVAL_UNAVAILABLE = "store_unavailable"
_RETRIEVAL_ERROR = "store_error"


class AttentionKind(str, Enum):
    """Why (or whether) a monitored record requires attention (closed set)."""

    FRESH = "fresh"
    STALE = "stale"
    UNCERTAIN = "uncertain"
    TEMPORALLY_UNKNOWN = "temporally_unknown"
    UNKNOWN = "unknown"


class MonitoringStatus(str, Enum):
    """Outcome of a bounded monitoring pass (mirrors the retrieval statuses)."""

    OK = "ok"
    EMPTY = "empty"
    STORE_UNAVAILABLE = "store_unavailable"
    STORE_ERROR = "store_error"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class MonitoringTarget:
    """One bounded monitoring target derived from retained knowledge."""

    record_id: str
    claim_id: str
    statement: str
    standing: str
    temporal_status: str
    monitored: bool
    sources: tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "claim_id": self.claim_id,
            "statement": self.statement,
            "standing": self.standing,
            "temporal_status": self.temporal_status,
            "monitored": self.monitored,
            "sources": list(self.sources),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class MonitoringObservation:
    """A deterministic monitoring observation for one monitored record."""

    observation_id: str
    record_id: str
    claim_id: str
    statement: str
    standing: str
    attention: str
    temporal_status: str
    age_days: float | None = None
    reasons: tuple[str, ...] = ()
    requires_attention: bool = False
    refresh_required: bool = False
    action: str = "none"
    query: str = ""
    sources: tuple[str, ...] = ()
    request: RefreshRequest | None = None
    findings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "record_id": self.record_id,
            "claim_id": self.claim_id,
            "statement": self.statement,
            "standing": self.standing,
            "attention": self.attention,
            "temporal_status": self.temporal_status,
            "age_days": self.age_days,
            "reasons": list(self.reasons),
            "requires_attention": self.requires_attention,
            "refresh_required": self.refresh_required,
            "action": self.action,
            "query": self.query,
            "sources": list(self.sources),
            "request": self.request.to_dict() if self.request is not None else None,
            "findings": list(self.findings),
        }


@dataclass(frozen=True, slots=True)
class MonitoringReport:
    """The bounded result of one monitoring pass (immutable)."""

    status: MonitoringStatus
    query: str
    targets: tuple[MonitoringTarget, ...] = ()
    observations: tuple[MonitoringObservation, ...] = ()
    message: str = ""
    findings: tuple[str, ...] = ()

    @property
    def observed_count(self) -> int:
        return len(self.observations)

    @property
    def attention_required(self) -> tuple[MonitoringObservation, ...]:
        return tuple(o for o in self.observations if o.requires_attention)

    @property
    def refresh_candidates(self) -> tuple[MonitoringObservation, ...]:
        return tuple(o for o in self.observations if o.refresh_required)

    @property
    def fresh_count(self) -> int:
        return sum(
            1 for o in self.observations if o.attention == AttentionKind.FRESH.value
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "query": self.query,
            "targets": [t.to_dict() for t in self.targets],
            "observations": [o.to_dict() for o in self.observations],
            "message": self.message,
            "findings": list(self.findings),
            "observed_count": self.observed_count,
            "fresh_count": self.fresh_count,
            "attention_required": [
                o.observation_id for o in self.attention_required
            ],
            "refresh_candidates": [
                o.observation_id for o in self.refresh_candidates
            ],
            "monitoring_rule": MONITORING_RULE,
        }


@dataclass(frozen=True, slots=True)
class MonitoringRun:
    """A monitoring pass plus the refresh it was explicitly asked to perform."""

    report: MonitoringReport
    refresh: KnowledgeRefresh | None = None

    @property
    def refreshed_count(self) -> int:
        return self.refresh.refreshed_count if self.refresh is not None else 0

    @property
    def preserved_count(self) -> int:
        return self.refresh.preserved_count if self.refresh is not None else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "report": self.report.to_dict(),
            "refresh": self.refresh.to_dict() if self.refresh is not None else None,
            "refreshed_count": self.refreshed_count,
            "preserved_count": self.preserved_count,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _value(value: Any, limit: int = 48) -> str:
    raw = getattr(value, "value", value)
    if raw is None:
        return ""
    return _clean(raw, limit)


def _float(value: Any) -> float | None:
    try:
        return round(float(value), 3)
    except Exception:
        return None


def attention_for(temporal_status: Any) -> tuple[AttentionKind, bool]:
    """Attention for an EXISTING temporal status (never assumes freshness).

    Public so a caller (or a test) can reason about the mapping directly, exactly
    like the Step 17 ``claim_standing`` helper. An unrecognised status yields
    ``unknown`` — never ``fresh``.
    """
    status = _value(temporal_status)
    if not status:
        status = _clean(temporal_status, 32).lower()
    if status == TemporalStatus.HISTORICAL.value:
        return AttentionKind.STALE, True
    if status == TemporalStatus.UNDATED.value:
        return AttentionKind.TEMPORALLY_UNKNOWN, True
    if status == TemporalStatus.UNKNOWN.value:
        return AttentionKind.UNCERTAIN, True
    if status == TemporalStatus.CURRENT_RELATIVE.value:
        return AttentionKind.FRESH, False
    return AttentionKind.UNKNOWN, False


def _observation_for(record: Any, request: RefreshRequest, *, now: Any = None,
                     assessor: Any | None = None) -> MonitoringObservation:
    view = assess_record_temporal(record, assessor=assessor, now=now)
    attention, requires_attention = attention_for(request.temporal_status)
    record_id = _clean(getattr(record, "record_id", ""), 120) or request.record_id
    claim_id = _clean(getattr(record, "claim_id", ""), 120) or request.claim_id

    findings: list[str] = []
    if attention is AttentionKind.STALE:
        findings.append(
            "the recorded evidence is older than the existing freshness window; a "
            "governed refresh is available for this record"
        )
    elif attention is AttentionKind.TEMPORALLY_UNKNOWN:
        findings.append(
            "no temporal evidence was recorded, so a governed review is required "
            "and no refresh was scheduled"
        )
    elif attention is AttentionKind.UNCERTAIN:
        findings.append(
            "the existing freshness evidence is uncertain; a governed review is "
            "required and no refresh was scheduled"
        )
    elif attention is AttentionKind.FRESH:
        findings.append("the record is current relative to its acquisition")
    else:
        findings.append(
            "no grounded freshness signal was available, so attention is unknown"
        )
    findings.append("observation only: nothing was fetched, replaced or promoted")

    return MonitoringObservation(
        observation_id=f"monitor:{record_id}:{attention.value}",
        record_id=record_id,
        claim_id=claim_id,
        statement=_clean(getattr(record, "statement", ""), 200) or request.statement,
        standing=_value(getattr(record, "standing", "")) or request.standing,
        attention=attention.value,
        temporal_status=request.temporal_status,
        age_days=_float(getattr(view, "age_days", None)),
        reasons=tuple(request.reasons)[:8],
        requires_attention=requires_attention,
        refresh_required=bool(request.required),
        action=request.action,
        query=request.query,
        sources=tuple(request.sources)[:_MAX_SOURCES],
        request=request,
        findings=tuple(findings[:_MAX_FINDINGS]),
    )


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------


class KnowledgeMonitor:
    """Bounded monitoring over retained knowledge (read-only, idempotent).

    ``storage`` is the EXISTING research storage; ``refresher`` is the EXISTING
    Step 20 ``KnowledgeRefresher``, used ONLY by :meth:`monitor_and_refresh`.
    """

    def __init__(
        self,
        *,
        storage: Any | None = None,
        retriever: Any | None = None,
        assessor: Any | None = None,
        refresher: KnowledgeRefresher | None = None,
        max_targets: int = _MAX_TARGETS,
    ) -> None:
        self._storage = storage
        self._retriever = retriever or RetainedKnowledgeRetriever(storage)
        self._assessor = assessor
        self._refresher = refresher
        self._max_targets = max(1, int(max_targets))

    # -- observation -------------------------------------------------------

    def monitor(self, query: str, *, now: Any = None) -> MonitoringReport:
        """Observe retained knowledge once; never fetches and never mutates."""
        retained = self._retrieve(query)
        status = _value(getattr(retained, "status", ""))
        message = _clean(getattr(retained, "message", ""), _MAX_TEXT_CHARS)
        if status in (_RETRIEVAL_UNAVAILABLE, _RETRIEVAL_ERROR):
            return MonitoringReport(
                status=(
                    MonitoringStatus.STORE_UNAVAILABLE
                    if status == _RETRIEVAL_UNAVAILABLE
                    else MonitoringStatus.STORE_ERROR
                ),
                query=_clean(query, 200),
                message=message,
                findings=("the retained-knowledge store could not be read; nothing "
                          "was observed (fail-closed)",),
            )

        records = tuple(getattr(retained, "records", ()) or ())
        targets: list[MonitoringTarget] = []
        observations: list[MonitoringObservation] = []
        seen: set[str] = set()
        for record in sorted(
            records, key=lambda r: _clean(getattr(r, "claim_id", ""), 120)
        )[: self._max_targets]:
            view = assess_record_temporal(record, assessor=self._assessor, now=now)
            request = build_refresh_request(
                record, temporal=view, assessor=self._assessor, now=now
            )
            targets.append(
                MonitoringTarget(
                    record_id=request.record_id,
                    claim_id=request.claim_id,
                    statement=request.statement,
                    standing=request.standing,
                    temporal_status=request.temporal_status,
                    monitored=True,
                    sources=tuple(request.sources)[:_MAX_SOURCES],
                    reason=_clean(request.reason, _MAX_REASON_CHARS),
                )
            )
            observation = _observation_for(
                record, request, now=now, assessor=self._assessor
            )
            if observation.observation_id in seen:
                continue  # idempotent: a repeated observation is collapsed
            seen.add(observation.observation_id)
            observations.append(observation)

        findings: list[str] = []
        if not records:
            findings.append(
                "no retained knowledge matched the query; nothing to monitor"
            )
        else:
            attention = sum(1 for o in observations if o.requires_attention)
            findings.append(
                f"{attention} of {len(observations)} monitored record(s) require "
                "attention"
            )
            if not attention:
                findings.append(
                    "every monitored record is current relative to its acquisition"
                )
        return MonitoringReport(
            status=(
                MonitoringStatus.OK if observations else MonitoringStatus.EMPTY
            ),
            query=_clean(query, 200),
            targets=tuple(targets[:_MAX_TARGETS]),
            observations=tuple(observations[:_MAX_OBSERVATIONS]),
            message=message,
            findings=tuple(findings[:_MAX_FINDINGS]),
        )

    def monitor_and_refresh(
        self,
        query: str,
        *,
        candidate_urls: Any = (),
        now: Any = None,
    ) -> MonitoringRun:
        """Monitor, then explicitly refresh the refresh candidates.

        The refresh is the EXISTING Step 20 ``KnowledgeRefresher`` — there is no
        second refresh path. With no candidate requiring refresh (or no refresher
        wired) the acquisition boundary is never touched.
        """
        retained = self._retrieve(query)
        report = self.monitor(query, now=now)
        candidates = report.refresh_candidates
        if not candidates or self._refresher is None:
            return MonitoringRun(report=report, refresh=None)
        wanted = {o.claim_id for o in candidates}
        records = tuple(
            r
            for r in (getattr(retained, "records", ()) or ())
            if _clean(getattr(r, "claim_id", ""), 120) in wanted
        )
        refresh = self._refresher.refresh_all(
            records, candidate_urls=candidate_urls, now=now
        )
        return MonitoringRun(report=report, refresh=refresh)

    # -- internals ---------------------------------------------------------

    def _retrieve(self, query: str) -> Any:
        try:
            return self._retriever.retrieve(query)
        except Exception:  # fail-closed: an unreadable store is reported
            return None


def knowledge_monitor(
    *,
    storage: Any | None = None,
    retriever: Any | None = None,
    assessor: Any | None = None,
    refresher: KnowledgeRefresher | None = None,
) -> KnowledgeMonitor:
    """Convenience constructor for :class:`KnowledgeMonitor`."""
    return KnowledgeMonitor(
        storage=storage,
        retriever=retriever,
        assessor=assessor,
        refresher=refresher,
    )


__all__ = [
    "AttentionKind",
    "KnowledgeMonitor",
    "MONITORING_RULE",
    "MonitoringObservation",
    "MonitoringReport",
    "MonitoringRun",
    "MonitoringStatus",
    "MonitoringTarget",
    "attention_for",
    "knowledge_monitor",
]
