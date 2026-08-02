"""
Atlas Evolution Autonomy — Boot Activation / Verification Tests — Phase 16.7

Tests for:
- VerificationService request + snapshot probes
- VerificationService PENDING_EFFECTIVE recommendation for CONFIG
- VerificationService FAILED recommendation for non-CONFIG
- BootActivationService staged config activation
- BootActivationService already-activated entry re-verification
- BootActivationService SAFE_MODE paths
- BootActivationService integrity check
"""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any

from atlas.evolution.autonomy.applier import DictStateReader, DictStateWriter
from atlas.evolution.autonomy.applier_registry import ApplierRegistry
from atlas.evolution.autonomy.boot_activation import BootActivationService
from atlas.evolution.autonomy.models import (
    AuthorizationMode,
    ChangeReceipt,
    EvolutionAuthorization,
    EvolutionRequest,
    EvolutionRequestStatus,
    RollbackPlan,
    RollbackStrategy,
    ScopeType,
    StagedConfigEntry,
    VerificationResult,
)
from atlas.evolution.autonomy.verification_service import VerificationService
from atlas.storage.autonomy_storage import AutonomySQLiteStorage


class InMemorySnapshotStore:
    """Snapshot store for tests."""

    def __init__(self) -> None:
        self._snapshots: dict[str, dict] = {}

    def load_snapshot(self, snapshot_id: str) -> dict | None:
        return self._snapshots.get(snapshot_id)

    def store_snapshot(self, snapshot_id: str, data: dict) -> None:
        self._snapshots[snapshot_id] = data


class InMemoryStagedStore:
    """Staged config store for tests."""

    def __init__(self) -> None:
        self._entries: list[StagedConfigEntry] = []

    def load_staged_configs(self, request_id: str | None = None) -> list[StagedConfigEntry]:
        if request_id is None:
            return list(self._entries)
        return [e for e in self._entries if e.request_id == request_id]

    def store_staged_config(self, entry: StagedConfigEntry) -> None:
        self._entries = [e for e in self._entries if e.entry_id != entry.entry_id]
        self._entries.append(entry)


class InMemoryRequestStore:
    """Request store for tests."""

    def __init__(self) -> None:
        self.requests: dict[str, EvolutionRequest] = {}

    def load_request(self, request_id: str) -> EvolutionRequest | None:
        return self.requests.get(request_id)

    def store_request(self, request: EvolutionRequest) -> None:
        self.requests[request.request_id] = request


def make_config_request(
    request_id: str,
    entries: list[dict],
    snapshot_id: str = "snap-R1",
) -> EvolutionRequest:
    return EvolutionRequest(
        request_id=request_id,
        source="test",
        target_scope=ScopeType.CONFIG,
        change_payload={"entries": entries},
        status=EvolutionRequestStatus.PENDING_EFFECTIVE,
        authorization=EvolutionAuthorization(
            request_id=request_id,
            mode=AuthorizationMode.EXPLICIT,
        ),
        receipt=ChangeReceipt(
            request_id=request_id,
            changed_keys=[e["key"] for e in entries],
            version_delta="+0.0.1",
            target_tags=["config"],
        ),
        rollback=RollbackPlan(
            strategy=RollbackStrategy.SNAPSHOT,
            snapshot_ref=snapshot_id,
        ),
    )


