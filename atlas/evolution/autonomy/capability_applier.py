"""
Atlas Evolution Autonomy — Capability Applier — Phase 16.5

Applies authorized ``EvolutionRequest`` objects targeting
``ScopeType.CAPABILITY``.

Per the architecture, capability changes are normal ``EvolutionRequest``
objects with ``target_scope=CAPABILITY`` and an ``upgrade_kind`` in the
payload. This applier handles the merged-request path: multiple capability
entries may be applied together under a single request.

Expected payload:
    {
        "entries": [
            {"capability_name": "...", "upgrade_kind": "register", "metadata": {}},
            {"capability_name": "...", "upgrade_kind": "enhance", "metadata": {}},
        ]
    }

The applier writes entries to the injected state writer and returns a
receipt. No gateway, no kernel, no AI, no scheduling.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from atlas.evolution.autonomy.applier import (
    ApplyResult,
    SnapshotStorage,
    StateReader,
    StateWriter,
    _checksum,
)
from atlas.evolution.autonomy.models import (
    ChangeReceipt,
    EvolutionRequest,
    RollbackPlan,
    RollbackStrategy,
    ScopeType,
    VerificationResult,
)


class CapabilityUpgradeKind(str, Enum):
    """Closed enum of supported capability upgrade kinds."""

    REGISTER = "register"
    ENHANCE = "enhance"


class CapabilityApplier:
    """Applier for CAPABILITY-scope evolution requests."""

    scope = ScopeType.CAPABILITY

    def supports(self, scope: ScopeType) -> bool:
        return scope == self.scope

    def can_apply(
        self,
        request: EvolutionRequest,
        reader: StateReader,
    ) -> bool:
        if request.target_scope != self.scope:
            return False
        entries = request.change_payload.get("entries")
        if not isinstance(entries, list) or not entries:
            return False
        for entry in entries:
            if not isinstance(entry, dict):
                return False
            if not isinstance(entry.get("capability_name"), str):
                return False
            kind = entry.get("upgrade_kind")
            if kind not in {k.value for k in CapabilityUpgradeKind}:
                return False
        return True

    def capture_snapshot(
        self,
        request_id: str,
        reader: StateReader,
        storage: SnapshotStorage,
        now: datetime | None = None,
    ) -> RollbackPlan:
        when = now if now is not None else datetime.now()
        snapshot_id = f"snap-capability-{request_id}-{int(when.timestamp())}"
        snapshot_data = {"domain": "capability", "keys": {}}
        storage.store_snapshot(
            snapshot_id=snapshot_id,
            request_id=request_id,
            snapshot_data=snapshot_data,
            checksum=_checksum(snapshot_data),
            created_at=when.isoformat(),
        )
        return RollbackPlan(
            strategy=RollbackStrategy.SNAPSHOT,
            snapshot_ref=snapshot_id,
            inverse_description="Remove added capability entries",
            steps=["delete added capability entries"],
        )

    def apply(
        self,
        request: EvolutionRequest,
        writer: StateWriter,
        now: datetime | None = None,
    ) -> ApplyResult:
        when = now if now is not None else datetime.now()
        entries = request.change_payload.get("entries", [])
        changed_keys: list[str] = []
        after_refs: dict[str, Any] = {}

        for entry in entries:
            name = entry["capability_name"]
            key = f"capability:{name}"
            writer.write(key, entry)
            changed_keys.append(name)
            after_refs[name] = entry

        receipt = ChangeReceipt(
            request_id=request.request_id,
            changed_keys=changed_keys,
            before_refs={},
            after_refs=after_refs,
            version_delta="+0.1.0",
            target_tags=["capability"],
            applied_at=when,
        )
        return ApplyResult(
            success=True,
            receipt=receipt,
            terminal_status="COMPLETED",
        )

    def verify(
        self,
        request: EvolutionRequest,
        reader: StateReader,
        now: datetime | None = None,
    ) -> VerificationResult:
        entries = request.change_payload.get("entries", [])
        checks: list[dict[str, Any]] = []
        all_present = True
        for entry in entries:
            name = entry["capability_name"]
            key = f"capability:{name}"
            present = reader.has(key)
            checks.append({"capability_name": name, "present": present})
            if not present:
                all_present = False

        return VerificationResult(
            passed=all_present,
            checks=checks,
            details="Capability entries visible" if all_present else "Missing capability entries",
            scope=self.scope,
            verified_at=now if now is not None else datetime.now(),
        )
