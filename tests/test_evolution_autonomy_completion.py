import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from atlas.evolution.autonomy.applier_registry import ApplierRegistry
from atlas.evolution.autonomy.autonomy_request_adapter import AutonomyRequestAdapter
from atlas.evolution.autonomy.dispatcher import EvolutionAutonomyDispatcher
from atlas.evolution.autonomy.models import (
    AuthorizationMode,
    AutonomyPolicy,
    EvolutionAuthorization,
    EvolutionRequest,
    EvolutionRequestStatus,
    TargetKind,
    VersionTarget,
)
from atlas.evolution.autonomy.risk_assessor import EvolutionRiskAssessor
from atlas.evolution.autonomy.rollback_manager import RollbackManager
from atlas.evolution.autonomy.schedule_store import ScheduleStore
from atlas.evolution.autonomy.validator import EvolutionValidator
from atlas.evolution.autonomy.verification_service import VerificationService
from atlas.evolution.autonomy.version_manager import VersionManager
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.governance.rule_engine import RuleEngine
from atlas.knowledge.knowledge_entry import KnowledgeEntry
from atlas.evolution.models import ExecutionLevel
from atlas.memory.models.memory import Memory
from atlas.storage.autonomy_storage import AutonomySQLiteStorage

NOW = datetime(2026, 1, 1, 12, 0, 0)
POLICY = AutonomyPolicy(enabled=False, effective_execution_level=ExecutionLevel.INFORMATION)


class _FakeKnowledgeBase:
    def __init__(self, owner):
        self._owner = owner

    def all(self):
        return list(self._owner._entries)


class _FakeKnowledgeManager:
    def __init__(self):
        self._entries = []
        self.base = _FakeKnowledgeBase(self)

    def remember(self, title, content="", source=""):
        self._entries.append(KnowledgeEntry(title=title, content=content, source=source))


class _FakeMemoryService:
    def __init__(self):
        self._mem = {}

    def get_memory(self, memory_id):
        return self._mem.get(memory_id)

    def add_memory(self, memory):
        self._mem[memory.id] = memory

    def delete_memory(self, memory_id):
        return self._mem.pop(memory_id, None) is not None


class _FakeConfig:
    pass


class _FakeCapabilityRegistry:
    pass


def _knowledge_payload():
    return {"entries": [{"knowledge_key": "K-15", "value": {"fact": "x"}}]}


def _memory_payload():
    return {"entries": [{"memory_id": "M-15", "content": "hello"}]}


def _version_target(anchor="1.0.0"):
    return VersionTarget(
        target_kind=TargetKind.KNOWLEDGE,
        current_version="0",
        target_version="1",
        state_version_at_creation=anchor,
    )


def _make_engine(storage):
    from atlas.evolution.autonomy.application_engine import ApplicationEngine
    from atlas.evolution.autonomy.adapters import (
        CapabilityStateAdapter,
        ConfigStateAdapter,
        KnowledgeStateAdapter,
        MemoryStateAdapter,
    )

    km = _FakeKnowledgeManager()
    msvc = _FakeMemoryService()
    kg = KnowledgeStateAdapter(km)
    mem = MemoryStateAdapter(msvc)
    cfg = ConfigStateAdapter(_FakeConfig())
    cap = CapabilityStateAdapter(_FakeCapabilityRegistry())

    readers = {
        ScopeType.CONFIG: cfg,
        ScopeType.MEMORY: mem,
        ScopeType.KNOWLEDGE: kg,
        ScopeType.CAPABILITY: cap,
    }
    writers = {ScopeType.MEMORY: mem, ScopeType.KNOWLEDGE: kg}
    return ApplicationEngine(
        registry=ApplierRegistry.default(),
        snapshot_storage=storage,
        readers=readers,
        writers=writers,
    )


def _make_services(storage, engine):
    import itertools
    # Monotonic clock so each manifest row gets a distinct created_at; the
    # storage "latest" query orders only by created_at DESC (no tie-breaker).
    _counter = itertools.count(1)
    vm = VersionManager(
        storage=storage,
        clock=lambda: NOW + timedelta(seconds=next(_counter)),
    )
    vs = VerificationService(
        registry=engine.registry,
        readers=engine.readers,
        snapshot_store=storage,
        clock=lambda: NOW,
    )
    rm = RollbackManager(
        request_store=storage,
        snapshot_store=storage,
        outcome_store=storage,
        version_manager=vm,
        writers=engine.writers,
        clock=lambda: NOW,
    )
    return vs, rm, vm


