"""Atlas Post-Core F11 - Long-Term Self-Management & Recovery Review.

A small, pure, deterministic, externally-invoked single-shot review that
aggregates bounded durable evidence from EXISTING stores into one JSON-safe
self-management report:

    EvolutionMemory records        (outcome trend / failure streaks)
    LearningMemory insights        (learning signal counts)
    ScheduleStore queues           (stale PENDING_AUTHORIZATION ages)
    F10 availability snapshot       (provider health)
    lifecycle component statuses    (DEGRADED / OFFLINE components)

ARCHITECTURAL BOUNDARY:
  * Evidence ONLY. The review never approves, rejects, authorizes, executes,
    applies, promotes, schedules, or rolls back anything. Flagged maintenance
    needs are inert assessment objects consumable by the EXISTING F6/F9
    governance flows; F11 stops well before any approval boundary.
  * Read-only: source stores are never mutated.
  * No persistence of its own; no new database/EventBus/scheduler/memory
    subsystem; no background loop; runs exactly once per invocation.
  * Model-independent: pure logic over stored data; never imports atlas.ai.
  * Fail-closed: constructor validates inputs; per-source runtime failures
    are recorded in the bounded ``source_errors`` list instead of crashing;
    malformed constructor inputs raise immediately.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

#: Default bounded evidence windows.
DEFAULT_MAX_RECORDS = 200
DEFAULT_MAX_INSIGHTS = 50
DEFAULT_MAX_REQUESTS = 100
DEFAULT_MAX_NEEDS = 10
DEFAULT_STALE_AUTHORIZATION_SECONDS = 86_400.0
DEFAULT_FAILURE_STREAK_THRESHOLD = 3
_MAX_EVIDENCE_IDS = 10


def utc_now() -> datetime:
    """Return the current UTC-aware datetime."""
    return datetime.now(timezone.utc)


def _bounded_text(exc: Exception, limit: int = 200) -> str:
    """Return a bounded, secret-free error message."""
    text = str(exc).strip() or type(exc).__name__
    return text[:limit]


@dataclass(frozen=True, slots=True)
class SelfManagementPolicy:
    """Deterministic bounds for one review invocation."""

    max_records: int = DEFAULT_MAX_RECORDS
    max_insights: int = DEFAULT_MAX_INSIGHTS
    max_requests: int = DEFAULT_MAX_REQUESTS
    max_needs: int = DEFAULT_MAX_NEEDS
    stale_authorization_seconds: float = DEFAULT_STALE_AUTHORIZATION_SECONDS
    failure_streak_threshold: int = DEFAULT_FAILURE_STREAK_THRESHOLD

    def __post_init__(self) -> None:
        for name in (
            "max_records",
            "max_insights",
            "max_requests",
            "max_needs",
            "failure_streak_threshold",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")
        if self.stale_authorization_seconds <= 0:
            raise ValueError("stale_authorization_seconds must be > 0")


@dataclass(frozen=True, slots=True)
class MaintenanceNeed:
    """Inert, evidence-backed maintenance need (never executed here).

    Attributes:
        need_id: Deterministic identifier within this review.
        kind: Stable category, e.g. ``review_stale_authorizations``.
        summary: Bounded human-readable description.
        evidence_ids: Bounded provenance pointing at durable records.
        detected_at: When the need was flagged.
    """

    need_id: str
    kind: str
    summary: str
    evidence_ids: tuple[str, ...]
    detected_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "need_id": self.need_id,
            "kind": self.kind,
            "summary": self.summary,
            "evidence_ids": list(self.evidence_ids),
            "detected_at": self.detected_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class SelfManagementReport:
    """Bounded, deterministic, JSON-safe result of one review invocation."""

    review_id: str
    decision: str = "reviewed"          # reviewed | failed
    status: str = "ok"                  # ok | failed
    generated_at: datetime = field(default_factory=utc_now)
    outcome_trend: dict[str, int] = field(default_factory=dict)
    failure_streak: int = 0
    stale_authorization_count: int = 0
    stale_authorization_ids: tuple[str, ...] = ()
    degraded_components: tuple[str, ...] = ()
    offline_components: tuple[str, ...] = ()
    availability_status: str = ""
    insight_count: int = 0
    failure_pattern_count: int = 0
    needs: tuple[MaintenanceNeed, ...] = ()
    source_errors: tuple[tuple[str, str], ...] = ()
    elapsed_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        """True when the review completed without hard failure."""
        return self.decision == "reviewed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "decision": self.decision,
            "status": self.status,
            "generated_at": self.generated_at.isoformat(),
            "outcome_trend": dict(self.outcome_trend),
            "failure_streak": self.failure_streak,
            "stale_authorization_count": self.stale_authorization_count,
            "stale_authorization_ids": list(self.stale_authorization_ids),
            "degraded_components": list(self.degraded_components),
            "offline_components": list(self.offline_components),
            "availability_status": self.availability_status,
            "insight_count": self.insight_count,
            "failure_pattern_count": self.failure_pattern_count,
            "needs": [n.to_dict() for n in self.needs],
            "source_errors": [list(e) for e in self.source_errors],
            "elapsed_seconds": round(self.elapsed_seconds, 4),
        }


class SelfManagementReview:
    """Single-shot, read-only aggregation of durable self-management evidence.

    Args:
        evolution_memory: EXISTING ``EvolutionMemory`` (duck-typed; uses
            ``get_records(n)`` only).
        learning_memory: EXISTING ``LearningMemory`` (duck-typed; uses
            ``get_insights`` / ``get_failures`` when available).
        schedule_store: EXISTING ``ScheduleStore`` (duck-typed; uses
            ``pending_authorization()`` only).
        availability: EXISTING F10 tracker (duck-typed; uses
            ``snapshot()`` only).
        components: Optional duck-typed iterable/callable of lifecycle
            components exposing ``name`` and ``status`` (ComponentStatus).
        policy: Deterministic bounds (defaults).
        clock: Optional ``Callable[[], datetime]`` (UTC) for tests.
    """

    def __init__(
        self,
        *,
        evolution_memory: Any | None = None,
        learning_memory: Any | None = None,
        schedule_store: Any | None = None,
        availability: Any | None = None,
        components: Any | None = None,
        policy: SelfManagementPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if policy is not None and not isinstance(policy, SelfManagementPolicy):
            raise ValueError("policy must be a SelfManagementPolicy")
        if clock is not None and not callable(clock):
            raise ValueError("clock must be callable")
        self._evolution_memory = evolution_memory
        self._learning_memory = learning_memory
        self._schedule_store = schedule_store
        self._availability = availability
        self._components = components
        self._policy = policy or SelfManagementPolicy()
        self._clock = clock or utc_now
        self._counter = 0

    @property
    def policy(self) -> SelfManagementPolicy:
        """The applied bounds (read-only)."""
        return self._policy

    # -- public single-shot entry -------------------------------------------

    def run_review(self) -> SelfManagementReport:
        """Run ONE bounded review invocation over durable evidence."""
        started = time.monotonic()
        generated_at = self._clock()
        self._counter += 1
        review_id = f"SMR-{self._counter:06d}"
        p = self._policy

        outcome_trend: dict[str, int] = {}
        failure_streak = 0
        needs: list[MaintenanceNeed] = []
        source_errors: list[tuple[str, str]] = []

        # 1. EvolutionMemory records — trend counts + trailing failure streak.
        record_ids_by_failure: list[str] = []
        if self._evolution_memory is not None:
            try:
                records = self._evolution_memory.get_records(p.max_records)
                for record in reversed(records):  # oldest -> newest
                    event_type = str(getattr(record, "event_type", ""))
                    outcome_trend[event_type] = outcome_trend.get(event_type, 0) + 1
                    if self._is_failure_record(record):
                        failure_streak += 1
                        rid = getattr(record, "record_id", "")
                        if rid and len(record_ids_by_failure) < _MAX_EVIDENCE_IDS:
                            record_ids_by_failure.append(str(rid))
                    else:
                        failure_streak = 0
            except Exception as exc:
                source_errors.append(("evolution_memory", _bounded_text(exc)))

        def _need(kind: str, summary: str, evidence: list[str]) -> None:
            if len(needs) < p.max_needs:
                now = self._clock()
                needs.append(
                    MaintenanceNeed(
                        need_id=f"NEED-{review_id}-{len(needs) + 1:02d}",
                        kind=kind,
                        summary=summary[:300],
                        evidence_ids=tuple(
                            dict.fromkeys(evidence)
                        )[:_MAX_EVIDENCE_IDS],
                        detected_at=now,
                    )
                )

        if (
            failure_streak
            >= p.failure_streak_threshold
            > 0
            and record_ids_by_failure
        ):
            _need(
                "investigate_recurring_failures",
                f"{failure_streak} consecutive failed outcomes recorded.",
                record_ids_by_failure,
            )

        # 2. ScheduleStore — stale PENDING_AUTHORIZATION requests.
        pending_ids: list[str] = []
        stale_ids: list[str] = []
        if self._schedule_store is not None:
            try:
                pending = self._schedule_store.pending_authorization()[
                    : p.max_requests
                ]
                now = self._clock()
                for request in pending:
                    request_id = str(getattr(request, "request_id", ""))
                    if request_id:
                        pending_ids.append(request_id)
                    created = getattr(request, "created_at", None)
                    # Normalize naive timestamps to UTC so age math never
                    # mixes offset-naive and offset-aware datetimes.
                    # (ApprovalManager stamps naive datetime.now().)
                    if (
                        created is not None
                        and isinstance(created, datetime)
                        and created.tzinfo is None
                    ):
                        created = created.replace(tzinfo=timezone.utc)
                    if (
                        request_id
                        and created is not None
                        and (now - created).total_seconds()
                        > p.stale_authorization_seconds
                    ):
                        stale_ids.append(request_id)
            except Exception as exc:
                source_errors.append(("schedule_store", _bounded_text(exc)))
        if stale_ids:
            _need(
                "review_stale_authorizations",
                f"{len(stale_ids)} request(s) awaiting user authorization "
                f"for more than {int(p.stale_authorization_seconds)}s.",
                stale_ids,
            )

        # 3. LearningMemory — insight / failure-pattern signal counts.
        insight_count = 0
        failure_pattern_count = 0
        failure_pattern_evidence: list[str] = []
        if self._learning_memory is not None:
            try:
                get_insights = getattr(self._learning_memory, "get_insights", None)
                if callable(get_insights):
                    insights = get_insights(p.max_insights)
                    insight_count = len(insights)
                get_failures = getattr(self._learning_memory, "get_failures", None)
                if callable(get_failures):
                    patterns = get_failures(p.max_insights)
                    failure_pattern_count = len(patterns)
                    for pattern in patterns[:_MAX_EVIDENCE_IDS]:
                        pid = str(getattr(pattern, "pattern_id", "") or "")
                        if pid:
                            failure_pattern_evidence.append(pid)
            except Exception as exc:
                source_errors.append(("learning_memory", _bounded_text(exc)))

        # 4. F10 availability snapshot — provider health visibility.
        availability_status = ""
        if self._availability is not None:
            try:
                snapshot = self._availability.snapshot()
                availability_status = str(snapshot.get("status", ""))
            except Exception as exc:
                source_errors.append(("availability", _bounded_text(exc)))
        if availability_status == "OFFLINE":
            _need(
                "investigate_provider_availability",
                "AI provider availability reported OFFLINE from recent "
                "outcome history.",
                ["ai_provider"],
            )

        # 5. Lifecycle components — DEGRADED / OFFLINE detection.
        degraded: list[str] = []
        offline: list[str] = []
        if self._components is not None:
            try:
                items = self._components
                if callable(items) and not hasattr(items, "name"):
                    items = items()
                for component in list(items)[: p.max_requests]:
                    name = str(getattr(component, "name", "") or "")
                    status_name = getattr(
                        getattr(component, "status", None), "name", ""
                    )
                    if not name:
                        continue
                    if status_name == "OFFLINE":
                        offline.append(name)
                    elif status_name == "DEGRADED":
                        degraded.append(name)
            except Exception as exc:
                source_errors.append(("components", _bounded_text(exc)))
        if offline:
            _need(
                "restore_offline_components",
                f"{len(offline)} lifecycle component(s) are OFFLINE.",
                offline,
            )
        if degraded:
            _need(
                "investigate_degraded_components",
                f"{len(degraded)} lifecycle component(s) are DEGRADED.",
                degraded,
            )

        return SelfManagementReport(
            review_id=review_id,
            decision="reviewed",
            status="ok",
            generated_at=generated_at,
            outcome_trend=dict(sorted(outcome_trend.items())),
            failure_streak=failure_streak,
            stale_authorization_count=len(stale_ids),
            stale_authorization_ids=tuple(stale_ids[:_MAX_EVIDENCE_IDS]),
            degraded_components=tuple(sorted(set(degraded))),
            offline_components=tuple(sorted(set(offline))),
            availability_status=availability_status,
            insight_count=insight_count,
            failure_pattern_count=failure_pattern_count,
            needs=tuple(needs),
            source_errors=tuple(source_errors)[-10:],
            elapsed_seconds=time.monotonic() - started,
        )

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _is_failure_record(record: Any) -> bool:
        """Deterministically classify one EvolutionRecord as a failure."""
        event_type = str(getattr(record, "event_type", ""))
        if "failure" in event_type.lower():
            return True
        metadata = getattr(record, "metadata", None)
        if isinstance(metadata, dict):
            if metadata.get("decision") in {"FAILURE_LIMIT", "failed"}:
                return True
            failures = metadata.get("failures")
            if isinstance(failures, (list, tuple)) and failures:
                return True
            if metadata.get("useful") is False and metadata.get("cycles"):
                return False
        description = str(getattr(record, "description", ""))
        if event_type == "operation_cycle" and "FAILURE_LIMIT" in description:
            return True
        return False