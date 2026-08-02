"""
Atlas Evolution Autonomy — Applier Tests — Phase 16.5

Tests for:
- Applier protocol and state reader/writer helpers.
- ConfigApplier (staged config, no live mutation).
- MemoryApplier / KnowledgeApplier (information scopes).
- CapabilityApplier (merged capability request path).
- ApplierRegistry (resolution, fail-closed UNKNOWN).
- ApplicationEngine (end-to-end apply with snapshot + verification).
"""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from atlas.evolution.autonomy.applier import (
    ApplyResult,
    DictStateReader,
    DictStateWriter,
)
from atlas.evolution.autonomy.applier_registry import ApplierRegistry, NoApplierError
from atlas.evolution.autonomy.application_engine import ApplicationEngine
from atlas.evolution.autonomy.capability_applier import CapabilityApplier
from atlas.evolution.autonomy.config_applier import ConfigApplier
from atlas.evolution.autonomy.information_applier import KnowledgeApplier, MemoryApplier
from atlas.evolution.autonomy.models import (
    ChangeReceipt,
    EvolutionRequest,
    EvolutionRequestStatus,
    RiskAssessment,
    RiskLevel,
    RollbackStrategy,
    ScopeType,
    VerificationResult,
)
from atlas.storage.autonomy_storage import AutonomySQLiteStorage


class InMemorySnapshotStorage:
    """SnapshotStorage implementation for tests."""

    def __init__(self) -> None:
        self._snapshots: dict[str, dict] = {}

    def store_snapshot(
        self,
        snapshot_id: str,
        request_id: str,
        snapshot_data: dict,
        checksum: str,
        created_at: str,
    ) -> None:
        self._snapshots[snapshot_id] = {
            "request_id": request_id,
            "snapshot_data": snapshot_data,
            "checksum": checksum,
            "created_at": created_at,
        }

    def load_snapshot(self, snapshot_id: str) -> dict | None:
        entry = self._snapshots.get(snapshot_id)
        return entry["snapshot_data"] if entry else None


def make_request(
    request_id: str,
    scope: ScopeType,
    payload: dict,
) -> EvolutionRequest:
    return EvolutionRequest(
        request_id=request_id,
        source="test",
        target_scope=scope,
        change_payload=payload,
    )


class TestDictStateHelpers(unittest.TestCase):
    """DictStateReader / DictStateWriter protocol compliance."""

    def test_read_write_remove(self):
        state = {}
        writer = DictStateWriter(state)
        reader = DictStateReader(state)
        writer.write("k", "v")
        self.assertEqual(reader.read("k"), "v")
        self.assertTrue(reader.has("k"))
        self.assertTrue(writer.remove("k"))
        self.assertFalse(reader.has("k"))


class TestConfigApplier(unittest.TestCase):
    """ConfigApplier stages entries but never applies live."""

    def test_can_apply_valid_payload(self):
        applier = ConfigApplier()
        req = make_request("R1", ScopeType.CONFIG, {
            "entries": [{"key": "logging.level", "value": "DEBUG"}],
        })
        self.assertTrue(applier.can_apply(req, DictStateReader({})))

    def test_can_apply_rejects_bad_payload(self):
        applier = ConfigApplier()
        req = make_request("R1", ScopeType.CONFIG, {"entries": "bad"})
        self.assertFalse(applier.can_apply(req, DictStateReader({})))

    def test_apply_stages_entries(self):
        applier = ConfigApplier()
        state = {}
        req = make_request("R1", ScopeType.CONFIG, {
            "entries": [
                {"key": "logging.level", "value": "DEBUG"},
                {"key": "history.limit", "value": 100},
            ],
        })
        result = applier.apply(req, DictStateWriter(state))
        self.assertTrue(result.success)
        self.assertEqual(result.receipt.changed_keys, ["logging.level", "history.limit"])
        self.assertEqual(result.terminal_status, "PENDING_EFFECTIVE")
        self.assertIn("staged-config-R1-0", state)
        self.assertEqual(state["staged-config-R1-0"]["value"], "DEBUG")

    def test_verify_detects_missing_entries(self):
        applier = ConfigApplier()
        req = make_request("R1", ScopeType.CONFIG, {
            "entries": [{"key": "logging.level", "value": "DEBUG"}],
        })
        verification = applier.verify(req, DictStateReader({}))
        self.assertFalse(verification.passed)