class TestVerificationService(unittest.TestCase):
    """VerificationService pure logic tests."""

    def setUp(self):
        self.now = datetime(2026, 1, 1, 12, 0, 0)
        self.registry = ApplierRegistry.default()
        self.states: dict[ScopeType, dict] = {}
        self.readers: dict[ScopeType, Any] = {
            scope: DictStateReader(self.states.setdefault(scope, {}))
            for scope in ScopeType
        }
        self.snapshot_store = InMemorySnapshotStore()
        self.service = VerificationService(
            registry=self.registry,
            readers=self.readers,
            snapshot_store=self.snapshot_store,
            clock=lambda: self.now,
        )

    def test_memory_request_verifies(self):
        self.states[ScopeType.MEMORY]["M1"] = {"memory_id": "M1", "content": "hello"}
        req = EvolutionRequest(
            request_id="R1",
            source="test",
            target_scope=ScopeType.MEMORY,
            change_payload={"entries": [{"memory_id": "M1", "content": "hello"}]},
            status=EvolutionRequestStatus.APPLIED,
            receipt=ChangeReceipt(
                request_id="R1",
                changed_keys=["M1"],
                target_tags=["memory"],
            ),
            rollback=RollbackPlan(snapshot_ref="snap-R1"),
        )
        self.snapshot_store.store_snapshot("snap-R1", {"domain": "memory"})

        report = self.service.verify(req)

        self.assertTrue(report.passed)
        self.assertEqual(report.recommended_status, "COMPLETED")

    def test_config_request_pending_effective(self):
        req = EvolutionRequest(
            request_id="R1",
            source="test",
            target_scope=ScopeType.CONFIG,
            change_payload={"entries": [{"key": "logging.level", "value": "DEBUG"}]},
            status=EvolutionRequestStatus.PENDING_EFFECTIVE,
            receipt=ChangeReceipt(
                request_id="R1",
                changed_keys=["logging.level"],
                target_tags=["config"],
            ),
            rollback=RollbackPlan(snapshot_ref="snap-R1"),
        )
        self.snapshot_store.store_snapshot("snap-R1", {"domain": "config"})

        report = self.service.verify(req)

        # Applier verify fails because staged entry not present, but CONFIG
        # should recommend PENDING_EFFECTIVE rather than FAILED.
        self.assertFalse(report.passed)
        self.assertEqual(report.recommended_status, "PENDING_EFFECTIVE")

    def test_missing_snapshot_fails(self):
        req = EvolutionRequest(
            request_id="R1",
            source="test",
            target_scope=ScopeType.MEMORY,
            change_payload={"entries": [{"memory_id": "M1", "content": "hello"}]},
            status=EvolutionRequestStatus.APPLIED,
            receipt=ChangeReceipt(
                request_id="R1",
                changed_keys=["M1"],
                target_tags=["memory"],
            ),
            rollback=RollbackPlan(snapshot_ref="missing"),
        )

        report = self.service.verify(req)

        self.assertFalse(report.passed)
        self.assertEqual(report.recommended_status, "FAILED")


