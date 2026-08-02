"""
Atlas Evolution Autonomy — Schedule Store — Phase 16.4

Persistent schedule store for ``EvolutionRequest`` lifecycle states.

Responsibilities:
- Save and load requests via ``AutonomySQLiteStorage``.
- Atomic compare-and-swap status transitions.
- Atomic claim: ``SCHEDULED`` → ``APPLIED`` with optimistic-concurrency
  version check (mismatch ⇒ ``SUPERSEDED``).
- Query queues: pending authorization, scheduled, due, in-flight.
- Quota accounting for the current policy window.
- Build an ``EvolutionStatusReport`` from storage.

The store is pure logic over the injected storage adapter. It does not
schedule timers, does not call the gateway, and does not execute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from atlas.evolution.autonomy.models import (
    AtlasStateVersion,
    AutonomyPolicy,
    AuthorizationMode,
    EvolutionAuthorization,
    EvolutionOutcomeRecord,
    EvolutionRequest,
    EvolutionRequestStatus,
    EvolutionSchedule,
    EvolutionStatusReport,
    EvolutionWindow,
    RiskAssessment,
    ValidationReport,
    VersionTarget,
)
from atlas.evolution.models import ExecutionLevel
from atlas.storage.autonomy_storage import AutonomySQLiteStorage


@dataclass(frozen=True, slots=True)
class ClaimResult:
    """Outcome of an atomic claim attempt.

    Attributes:
        request: The request after the claim (or after superseding), or None
            if the request was not found.
        superseded: True when the claim was aborted because the version anchor
            no longer matched and the request was marked SUPERSEDED.
        claimed: True when the request was successfully moved to APPLIED.
    """

    request: EvolutionRequest | None
    superseded: bool = False
    claimed: bool = False


@dataclass(frozen=True, slots=True)
class ScheduleStore:
    """Persistent schedule store for EvolutionRequest lifecycle.

    Dependencies (constructor-injected):
      - storage: ``AutonomySQLiteStorage`` adapter.
      - policy: the active ``AutonomyPolicy`` snapshot.
      - clock: optional callable returning ``datetime.now()`` for tests.

    All mutable state lives in SQLite. This object is stateless.
    """

    storage: AutonomySQLiteStorage
    policy: AutonomyPolicy
    clock: Any = field(default_factory=lambda: datetime.now)

    def __post_init__(self) -> None:
        if self.storage is None:
            raise ValueError("AutonomySQLiteStorage is required")
        if self.policy is None:
            raise ValueError("AutonomyPolicy is required")

    # ------------------------------------------------------------------
    # Basic persistence
    # ------------------------------------------------------------------

    def save_request(self, request: EvolutionRequest) -> None:
        """Persist a request."""
        self.storage.store_request(request)

    def get_request(self, request_id: str) -> EvolutionRequest | None:
        """Load a request by ID."""
        return self.storage.load_request(request_id)

    def delete_request(self, request_id: str) -> None:
        """Delete a request by ID (mainly for tests)."""
        self.storage.delete_request(request_id)

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------

    def update_status(
        self,
        request_id: str,
        expected_status: EvolutionRequestStatus,
        new_status: EvolutionRequestStatus,
        now: datetime | None = None,
    ) -> bool:
        """Atomic CAS status update.

        Returns True iff the request existed with ``expected_status``.
        """
        when = now if now is not None else self.clock()
        return self.storage.update_status(
            request_id,
            expected_status.name,
            new_status.name,
            when.isoformat(),
        )

    def claim_scheduled(
        self,
        request_id: str,
        state_version_at_creation: str,
        now: datetime | None = None,
    ) -> ClaimResult:
        """Atomic claim: ``SCHEDULED`` → ``APPLIED`` with version anchor check.

        Per the architecture:
          - If the request is not SCHEDULED, refuse.
          - If ``state_version_at_creation`` does not match the request's
            anchor, mark the request ``SUPERSEDED`` and return it.
          - Otherwise atomically move it to ``APPLIED``.

        The storage CAS guarantees that only one caller can claim the row.
        """
        when = now if now is not None else self.clock()
        req = self.storage.load_request(request_id)
        if req is None:
            return ClaimResult(request=None)

        if req.status != EvolutionRequestStatus.SCHEDULED:
            return ClaimResult(request=req)

        if req.version_target is None:
            return ClaimResult(request=req)

        if req.version_target.state_version_at_creation != state_version_at_creation:
            self.storage.update_status(
                request_id,
                EvolutionRequestStatus.SCHEDULED.name,
                EvolutionRequestStatus.SUPERSEDED.name,
                when.isoformat(),
            )
            return ClaimResult(
                request=self.storage.load_request(request_id),
                superseded=True,
            )

        ok = self.storage.update_status(
            request_id,
            EvolutionRequestStatus.SCHEDULED.name,
            EvolutionRequestStatus.APPLIED.name,
            when.isoformat(),
        )
        if not ok:
            return ClaimResult(request=self.storage.load_request(request_id))
        return ClaimResult(
            request=self.storage.load_request(request_id),
            claimed=True,
        )

    # ------------------------------------------------------------------
    # Filtering and queues
    # ------------------------------------------------------------------

    def list_by_status(self, status: EvolutionRequestStatus) -> list[EvolutionRequest]:
        """Return all requests with the given status."""
        return self.storage.load_requests(status=status.name)

    def pending_authorization(self) -> list[EvolutionRequest]:
        """Return requests awaiting user authorization."""
        return self.storage.load_requests(
            status=EvolutionRequestStatus.PENDING_AUTHORIZATION.name
        )

    def scheduled(self) -> list[EvolutionRequest]:
        """Return all SCHEDULED requests."""
        return self.storage.load_requests(status=EvolutionRequestStatus.SCHEDULED.name)

    def in_flight(self) -> list[EvolutionRequest]:
        """Return APPLIED or PENDING_EFFECTIVE requests."""
        return [
            r
            for r in self.storage.load_requests()
            if r.status
            in {
                EvolutionRequestStatus.APPLIED,
                EvolutionRequestStatus.PENDING_EFFECTIVE,
            }
        ]

    def due_queue(self, now: datetime | None = None) -> list[EvolutionRequest]:
        """Return SCHEDULED requests that are eligible to apply now.

        Eligibility checks:
          - status is SCHEDULED
          - not cooling down
          - current time is within the request's own schedule window, if any
        """
        when = now if now is not None else self.clock()
        scheduled = self.scheduled()
        result: list[EvolutionRequest] = []
        for req in scheduled:
            if req.schedule is None:
                result.append(req)
                continue
            sched = req.schedule
            if sched.cooldown_until is not None and when < sched.cooldown_until:
                continue
            if sched.window_start is not None and when < sched.window_start:
                continue
            if sched.window_end is not None and when > sched.window_end:
                continue
            result.append(req)
        return result

    def find_ready_requests(self, now: datetime | None = None) -> list[EvolutionRequest]:
        """Return requests ready for the dispatcher to claim.

        A request is ready when:
          - status is SCHEDULED
          - it has passed any authorization expiry check (caller validates)
          - it is within its own schedule window

        Results are sorted by ``scheduled_at`` (FIFO) so the dispatcher
        applies the oldest scheduled request first.
        """
        return sorted(
            self.due_queue(now),
            key=lambda r: (
                r.schedule.scheduled_at if r.schedule is not None else r.created_at
            ),
        )

    def is_on_hold(self) -> bool:
        """Return True if any request is in ``EVOLUTION_HOLD``."""
        return any(
            r.status == EvolutionRequestStatus.EVOLUTION_HOLD
            for r in self.storage.load_requests()
        )

    # ------------------------------------------------------------------
    # Quota accounting
    # ------------------------------------------------------------------

    def quota_used_this_window(
        self,
        window: EvolutionWindow | None = None,
    ) -> int:
        """Count autonomous requests that have consumed quota in the window.

        Counts requests authorized by ``system:autonomy`` whose status is
        SCHEDULED, APPLIED, PENDING_EFFECTIVE, COMPLETED, FAILED, or
        ROLLED_BACK and whose ``updated_at`` falls within the window.
        """
        if window is None:
            return 0
        autonomous = [
            r
            for r in self.storage.load_requests()
            if r.authorization is not None
            and r.authorization.mode == AuthorizationMode.AUTONOMY
            and r.status
            in {
                EvolutionRequestStatus.SCHEDULED,
                EvolutionRequestStatus.APPLIED,
                EvolutionRequestStatus.PENDING_EFFECTIVE,
                EvolutionRequestStatus.COMPLETED,
                EvolutionRequestStatus.FAILED,
                EvolutionRequestStatus.ROLLED_BACK,
            }
            and window.window_start <= r.updated_at <= window.window_end
        ]
        return len(autonomous)

    # ------------------------------------------------------------------
    # Status report
    # ------------------------------------------------------------------

    def status_report(self) -> EvolutionStatusReport:
        """Build a typed status report from storage.

        ``state_version`` is derived from the latest persisted
        ``AtlasStateVersion`` manifest. ``hold`` is true if any request is
        in ``EVOLUTION_HOLD``.
        """
        all_requests = self.storage.load_requests()
        latest_version = self.storage.load_latest_version()
        state_version = ""
        if latest_version is not None:
            state_version = f"{latest_version.major}.{latest_version.minor}.{latest_version.patch}"

        pending_authorizations = sum(
            1
            for r in all_requests
            if r.status == EvolutionRequestStatus.PENDING_AUTHORIZATION
        )
        scheduled_ids = [
            r.request_id
            for r in all_requests
            if r.status == EvolutionRequestStatus.SCHEDULED
        ]
        in_flight_ids = [
            r.request_id
            for r in all_requests
            if r.status
            in {
                EvolutionRequestStatus.APPLIED,
                EvolutionRequestStatus.PENDING_EFFECTIVE,
            }
        ]
        hold = any(
            r.status == EvolutionRequestStatus.EVOLUTION_HOLD for r in all_requests
        )

        window = self.policy.window
        quota_used = self.quota_used_this_window(window)

        envelope = {
            "enabled": self.policy.enabled,
            "effective_execution_level": self.policy.effective_execution_level.name,
            "allowed_scopes": [s.name for s in self.policy.allowed_scopes],
            "max_risk_level": self.policy.max_risk_level.name,
            "max_requests_per_window": self.policy.max_requests_per_window,
            "requires_user_approval_scopes": [
                s.name for s in self.policy.requires_user_approval_scopes
            ],
        }
        if window is not None:
            envelope["window_start"] = window.window_start.isoformat()
            envelope["window_end"] = window.window_end.isoformat()

        return EvolutionStatusReport(
            state_version=state_version,
            hold=hold,
            pending_authorizations=pending_authorizations,
            scheduled=scheduled_ids,
            in_flight=in_flight_ids,
            window_quota_used=quota_used,
            envelope=envelope,
            policy_version=self.policy.version,
        )

    # ------------------------------------------------------------------
    # Convenience lifecycle builders
    # ------------------------------------------------------------------

    def create_request(
        self,
        request_id: str,
        source: str,
        target_scope: Any,
        change_payload: dict[str, Any],
        intended_level: ExecutionLevel = ExecutionLevel.ADMINISTRATIVE,
        version_target: VersionTarget | None = None,
        now: datetime | None = None,
    ) -> EvolutionRequest:
        """Create and persist a new DRAFTED request."""
        when = now if now is not None else self.clock()
        req = EvolutionRequest(
            request_id=request_id,
            source=source,
            target_scope=target_scope,
            change_payload=change_payload,
            intended_level=intended_level,
            status=EvolutionRequestStatus.DRAFTED,
            version_target=version_target,
            created_at=when,
            updated_at=when,
        )
        self.storage.store_request(req)
        return req

    def record_validation(
        self,
        request_id: str,
        report: ValidationReport,
        now: datetime | None = None,
    ) -> EvolutionRequest | None:
        """Record a validation report and transition to VALIDATED if valid."""
        when = now if now is not None else self.clock()
        req = self.storage.load_request(request_id)
        if req is None:
            return None
        new_status = (
            EvolutionRequestStatus.VALIDATED
            if report.valid
            else EvolutionRequestStatus.REJECTED
        )
        req = self._replace(
            req,
            validation=report,
            status=new_status,
            updated_at=when,
        )
        self.storage.store_request(req)
        return req

    def record_risk(
        self,
        request_id: str,
        assessment: RiskAssessment,
        now: datetime | None = None,
    ) -> EvolutionRequest | None:
        """Record a risk assessment and transition to RISK_ASSESSED."""
        when = now if now is not None else self.clock()
        req = self.storage.load_request(request_id)
        if req is None:
            return None
        req = self._replace(
            req,
            risk=assessment,
            status=EvolutionRequestStatus.RISK_ASSESSED,
            updated_at=when,
        )
        self.storage.store_request(req)
        return req

    def record_authorization(
        self,
        request_id: str,
        authorization: EvolutionAuthorization,
        now: datetime | None = None,
    ) -> EvolutionRequest | None:
        """Record an authorization and transition to AUTHORIZED."""
        when = now if now is not None else self.clock()
        req = self.storage.load_request(request_id)
        if req is None:
            return None
        req = self._replace(
            req,
            authorization=authorization,
            status=EvolutionRequestStatus.AUTHORIZED,
            updated_at=when,
        )
        self.storage.store_request(req)
        return req

    def schedule_request(
        self,
        request_id: str,
        schedule: EvolutionSchedule | None = None,
        now: datetime | None = None,
    ) -> EvolutionRequest | None:
        """Transition an AUTHORIZED request to SCHEDULED."""
        when = now if now is not None else self.clock()
        req = self.storage.load_request(request_id)
        if req is None or req.status != EvolutionRequestStatus.AUTHORIZED:
            return None
        if schedule is None:
            schedule = EvolutionSchedule(scheduled_at=when)
        req = self._replace(
            req,
            schedule=schedule,
            status=EvolutionRequestStatus.SCHEDULED,
            updated_at=when,
        )
        self.storage.store_request(req)
        return req

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _replace(req: EvolutionRequest, **changes: Any) -> EvolutionRequest:
        """Return a new ``EvolutionRequest`` with selected fields replaced."""
        data = {
            "request_id": req.request_id,
            "source": req.source,
            "target_scope": req.target_scope,
            "change_payload": req.change_payload,
            "intended_level": req.intended_level,
            "status": req.status,
            "validation": req.validation,
            "risk": req.risk,
            "authorization": req.authorization,
            "schedule": req.schedule,
            "version_target": req.version_target,
            "rollback": req.rollback,
            "receipt": req.receipt,
            "verification": req.verification,
            "outcome": req.outcome,
            "parent_request_ids": req.parent_request_ids,
            "created_at": req.created_at,
            "updated_at": req.updated_at,
            "metadata": req.metadata,
        }
        data.update(changes)
        return EvolutionRequest(**data)
