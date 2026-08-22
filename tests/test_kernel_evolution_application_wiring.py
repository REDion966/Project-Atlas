"""Tests for Foundation Strengthening Batch 11 — ApplicationEngine kernel wiring.

Covers:
- Kernel wiring of the kernel-private ApplicationEngine
- reader/writer scope surfaces (readers: CONFIG/MEMORY/KNOWLEDGE/CAPABILITY;
  writers: MEMORY/KNOWLEDGE only)
- ApplierRegistry.default() integration
- SnapshotStorage reuse of the shared AutonomySQLiteStorage
- authorized MEMORY/KNOWLEDGE application (Batch 10 user:cli path,
  policy disabled)
- CONFIG/CAPABILITY fail-closed (no writer wired)
- protected scope (UNKNOWN) fail-closed
- Knowledge removal fail-closed contract preserved
- no public ServiceContainer key introduced
- shutdown clears the kernel-private reference
"""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from atlas.evolution.autonomy.authorization_manager import (
    AuthorizationManager,
    AuthorizationRequest,
)
from atlas.evolution.autonomy.models import (
    AuthorizationMode,
    AutonomyPolicy,
    EvolutionRequest,
)
from atlas.evolution.autonomy.schedule_store import ScheduleStore
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import ExecutionLevel
from atlas.kernel.atlas import Atlas
from atlas.memory.models.memory import Memory


def _memory_request(request_id: str = "AUTORQ-MEM-1") -> EvolutionRequest:
    return EvolutionRequest(
        request_id=request_id,
        source="test",
        target_scope=ScopeType.MEMORY,
        change_payload={"entries": [{"memory_id": "M-1", "content": "hello"}]},
        intended_level=ExecutionLevel.INFORMATION,
    )


def _knowledge_request(request_id: str = "AUTORQ-KNW-1") -> EvolutionRequest:
    return EvolutionRequest(
        request_id=request_id,
        source="test",
        target_scope=ScopeType.KNOWLEDGE,
        change_payload={
            "entries": [{"knowledge_key": "K-1", "value": {"fact": "x"}}]
        },
        intended_level=ExecutionLevel.INFORMATION,
    )


def _config_request(request_id: str = "AUTORQ-CFG-1") -> EvolutionRequest:
    return EvolutionRequest(
        request_id=request_id,
        source="test",
        target_scope=ScopeType.CONFIG,
        change_payload={"entries": [{"key": "ai.provider", "value": "evil"}]},
        intended_level=ExecutionLevel.SELF_CONFIG,
    )


def _capability_request(request_id: str = "AUTORQ-CAP-1") -> EvolutionRequest:
    return EvolutionRequest(
        request_id=request_id,
        source="test",
        target_scope=ScopeType.CAPABILITY,
        change_payload={
            "entries": [{"capability_name": "RogueCap", "upgrade_kind": "register"}]
        },
        intended_level=ExecutionLevel.SELF_CONFIG,
    )


def _unknown_request(request_id: str = "AUTORQ-UNK-1") -> EvolutionRequest:
    return EvolutionRequest(
        request_id=request_id,
        source="test",
        target_scope=ScopeType.UNKNOWN,
        change_payload={},
        intended_level=ExecutionLevel.ADMINISTRATIVE,
    )


def _authorize_information(request: EvolutionRequest) -> EvolutionRequest:
    """Authorize an INFORMATION-boundary request via the Batch 10 path.

    user:cli + EXPLICIT + policy disabled — permitted for MEMORY/KNOWLEDGE.
    """
    manager = AuthorizationManager(policy=AutonomyPolicy(enabled=False))
    result = manager.request_user_authorization(
        request,
        AuthorizationRequest(
            authorized_by="user:cli", mode=AuthorizationMode.EXPLICIT
        ),
    )
    assert result.authorized and result.authorization is not None
    return replace(request, authorization=result.authorization)


