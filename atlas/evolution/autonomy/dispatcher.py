"""Atlas Evolution Autonomy — EvolutionAutonomyDispatcher — Batch 13.

Orchestration-only consumer of persisted ``EvolutionRequest`` records.

The dispatcher is the kernel-private consumer that advances DRAFTED requests
through the existing governance gates and hands SCHEDULED requests to
``EvolutionExecutionGateway.execute_request`` — the *sole* applied-evolution
path (Phase 16 D3 / D10).

Lifecycle advanced here:
    DRAFTED → VALIDATED → RISK_ASSESSED → PENDING_AUTHORIZATION   (production terminus)
    SCHEDULED → (atomic claim) → gateway.execute_request
             → COMPLETED / PENDING_EFFECTIVE / FAILED | REJECTED / SUPERSEDED / EXPIRED

HARD BOUNDARY — this dispatcher:
  - NEVER authorizes anything.
  - NEVER calls ``AuthorizationManager.authorize_autonomously()``.
  - NEVER manufactures an EXPLICIT user:cli authorization.
  - Production-ingested requests STOP at ``PENDING_AUTHORIZATION``. A request
    is only ever applied when an authorization is ALREADY present on it
    (injected by tests or a future external authorization surface).
  - Calls ``ApplicationEngine.apply()`` ONLY through ``gateway.execute_request()``.
    It does not hold or import the engine.
  - Does not duplicate Validator / RiskAssessor / AuthorizationManager /
    ScheduleStore / RuleEngine / ApplicationEngine logic — it only sequences
    their existing public methods.

Orchestration only. No AI. No async. Single-threaded. ``authorization_manager``
and ``verification_service`` are accepted as reserved injections for forward
compatibility but are NEVER invoked for granting or verifying: authorization is
a separate human gate, and verification already runs inside
``ApplicationEngine`` / ``execute_request``.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any, Callable

from atlas.evolution.autonomy.models import (
    AuthorizationMode,
    EvolutionOutcomeRecord,
    EvolutionRequest,
    EvolutionRequestStatus,
    RiskLevel,
)


class EvolutionAutonomyDispatcher:
    """Advances governed requests through the documented lifecycle gates.

    Dependencies (constructor-injected):
      - schedule_store: the persistent request store + policy snapshot.
      - validator: EvolutionValidator (gate 2).
      - risk_assessor: EvolutionRiskAssessor (gate 3).
      - execution_gateway: the injected gateway exposing ``execute_request``
        (gate 1 + UNKNOWN-close + ApplicationEngine.apply reachability).
      - authorization_manager: reserved; never invoked to grant authorization.
      - verification_service: reserved; engine already verifies after apply.
      - audit_callback: optional ``Callable[[dict], None]`` for audit records.
      - state_version_provider: optional ``Callable[[], str]`` returning the
        current ``AtlasStateVersion`` anchor used by ``claim_scheduled``.
        Defaults to ``""`` (matches a request carrying an empty anchor).
      - clock: optional datetime callable for tests.

    The dispatcher is orchestration-only. It never mints an authorization and
    never decides governance, validation, risk, or application policy itself.
    """

    def __init__(
        self,
        schedule_store: Any,
        validator: Any,
        risk_assessor: Any,
        execution_gateway: Any,
        authorization_manager: Any | None = None,
        verification_service: Any | None = None,
        rollback_manager: Any | None = None,
        version_manager: Any | None = None,
        outcome_store: Any | None = None,
        audit_callback: Callable[[dict], None] | None = None,
        state_version_provider: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if schedule_store is None:
            raise ValueError("ScheduleStore is required")
        if validator is None:
            raise ValueError("EvolutionValidator is required")
        if risk_assessor is None:
            raise ValueError("EvolutionRiskAssessor is required")
        if execution_gateway is None:
            raise ValueError("EvolutionExecutionGateway is required")

        self._schedule_store = schedule_store
        self._validator = validator
        self._risk_assessor = risk_assessor
        self._gateway = execution_gateway
        # Reserved for forward compatibility — never used to grant/verify here.
        self._authorization_manager = authorization_manager
        self._verification_service = verification_service
        self._rollback_manager = rollback_manager
        self._version_manager = version_manager
        self._outcome_store = outcome_store
        self._audit_callback = audit_callback
        self._state_version_provider = state_version_provider or (lambda: "")
        self._clock = clock if clock is not None else datetime.now

    # ------------------------------------------------------------------
    # Injected dependencies (exposed for inspection / wiring verification)
    # ------------------------------------------------------------------

    @property
    def schedule_store(self) -> Any:
        """The injected request store."""
        return self._schedule_store

    @property
    def execution_gateway(self) -> Any:
        """The injected execution gateway (sole applied-evolution path)."""
        return self._gateway

    @property
    def authorization_manager(self) -> Any | None:
        """Reserved injection — NEVER invoked to grant authorization."""
        return self._authorization_manager

    @property
    def verification_service(self) -> Any | None:
        """Reserved injection — verification already runs inside apply."""
        return self._verification_service

    # ------------------------------------------------------------------
    # Public orchestration entry
    # ------------------------------------------------------------------

    def settle(self, now: datetime | None = None) -> None:
        """Run one non-blocking lifecycle pass.

        - Advances DRAFTED → VALIDATED → RISK_ASSESSED → PENDING_AUTHORIZATION.
        - Applies already-SCHEDULED (pre-authorized) requests through the
          gateway, one atomic claim + execute per ready request.
        - When any request is in ``EVOLUTION_HOLD``, application is blocked;
          DRAFTED advancement is still permitted (no mutation involved).
        """
        when = now if now is not None else self._clock()
        self._advance_drafted(now=when)
        if self._schedule_store.is_on_hold():
            return
        self._apply_due(now=when)
# ------------------------------------------------------------------
    # DRAFTED → PENDING_AUTHORIZATION (production terminus)
    # ------------------------------------------------------------------

    def _advance_drafted(self, now: datetime) -> None:
        """Move valid DRAFTED requests to the PENDING_AUTHORIZATION terminus."""
        drafted = self._schedule_store.list_by_status(
            EvolutionRequestStatus.DRAFTED
        )
        for request in drafted:
            report = self._validator.validate(request)
            validated = self._schedule_store.record_validation(
                request.request_id,
                report,
                now=now,
            )
            if validated is None:
                continue
            if validated.status != EvolutionRequestStatus.VALIDATED:
                self._audit(
                    "phase16.dispatcher.rejected",
                    request.request_id,
                    reason="validation_failed",
                )
                continue

            assessment = self._risk_assessor.assess(request)
            risked = self._schedule_store.record_risk(
                request.request_id,
                assessment,
                now=now,
            )
            if risked is None:
                continue

            # Production terminus. NEVER auto-grant here.
            advanced = self._schedule_store.update_status(
                request.request_id,
                EvolutionRequestStatus.RISK_ASSESSED,
                EvolutionRequestStatus.PENDING_AUTHORIZATION,
                now=now,
            )
            if advanced:
                self._audit(
                    "phase16.dispatcher.pending_authorization",
                    request.request_id,
                    risk_level=assessment.risk_level.name,
                )

    # ------------------------------------------------------------------
    # SCHEDULED → apply (only for already-authorized requests)
    # ------------------------------------------------------------------

    def _apply_due(self, now: datetime) -> None:
        """Claim and apply ready pre-authorized SCHEDULED requests."""
        due = self._schedule_store.find_ready_requests(now=now)
        for request in due:
            if not self._authorization_ok(request, now=now):
                self._schedule_store.update_status(
                    request.request_id,
                    EvolutionRequestStatus.SCHEDULED,
                    EvolutionRequestStatus.EXPIRED,
                    now=now,
                )
                self._audit(
                    "phase16.dispatcher.expired",
                    request.request_id,
                    reason="missing_or_expired_authorization",
                )
                continue

            # Gate 5 — intended execution level within the policy boundary.
            if not self._within_execution_level(request):
                self._schedule_store.update_status(
                    request.request_id,
                    EvolutionRequestStatus.SCHEDULED,
                    EvolutionRequestStatus.REJECTED,
                    now=now,
                )
                self._audit(
                    "phase16.dispatcher.rejected",
                    request.request_id,
                    reason="gate5_execution_level",
                )
                continue

            # Atomic claim (single application owner; SUPERSEDED on drift).
            anchor = self._state_version_provider()
            claim = self._schedule_store.claim_scheduled(
                request.request_id,
                anchor,
                now=now,
            )
            if claim.superseded:
                self._audit(
                    "phase16.dispatcher.superseded",
                    request.request_id,
                    reason="version_drift",
                )
                continue
            if not claim.claimed:
                # Already claimed / not schedulable — never double-apply.
                continue

            result = self._gateway.execute_request(request)
            self._record_execution_result(request, result, now=now)
# ------------------------------------------------------------------
    # Result recording (delegates persistence to the existing store)
    # ------------------------------------------------------------------

    def _record_execution_result(
        self,
        request: EvolutionRequest,
        result: Any,
        now: datetime,
    ) -> None:
        """Persist the terminal outcome of a gateway/engine result.

        When batch-15 lifecycle services (verification, versioning, outcome
        persistence, rollback) are injected this runs the full completion seam:
          - verified application success -> COMPLETED + outcome + version bump
          - verification failure        -> rollback -> ROLLED_BACK | EVOLUTION_HOLD
          - application failure         -> rollback (when a plan exists) else FAILED
        Without those services this preserves the batch-13 bare status splice.
        """
        if result.success:
            if self._completion_ready():
                self._complete_success(request, result, now)
            else:
                self._schedule_store.save_request(result.request)
                self._audit(
                    "phase16.dispatcher.applied",
                    request.request_id,
                    terminal_status=result.terminal_status,
                )
            return

        if result.terminal_status in ("REFUSED", "REJECTED"):
            self._schedule_store.update_status(
                request.request_id,
                EvolutionRequestStatus.APPLIED,
                EvolutionRequestStatus.REJECTED,
                now=now,
            )
            self._audit(
                "phase16.dispatcher.rejected",
                request.request_id,
                reason="gateway_refused",
                detail=result.error,
            )
            return

        if self._rollback_manager is not None and result.request.rollback is not None:
            # Persist the applied/failed request so RollbackManager (which
            # reloads by request_id) sees the receipt + rollback plan.
            self._schedule_store.save_request(result.request)
            self._rollback_result(request, now)
            return

        self._schedule_store.save_request(result.request)
        self._audit(
            "phase16.dispatcher.failed",
            request.request_id,
            terminal_status="FAILED",
            error=result.error,
        )

    # ------------------------------------------------------------------
    # Batch 15 - post-application completion seam
    # ------------------------------------------------------------------

    def _completion_ready(self) -> bool:
        """True when all batch-15 lifecycle services are injected."""
        return (
            self._verification_service is not None
            and self._version_manager is not None
            and self._outcome_store is not None
        )

    def _complete_success(
        self,
        request: EvolutionRequest,
        result: Any,
        now: datetime,
    ) -> None:
        """Run verification and, on pass, finalize COMPLETED + outcome + version."""
        report = self._verification_service.verify(result.request)
        if report.passed:
            completed = result.request
            outcome = self._build_outcome(
                completed,
                now,
                outcome="COMPLETED",
                verification_passed=True,
                rollback_occurred=False,
                effectiveness=1.0,
            )
            self._outcome_store.store_outcome(outcome)
            if completed.receipt is not None:
                self._version_manager.record_version(completed, completed.receipt)
                current = self._version_manager.current_version
                self._audit(
                    "phase16.dispatcher.versioned",
                    request.request_id,
                    version=(
                        f"{current.major}.{current.minor}.{current.patch}"
                        if current is not None
                        else ""
                    ),
                )
            self._schedule_store.save_request(completed)
            self._audit(
                "phase16.dispatcher.completed",
                request.request_id,
                verification=report.details,
            )
            return

        if self._rollback_manager is not None and result.request.rollback is not None:
            # Persist the verified-failure request (receipt + rollback plan) so
            # RollbackManager can reload and undo the mutation.
            self._schedule_store.save_request(result.request)
            self._rollback_result(request, now)
        else:
            failed = replace(result.request, status=EvolutionRequestStatus.FAILED)
            self._schedule_store.save_request(failed)
            self._audit(
                "phase16.dispatcher.failed",
                request.request_id,
                terminal_status="FAILED",
                error=report.details,
            )

    def _rollback_result(
        self,
        request: EvolutionRequest,
        now: datetime,
    ) -> None:
        """Invoke the existing RollbackManager; it sets ROLLED_BACK or HOLD."""
        rb = self._rollback_manager.rollback(request.request_id)
        self._audit(
            "phase16.dispatcher.rollback",
            request.request_id,
            success=rb.success,
            hold=rb.hold,
            error=rb.error,
        )

    def _build_outcome(
        self,
        req: EvolutionRequest,
        now: datetime,
        outcome: str,
        verification_passed: bool,
        rollback_occurred: bool,
        effectiveness: float,
    ) -> EvolutionOutcomeRecord:
        """Build the Phase 17 evidence record for a terminal request state."""
        risk = RiskLevel.LOW
        if req.risk is not None:
            risk = req.risk.risk_level
        mode = AuthorizationMode.EXPLICIT
        if req.authorization is not None:
            mode = req.authorization.mode
        return EvolutionOutcomeRecord(
            outcome_record_id=f"outcome-{req.request_id}",
            request_id=req.request_id,
            scope=req.target_scope,
            area=req.target_scope.name.lower(),
            risk_level=risk,
            intended_level=req.intended_level,
            authorization_mode=mode,
            outcome=outcome,
            verification_passed=verification_passed,
            rollback_occurred=rollback_occurred,
            effectiveness_proxy=effectiveness,
            started_at=req.created_at,
            finished_at=now,
            metadata=req.metadata,
        )

    # ------------------------------------------------------------------
    # Gate helpers
    # ------------------------------------------------------------------

    def _authorization_ok(self, request: EvolutionRequest, now: datetime) -> bool:
        """Return True when an authorization is present and unexpired."""
        auth = request.authorization
        if auth is None:
            return False
        if auth.expires_at is not None and now > auth.expires_at:
            return False
        return True

    def _within_execution_level(self, request: EvolutionRequest) -> bool:
        """Gate 5 — intended_level must be within the policy's effective level."""
        try:
            effective = self._schedule_store.policy.effective_execution_level
        except AttributeError:
            # Missing/unknown policy → fail closed (conservative).
            return False
        return request.intended_level.value <= effective.value

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def _audit(self, event: str, request_id: str, **kwargs: Any) -> None:
        """Emit an audit record via the injected callback, if any."""
        if self._audit_callback is None:
            return
        self._audit_callback(
            {
                "event": event,
                "request_id": request_id,
                **kwargs,
            }
        )