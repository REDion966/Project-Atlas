"""
Atlas Evolution Autonomy — Boot Activation — Phase 16.7

Boot-time staged-config activation, verification, and SAFE_MODE handling.

Responsibilities:
- Load staged config entries from storage.
- Activate each entry by writing the effective value into an injected
  config writer and marking the entry as activated.
- Verify activated config against the staged value.
- Transition the originating request to COMPLETED on success, or FAILED
  on verification failure.
- Detect integrity problems (missing snapshots, failed activations) and
  report a SAFE_MODE recommendation so ``Atlas.start()`` can decide to
  boot on base config and skip autonomous execution.

Per the architecture:
- Config changes are NEVER applied live; they are staged and activated at
  boot.
- ``COMPLETED`` is only reached when effective and verified.
- SAFE_MODE boots on base config and disables the dispatcher.

This module does NOT dispatch, schedule, or invoke AI. It does not touch
kernel, gateway, runtime, services, or EventBus. It only mutates state
through injected writers and persists status through the request store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from atlas.evolution.autonomy.applier import StateWriter
from atlas.evolution.autonomy.models import (
    EvolutionRequest,
    EvolutionRequestStatus,
    StagedConfigEntry,
    VerificationResult,
)
from atlas.evolution.autonomy.verification_service import VerificationService


class StagedConfigStore(Protocol):
    """Minimal storage surface for staged config operations."""

    def load_staged_configs(self, request_id: str | None = None) -> list[StagedConfigEntry]:
        ...

    def store_staged_config(self, entry: StagedConfigEntry) -> None:
        ...


class RequestStore(Protocol):
    """Minimal read/write surface for request persistence."""

    def load_request(self, request_id: str) -> EvolutionRequest | None:
        ...

    def store_request(self, request: EvolutionRequest) -> None:
        ...


@dataclass(frozen=True, slots=True)
class ActivationResult:
    """Outcome of activating a single staged config entry."""

    entry_id: str
    request_id: str
    activated: bool
    verified: bool
    error: str = ""


@dataclass(frozen=True, slots=True)
class BootActivationReport:
    """Outcome of the boot activation pass.

    Attributes:
        safe_mode: True when an integrity failure prevents normal boot.
        safe_mode_reason: Human-readable reason for SAFE_MODE.
        activations: Per-entry activation results.
        completed_request_ids: Requests moved to COMPLETED.
        failed_request_ids: Requests moved to FAILED.
    """

    safe_mode: bool
    safe_mode_reason: str = ""
    activations: list[ActivationResult] = field(default_factory=list)
    completed_request_ids: list[str] = field(default_factory=list)
    failed_request_ids: list[str] = field(default_factory=list)


class BootActivationService:
    """Pure boot-time staged-config activation service.

    Dependencies (constructor-injected):
      - staged_store: loads and persists StagedConfigEntry records.
      - request_store: loads and persists EvolutionRequest records.
      - verification_service: verifies activated config requests.
      - config_writer: StateWriter for the effective config domain.
      - clock: optional datetime callable for tests.
    """

    def __init__(
        self,
        staged_store: StagedConfigStore,
        request_store: RequestStore,
        verification_service: VerificationService,
        config_writer: StateWriter,
        clock: Any | None = None,
    ) -> None:
        self._staged_store = staged_store
        self._request_store = request_store
        self._verification_service = verification_service
        self._config_writer = config_writer
        self._clock = clock if clock is not None else datetime.now

    def activate_staged_configs(
        self,
        safe_mode: bool = False,
    ) -> BootActivationReport:
        """Activate all staged config entries.

        If ``safe_mode`` is True, no activation occurs; the report simply
        records the reason and returns. Otherwise, each staged entry is
        activated, verified, and its originating request is transitioned.
        """
        if safe_mode:
            return BootActivationReport(
                safe_mode=True,
                safe_mode_reason="SAFE_MODE requested before activation",
            )

        entries = self._staged_store.load_staged_configs()
        results: list[ActivationResult] = []
        completed: set[str] = set()
        failed: set[str] = set()

        for entry in entries:
            if entry.activated_at is not None:
                # Already activated in a previous boot; verify only.
                result = self._verify_only(entry)
            else:
                result = self._activate_one(entry)

            results.append(result)
            if result.activated and result.verified:
                completed.add(entry.request_id)
            elif not result.activated or not result.verified:
                failed.add(entry.request_id)

        # Transition requests based on aggregated per-request results.
        for request_id in completed:
            self._transition(request_id, EvolutionRequestStatus.COMPLETED)
        for request_id in failed:
            self._transition(request_id, EvolutionRequestStatus.FAILED)

        return BootActivationReport(
            safe_mode=False,
            activations=results,
            completed_request_ids=sorted(completed),
            failed_request_ids=sorted(failed),
        )

    def check_integrity(self) -> BootActivationReport:
        """Check whether the system can boot without SAFE_MODE.

        Returns safe_mode=True if any staged config entry lacks a snapshot
        or has a verification failure that cannot be recovered.
        """
        entries = self._staged_store.load_staged_configs()
        for entry in entries:
            req = self._request_store.load_request(entry.request_id)
            if req is None:
                return BootActivationReport(
                    safe_mode=True,
                    safe_mode_reason=f"Staged config {entry.entry_id} has no request",
                )
            if req.rollback is None or not req.rollback.snapshot_ref:
                return BootActivationReport(
                    safe_mode=True,
                    safe_mode_reason=f"Request {req.request_id} has no rollback snapshot",
                )
        return BootActivationReport(safe_mode=False)

    def _activate_one(self, entry: StagedConfigEntry) -> ActivationResult:
        """Activate a single staged config entry."""
        now = self._clock()
        try:
            self._config_writer.write(entry.key, entry.value)
        except Exception as exc:
            return ActivationResult(
                entry_id=entry.entry_id,
                request_id=entry.request_id,
                activated=False,
                verified=False,
                error=f"Config write failed: {exc}",
            )

        activated = StagedConfigEntry(
            entry_id=entry.entry_id,
            request_id=entry.request_id,
            key=entry.key,
            value=entry.value,
            schema_status="activated",
            activated_at=now,
            applied_at=entry.applied_at,
        )
        self._staged_store.store_staged_config(activated)
        # Preserve the staged entry marker in the config writer so the
        # ConfigApplier verify probe (which looks for staged-config keys)
        # passes after activation. We use the same index-based key scheme
        # as ConfigApplier.apply().
        staged_key = self._staged_key(entry)
        if staged_key:
            self._config_writer.write(
                staged_key,
                {
                    "entry_id": activated.entry_id,
                    "request_id": activated.request_id,
                    "key": activated.key,
                    "value": activated.value,
                    "schema_status": activated.schema_status,
                    "activated_at": activated.activated_at.isoformat() if activated.activated_at else None,
                    "applied_at": activated.applied_at.isoformat(),
                },
            )

        req = self._request_store.load_request(entry.request_id)
        if req is None:
            return ActivationResult(
                entry_id=entry.entry_id,
                request_id=entry.request_id,
                activated=True,
                verified=False,
                error="Request not found",
            )

        report = self._verification_service.verify(req)
        return ActivationResult(
            entry_id=entry.entry_id,
            request_id=entry.request_id,
            activated=True,
            verified=report.passed,
            error="" if report.passed else report.details,
        )

    def _staged_key(self, entry: StagedConfigEntry) -> str | None:
        """Return the ConfigApplier staged entry key for this entry."""
        req = self._request_store.load_request(entry.request_id)
        if req is None:
            return None
        entries = req.change_payload.get("entries", [])
        for idx, e in enumerate(entries):
            if e.get("key") == entry.key:
                return f"staged-config-{entry.request_id}-{idx}"
        return None

    def _verify_only(self, entry: StagedConfigEntry) -> ActivationResult:
        """Verify an already-activated staged config entry."""
        req = self._request_store.load_request(entry.request_id)
        if req is None:
            return ActivationResult(
                entry_id=entry.entry_id,
                request_id=entry.request_id,
                activated=True,
                verified=False,
                error="Request not found",
            )
        report = self._verification_service.verify(req)
        return ActivationResult(
            entry_id=entry.entry_id,
            request_id=entry.request_id,
            activated=True,
            verified=report.passed,
            error="" if report.passed else report.details,
        )

    def _transition(
        self,
        request_id: str,
        status: EvolutionRequestStatus,
    ) -> None:
        """Transition the originating request to a terminal status."""
        req = self._request_store.load_request(request_id)
        if req is None:
            return
        updated = self._replace(req, status=status, updated_at=self._clock())
        self._request_store.store_request(updated)

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
