"""
Atlas Evolution Autonomy — Versioning/Rollback Tests — Phase 16.6

Tests for:
- VersionManager genesis and version computation
- VersionManager per-scope bumps
- VersionManager rollback version bump
- RollbackManager single-request rollback
- RollbackManager cascade LIFO rollback
- RollbackManager failure → EVOLUTION_HOLD
"""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any

from atlas.evolution.autonomy.applier import DictStateReader, DictStateWriter
from atlas.evolution.autonomy.models import (
    AtlasStateVersion,
    AuthorizationMode,
    ChangeReceipt,
    EvolutionAuthorization,
    EvolutionOutcomeRecord,
    EvolutionRequest,
    EvolutionRequestStatus,
    RiskAssessment,
    RiskLevel,
    RollbackPlan,
    RollbackStrategy,
    ScopeType,
    VerificationResult,
)
from atlas.evolution.autonomy.rollback_manager import RollbackManager, RollbackResult
from atlas.evolution.autonomy.version_manager import VersionManager, ScopedVersionView
from atlas.storage.autonomy_storage import AutonomySQLiteStorage


class InMemoryVersionStorage:
    """VersionStorage implementation for tests."""

    def __init__(self) -> None:
        self._versions: list[AtlasStateVersion] = []

    def store_version(self, version: AtlasStateVersion) -> None:
        self._versions.append(version)

    def load_latest_version(self) -> AtlasStateVersion | None:
        if not self._versions:
            return None
        return self._versions[-1]


class InMemoryRequestStore:
    """RequestStore + SnapshotStore + OutcomeStore for tests."""

    def __init__(self) -> None:
        self.requests: dict[str, EvolutionRequest] = {}
        self.snapshots: dict[str, dict] = {}
        self.outcomes: dict[str, EvolutionOutcomeRecord] = {}

    def load_request(self, request_id: str) -> EvolutionRequest | None:
        return self.requests.get(request_id)

    def store_request(self, request: EvolutionRequest) -> None:
        self.requests[request.request_id] = request

    def load_snapshot(self, snapshot_id: str) -> dict | None:
        return self.snapshots.get(snapshot_id)

    def store_snapshot(self, snapshot_id: str, data: dict) -> None:
        self.snapshots[snapshot_id] = data

    def store_outcome(self, outcome: EvolutionOutcomeRecord) -> None:
        self.outcomes[outcome.request_id] = outcome


def make_request(
    request_id: str,
    scope: ScopeType,
    payload: dict,
    status: EvolutionRequestStatus = EvolutionRequestStatus.APPLIED,
    parent_request_ids: list[str] | None = None,
) -> EvolutionRequest:
    return EvolutionRequest(
        request_id=request_id,
        source="test",
        target_scope=scope,
        change_payload=payload,
        status=status,
        parent_request_ids=parent_request_ids or [],
        risk=RiskAssessment(risk_level=RiskLevel.LOW),
        authorization=EvolutionAuthorization(
            request_id=request_id,
            mode=AuthorizationMode.EXPLICIT,
        ),
    )




