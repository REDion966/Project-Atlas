"""Tests for Foundation Strengthening Batch 13 — EvolutionAutonomyDispatcher.

Covers:
- DRAFTED → VALIDATED → RISK_ASSESSED → PENDING_AUTHORIZATION (production terminus)
- PENDING_AUTHORIZATION is a hard terminus; the dispatcher never auto-authorizes
- the dispatcher never calls authorize_autonomously() and never mints auth
- test-injected explicit user:cli authorization → SCHEDULED → atomic claim → execute → COMPLETED
- UNKNOWN scope rejected at gate 2 and at execute_request
- protected scopes remain fail-closed
- missing application_engine / autonomy_request_adapter → fail closed
- gate-5 execution-level mismatch → REJECTED
- missing/expired authorization never reaches application (EXPIRED)
- version drift → SUPERSEDED
- concurrent claim cannot double-apply
- failed apply persists FAILED; EVOLUTION_HOLD blocks application
- kernel: tick() calls settle() once; shutdown clears; not in ServiceContainer
"""

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from atlas.evolution.autonomy.application_engine import ApplicationResult
from atlas.evolution.autonomy.authorization_manager import (
    AuthorizationManager,
    AuthorizationRequest,
)
from atlas.evolution.autonomy.autonomy_request_adapter import (
    AutonomyRequestAdapter,
)
from atlas.evolution.autonomy.dispatcher import EvolutionAutonomyDispatcher
from atlas.evolution.autonomy.models import (
    AuthorizationMode,
    AutonomyPolicy,
    ChangeReceipt,
    EvolutionAuthorization,
    EvolutionRequest,
    EvolutionRequestStatus,
    TargetKind,
    VerificationResult,
    VersionTarget,
)
from atlas.evolution.autonomy.risk_assessor import EvolutionRiskAssessor
from atlas.evolution.autonomy.schedule_store import ScheduleStore
from atlas.evolution.autonomy.validator import EvolutionValidator
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.governance.rule_engine import RuleEngine
from atlas.evolution.models import ExecutionLevel
from atlas.storage.autonomy_storage import AutonomySQLiteStorage

NOW = datetime(2026, 1, 1, 12, 0, 0)

INFORMATION_POLICY = AutonomyPolicy(
    enabled=False,
    effective_execution_level=ExecutionLevel.INFORMATION,
)
ADMIN_POLICY = AutonomyPolicy(enabled=False)


def _make_storage_and_store(
    policy: AutonomyPolicy = INFORMATION_POLICY,
) -> tuple[AutonomySQLiteStorage, ScheduleStore]:
    """Create a temp AutonomySQLiteStorage + ScheduleStore pair."""
    tmp = tempfile.mkdtemp(prefix="atlas_b13_")
    db = Path(tmp) / "autonomy.db"
    storage = AutonomySQLiteStorage(db_path=str(db))
    storage.initialize()
    store = ScheduleStore(storage=storage, policy=policy)
    return storage, store


def _knowledge_payload() -> dict:
    return {
        "operation": "add",
        "entry_id": "K-13",
        "domain": "test",
        "content": "knowledge content",
        "confidence": 0.9,
    }


def _memory_payload() -> dict:
    return {
        "operation": "add",
        "memory_id": "M-13",
        "content": "memory content",
    }


def _make_version_target(anchor: str = "1.0.0") -> VersionTarget:
    return VersionTarget(
        target_kind=TargetKind.KNOWLEDGE,
        current_version="1.0.0",
        target_version="1.0.1",
        state_version_at_creation=anchor,
    )


def _make_request(
    request_id: str,
    scope: ScopeType,
    payload: dict,
    *,
    level: ExecutionLevel = ExecutionLevel.INFORMATION,
    version_target: VersionTarget | None = None,
    source: str = "test",
) -> EvolutionRequest:
    return EvolutionRequest(
        request_id=request_id,
        source=source,
        target_scope=scope,
        change_payload=payload,
        intended_level=level,
        version_target=version_target,
    )
