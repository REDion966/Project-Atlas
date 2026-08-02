"""
Atlas Evolution Autonomy — Rollback Manager — Phase 16.6

Orchestrates deterministic rollback of an applied ``EvolutionRequest``.

Responsibilities:
- Accept a target request and an ordered list of requests to roll back
  (cascade, LIFO).
- For each request, load its snapshot, remove added keys via the injected
  ``StateWriter``, and record an outcome with ``rollback_occurred=True``.
- On any failure, transition the request to ``EVOLUTION_HOLD`` and stop.
- Update the manifest version via ``VersionManager`` for every rollback.

Per the architecture:
- Rollback is triggered by verification failure, explicit user command,
  boot SAFE_MODE, or health-probe invariant violation.
- Cascade follows declared parent_request_ids plus receipt target tags:
  later requests whose receipt tags overlap the target are rolled back first.
- Snapshot is a store-level artifact; restoration deletes keys added by the
  request and writes back any before_refs that were recorded.
- Every rollback is audited; hold is the failure mode.

This module does NOT dispatch, schedule, or invoke AI. It relies on
injected storage, request store, snapshot store, state writers, and
VersionManager.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from atlas.evolution.autonomy.models import (
    AtlasStateVersion,
    AuthorizationMode,
    ChangeReceipt,
    EvolutionAuthorization,
    EvolutionOutcomeRecord,
    EvolutionRequest,
    EvolutionRequestStatus,
    RiskAssessment,
    RollbackPlan,
    RiskLevel,
    ScopeType,
    VerificationResult,
)
from atlas.evolution.autonomy.version_manager import VersionManager
from atlas.evolution.autonomy.applier import StateWriter


class RequestStore(Protocol):
    """Minimal read/write surface for request persistence."""

    def load_request(self, request_id: str) -> EvolutionRequest | None:
        ...

    def store_request(self, request: EvolutionRequest) -> None:
        ...


class SnapshotStore(Protocol):
    """Minimal read surface for rollback snapshots."""

    def load_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        ...


class OutcomeStore(Protocol):
    """Minimal write surface for outcome records."""

    def store_outcome(self, outcome: EvolutionOutcomeRecord) -> None:
        ...


@dataclass(frozen=True, slots=True)
class RollbackResult:
    """Outcome of a rollback operation.

    Attributes:
        success: True when all cascade steps rolled back cleanly.
        rolled_back_request_ids: IDs successfully rolled back.
        failed_request_id: ID of the first failed step (None if success).
        hold: True when a failure forced EVOLUTION_HOLD.
        version: Manifest version after rollback.
        error: Human-readable error when success is False.
    """

    success: bool
    rolled_back_request_ids: list[str] = field(default_factory=list)
    failed_request_id: str | None = None
    hold: bool = False
    version: AtlasStateVersion | None = None
    error: str = ""


class RollbackManager:
    """Pure rollback orchestration engine.

    Dependencies (constructor-injected):
      - request_store: loads and persists EvolutionRequest objects.
      - snapshot_store: loads rollback snapshot artifacts.
      - outcome_store: persists EvolutionOutcomeRecord objects.
      - version_manager: records rollback manifest bumps.
      - writers: dict[ScopeType, StateWriter] per scope.
      - clock: optional datetime callable for tests.
    """

    def __init__(
        self,
        request_store: RequestStore,
        snapshot_store: SnapshotStore,
        outcome_store: OutcomeStore,
        version_manager: VersionManager,
        writers: dict[ScopeType, StateWriter],
        clock: Any | None = None,
    ) -> None:
        self._request_store = request_store
        self._snapshot_store = snapshot_store
        self._outcome_store = outcome_store
        self._version_manager = version_manager
        self._writers = writers
        self._clock = clock if clock is not None else datetime.now

    def rollback(
        self,
        target_request_id: str,
        cascade_ids: list[str] | None = None,
    ) -> RollbackResult:
        """Roll back ``target_request_id`` and its cascade.

        Steps:
          1. Build ordered rollback chain (cascade LIFO + target last).
          2. For each request: load, verify snapshot exists, mutate state,
             update request status to ROLLED_BACK, store outcome.
          3. Record rollback manifest version.
          4. On failure: set target to EVOLUTION_HOLD and return hold result.
        """
        chain = list(reversed(cascade_ids or [])) + [target_request_id]
        rolled_back: list[str] = []

        for request_id in chain:
            req = self._request_store.load_request(request_id)
            if req is None:
                return self._hold(target_request_id, request_id, f"Request {request_id} not found")

            step = self._rollback_one(req)
            if not step.success:
                return self._hold(
                    target_request_id,
                    request_id,
                    step.error or f"Rollback failed for {request_id}",
                    rolled_back=rolled_back,
                )
            rolled_back.append(request_id)

        version = self._version_manager.record_rollback_version(target_request_id)
        return RollbackResult(
            success=True,
            rolled_back_request_ids=rolled_back,
            version=version,
        )

    def _rollback_one(self, request: EvolutionRequest) -> RollbackResult:
        """Roll back a single request deterministically."""
        if request.rollback is None:
            return RollbackResult(success=False, error=f"No rollback plan for {request.request_id}")
        if request.receipt is None:
            return RollbackResult(success=False, error=f"No receipt for {request.request_id}")

        snapshot = self._snapshot_store.load_snapshot(request.rollback.snapshot_ref)
        if snapshot is None:
            return RollbackResult(
                success=False,
                error=f"Snapshot missing for {request.request_id}",
            )

        writer = self._writers.get(request.target_scope)
        if writer is None:
            return RollbackResult(
                success=False,
                error=f"No state writer for scope {request.target_scope.name}",
            )

        try:
            self._apply_inverse(request.receipt, writer)
        except Exception as exc:
            return RollbackResult(
                success=False,
                error=f"State mutation failed for {request.request_id}: {exc}",
            )

        now = self._clock()
        updated = self._replace(
            request,
            status=EvolutionRequestStatus.ROLLED_BACK,
            updated_at=now,
        )
        self._request_store.store_request(updated)

        outcome = self._build_outcome(updated, now)
        self._outcome_store.store_outcome(outcome)

        return RollbackResult(success=True, rolled_back_request_ids=[request.request_id])

    def _apply_inverse(
        self,
        receipt: ChangeReceipt,
        writer: StateWriter,
    ) -> None:
        """Apply inverse mutation for a snapshot-style rollback.

        For information scopes, this removes added keys. Where before_refs
        are present, it restores previous values. The exact semantics are
        scope-specific; this implementation covers the Phase 16.5 applier
        contract (entries keyed by memory_id/knowledge_key/capability:name
        or staged-config entry_id).
        """
        # Remove added keys first.
        for key in receipt.changed_keys:
            writer.remove(key)
            writer.remove(f"capability:{key}")
            writer.remove(f"staged-config-{receipt.request_id}-{key}")

        # Restore before_refs where captured.
        for key, value in (receipt.before_refs or {}).items():
            writer.write(key, value)

    def _hold(
        self,
        target_request_id: str,
        failed_request_id: str,
        error: str,
        rolled_back: list[str] | None = None,
    ) -> RollbackResult:
        """Transition target to EVOLUTION_HOLD and return failure result."""
        req = self._request_store.load_request(target_request_id)
        if req is not None:
            updated = self._replace(
                req,
                status=EvolutionRequestStatus.EVOLUTION_HOLD,
                updated_at=self._clock(),
            )
            self._request_store.store_request(updated)
        return RollbackResult(
            success=False,
            rolled_back_request_ids=rolled_back or [],
            failed_request_id=failed_request_id,
            hold=True,
            error=error,
        )

    @staticmethod
    def _replace(request: EvolutionRequest, **changes: Any) -> EvolutionRequest:
        """Return a new EvolutionRequest with selected fields replaced."""
        data = {
            "request_id": request.request_id,
            "source": request.source,
            "target_scope": request.target_scope,
            "change_payload": request.change_payload,
            "intended_level": request.intended_level,
            "status": request.status,
            "validation": request.validation,
            "risk": request.risk,
            "authorization": request.authorization,
            "schedule": request.schedule,
            "version_target": request.version_target,
            "rollback": request.rollback,
            "receipt": request.receipt,
            "verification": request.verification,
            "outcome": request.outcome,
            "parent_request_ids": request.parent_request_ids,
            "created_at": request.created_at,
            "updated_at": request.updated_at,
            "metadata": request.metadata,
        }
        data.update(changes)
        return EvolutionRequest(**data)

    def _build_outcome(
        self,
        request: EvolutionRequest,
        finished_at: datetime,
    ) -> EvolutionOutcomeRecord:
        """Build a terminal ROLLED_BACK outcome record."""
        risk = RiskLevel.LOW
        if request.risk and isinstance(request.risk, RiskAssessment):
            risk = request.risk.risk_level
        auth_mode = AuthorizationMode.EXPLICIT
        if request.authorization and isinstance(request.authorization, EvolutionAuthorization):
            auth_mode = request.authorization.mode
        return EvolutionOutcomeRecord(
            outcome_record_id=f"outcome-{request.request_id}",
            request_id=request.request_id,
            scope=request.target_scope,
            area=request.target_scope.name.lower(),
            risk_level=risk,
            intended_level=request.intended_level,
            authorization_mode=auth_mode,
            outcome="ROLLED_BACK",
            verification_passed=False,
            rollback_occurred=True,
            effectiveness_proxy=0.0,
            started_at=request.created_at,
            finished_at=finished_at,
            related_ids=[],
            metadata=request.metadata,
        )