class TestVersionManager(unittest.TestCase):
    """VersionManager pure logic tests."""

    def setUp(self):
        self.now = datetime(2026, 1, 1, 12, 0, 0)
        self.storage = InMemoryVersionStorage()
        self.manager = VersionManager(self.storage, clock=lambda: self.now)

    def test_genesis_created_when_empty(self):
        version = self.manager.ensure_genesis()
        self.assertEqual(version.major, 1)
        self.assertEqual(version.minor, 0)
        self.assertEqual(version.patch, 0)
        self.assertEqual(version.scope_versions["memory"], "0")

    def test_genesis_returns_existing(self):
        first = self.manager.ensure_genesis()
        second = self.manager.ensure_genesis()
        self.assertEqual(first.manifest_id, second.manifest_id)

    def test_patch_bump_for_memory(self):
        self.manager.ensure_genesis()
        req = make_request("R1", ScopeType.MEMORY, {
            "entries": [{"memory_id": "M1", "content": "hello"}],
        })
        receipt = ChangeReceipt(
            request_id="R1",
            changed_keys=["M1"],
            version_delta="+0.0.1",
            target_tags=["memory"],
        )
        version = self.manager.record_version(req, receipt)
        self.assertEqual((version.major, version.minor, version.patch), (1, 0, 1))
        self.assertEqual(version.scope_versions["memory"], "1")
        self.assertIn("R1", version.applied_request_ids)

    def test_minor_bump_for_capability(self):
        self.manager.ensure_genesis()
        req = make_request("R1", ScopeType.CAPABILITY, {
            "entries": [{"capability_name": "C1", "upgrade_kind": "register"}],
        })
        receipt = ChangeReceipt(
            request_id="R1",
            changed_keys=["C1"],
            version_delta="+0.1.0",
            target_tags=["capability"],
        )
        version = self.manager.record_version(req, receipt)
        self.assertEqual((version.major, version.minor, version.patch), (1, 1, 0))
        self.assertEqual(version.scope_versions["capability"], "1")

    def test_major_bump(self):
        self.manager.ensure_genesis()
        req = make_request("R1", ScopeType.MEMORY, {})
        receipt = ChangeReceipt(
            request_id="R1",
            changed_keys=[],
            version_delta="+1.0.0",
            target_tags=["memory"],
        )
        version = self.manager.record_version(req, receipt)
        self.assertEqual((version.major, version.minor, version.patch), (2, 0, 0))

    def test_rollback_bump(self):
        self.manager.ensure_genesis()
        version = self.manager.record_rollback_version("R1")
        self.assertEqual((version.major, version.minor, version.patch), (1, 0, 1))
        self.assertEqual(version.tags, ["rollback"])

    def test_scoped_version_view(self):
        self.manager.ensure_genesis()
        req = make_request("R1", ScopeType.KNOWLEDGE, {
            "entries": [{"knowledge_key": "K1", "value": {}}],
        })
        receipt = ChangeReceipt(
            request_id="R1",
            changed_keys=["K1"],
            version_delta="+0.0.1",
            target_tags=["knowledge"],
        )
        self.manager.record_version(req, receipt)
        view = ScopedVersionView.from_state_version(self.manager.current_version)
        self.assertEqual(view.knowledge_version, "1")
        self.assertEqual(view.config_version, "0")


class TestRollbackManager(unittest.TestCase):
    """RollbackManager pure logic tests."""

    def setUp(self):
        self.now = datetime(2026, 1, 1, 12, 0, 0)
        self.storage = InMemoryVersionStorage()
        self.version_manager = VersionManager(self.storage, clock=lambda: self.now)
        self.store = InMemoryRequestStore()
        self.states: dict[ScopeType, dict] = {}
        self.writers: dict[ScopeType, Any] = {
            scope: DictStateWriter(self.states.setdefault(scope, {}))
            for scope in ScopeType
        }
        self.manager = RollbackManager(
            request_store=self.store,
            snapshot_store=self.store,
            outcome_store=self.store,
            version_manager=self.version_manager,
            writers=self.writers,
            clock=lambda: self.now,
        )

    def _install_request(
        self,
        request_id: str,
        scope: ScopeType,
        changed_keys: list[str],
        parent_request_ids: list[str] | None = None,
    ) -> EvolutionRequest:
        req = make_request(
            request_id,
            scope,
            {},
            status=EvolutionRequestStatus.COMPLETED,
            parent_request_ids=parent_request_ids or [],
        )
        receipt = ChangeReceipt(
            request_id=request_id,
            changed_keys=changed_keys,
            version_delta="+0.0.1",
            target_tags=[scope.name.lower()],
        )
        rollback = RollbackPlan(
            strategy=RollbackStrategy.SNAPSHOT,
            snapshot_ref=f"snap-{request_id}",
        )
        req = RollbackManager._replace(
            req,
            receipt=receipt,
            rollback=rollback,
        )
        self.store.requests[request_id] = req
        self.store.snapshots[rollback.snapshot_ref] = {"domain": scope.name.lower()}
        # Simulate applied state
        for key in changed_keys:
            self.writers[scope].write(key, {"value": "applied"})
        return req

    def test_single_rollback_removes_state(self):
        req = self._install_request("R1", ScopeType.MEMORY, ["M1"])
        reader = DictStateReader(self.states[ScopeType.MEMORY])
        self.assertTrue(reader.has("M1"))

        result = self.manager.rollback("R1")

        self.assertTrue(result.success)
        self.assertEqual(result.rolled_back_request_ids, ["R1"])
        self.assertFalse(reader.has("M1"))
        self.assertEqual(self.store.requests["R1"].status, EvolutionRequestStatus.ROLLED_BACK)
        self.assertTrue(self.store.outcomes["R1"].rollback_occurred)
        version = result.version
        self.assertIsNotNone(version)
        self.assertEqual((version.major, version.patch), (1, 1))

    def test_cascade_lifo(self):
        self._install_request("R1", ScopeType.MEMORY, ["M1"])
        self._install_request("R2", ScopeType.MEMORY, ["M2"], parent_request_ids=["R1"])

        result = self.manager.rollback("R1", cascade_ids=["R2"])

        self.assertTrue(result.success)
        # cascade is reversed: R2 first, then R1
        self.assertEqual(result.rolled_back_request_ids, ["R2", "R1"])

    def test_missing_request_goes_to_hold(self):
        result = self.manager.rollback("missing")
        self.assertFalse(result.success)
        self.assertTrue(result.hold)

    def test_missing_snapshot_goes_to_hold(self):
        req = make_request("R1", ScopeType.MEMORY, {}, status=EvolutionRequestStatus.COMPLETED)
        req = RollbackManager._replace(
            req,
            receipt=ChangeReceipt(request_id="R1", changed_keys=["M1"]),
            rollback=RollbackPlan(snapshot_ref="missing-snap"),
        )
        self.store.requests["R1"] = req

        result = self.manager.rollback("R1")

        self.assertFalse(result.success)
        self.assertTrue(result.hold)
        self.assertEqual(self.store.requests["R1"].status, EvolutionRequestStatus.EVOLUTION_HOLD)

    def test_missing_writer_goes_to_hold(self):
        req = self._install_request("R1", ScopeType.MEMORY, ["M1"])
        manager = RollbackManager(
            request_store=self.store,
            snapshot_store=self.store,
            outcome_store=self.store,
            version_manager=self.version_manager,
            writers={},
            clock=lambda: self.now,
        )
        result = manager.rollback("R1")
        self.assertFalse(result.success)
        self.assertTrue(result.hold)