class TestBootActivationService(unittest.TestCase):
    """BootActivationService pure logic tests."""

    def setUp(self):
        self.now = datetime(2026, 1, 1, 12, 0, 0)
        self.staged_store = InMemoryStagedStore()
        self.request_store = InMemoryRequestStore()
        self.snapshot_store = InMemorySnapshotStore()
        self.config_state: dict = {}
        self.config_writer = DictStateWriter(self.config_state)
        self.readers: dict[ScopeType, Any] = {ScopeType.CONFIG: DictStateReader(self.config_state)}
        self.verification_service = VerificationService(
            registry=ApplierRegistry.default(),
            readers=self.readers,
            snapshot_store=self.snapshot_store,
            clock=lambda: self.now,
        )
        self.service = BootActivationService(
            staged_store=self.staged_store,
            request_store=self.request_store,
            verification_service=self.verification_service,
            config_writer=self.config_writer,
            clock=lambda: self.now,
        )

    def _install_staged(
        self,
        request_id: str,
        key: str,
        value: Any,
        snapshot_id: str = "snap-R1",
        activated_at: datetime | None = None,
    ) -> StagedConfigEntry:
        entry = StagedConfigEntry(
            entry_id=f"entry-{request_id}-{key}",
            request_id=request_id,
            key=key,
            value=value,
            activated_at=activated_at,
            applied_at=self.now,
        )
        self.staged_store.store_staged_config(entry)
        req = make_config_request(request_id, [{"key": key, "value": value}], snapshot_id)
        self.request_store.store_request(req)
        self.snapshot_store.store_snapshot(snapshot_id, {"domain": "config"})
        return entry

    def test_activate_config(self):
        self._install_staged("R1", "logging.level", "DEBUG")

        report = self.service.activate_staged_configs()

        self.assertFalse(report.safe_mode)
        self.assertEqual(len(report.activations), 1)
        self.assertTrue(report.activations[0].activated)
        self.assertTrue(report.activations[0].verified)
        self.assertEqual(self.config_state["logging.level"], "DEBUG")
        self.assertEqual(report.completed_request_ids, ["R1"])
        self.assertEqual(
            self.request_store.requests["R1"].status,
            EvolutionRequestStatus.COMPLETED,
        )

    def test_already_activated_reverified(self):
        self._install_staged(
            "R1",
            "logging.level",
            "DEBUG",
            activated_at=self.now,
        )
        self.config_state["logging.level"] = "DEBUG"
        # Simulate the staged marker left by the original activation.
        self.config_state["staged-config-R1-0"] = {
            "entry_id": "entry-R1-logging.level",
            "request_id": "R1",
            "key": "logging.level",
            "value": "DEBUG",
            "schema_status": "activated",
            "activated_at": self.now.isoformat(),
            "applied_at": self.now.isoformat(),
        }

        report = self.service.activate_staged_configs()

        self.assertTrue(report.activations[0].verified)
        self.assertEqual(report.completed_request_ids, ["R1"])

    def test_safe_mode_requested(self):
        report = self.service.activate_staged_configs(safe_mode=True)
        self.assertTrue(report.safe_mode)
        self.assertIn("SAFE_MODE", report.safe_mode_reason)

    def test_integrity_check_missing_request(self):
        entry = StagedConfigEntry(
            entry_id="entry-1",
            request_id="missing",
            key="k",
            value="v",
            applied_at=self.now,
        )
        self.staged_store.store_staged_config(entry)
        report = self.service.check_integrity()
        self.assertTrue(report.safe_mode)

    def test_integrity_check_missing_snapshot(self):
        self._install_staged("R1", "k", "v", snapshot_id="")
        report = self.service.check_integrity()
        self.assertTrue(report.safe_mode)


class TestBootActivationWithSQLite(unittest.TestCase):
    """BootActivationService persists through AutonomySQLiteStorage."""

    def setUp(self):
        self.now = datetime(2026, 1, 1, 12, 0, 0)
        self.tmp_dir = tempfile.mkdtemp(prefix="atlas_boot_activation_")
        self.db_path = Path(self.tmp_dir) / "boot.db"
        self.storage = AutonomySQLiteStorage(db_path=self.db_path)
        self.storage.initialize()
        self.config_state: dict = {}
        self.readers: dict[ScopeType, Any] = {ScopeType.CONFIG: DictStateReader(self.config_state)}
        self.snapshot_store = InMemorySnapshotStore()
        self.verification_service = VerificationService(
            registry=ApplierRegistry.default(),
            readers=self.readers,
            snapshot_store=self.snapshot_store,
            clock=lambda: self.now,
        )
        self.service = BootActivationService(
            staged_store=self.storage,
            request_store=self.storage,
            verification_service=self.verification_service,
            config_writer=DictStateWriter(self.config_state),
            clock=lambda: self.now,
        )

    def tearDown(self):
        self.storage.close()
        import os
        os.remove(self.db_path)
        os.rmdir(self.tmp_dir)

    def test_sqlite_persistence(self):
        req = make_config_request("R1", [{"key": "x", "value": 1}])
        self.storage.store_request(req)
        self.storage.store_staged_config(
            StagedConfigEntry(
                entry_id="entry-R1-x",
                request_id="R1",
                key="x",
                value=1,
                applied_at=self.now,
            )
        )
        self.snapshot_store.store_snapshot("snap-R1", {"domain": "config"})

        report = self.service.activate_staged_configs()

        self.assertEqual(report.completed_request_ids, ["R1"])
        loaded = self.storage.load_request("R1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.status, EvolutionRequestStatus.COMPLETED)


if __name__ == "__main__":
    unittest.main()
