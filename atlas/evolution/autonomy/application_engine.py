"""
Atlas Evolution Autonomy — Application Engine — Phase 16.5

The ApplicationEngine is the sole component that applies an already-
authorized ``EvolutionRequest`` to the state domains.

Responsibilities:
- Resolve the correct ``Applier`` from ``ApplierRegistry``.
- Capture a snapshot before mutation.
- Apply the mutation via the applier.
- Verify the result with a read-back probe.
- Build and return an ``ApplicationResult`` with the updated request.

Per the architecture, the ApplicationEngine:
- Does NOT dispatch, schedule, authorize, validate, or invoke AI.
- Does NOT touch the kernel, gateway, runtime, services, or EventBus.
- Returns a deterministic result; callers decide what lifecycle transition
  to record.

State readers and writers are injected per scope so the engine remains
pure and testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from atlas.evolution.autonomy.applier import (
    ApplyResult,
    SnapshotStorage,
    StateReader,
    StateWriter,
)
from atlas.evolution.autonomy.applier_registry import ApplierRegistry, NoApplierError
from atlas.evolution.autonomy.models import (
    ChangeReceipt,
    EvolutionRequest,
    EvolutionRequestStatus,
    RollbackPlan,
    VerificationResult,
)
from atlas.evolution.governance.models import ScopeType


class ApplicationError(Exception):
    """Raised when an application cannot proceed deterministically."""


@dataclass(frozen=True, slots=True)
class ApplicationResult:
    """Outcome of applying an EvolutionRequest.

    Attributes:
        request: The request after application/verification fields are set.
        success: True when apply + verify both succeeded.
        receipt: The ChangeReceipt returned by the applier (None on failure).
        verification: The VerificationResult returned by the applier.
        rollback: The RollbackPlan captured before mutation.
        error: Human-readable error when success is False.
        terminal_status: Suggested terminal status.
    """

    request: EvolutionRequest
    success: bool
    receipt: ChangeReceipt | None = None
    verification: VerificationResult | None = None
    rollback: RollbackPlan | None = None
    error: str = ""
    terminal_status: str = "FAILED"


@dataclass(frozen=True, slots=True)
class ApplicationEngine:
    """Pure state-application engine for authorized evolution requests.

    Dependencies (constructor-injected):
      - registry: ApplierRegistry mapping ScopeType → Applier.
      - snapshot_storage: minimal storage surface for rollback snapshots.
      - readers: dict[ScopeType, StateReader] for snapshot/verification.
      - writers: dict[ScopeType, StateWriter] for mutations.
      - clock: optional callable returning datetime.now() for tests.
    """

    registry: ApplierRegistry
    snapshot_storage: SnapshotStorage
    readers: dict[ScopeType, StateReader] = field(default_factory=dict)
    writers: dict[ScopeType, StateWriter] = field(default_factory=dict)
    clock: Any = field(default_factory=lambda: datetime.now)

    def __post_init__(self) -> None:
        if self.registry is None:
            raise ValueError("ApplierRegistry is required")
        if self.snapshot_storage is None:
            raise ValueError("SnapshotStorage is required")

    def apply(
        self,
        request: EvolutionRequest,
        now: datetime | None = None,
    ) -> ApplicationResult:
        """Apply ``request`` to its target state domain.

        Steps:
          1. Resolve applier; fail closed if none.
          2. Resolve reader/writer for the scope.
          3. Run can_apply pre-check.
          4. Capture snapshot + rollback plan.
          5. Apply mutation.
          6. Verify.
          7. Return ApplicationResult with updated request.
        """
        when = now if now is not None else self.clock()
        scope = request.target_scope

        # 1. Resolve applier.
        try:
            applier = self.registry.resolve(scope)
        except NoApplierError as exc:
            return self._failure(request, str(exc), "FAILED", when)

        # 2. Resolve reader and writer.
        reader = self.readers.get(scope)
        writer = self.writers.get(scope)
        if reader is None or writer is None:
            return self._failure(
                request,
                f"Missing state reader or writer for scope {scope.name}",
                "FAILED",
                when,
            )

        # 3. Pre-check.
        if not applier.can_apply(request, reader):
            return self._failure(
                request,
                f"Applier pre-check failed for scope {scope.name}",
                "FAILED",
                when,
            )

        # 4. Capture snapshot.
        try:
            rollback = applier.capture_snapshot(
                request.request_id,
                reader,
                self.snapshot_storage,
                now=when,
            )
        except Exception as exc:
            return self._failure(
                request,
                f"Snapshot capture failed: {exc}",
                "FAILED",
                when,
            )

        # 5. Apply.
        apply_result = applier.apply(request, writer, now=when)
        if not apply_result.success or apply_result.receipt is None:
            return self._failure(
                request,
                apply_result.error or "Applier returned failure",
                apply_result.terminal_status,
                when,
                rollback=rollback,
            )

        # 6. Verify.
        verification = applier.verify(request, reader, now=when)

        # 7. Build updated request.
        updated = self._updated_request(
            request,
            receipt=apply_result.receipt,
            verification=verification,
            rollback=rollback,
            status=EvolutionRequestStatus.COMPLETED
            if verification.passed and apply_result.terminal_status == "COMPLETED"
            else EvolutionRequestStatus.PENDING_EFFECTIVE
            if apply_result.terminal_status == "PENDING_EFFECTIVE"
            else EvolutionRequestStatus.FAILED,
            updated_at=when,
        )

        terminal_status = (
            "COMPLETED"
            if updated.status == EvolutionRequestStatus.COMPLETED
            else "PENDING_EFFECTIVE"
            if updated.status == EvolutionRequestStatus.PENDING_EFFECTIVE
            else "FAILED"
        )

        return ApplicationResult(
            request=updated,
            success=verification.passed
            and apply_result.success
            and terminal_status != "FAILED",
            receipt=apply_result.receipt,
            verification=verification,
            rollback=rollback,
            terminal_status=terminal_status,
        )

    def _failure(
        self,
        request: EvolutionRequest,
        error: str,
        terminal_status: str,
        now: datetime,
        rollback: RollbackPlan | None = None,
    ) -> ApplicationResult:
        updated = self._updated_request(
            request,
            status=EvolutionRequestStatus.FAILED,
            updated_at=now,
            rollback=rollback,
        )
        return ApplicationResult(
            request=updated,
            success=False,
            error=error,
            terminal_status=terminal_status,
            rollback=rollback,
        )

    @staticmethod
    def _updated_request(
        request: EvolutionRequest,
        status: EvolutionRequestStatus | None = None,
        updated_at: datetime | None = None,
        receipt: ChangeReceipt | None = None,
        verification: VerificationResult | None = None,
        rollback: RollbackPlan | None = None,
    ) -> EvolutionRequest:
        """Return a new EvolutionRequest with optional fields replaced."""
        data = {
            "request_id": request.request_id,
            "source": request.source,
            "target_scope": request.target_scope,
            "change_payload": request.change_payload,
            "intended_level": request.intended_level,
            "status": status if status is not None else request.status,
            "validation": request.validation,
            "risk": request.risk,
            "authorization": request.authorization,
            "schedule": request.schedule,
            "version_target": request.version_target,
            "rollback": rollback if rollback is not None else request.rollback,
            "receipt": receipt if receipt is not None else request.receipt,
            "verification": verification
            if verification is not None
            else request.verification,
            "outcome": request.outcome,
            "parent_request_ids": request.parent_request_ids,
            "created_at": request.created_at,
            "updated_at": updated_at if updated_at is not None else request.updated_at,
            "metadata": request.metadata,
        }
        return EvolutionRequest(**data)