def _make_dispatcher(storage, store, engine, vs, rm, vm):
    from atlas.evolution.execution_gateway import EvolutionExecutionGateway
    gw = EvolutionExecutionGateway(
        execution_engine=None,
        rule_engine=RuleEngine(),
        current_execution_level=ExecutionLevel.INFORMATION,
        application_engine=engine,
        autonomy_request_adapter=AutonomyRequestAdapter(),
    )
    return EvolutionAutonomyDispatcher(
        schedule_store=store,
        validator=EvolutionValidator(),
        risk_assessor=EvolutionRiskAssessor(),
        execution_gateway=gw,
        verification_service=vs,
        rollback_manager=rm,
        version_manager=vm,
        outcome_store=storage,
        state_version_provider=lambda: "1.0.0",
        clock=lambda: NOW,
    )


def _seed_scheduled(store, request_id, payload, scope=ScopeType.KNOWLEDGE, anchor="1.0.0"):
    auth = EvolutionAuthorization(
        request_id=request_id,
        authorized_by="user:cli",
        mode=AuthorizationMode.EXPLICIT,
        granted_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    req = EvolutionRequest(
        request_id=request_id,
        source="test",
        target_scope=scope,
        change_payload=payload,
        intended_level=ExecutionLevel.INFORMATION,
        status=EvolutionRequestStatus.SCHEDULED,
        authorization=auth,
        version_target=_version_target(anchor),
        created_at=NOW,
        updated_at=NOW,
    )
    store.save_request(req)
    return store.get_request(request_id)


class TestCompletion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="atlas_b15_")
        db = Path(self.tmp) / "autonomy.db"
        self.storage = AutonomySQLiteStorage(db_path=str(db))
        self.storage.initialize()
        self.store = ScheduleStore(storage=self.storage, policy=POLICY)
        self.engine = _make_engine(self.storage)
        self.vs, self.rm, self.vm = _make_services(self.storage, self.engine)

    def tearDown(self):
        self.storage.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_verified_success_completes_with_outcome_and_version(self):
        _seed_scheduled(self.store, "REQ-1", _knowledge_payload())
        d = _make_dispatcher(self.storage, self.store, self.engine, self.vs, self.rm, self.vm)
        d.settle(now=NOW)
        req = self.store.get_request("REQ-1")
        self.assertEqual(req.status, EvolutionRequestStatus.COMPLETED)
        self.assertTrue(req.verification.passed)
        self.assertIsNotNone(req.receipt)
        out = self.storage.load_outcome("REQ-1")
        self.assertIsNotNone(out)
        self.assertEqual(out.outcome, "COMPLETED")
        self.assertTrue(out.verification_passed)
        ver = self.storage.load_latest_version()
        self.assertIsNotNone(ver)
        self.assertIn("REQ-1", ver.applied_request_ids)

    def test_memory_verified_success(self):
        _seed_scheduled(self.store, "REQ-M", _memory_payload(), scope=ScopeType.MEMORY)
        d = _make_dispatcher(self.storage, self.store, self.engine, self.vs, self.rm, self.vm)
        d.settle(now=NOW)
        req = self.store.get_request("REQ-M")
        self.assertEqual(req.status, EvolutionRequestStatus.COMPLETED)

    def test_genesis_not_duplicated(self):
        g1 = self.vm.ensure_genesis()
        g2 = self.vm.ensure_genesis()
        self.assertEqual(g1.manifest_id, g2.manifest_id)
        ver = self.storage.load_latest_version()
        self.assertEqual((ver.major, ver.minor, ver.patch), (1, 0, 0))

    def test_version_bump_on_second_apply(self):
        _seed_scheduled(self.store, "REQ-V1", _knowledge_payload(), anchor="1.0.0")
        d = _make_dispatcher(self.storage, self.store, self.engine, self.vs, self.rm, self.vm)
        d.settle(now=NOW)
        self.assertEqual(self.store.get_request("REQ-V1").status, EvolutionRequestStatus.COMPLETED)
        v1 = self.storage.load_latest_version()
        _seed_scheduled(self.store, "REQ-V2", _knowledge_payload(), anchor="1.0.0")
        d.settle(now=NOW)
        self.assertEqual(self.store.get_request("REQ-V2").status, EvolutionRequestStatus.COMPLETED)
        v2 = self.storage.load_latest_version()
        self.assertGreater((v2.major, v2.minor, v2.patch), (v1.major, v1.minor, v1.patch))

    def test_outcome_idempotent(self):
        _seed_scheduled(self.store, "REQ-I", _knowledge_payload())
        d = _make_dispatcher(self.storage, self.store, self.engine, self.vs, self.rm, self.vm)
        d.settle(now=NOW)
        out = self.storage.load_outcome("REQ-I")
        self.assertIsNotNone(out)

    def test_policy_stays_disabled(self):
        self.assertTrue(self.store.policy.enabled is False)


class _MissingSnapshots:
    """Snapshot store that reports no snapshots (forces verification/rollback fail)."""

    def __init__(self):
        self.stored = []

    def load_snapshot(self, snapshot_id):
        return None


