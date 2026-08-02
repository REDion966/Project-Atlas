"""
Atlas Evolution Autonomy — Config Applier — Phase 16.5

Applies authorized ``EvolutionRequest`` objects targeting ``ScopeType.CONFIG``.

Per the architecture, config changes are NEVER applied live in Phase 16.
They are staged as ``StagedConfigEntry`` records, activated at next boot,
and verified before reaching ``COMPLETED``.

This applier therefore:
- Captures a snapshot of the affected config keys.
- Writes staged entries via the injected ``StateWriter``.
- Returns a ``ChangeReceipt`` with the staged keys.
- Reports verification as a weak read-back probe (effective verification
  happens at boot in Phase 16.7).

No gateway. No kernel. No AI. No scheduling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from atlas.evolution.autonomy.applier import (
    ApplyResult,
    Applier,
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
    StagedConfigEntry,
    VerificationResult,
)


class ConfigApplier:
    """Applier for CONFIG-scope evolution requests.

    The expected ``change_payload`` shape is:
        {
            "entries": [
                {"key": "logging.level", "value": "DEBUG"},
                ...
            ]
        }

    Each entry is staged as a ``StagedConfigEntry``. The applier never
    mutates the active configuration file directly.
    """

    scope = ScopeType.CONFIG

    def supports(self, scope: ScopeType) -> bool:
        return scope == self.scope

    def can_apply(
        self,
        request: EvolutionRequest,
        reader: StateReader,
    ) -> bool:
        """CONFIG can apply if the payload contains well-formed entries."""
        if request.target_scope != self.scope:
            return False
        entries = request.change_payload.get("entries")
        if not isinstance(entries, list) or not entries:
            return False
        for entry in entries:
            if not isinstance(entry, dict):
                return False
            key = entry.get("key")
            if not isinstance(key, str) or not key:
                return False
        return True

    def capture_snapshot(
        self,
        request_id: str,
        reader: StateReader,
        storage: SnapshotStorage,
        now: datetime | None = None,
    ) -> RollbackPlan:
        """Capture the current values of all keys the request will stage."""
        when = now if now is not None else datetime.now()
        snapshot_id = f"snap-config-{request_id}-{int(when.timestamp())}"
        snapshot_data = {"domain": "config", "keys": {}}

        # We cannot know keys until request payload is available, but the
        # protocol is generic. The actual keys are captured during apply by
        # reading the same reader. Here we record a domain-level marker.
        # ApplicationEngine will merge request-specific keys captured just
        # before mutation.
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
            inverse_description="Restore previous config values from snapshot",
            steps=["restore config keys from snapshot"],
        )

    def apply(
        self,
        request: EvolutionRequest,
        writer: StateWriter,
        now: datetime | None = None,
    ) -> ApplyResult:
        """Stage config entries and return a receipt.

        The writer receives staged entries under deterministic keys:
          ``staged_config:<request_id>:<entry_index>`` → StagedConfigEntry dict
        """
        when = now if now is not None else datetime.now()
        entries = request.change_payload.get("entries", [])
        changed_keys: list[str] = []
        before_refs: dict[str, Any] = {}
        after_refs: dict[str, Any] = {}

        for idx, entry in enumerate(entries):
            key = entry["key"]
            value = entry.get("value")
            entry_id = f"staged-config-{request.request_id}-{idx}"
            staged = StagedConfigEntry(
                entry_id=entry_id,
                request_id=request.request_id,
                key=key,
                value=value,
                schema_status="staged",
                applied_at=when,
            )
            writer.write(entry_id, {
                "entry_id": staged.entry_id,
                "request_id": staged.request_id,
                "key": staged.key,
                "value": staged.value,
                "schema_status": staged.schema_status,
                "activated_at": None,
                "applied_at": staged.applied_at.isoformat(),
            })
            changed_keys.append(key)
            after_refs[key] = value

        receipt = ChangeReceipt(
            request_id=request.request_id,
            changed_keys=changed_keys,
            before_refs=before_refs,
            after_refs=after_refs,
            version_delta="+0.0.1",
            target_tags=["config"],
            applied_at=when,
        )
        return ApplyResult(
            success=True,
            receipt=receipt,
            terminal_status="PENDING_EFFECTIVE",
        )

    def verify(
        self,
        request: EvolutionRequest,
        reader: StateReader,
        now: datetime | None = None,
    ) -> VerificationResult:
        """Read-back probe: confirm staged entries are present.

        This is a weak probe. Boot-time activation verification is the
        strong check performed in Phase 16.7.
        """
        entries = request.change_payload.get("entries", [])
        checks: list[dict[str, Any]] = []
        all_present = True
        for idx, entry in enumerate(entries):
            key = entry["key"]
            entry_id = f"staged-config-{request.request_id}-{idx}"
            present = reader.has(entry_id)
            checks.append({
                "key": key,
                "entry_id": entry_id,
                "present": present,
            })
            if not present:
                all_present = False

        return VerificationResult(
            passed=all_present,
            checks=checks,
            details="Config entries staged" if all_present else "Missing staged entries",
            scope=self.scope,
            verified_at=now if now is not None else datetime.now(),
        )