class TestApplicationEngineKernelWiring(unittest.TestCase):
    """Engine construction through Atlas.start() with correct surfaces."""

    def setUp(self) -> None:
        # Isolate memory persistence so kernel memory writes never touch the
        # real data/memory.json file.
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="atlas_b11_"))
        from atlas.memory.storage.json_storage import Storage

        Storage.MEMORY_FILE = self.tmp_dir / "memory.json"
        Storage.DATA_DIR = self.tmp_dir

        self.atlas = Atlas()
        self.atlas.start()
        self.engine = self.atlas.application_engine

    def tearDown(self) -> None:
        if self.atlas.started:
            try:
                self.atlas.shutdown()
            except Exception:
                pass
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_engine_is_constructed(self):
        self.assertIsNotNone(self.engine)

    def test_readers_contain_four_state_scopes(self):
        self.assertEqual(
            set(self.engine.readers.keys()),
            {
                ScopeType.CONFIG,
                ScopeType.MEMORY,
                ScopeType.KNOWLEDGE,
                ScopeType.CAPABILITY,
            },
        )

    def test_writers_contain_memory_and_knowledge_only(self):
        self.assertEqual(
            set(self.engine.writers.keys()),
            {ScopeType.MEMORY, ScopeType.KNOWLEDGE},
        )

    def test_registry_is_default_compatible(self):
        self.assertEqual(
            self.engine.registry.scopes,
            {
                ScopeType.CONFIG,
                ScopeType.MEMORY,
                ScopeType.KNOWLEDGE,
                ScopeType.CAPABILITY,
            },
        )

    def test_snapshot_storage_is_shared_autonomy_storage(self):
        self.assertIs(
            self.engine.snapshot_storage,
            self.atlas._autonomy_storage,  # noqa: SLF001 - kernel integration test
        )

    def test_no_public_service_container_key(self):
        self.assertNotIn("application_engine", self.atlas.container.names())

    def test_schedule_store_not_injected_into_engine(self):
        # The engine must not depend on ScheduleStore (Batch 11 scope).
        self.assertNotIn("schedule_store", getattr(self.engine, "__slots__", ()))
        self.assertIsInstance(self.atlas.schedule_store, ScheduleStore)


class TestAuthorizedMemoryApplication(unittest.TestCase):
    """MEMORY INFORMATION apply through the wired engine (policy disabled)."""

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="atlas_b11_mem_"))
        from atlas.memory.storage.json_storage import Storage

        Storage.MEMORY_FILE = self.tmp_dir / "memory.json"
        Storage.DATA_DIR = self.tmp_dir

        self.atlas = Atlas()
        self.atlas.start()
        self.engine = self.atlas.application_engine

    def tearDown(self) -> None:
        if self.atlas.started:
            try:
                self.atlas.shutdown()
            except Exception:
                pass
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_authorized_memory_apply_succeeds(self):
        request = _authorize_information(_memory_request())
        result = self.engine.apply(request)

        self.assertTrue(result.success)
        self.assertEqual(result.terminal_status, "COMPLETED")
        self.assertIsNotNone(result.receipt)
        self.assertIsNotNone(result.rollback)

        # Memory visible through the production service.
        memory: Memory | None = self.atlas._memory_service.get_memory("M-1")  # noqa: SLF001
        self.assertIsNotNone(memory)
        self.assertEqual(memory.content, "hello")

        # Snapshot persisted to the shared autonomy storage.
        snapshot = self.atlas._autonomy_storage.load_snapshot(  # noqa: SLF001
            result.rollback.snapshot_ref
        )
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["domain"], "memory")