class TestVersionManagerWithSQLite(unittest.TestCase):
    """VersionManager persists through AutonomySQLiteStorage."""

    def setUp(self):
        self.now = datetime(2026, 1, 1, 12, 0, 0)
        self.tmp_dir = tempfile.mkdtemp(prefix="atlas_version_manager_")
        self.db_path = Path(self.tmp_dir) / "versions.db"
        self.storage = AutonomySQLiteStorage(db_path=self.db_path)
        self.storage.initialize()
        self.manager = VersionManager(self.storage, clock=lambda: self.now)

    def tearDown(self):
        self.storage.close()
        import os
        os.remove(self.db_path)
        os.rmdir(self.tmp_dir)

    def test_genesis_persisted(self):
        genesis = self.manager.ensure_genesis()
        loaded = self.storage.load_latest_version()
        self.assertIsNotNone(loaded)
        self.assertIsNotNone(genesis)
        self.assertEqual(loaded.manifest_id, genesis.manifest_id)


class TestRollbackManagerWithSQLite(unittest.TestCase):
    """RollbackManager persists outcomes via AutonomySQLiteStorage."""

    def setUp(self):
        self.now = datetime(2026, 1, 1, 12, 0, 0)
        self.tmp_dir = tempfile.mkdtemp(prefix="atlas_rollback_manager_")
        self.db_path = Path(self.tmp_dir) / "rollback.db"
        self.storage = AutonomySQLiteStorage(db_path=self.db_path)
        self.storage.initialize()
        self.version_manager = VersionManager(self.storage, clock=lambda: self.now)
        self.store = InMemoryRequestStore()
        self.states: dict[ScopeType, dict] = {}
        self.writers: dict[ScopeType, Any] = {
            scope: DictStateWriter(self.states.setdefault(scope, {}))
            for scope in ScopeType
        }
        self.manager = RollbackManager(
            request_store=self.store,
            snapshot_store=self.store,
            outcome_store=self.storage,
            version_manager=self.version_manager,
            writers=self.writers,
            clock=lambda: self.now,
        )

    def tearDown(self):
        self.storage.close()
        import os
        os.remove(self.db_path)
        os.rmdir(self.tmp_dir)

    def test_outcome_persisted(self):
        req = make_request("R1", ScopeType.MEMORY, {}, status=EvolutionRequestStatus.COMPLETED)
        req = RollbackManager._replace(
            req,
            receipt=ChangeReceipt(request_id="R1", changed_keys=["M1"]),
            rollback=RollbackPlan(snapshot_ref="snap-R1"),
        )
        self.store.requests["R1"] = req
        self.store.snapshots["snap-R1"] = {"domain": "memory"}

        self.manager.rollback("R1")

        outcome = self.storage.load_outcome("R1")
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.outcome, "ROLLED_BACK")
        self.assertTrue(outcome.rollback_occurred)


if __name__ == "__main__":
    unittest.main()