class TestMemoryApplier(unittest.TestCase):
    """MemoryApplier writes entries in-session."""

    def test_apply_and_verify(self):
        applier = MemoryApplier()
        state = {}
        req = make_request("R1", ScopeType.MEMORY, {
            "entries": [{"memory_id": "M1", "content": "hello"}],
        })
        result = applier.apply(req, DictStateWriter(state))
        self.assertTrue(result.success)
        self.assertEqual(result.terminal_status, "COMPLETED")
        verification = applier.verify(req, DictStateReader(state))
        self.assertTrue(verification.passed)


class TestKnowledgeApplier(unittest.TestCase):
    """KnowledgeApplier writes knowledge entries in-session."""

    def test_apply_and_verify(self):
        applier = KnowledgeApplier()
        state = {}
        req = make_request("R1", ScopeType.KNOWLEDGE, {
            "entries": [{"knowledge_key": "K1", "value": {"x": 1}}],
        })
        result = applier.apply(req, DictStateWriter(state))
        self.assertTrue(result.success)
        self.assertEqual(result.terminal_status, "COMPLETED")
        verification = applier.verify(req, DictStateReader(state))
        self.assertTrue(verification.passed)


class TestCapabilityApplier(unittest.TestCase):
    """CapabilityApplier handles merged capability request path."""

    def test_apply_multiple_capabilities(self):
        applier = CapabilityApplier()
        state = {}
        req = make_request("R1", ScopeType.CAPABILITY, {
            "entries": [
                {"capability_name": "C1", "upgrade_kind": "register"},
                {"capability_name": "C2", "upgrade_kind": "enhance"},
            ],
        })
        self.assertTrue(applier.can_apply(req, DictStateReader({})))
        result = applier.apply(req, DictStateWriter(state))
        self.assertTrue(result.success)
        self.assertEqual(result.receipt.version_delta, "+0.1.0")
        self.assertEqual(set(result.receipt.changed_keys), {"C1", "C2"})
        verification = applier.verify(req, DictStateReader(state))
        self.assertTrue(verification.passed)

    def test_can_apply_rejects_unknown_upgrade_kind(self):
        applier = CapabilityApplier()
        req = make_request("R1", ScopeType.CAPABILITY, {
            "entries": [{"capability_name": "C1", "upgrade_kind": "sandboxed"}],
        })
        self.assertFalse(applier.can_apply(req, DictStateReader({})))


class TestApplierRegistry(unittest.TestCase):
    """Registry resolves and fails closed for UNKNOWN."""

    def test_default_registry_has_four_scopes(self):
        registry = ApplierRegistry.default()
        self.assertEqual(
            registry.scopes,
            {ScopeType.CONFIG, ScopeType.MEMORY, ScopeType.KNOWLEDGE, ScopeType.CAPABILITY},
        )

    def test_resolve_config(self):
        registry = ApplierRegistry.default()
        applier = registry.resolve(ScopeType.CONFIG)
        self.assertIsInstance(applier, ConfigApplier)

    def test_unknown_scope_raises(self):
        registry = ApplierRegistry.default()
        with self.assertRaises(NoApplierError):
            registry.resolve(ScopeType.UNKNOWN)

    def test_register_new_applier(self):
        registry = ApplierRegistry.default()
        new_applier = MemoryApplier()
        updated = registry.register(ScopeType.MEMORY, new_applier)
        self.assertIs(updated.resolve(ScopeType.MEMORY), new_applier)

    def test_register_incompatible_applier_raises(self):
        registry = ApplierRegistry({})
        with self.assertRaises(ValueError):
            registry.register(ScopeType.CONFIG, MemoryApplier())