def _authorize_and_schedule(
    store: ScheduleStore,
    request: EvolutionRequest,
    *,
    expires: datetime | None = None,
    policy: AutonomyPolicy | None = None,
) -> None:
    """Advance an existing DRAFTED request to SCHEDULED via a user:cli grant."""
    manager = AuthorizationManager(policy=policy or store.policy, clock=lambda: NOW)
    result = manager.request_user_authorization(
        request,
        AuthorizationRequest(
            authorized_by="user:cli",
            mode=AuthorizationMode.EXPLICIT,
            comment="test-injected authorization",
        ),
    )
    auth = result.authorization
    if expires is not None:
        auth = replace(auth, expires_at=expires)
    store.record_validation(
        request.request_id,
        EvolutionValidator().validate(request),
        now=NOW,
    )
    store.record_risk(
        request.request_id,
        EvolutionRiskAssessor().assess(request),
        now=NOW,
    )
    store.record_authorization(request.request_id, auth, now=NOW)
    store.schedule_request(request.request_id, now=NOW)


class _FakeApplicationEngine:
    """Deterministic stand-in for ApplicationEngine applying a request."""

    def __init__(
        self,
        success: bool = True,
        terminal: str = "COMPLETED",
        error: str = "",
    ) -> None:
        self.success = success
        self.terminal = terminal
        self.error = error
        self.calls: list[EvolutionRequest] = []

    def apply(self, request: EvolutionRequest) -> ApplicationResult:
        self.calls.append(request)
        terminal_status = (
            EvolutionRequestStatus.COMPLETED
            if self.terminal == "COMPLETED"
            else EvolutionRequestStatus.PENDING_EFFECTIVE
            if self.terminal == "PENDING_EFFECTIVE"
            else EvolutionRequestStatus.FAILED
        )
        updated = replace(
            request,
            status=terminal_status,
            receipt=ChangeReceipt(request_id=request.request_id, changed_keys=["x"]),
            verification=VerificationResult(
                passed=self.success,
                details=self.error,
                scope=request.target_scope,
                verified_at=datetime.now(),
            ),
        )
        return ApplicationResult(
            request=updated,
            success=self.success,
            receipt=updated.receipt,
            verification=updated.verification,
            terminal_status=self.terminal,
            error=self.error,
        )


def _make_real_gateway(
    engine,
    *,
    include_engine: bool = True,
    include_adapter: bool = True,
    level: ExecutionLevel = ExecutionLevel.INFORMATION,
):
    from atlas.evolution.execution_gateway import EvolutionExecutionGateway

    return EvolutionExecutionGateway(
        execution_engine=None,
        rule_engine=RuleEngine(),
        current_execution_level=level,
        application_engine=engine if include_engine else None,
        autonomy_request_adapter=AutonomyRequestAdapter() if include_adapter else None,
    )


def _make_dispatcher(
    store: ScheduleStore,
    gateway,
    *,
    version_provider=None,
    audit=None,
) -> EvolutionAutonomyDispatcher:
    return EvolutionAutonomyDispatcher(
        schedule_store=store,
        validator=EvolutionValidator(),
        risk_assessor=EvolutionRiskAssessor(),
        execution_gateway=gateway,
        authorization_manager=AuthorizationManager(policy=store.policy),
        verification_service=None,
        audit_callback=audit,
        state_version_provider=version_provider or (lambda: "1.0.0"),
        clock=lambda: NOW,
    )
class _StoreTestCase(unittest.TestCase):
    """Base fixture creating a temp store + dispatcher with a real gateway."""

    def setUp(self) -> None:
        self._storage, self._store = _make_storage_and_store(INFORMATION_POLICY)
        self._engine = _FakeApplicationEngine()
        self._gateway = _make_real_gateway(self._engine)
        self._audits: list[dict] = []
        self._dispatcher = _make_dispatcher(
            self._store,
            self._gateway,
            audit=self._audits.append,
        )

    def tearDown(self) -> None:
        self._storage.close()
        import shutil

        shutil.rmtree(Path(self._storage._db_path).parent, ignore_errors=True)


# ---------------------------------------------------------------------------
# Governance: DRAFTED → VALIDATED → RISK_ASSESSED → PENDING_AUTHORIZATION
# ---------------------------------------------------------------------------


