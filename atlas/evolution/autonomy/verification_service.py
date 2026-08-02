"""
Atlas Evolution Autonomy — Verification Service — Phase 16.7

Performs deterministic post-application verification probes for already-
applied ``EvolutionRequest`` objects.

Responsibilities:
- Re-run the appropriate applier's ``verify`` method against the current
  state reader to confirm a change is visible.
- Run integrity probes for snapshots (existence, checksum/domain match).
- Provide a decision surface for the boot activation pipeline: a request
  reaches ``COMPLETED`` only when verification passes; otherwise it stays
  ``PENDING_EFFECTIVE`` (config) or transitions to ``FAILED``.

Per the architecture:
- Verification is separate from application; it is a read-only probe
  after mutation.
- Config changes are weak-verified as staged; strong verification happens
  after boot activation in Phase 16.7.
- Snapshot verification ensures every applied request has a restorable
  artifact.

This module does NOT dispatch, schedule, authorize, or invoke AI. It
relies on injected ``ApplierRegistry``, state readers, and snapshot store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from atlas.evolution.autonomy.applier import StateReader
from atlas.evolution.autonomy.applier_registry import ApplierRegistry
from atlas.evolution.autonomy.models import (
    EvolutionRequest,
    EvolutionRequestStatus,
    ScopeType,
    VerificationResult,
)


class SnapshotStore(Protocol):
    """Minimal read surface for snapshot existence checks."""

    def load_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        ...


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """Aggregated verification decision for a request.

    Attributes:
        request_id: The verified request ID.
        passed: True when all probes passed.
        request_verification: Result from the applier's verify() probe.
        snapshot_verification: Result from the snapshot integrity probe.
        details: Human-readable summary.
        recommended_status: COMPLETED, PENDING_EFFECTIVE, or FAILED.
    """

    request_id: str
    passed: bool
    request_verification: VerificationResult | None = None
    snapshot_verification: VerificationResult | None = None
    details: str = ""
    recommended_status: str = "FAILED"


class VerificationService:
    """Pure verification engine for applied evolution requests.

    Dependencies (constructor-injected):
      - registry: ApplierRegistry for resolving scope-specific appliers.
      - readers: dict[ScopeType, StateReader] for read-back probes.
      - snapshot_store: loads snapshot artifacts for integrity checks.
      - clock: optional datetime callable for tests.
    """

    def __init__(
        self,
        registry: ApplierRegistry,
        readers: dict[ScopeType, StateReader],
        snapshot_store: SnapshotStore,
        clock: Any | None = None,
    ) -> None:
        self._registry = registry
        self._readers = readers
        self._snapshot_store = snapshot_store
        self._clock = clock if clock is not None else datetime.now

    def verify(
        self,
        request: EvolutionRequest,
    ) -> VerificationReport:
        """Verify an applied request.

        Runs two probes:
          1. Applier read-back probe via the registered applier.
          2. Snapshot integrity probe (exists, has expected domain).

        Returns a VerificationReport with a recommended terminal status.
        """
        now = self._clock()

        # Probe 1: applier-level verification.
        request_verification = self._verify_request(request, now)

        # Probe 2: snapshot integrity.
        snapshot_verification = self._verify_snapshot(request, now)

        probes = [request_verification, snapshot_verification]
        all_passed = all(p.passed for p in probes)

        if all_passed:
            recommended = "COMPLETED"
            details = "Request and snapshot verification passed"
        elif request is not None and request.target_scope == ScopeType.CONFIG:
            recommended = "PENDING_EFFECTIVE"
            details = "Config request awaiting boot activation"
        else:
            recommended = "FAILED"
            details = "Verification failed"

        return VerificationReport(
            request_id=request.request_id,
            passed=all_passed,
            request_verification=request_verification,
            snapshot_verification=snapshot_verification,
            details=details,
            recommended_status=recommended,
        )

    def _verify_request(
        self,
        request: EvolutionRequest,
        now: datetime,
    ) -> VerificationResult:
        """Run the scope-specific applier verify probe."""
        reader = self._readers.get(request.target_scope)
        if reader is None:
            return VerificationResult(
                passed=False,
                details=f"No state reader for scope {request.target_scope.name}",
                scope=request.target_scope,
                verified_at=now,
            )

        try:
            applier = self._registry.resolve(request.target_scope)
        except Exception as exc:
            return VerificationResult(
                passed=False,
                details=f"No applier for scope {request.target_scope.name}: {exc}",
                scope=request.target_scope,
                verified_at=now,
            )

        try:
            return applier.verify(request, reader, now=now)
        except Exception as exc:
            return VerificationResult(
                passed=False,
                details=f"Verify probe raised: {exc}",
                scope=request.target_scope,
                verified_at=now,
            )

    def _verify_snapshot(
        self,
        request: EvolutionRequest,
        now: datetime,
    ) -> VerificationResult:
        """Check that the rollback snapshot artifact exists and is well-formed."""
        if request.rollback is None:
            return VerificationResult(
                passed=False,
                details="No rollback plan",
                scope=request.target_scope,
                verified_at=now,
            )

        snapshot_id = request.rollback.snapshot_ref
        if not snapshot_id:
            return VerificationResult(
                passed=False,
                details="Empty snapshot reference",
                scope=request.target_scope,
                verified_at=now,
            )

        try:
            snapshot = self._snapshot_store.load_snapshot(snapshot_id)
        except Exception as exc:
            return VerificationResult(
                passed=False,
                details=f"Snapshot load failed: {exc}",
                scope=request.target_scope,
                verified_at=now,
            )

        if snapshot is None:
            return VerificationResult(
                passed=False,
                details=f"Snapshot {snapshot_id} not found",
                scope=request.target_scope,
                verified_at=now,
            )

        expected_domain = request.target_scope.name.lower()
        actual_domain = snapshot.get("domain", "")
        if actual_domain != expected_domain:
            return VerificationResult(
                passed=False,
                details=f"Snapshot domain mismatch: {actual_domain} != {expected_domain}",
                scope=request.target_scope,
                verified_at=now,
            )

        return VerificationResult(
            passed=True,
            details=f"Snapshot {snapshot_id} present and domain-valid",
            scope=request.target_scope,
            verified_at=now,
        )