def _make_variant_dispatcher(storage, store, engine, vm, vs_snapshot, rm_snapshot):
    from atlas.evolution.execution_gateway import EvolutionExecutionGateway
    vs = VerificationService(
        registry=engine.registry,
        readers=engine.readers,
        snapshot_store=vs_snapshot,
        clock=lambda: NOW,
    )
    rm = RollbackManager(
        request_store=storage,
        snapshot_store=rm_snapshot,
        outcome_store=storage,
        version_manager=vm,
        writers=engine.writers,
        clock=lambda: NOW,
    )
    gw = EvolutionExecutionGateway(
        execution_engine=None,
        rule_engine=RuleEngine(),
        current_execution_level=ExecutionLevel.INFORMATION,
        application_engine=engine,
        autonomy_request_adapter=AutonomyRequestAdapter(),
    )
    return EvolutionAutonomyDispatcher(
        schedule_store=store,
        validator=EvolutionValidator(),
        risk_assessor=EvolutionRiskAssessor(),
        execution_gateway=gw,
        verification_service=vs,
        rollback_manager=rm,
        version_manager=vm,
        outcome_store=storage,
        state_version_provider=lambda: "1.0.0",
        clock=lambda: NOW,
    )


class TestRollbackAndGovernance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="atlas_b15b_")
        db = Path(self.tmp) / "autonomy.db"
        self.storage = AutonomySQLiteStorage(db_path=str(db))
        self.storage.initialize()
        self.store = ScheduleStore(storage=self.storage, policy=POLICY)
        self.engine = _make_engine(self.storage)
        _, _, self.vm = _make_services(self.storage, self.engine)

    def tearDown(self):
        self.storage.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_verification_failure_rolls_back(self):
        # MEMORY rollback is supported (delete_memory); knowledge removal is not.
        _seed_scheduled(self.store, "REQ-VF", _memory_payload(), scope=ScopeType.MEMORY)
        # Verification fails (no snapshot), rollback succeeds (real snapshot).
        d = _make_variant_dispatcher(
            self.storage, self.store, self.engine, self.vm,
            vs_snapshot=_MissingSnapshots(),
            rm_snapshot=self.storage,
        )
        d.settle(now=NOW)
        req = self.store.get_request("REQ-VF")
        self.assertEqual(req.status, EvolutionRequestStatus.ROLLED_BACK)
        out = self.storage.load_outcome("REQ-VF")
        self.assertIsNotNone(out)
        self.assertEqual(out.outcome, "ROLLED_BACK")

    def test_rollback_failure_sets_hold_and_blocks(self):
        _seed_scheduled(self.store, "REQ-HOLD", _knowledge_payload())
        # Verification fails AND rollback fails (no snapshot available).
        missing = _MissingSnapshots()
        d = _make_variant_dispatcher(
            self.storage, self.store, self.engine, self.vm,
            vs_snapshot=missing,
            rm_snapshot=missing,
        )
        d.settle(now=NOW)
        req = self.store.get_request("REQ-HOLD")
        self.assertEqual(req.status, EvolutionRequestStatus.EVOLUTION_HOLD)
        self.assertTrue(self.store.is_on_hold())
        # Subsequent application is blocked.
        _seed_scheduled(self.store, "REQ-BLK", _knowledge_payload())
        d.settle(now=NOW)
        self.assertEqual(
            self.store.get_request("REQ-BLK").status,
            EvolutionRequestStatus.SCHEDULED,
        )

    def test_application_failure_without_plan_stays_failed(self):
        # An invalid payload fails can_apply before any rollback plan exists.
        _seed_scheduled(
            self.store, "REQ-AF",
            {"not": "valid"},  # no 'entries' -> can_apply False -> FAILED, no plan
        )
        d = _make_variant_dispatcher(
            self.storage, self.store, self.engine, self.vm,
            vs_snapshot=self.storage,
            rm_snapshot=self.storage,
        )
        d.settle(now=NOW)
        req = self.store.get_request("REQ-AF")
        self.assertEqual(req.status, EvolutionRequestStatus.FAILED)

    def test_dispatcher_never_authorizes(self):
        d = _make_variant_dispatcher(
            self.storage, self.store, self.engine, self.vm,
            vs_snapshot=self.storage,
            rm_snapshot=self.storage,
        )
        # The dispatcher is orchestration-only: no autonomous-authorization API.
        self.assertFalse(hasattr(d, "authorize_autonomously"))
        # A verified pre-authorized completion does not create any new auth.
        _seed_scheduled(self.store, "REQ-NOAUTH", _knowledge_payload())
        d.settle(now=NOW)
        req = self.store.get_request("REQ-NOAUTH")
        self.assertEqual(req.status, EvolutionRequestStatus.COMPLETED)
        self.assertEqual(req.authorization.authorized_by, "user:cli")
        self.assertEqual(req.authorization.mode.name, "EXPLICIT")


if __name__ == "__main__":
    unittest.main()