class TestGovernanceAdvancement(_StoreTestCase):
    """Valid requests advance to PENDING_AUTHORIZATION; invalid ones fail."""

    def test_knowledge_advances_to_pending_authorization(self):
        self._store.create_request(
            "REQ-K", "test:know", ScopeType.KNOWLEDGE, _knowledge_payload()
        )
        self._dispatcher.settle()
        stored = self._store.get_request("REQ-K")
        self.assertEqual(
            stored.status, EvolutionRequestStatus.PENDING_AUTHORIZATION
        )
        self.assertIsNotNone(stored.validation)
        self.assertIsNotNone(stored.risk)
        # Hard terminus — must NOT be authorized or scheduled.
        self.assertIsNone(stored.authorization)

    def test_memory_advances_to_pending_authorization(self):
        self._store.create_request(
            "REQ-M", "test:mem", ScopeType.MEMORY, _memory_payload()
        )
        self._dispatcher.settle()
        self.assertEqual(
            self._store.get_request("REQ-M").status,
            EvolutionRequestStatus.PENDING_AUTHORIZATION,
        )

    def test_protected_scope_rejected_at_gate2(self):
        self._store.create_request("REQ-UNK", "test", ScopeType.UNKNOWN, {})
        self._dispatcher.settle()
        req = self._store.get_request("REQ-UNK")
        self.assertEqual(req.status, EvolutionRequestStatus.REJECTED)
        self.assertIsNone(req.risk)

    def test_invalid_payload_rejected_at_gate2(self):
        # KNOWLEDGE payload without 'operation' → validator rejects.
        self._store.create_request(
            "REQ-BAD", "test", ScopeType.KNOWLEDGE, {"entry_id": "x", "domain": "d"}
        )
        self._dispatcher.settle()
        self.assertEqual(
            self._store.get_request("REQ-BAD").status,
            EvolutionRequestStatus.REJECTED,
        )

    def test_dispatcher_never_calls_authorize_autonomously(self):
        called = []

        class _SpyAuthManager:
            def authorize_autonomously(self, *args, **kwargs):  # pragma: no cover
                called.append(True)

        dispatcher = EvolutionAutonomyDispatcher(
            schedule_store=self._store,
            validator=EvolutionValidator(),
            risk_assessor=EvolutionRiskAssessor(),
            execution_gateway=self._gateway,
            authorization_manager=_SpyAuthManager(),
            state_version_provider=lambda: "1.0.0",
            clock=lambda: NOW,
        )
        self._store.create_request(
            "REQ-SPY", "test", ScopeType.KNOWLEDGE, _knowledge_payload()
        )
        dispatcher.settle()
        req = self._store.get_request("REQ-SPY")
        self.assertEqual(req.status, EvolutionRequestStatus.PENDING_AUTHORIZATION)
        self.assertIsNone(req.authorization)
        self.assertEqual(called, [])
# ---------------------------------------------------------------------------
# Authorized path: SCHEDULED → atomic claim → execute → COMPLETED
# ---------------------------------------------------------------------------