class TestApplicationEngine(unittest.TestCase):
    """ApplicationEngine end-to-end apply flow."""

    def setUp(self):
        self.now = datetime(2026, 1, 1, 12, 0, 0)
        self.snapshot_storage = InMemorySnapshotStorage()
        self.registry = ApplierRegistry.default()

    def _make_engine(self, states: dict) -> ApplicationEngine:
        writers = {scope: DictStateWriter(states.setdefault(scope, {})) for scope in ScopeType}
        readers = {scope: DictStateReader(states.get(scope, {})) for scope in ScopeType}
        return ApplicationEngine(
            registry=self.registry,
            snapshot_storage=self.snapshot_storage,
            readers=readers,
            writers=writers,
            clock=lambda: self.now,
        )

    def test_apply_memory_completes(self):
        states = {}
        engine = self._make_engine(states)
        req = make_request("R1", ScopeType.MEMORY, {
            "entries": [{"memory_id": "M1", "content": "hello"}],
        })
        result = engine.apply(req)
        self.assertTrue(result.success)
        self.assertEqual(result.terminal_status, "COMPLETED")
        self.assertEqual(result.request.status, EvolutionRequestStatus.COMPLETED)
        self.assertIsNotNone(result.receipt)
        self.assertIsNotNone(result.rollback)
        self.assertEqual(result.rollback.strategy, RollbackStrategy.SNAPSHOT)

    def test_apply_config_is_pending_effective(self):
        states = {}
        engine = self._make_engine(states)
        req = make_request("R1", ScopeType.CONFIG, {
            "entries": [{"key": "logging.level", "value": "DEBUG"}],
        })
        result = engine.apply(req)
        self.assertTrue(result.success)
        self.assertEqual(result.terminal_status, "PENDING_EFFECTIVE")
        self.assertEqual(result.request.status, EvolutionRequestStatus.PENDING_EFFECTIVE)

    def test_apply_unknown_scope_fails_closed(self):
        states = {}
        engine = self._make_engine(states)
        req = make_request("R1", ScopeType.UNKNOWN, {})
        result = engine.apply(req)
        self.assertFalse(result.success)
        self.assertEqual(result.request.status, EvolutionRequestStatus.FAILED)

    def test_apply_missing_writer_fails(self):
        engine = ApplicationEngine(
            registry=self.registry,
            snapshot_storage=self.snapshot_storage,
            readers={},
            writers={},
            clock=lambda: self.now,
        )
        req = make_request("R1", ScopeType.MEMORY, {
            "entries": [{"memory_id": "M1", "content": "hello"}],
        })
        result = engine.apply(req)
        self.assertFalse(result.success)

    def test_apply_captures_snapshot(self):
        states = {}
        engine = self._make_engine(states)
        req = make_request("R1", ScopeType.KNOWLEDGE, {
            "entries": [{"knowledge_key": "K1", "value": {"x": 1}}],
        })
        result = engine.apply(req)
        self.assertTrue(result.success)
        self.assertIsNotNone(result.rollback)
        snapshot = self.snapshot_storage.load_snapshot(result.rollback.snapshot_ref)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["domain"], "knowledge")


class TestApplicationEngineWithSQLiteStorage(unittest.TestCase):
    """ApplicationEngine persists snapshots via AutonomySQLiteStorage."""

    def setUp(self):
        self.now = datetime(2026, 1, 1, 12, 0, 0)
        self.tmp_dir = tempfile.mkdtemp(prefix="atlas_applier_engine_")
        self.db_path = Path(self.tmp_dir) / "test_engine.db"
        self.storage = AutonomySQLiteStorage(db_path=self.db_path)
        self.storage.initialize()

    def tearDown(self):
        self.storage.close()
        import os
        os.remove(self.db_path)
        os.rmdir(self.tmp_dir)

    def test_snapshot_persisted_to_sqlite(self):
        states = {}
        engine = ApplicationEngine(
            registry=ApplierRegistry.default(),
            snapshot_storage=self.storage,
            readers={scope: DictStateReader(states.setdefault(scope, {})) for scope in ScopeType},
            writers={scope: DictStateWriter(states[scope]) for scope in ScopeType},
            clock=lambda: self.now,
        )
        req = make_request("R1", ScopeType.CAPABILITY, {
            "entries": [{"capability_name": "C1", "upgrade_kind": "register"}],
        })
        result = engine.apply(req)
        self.assertTrue(result.success)
        loaded = self.storage.load_snapshot(result.rollback.snapshot_ref)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["domain"], "capability")


if __name__ == "__main__":
    unittest.main()