class TestAuthorizedKnowledgeApplication(unittest.TestCase):
    """KNOWLEDGE INFORMATION apply through the wired engine."""

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="atlas_b11_knw_"))
        from atlas.memory.storage.json_storage import Storage

        Storage.MEMORY_FILE = self.tmp_dir / "memory.json"
        Storage.DATA_DIR = self.tmp_dir

        self.atlas = Atlas()
        self.atlas.start()
        self.engine = self.atlas.application_engine

    def tearDown(self) -> None:
        if self.atlas.started:
            try:
                self.atlas.shutdown()
            except Exception:
                pass
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_authorized_knowledge_apply_succeeds(self):
        request = _authorize_information(_knowledge_request())
        result = self.engine.apply(request)

        self.assertTrue(result.success)
        self.assertEqual(result.terminal_status, "COMPLETED")
        self.assertIsNotNone(result.receipt)

        # Knowledge entry visible through the production service.
        entry = self.atlas._knowledge_manager.base.all()  # noqa: SLF001
        self.assertTrue(any(e.title == "K-1" for e in entry))


class TestFailClosedScopes(unittest.TestCase):
    """CONFIG/CAPABILITY/UNKNOWN fail closed through the wired engine."""

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="atlas_b11_fail_"))
        from atlas.memory.storage.json_storage import Storage

        Storage.MEMORY_FILE = self.tmp_dir / "memory.json"
        Storage.DATA_DIR = self.tmp_dir

        self.atlas = Atlas()
        self.atlas.start()
        self.engine = self.atlas.application_engine

    def tearDown(self) -> None:
        if self.atlas.started:
            try:
                self.atlas.shutdown()
            except Exception:
                pass
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_config_apply_fails_cleanly_and_does_not_mutate(self):
        # Capture the live value first (config.toml is the real kernel config).
        provider_before = self.atlas._config.get("ai", "provider")  # noqa: SLF001
        result = self.engine.apply(_config_request())
        self.assertFalse(result.success)
        # No writer wired → engine refuses before any mutation.
        self.assertIn("writer", result.error)
        # Live configuration unchanged (no staged entries, no live mutation).
        self.assertEqual(
            self.atlas._config.get("ai", "provider"),  # noqa: SLF001
            provider_before,
        )

    def test_capability_apply_fails_cleanly_and_does_not_mutate(self):
        result = self.engine.apply(_capability_request())
        self.assertFalse(result.success)
        self.assertIn("writer", result.error)
        # No rogue capability was registered.
        self.assertFalse(self.atlas._capability_registry.has("RogueCap"))  # noqa: SLF001

    def test_unknown_scope_fails_closed(self):
        result = self.engine.apply(_unknown_request())
        self.assertFalse(result.success)


class TestAdapterContractPreserved(unittest.TestCase):
    """Knowledge remove() must remain fail-closed through the wired engine."""

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="atlas_b11_contract_"))
        from atlas.memory.storage.json_storage import Storage

        Storage.MEMORY_FILE = self.tmp_dir / "memory.json"
        Storage.DATA_DIR = self.tmp_dir

        self.atlas = Atlas()
        self.atlas.start()
        self.engine = self.atlas.application_engine

    def tearDown(self) -> None:
        if self.atlas.started:
            try:
                self.atlas.shutdown()
            except Exception:
                pass
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_knowledge_remove_still_raises(self):
        from atlas.evolution.autonomy.adapters.knowledge_adapter import (
            StateRemoveUnsupportedError,
        )

        writer = self.engine.writers[ScopeType.KNOWLEDGE]
        with self.assertRaises(StateRemoveUnsupportedError):
            writer.remove("knowledge.K-1")


class TestShutdown(unittest.TestCase):
    """The kernel clears the ApplicationEngine reference on shutdown."""

    def test_shutdown_clears_engine_reference(self):
        tmp_dir = Path(tempfile.mkdtemp(prefix="atlas_b11_shut_"))
        from atlas.memory.storage.json_storage import Storage

        Storage.MEMORY_FILE = tmp_dir / "memory.json"
        Storage.DATA_DIR = tmp_dir
        try:
            atlas = Atlas()
            atlas.start()
            self.assertIsNotNone(atlas._application_engine)  # noqa: SLF001
            atlas.shutdown()
            self.assertIsNone(atlas.application_engine)
            self.assertIsNone(atlas._autonomy_storage)  # noqa: SLF001
        finally:
            import shutil

            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