class TestAuthorizedPath(_StoreTestCase):
    """A pre-authorized / pre-scheduled request is applied via the gateway."""

    def setUp(self) -> None:
        super().setUp()
        self._store.create_request(
            "REQ-AP",
            "test",
            ScopeType.KNOWLEDGE,
            _knowledge_payload(),
            intended_level=ExecutionLevel.INFORMATION,
            version_target=_make_version_target(),
        )

    def test_authorized_scheduled_applies_to_completed(self):
        _authorize_and_schedule(self._store, self._store.get_request("REQ-AP"))
        self.assertEqual(
            self._store.get_request("REQ-AP").status,
            EvolutionRequestStatus.SCHEDULED,
        )
        self._dispatcher.settle()
        stored = self._store.get_request("REQ-AP")
        self.assertEqual(stored.status, EvolutionRequestStatus.COMPLETED)
        self.assertIsNotNone(stored.receipt)
        self.assertIsNotNone(stored.verification)
        self.assertEqual(len(self._engine.calls), 1)

    def test_double_settle_does_not_double_apply(self):
        _authorize_and_schedule(self._store, self._store.get_request("REQ-AP"))
        self._dispatcher.settle()
        self._dispatcher.settle()
        self.assertEqual(len(self._engine.calls), 1)
        self.assertEqual(
            self._store.get_request("REQ-AP").status,
            EvolutionRequestStatus.COMPLETED,
        )

    def test_gate5_level_mismatch_rejected(self):
        self._storage.close()
        self._storage, self._store = _make_storage_and_store(ADMIN_POLICY)
        self._store.create_request(
            "REQ-G5",
            "test",
            ScopeType.KNOWLEDGE,
            _knowledge_payload(),
            intended_level=ExecutionLevel.INFORMATION,
            version_target=_make_version_target(),
        )
        _authorize_and_schedule(
            self._store,
            self._store.get_request("REQ-G5"),
            policy=ADMIN_POLICY,
        )
        dispatcher = _make_dispatcher(self._store, self._gateway)
        dispatcher.settle()
        self.assertEqual(
            self._store.get_request("REQ-G5").status,
            EvolutionRequestStatus.REJECTED,
        )
        self.assertEqual(self._engine.calls, [])

    def test_missing_authorization_never_applies(self):
        self._store.create_request(
            "REQ-NA",
            "test",
            ScopeType.KNOWLEDGE,
            _knowledge_payload(),
            intended_level=ExecutionLevel.INFORMATION,
            version_target=_make_version_target(),
        )
        self._store.update_status(
            "REQ-NA",
            EvolutionRequestStatus.DRAFTED,
            EvolutionRequestStatus.SCHEDULED,
            now=NOW,
        )
        self._dispatcher.settle()
        self.assertEqual(
            self._store.get_request("REQ-NA").status,
            EvolutionRequestStatus.EXPIRED,
        )
        self.assertEqual(self._engine.calls, [])

    def test_expired_authorization_never_applies(self):
        self._store.create_request(
            "REQ-EX",
            "test",
            ScopeType.KNOWLEDGE,
            _knowledge_payload(),
            intended_level=ExecutionLevel.INFORMATION,
            version_target=_make_version_target(),
        )
        _authorize_and_schedule(
            self._store,
            self._store.get_request("REQ-EX"),
            expires=NOW - timedelta(hours=1),
        )
        self._dispatcher.settle()
        self.assertEqual(
            self._store.get_request("REQ-EX").status,
            EvolutionRequestStatus.EXPIRED,
        )
        self.assertEqual(self._engine.calls, [])

    def test_version_drift_superseded(self):
        self._store.create_request(
            "REQ-VD",
            "test",
            ScopeType.KNOWLEDGE,
            _knowledge_payload(),
            intended_level=ExecutionLevel.INFORMATION,
            version_target=_make_version_target(anchor="1.0.0"),
        )
        _authorize_and_schedule(self._store, self._store.get_request("REQ-VD"))
        dispatcher = _make_dispatcher(
            self._store,
            self._gateway,
            version_provider=lambda: "2.0.0",
        )
        dispatcher.settle()
        self.assertEqual(
            self._store.get_request("REQ-VD").status,
            EvolutionRequestStatus.SUPERSEDED,
        )
        self.assertEqual(self._engine.calls, [])

    def test_failed_apply_persists_failed(self):
        self._storage.close()
        self._storage, self._store = _make_storage_and_store()
        failing = _FakeApplicationEngine(success=False, terminal="FAILED", error="boom")
        gateway = _make_real_gateway(failing)
        self._store.create_request(
            "REQ-FAIL",
            "test",
            ScopeType.KNOWLEDGE,
            _knowledge_payload(),
            intended_level=ExecutionLevel.INFORMATION,
            version_target=_make_version_target(),
        )
        _authorize_and_schedule(self._store, self._store.get_request("REQ-FAIL"))
        dispatcher = _make_dispatcher(self._store, gateway)
        dispatcher.settle()
        self.assertEqual(
            self._store.get_request("REQ-FAIL").status,
            EvolutionRequestStatus.FAILED,
        )
        self.assertEqual(len(failing.calls), 1)

    def test_hold_blocks_application(self):
        self._store.create_request("REQ-HOLD", "test", ScopeType.KNOWLEDGE, {})
        self._store.update_status(
            "REQ-HOLD",
            EvolutionRequestStatus.DRAFTED,
            EvolutionRequestStatus.EVOLUTION_HOLD,
            now=NOW,
        )
        self._store.create_request(
            "REQ-BLOCKED",
            "test",
            ScopeType.KNOWLEDGE,
            _knowledge_payload(),
            intended_level=ExecutionLevel.INFORMATION,
            version_target=_make_version_target(),
        )
        _authorize_and_schedule(self._store, self._store.get_request("REQ-BLOCKED"))
        self._dispatcher.settle()
        self.assertEqual(
            self._store.get_request("REQ-BLOCKED").status,
            EvolutionRequestStatus.SCHEDULED,
        )
        self.assertEqual(self._engine.calls, [])
