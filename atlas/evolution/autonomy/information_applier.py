"""
Atlas Evolution Autonomy — Information Applier — Phase 16.5

Applies authorized ``EvolutionRequest`` objects targeting:
  - ``ScopeType.MEMORY``
  - ``ScopeType.KNOWLEDGE``

These are "information" scopes: the mutation is in-session and can be
verified with a read-back probe on the injected state interface. They do
not require staged boot activation.

The applier expects payloads of the form:
  MEMORY:   {"entries": [{"memory_id": "...", "content": "..."}, ...]}
  KNOWLEDGE:{"entries": [{"knowledge_key": "...", "value": <dict>}, ...]}

No gateway. No kernel. No AI. No scheduling.
"""

from __future__ import annotations

from datetime import datetime
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


class MemoryApplier:
    """Applier for MEMORY-scope evolution requests."""

    scope = ScopeType.MEMORY

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
            if not isinstance(entry.get("memory_id"), str):
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
        snapshot_id = f"snap-memory-{request_id}-{int(when.timestamp())}"
        snapshot_data = {"domain": "memory", "keys": {}}
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
            inverse_description="Remove added memory entries",
            steps=["delete added memory entries"],
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
            memory_id = entry["memory_id"]
            writer.write(memory_id, entry)
            changed_keys.append(memory_id)
            after_refs[memory_id] = entry

        receipt = ChangeReceipt(
            request_id=request.request_id,
            changed_keys=changed_keys,
            before_refs={},
            after_refs=after_refs,
            version_delta="+0.0.1",
            target_tags=["memory"],
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
            memory_id = entry["memory_id"]
            present = reader.has(memory_id)
            checks.append({"memory_id": memory_id, "present": present})
            if not present:
                all_present = False

        return VerificationResult(
            passed=all_present,
            checks=checks,
            details="Memory entries visible" if all_present else "Missing memory entries",
            scope=self.scope,
            verified_at=now if now is not None else datetime.now(),
        )


class KnowledgeApplier:
    """Applier for KNOWLEDGE-scope evolution requests."""

    scope = ScopeType.KNOWLEDGE

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
            if not isinstance(entry.get("knowledge_key"), str):
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
        snapshot_id = f"snap-knowledge-{request_id}-{int(when.timestamp())}"
        snapshot_data = {"domain": "knowledge", "keys": {}}
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
            inverse_description="Remove added knowledge entries",
            steps=["delete added knowledge entries"],
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
            key = entry["knowledge_key"]
            writer.write(key, entry)
            changed_keys.append(key)
            after_refs[key] = entry

        receipt = ChangeReceipt(
            request_id=request.request_id,
            changed_keys=changed_keys,
            before_refs={},
            after_refs=after_refs,
            version_delta="+0.0.1",
            target_tags=["knowledge"],
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
            key = entry["knowledge_key"]
            present = reader.has(key)
            checks.append({"knowledge_key": key, "present": present})
            if not present:
                all_present = False

        return VerificationResult(
            passed=all_present,
            checks=checks,
            details="Knowledge entries visible" if all_present else "Missing knowledge entries",
            scope=self.scope,
            verified_at=now if now is not None else datetime.now(),
        )