# ---------------------------------------------------------------------------
# execute_request safety (additive gateway contract)
# ---------------------------------------------------------------------------


class TestExecuteRequestContract(unittest.TestCase):
    """The new gateway.execute_request() fails closed and rejects UNKNOWN."""

    def test_missing_application_engine_fails_closed(self):
        gateway = _make_real_gateway(
            _FakeApplicationEngine(), include_engine=False
        )
        req = _make_request(
            "REQ-ME", ScopeType.KNOWLEDGE, _knowledge_payload()
        )
        result = gateway.execute_request(req)
        self.assertFalse(result.success)
        self.assertEqual(result.terminal_status, "REFUSED")
        self.assertIn("ApplicationEngine", result.error)
        self.assertIs(result.request, req)  # unchanged

    def test_missing_autonomy_request_adapter_fails_closed(self):
        gateway = _make_real_gateway(
            _FakeApplicationEngine(), include_adapter=False
        )
        result = gateway.execute_request(
            _make_request("REQ-MA", ScopeType.KNOWLEDGE, _knowledge_payload())
        )
        self.assertFalse(result.success)
        self.assertEqual(result.terminal_status, "REFUSED")
        self.assertIn("AutonomyRequestAdapter", result.error)

    def test_unknown_scope_refused_unconditionally(self):
        engine = _FakeApplicationEngine()
        gateway = _make_real_gateway(engine)
        result = gateway.execute_request(
            _make_request("REQ-U", ScopeType.UNKNOWN, {})
        )
        self.assertFalse(result.success)
        self.assertEqual(result.terminal_status, "REFUSED")
        self.assertIn("protected", result.error)
        self.assertEqual(engine.calls, [])

    def test_success_returns_updated_request(self):
        engine = _FakeApplicationEngine()
        gateway = _make_real_gateway(engine)
        req = _make_request(
            "REQ-OK",
            ScopeType.KNOWLEDGE,
            _knowledge_payload(),
            version_target=_make_version_target(),
        )
        result = gateway.execute_request(req)
        self.assertTrue(result.success)
        self.assertEqual(result.terminal_status, "COMPLETED")
        self.assertIsNotNone(result.request.receipt)
        self.assertEqual(len(engine.calls), 1)


# ---------------------------------------------------------------------------
# Kernel: tick() calls settle() once; shutdown clears; not in container
# ---------------------------------------------------------------------------


class TestKernelWiring(unittest.TestCase):
    """Atlas wiring — dispatcher is kernel-private and settles on tick()."""

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="atlas_b13_kernel_"))
        from atlas.memory.storage.json_storage import Storage

        Storage.MEMORY_FILE = self.tmp_dir / "memory.json"
        Storage.DATA_DIR = self.tmp_dir
        from atlas.kernel.atlas import Atlas

        self.atlas = Atlas()
        self.atlas.start()

    def tearDown(self) -> None:
        if self.atlas.started:
            try:
                self.atlas.shutdown()
            except Exception:
                pass
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_dispatcher_constructed_and_wired(self):
        self.assertIsNotNone(self.atlas._autonomy_dispatcher)  # noqa: SLF001
        self.assertIsNotNone(self.atlas._autonomy_request_adapter)  # noqa: SLF001
        gw = self.atlas._execution_gateway  # noqa: SLF001
        self.assertIsNotNone(gw.application_engine)
        self.assertIsNotNone(gw.autonomy_request_adapter)

    def test_tick_calls_settle_once(self):
        calls = []

        def _settle():
            calls.append(1)

        self.atlas._autonomy_dispatcher.settle = _settle  # noqa: SLF001
        self.atlas.tick()
        self.assertEqual(len(calls), 1)

    def test_dispatcher_not_in_service_container(self):
        self.assertFalse(self.atlas.container.has("autonomy_dispatcher"))

    def test_shutdown_clears_dispatcher(self):
        self.assertIsNotNone(self.atlas._autonomy_dispatcher)  # noqa: SLF001
        self.atlas.shutdown()
        self.assertIsNone(self.atlas._autonomy_dispatcher)  # noqa: SLF001
        self.assertIsNone(self.atlas._autonomy_request_adapter)  # noqa: SLF001


if __name__ == "__main__":
    unittest.main()