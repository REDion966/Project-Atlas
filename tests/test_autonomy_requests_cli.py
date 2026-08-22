import argparse
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from atlas.cli import autonomy_commands as ac
from atlas.evolution.autonomy.models import (
    AuthorizationMode,
    AutonomyPolicy,
    EvolutionRequestStatus,
)
from atlas.evolution.autonomy.schedule_store import ScheduleStore
from atlas.evolution.autonomy.validator import EvolutionValidator
from atlas.evolution.autonomy.risk_assessor import EvolutionRiskAssessor
from atlas.evolution.autonomy.dispatcher import EvolutionAutonomyDispatcher
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import ExecutionLevel
from atlas.storage.autonomy_storage import AutonomySQLiteStorage

NOW = datetime(2026, 1, 1, 12, 0, 0)
INFORMATION_POLICY = AutonomyPolicy(enabled=False, effective_execution_level=ExecutionLevel.INFORMATION)


class _StubGateway:
    def execute_request(self, *args, **kwargs):
        raise AssertionError("execution must never be reached in CLI tests")


def _make_store(policy=INFORMATION_POLICY):
    tmp = tempfile.mkdtemp(prefix="atlas_b14_")
    db = Path(tmp) / "autonomy.db"
    storage = AutonomySQLiteStorage(db_path=str(db))
    storage.initialize()
    return storage, ScheduleStore(storage=storage, policy=policy), tmp


def _info_payload():
    return {"operation": "add", "entry_id": "K-14", "domain": "test", "content": "knowledge content", "confidence": 0.9}


def _make_pending(store, request_id, scope=ScopeType.KNOWLEDGE, payload=None, level=ExecutionLevel.INFORMATION):
    store.create_request(request_id, "test", scope, payload or _info_payload(), intended_level=level)
    dispatcher = EvolutionAutonomyDispatcher(
        schedule_store=store,
        validator=EvolutionValidator(),
        risk_assessor=EvolutionRiskAssessor(),
        execution_gateway=_StubGateway(),
        clock=lambda: NOW,
    )
    dispatcher._apply_due = lambda now: None
    dispatcher.settle(now=NOW)
    return store.get_request(request_id)


class TestPending(unittest.TestCase):
    def test_lists_only_pending(self):
        storage, store, tmp = _make_store()
        try:
            _make_pending(store, "REQ-P1")
            _make_pending(store, "REQ-P2")
            store.create_request("REQ-DONE", "test", ScopeType.KNOWLEDGE, _info_payload(), intended_level=ExecutionLevel.INFORMATION)
            store.update_status("REQ-DONE", EvolutionRequestStatus.DRAFTED, EvolutionRequestStatus.REJECTED, now=NOW)
            out = ac.cmd_requests_pending(store, argparse.Namespace())
            self.assertIn("REQ-P1", out)
            self.assertIn("REQ-P2", out)
            self.assertNotIn("REQ-DONE", out)
            self.assertEqual(store.get_request("REQ-P1").status, EvolutionRequestStatus.PENDING_AUTHORIZATION)
        finally:
            storage.close(); shutil.rmtree(tmp, ignore_errors=True)

    def test_empty_pending(self):
        storage, store, tmp = _make_store()
        try:
            out = ac.cmd_requests_pending(store, argparse.Namespace())
            self.assertIn("No requests", out)
        finally:
            storage.close(); shutil.rmtree(tmp, ignore_errors=True)


class TestShow(unittest.TestCase):
    def test_show_displays_context_and_no_mutation(self):
        storage, store, tmp = _make_store()
        try:
            _make_pending(store, "REQ-S")
            before = store.get_request("REQ-S")
            out = ac.cmd_request_show(store, argparse.Namespace(request_id="REQ-S"))
            self.assertIn("REQ-S", out)
            self.assertIn("KNOWLEDGE", out)
            self.assertIn("INFORMATION", out)
            self.assertIn("Validation", out)
            self.assertIn("Risk", out)
            self.assertEqual(store.get_request("REQ-S"), before)
        finally:
            storage.close(); shutil.rmtree(tmp, ignore_errors=True)

    def test_show_missing_request(self):
        storage, store, tmp = _make_store()
        try:
            out = ac.cmd_request_show(store, argparse.Namespace(request_id="NOPE"))
            self.assertIn("not found", out)
        finally:
            storage.close(); shutil.rmtree(tmp, ignore_errors=True)

    def test_show_requires_request_id(self):
        storage, store, tmp = _make_store()
        try:
            out = ac.cmd_request_show(store, argparse.Namespace(request_id=""))
            self.assertTrue(out.startswith("error:"))
        finally:
            storage.close(); shutil.rmtree(tmp, ignore_errors=True)


class TestAuthorize(unittest.TestCase):
    def test_success_knowledge_information(self):
        storage, store, tmp = _make_store()
        try:
            _make_pending(store, "REQ-A")
            out = ac.cmd_request_authorize(store, argparse.Namespace(request_id="REQ-A", comment="ok"))
            self.assertIn("AUTHORIZED", out)
            self.assertIn("SCHEDULED", out)
            req = store.get_request("REQ-A")
            self.assertEqual(req.status, EvolutionRequestStatus.SCHEDULED)
            self.assertEqual(req.authorization.authorized_by, "user:cli")
            self.assertEqual(req.authorization.mode, AuthorizationMode.EXPLICIT)
        finally:
            storage.close(); shutil.rmtree(tmp, ignore_errors=True)

    def test_success_memory_information(self):
        storage, store, tmp = _make_store()
        try:
            mem_payload = {"operation": "add", "memory_id": "M-14", "content": "x"}
            _make_pending(store, "REQ-M", scope=ScopeType.MEMORY, payload=mem_payload)
            out = ac.cmd_request_authorize(store, argparse.Namespace(request_id="REQ-M", comment="ok"))
            self.assertIn("AUTHORIZED", out)
            req = store.get_request("REQ-M")
            self.assertEqual(req.status, EvolutionRequestStatus.SCHEDULED)
            self.assertEqual(req.authorization.authorized_by, "user:cli")
        finally:
            storage.close(); shutil.rmtree(tmp, ignore_errors=True)

    def test_config_fails_closed(self):
        storage, store, tmp = _make_store()
        try:
            cfg = {"operation": "set", "key": "ai.provider", "value": "x"}
            store.create_request("REQ-CFG", "test", ScopeType.CONFIG, cfg, intended_level=ExecutionLevel.INFORMATION); store.update_status("REQ-CFG", EvolutionRequestStatus.DRAFTED, EvolutionRequestStatus.PENDING_AUTHORIZATION, now=NOW)
            out = ac.cmd_request_authorize(store, argparse.Namespace(request_id="REQ-CFG", comment=""))
            self.assertTrue(out.startswith("error:"))
            req = store.get_request("REQ-CFG")
            self.assertEqual(req.status, EvolutionRequestStatus.PENDING_AUTHORIZATION)
            self.assertIsNone(req.authorization)
        finally:
            storage.close(); shutil.rmtree(tmp, ignore_errors=True)

    def test_capability_fails_closed(self):
        storage, store, tmp = _make_store()
        try:
            cap = {"operation": "register", "capability_name": "Rogue"}
            store.create_request("REQ-CAP", "test", ScopeType.CAPABILITY, cap, intended_level=ExecutionLevel.INFORMATION); store.update_status("REQ-CAP", EvolutionRequestStatus.DRAFTED, EvolutionRequestStatus.PENDING_AUTHORIZATION, now=NOW)
            out = ac.cmd_request_authorize(store, argparse.Namespace(request_id="REQ-CAP", comment=""))
            self.assertTrue(out.startswith("error:"))
            req = store.get_request("REQ-CAP")
            self.assertEqual(req.status, EvolutionRequestStatus.PENDING_AUTHORIZATION)
            self.assertIsNone(req.authorization)
        finally:
            storage.close(); shutil.rmtree(tmp, ignore_errors=True)

    def test_unknown_scope_fails_closed(self):
        storage, store, tmp = _make_store()
        try:
            store.create_request("REQ-U", "test", ScopeType.UNKNOWN, {}, intended_level=ExecutionLevel.INFORMATION); store.update_status("REQ-U", EvolutionRequestStatus.DRAFTED, EvolutionRequestStatus.PENDING_AUTHORIZATION, now=NOW)
            out = ac.cmd_request_authorize(store, argparse.Namespace(request_id="REQ-U", comment=""))
            self.assertTrue(out.startswith("error:"))
            self.assertIsNone(store.get_request("REQ-U").authorization)
        finally:
            storage.close(); shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_request(self):
        storage, store, tmp = _make_store()
        try:
            out = ac.cmd_request_authorize(store, argparse.Namespace(request_id="NOPE", comment=""))
            self.assertTrue(out.startswith("error:"))
        finally:
            storage.close(); shutil.rmtree(tmp, ignore_errors=True)

    def test_not_pending_fails_closed(self):
        storage, store, tmp = _make_store()
        try:
            store.create_request("REQ-D", "test", ScopeType.KNOWLEDGE, _info_payload(), intended_level=ExecutionLevel.INFORMATION)
            out = ac.cmd_request_authorize(store, argparse.Namespace(request_id="REQ-D", comment=""))
            self.assertTrue(out.startswith("error:"))
            self.assertIn("not awaiting", out)
            self.assertIsNone(store.get_request("REQ-D").authorization)
        finally:
            storage.close(); shutil.rmtree(tmp, ignore_errors=True)

    def test_existing_authorization_no_regrant(self):
        storage, store, tmp = _make_store()
        try:
            _make_pending(store, "REQ-E")
            store.update_status("REQ-E", EvolutionRequestStatus.PENDING_AUTHORIZATION, EvolutionRequestStatus.AUTHORIZED, now=NOW)
            out = ac.cmd_request_authorize(store, argparse.Namespace(request_id="REQ-E", comment=""))
            self.assertTrue(out.startswith("error:"))
        finally:
            storage.close(); shutil.rmtree(tmp, ignore_errors=True)

    def test_double_authorize_no_regrant(self):
        storage, store, tmp = _make_store()
        try:
            _make_pending(store, "REQ-2")
            first = ac.cmd_request_authorize(store, argparse.Namespace(request_id="REQ-2", comment="a"))
            self.assertIn("AUTHORIZED", first)
            granted_at = store.get_request("REQ-2").authorization.granted_at
            second = ac.cmd_request_authorize(store, argparse.Namespace(request_id="REQ-2", comment="b"))
            self.assertTrue(second.startswith("error:"))
            after = store.get_request("REQ-2")
            self.assertEqual(after.authorization.granted_at, granted_at)
            self.assertEqual(after.authorization.comment, "a")
            self.assertEqual(after.status, EvolutionRequestStatus.SCHEDULED)
        finally:
            storage.close(); shutil.rmtree(tmp, ignore_errors=True)


class TestStatus(unittest.TestCase):
    def test_status_reports_counts(self):
        storage, store, tmp = _make_store()
        try:
            _make_pending(store, "REQ-S1")
            out = ac.cmd_requests_status(store, argparse.Namespace())
            self.assertIn("Pending authorizations: 1", out)
            self.assertIn("Policy enabled: False", out)
        finally:
            storage.close(); shutil.rmtree(tmp, ignore_errors=True)


class TestNoEngineExecution(unittest.TestCase):
    """The CLI must never invoke ApplicationEngine directly."""

    def test_authorize_module_never_references_engine_or_gateway(self):
        import inspect
        import atlas.cli.autonomy_commands as ac
        src = inspect.getsource(ac)
        self.assertNotIn("application_engine", src)
        self.assertNotIn(".apply(", src)
        self.assertNotIn("execute_request", src)

    def test_authorize_does_not_apply_on_success(self):
        # Success only goes to AUTHORIZED/SCHEDULED, never APPLIED/COMPLETED.
        storage, store, tmp = _make_store()
        try:
            _make_pending(store, "REQ-NE")
            ac.cmd_request_authorize(store, argparse.Namespace(request_id="REQ-NE", comment="ok"))
            req = store.get_request("REQ-NE")
            self.assertEqual(req.status, EvolutionRequestStatus.SCHEDULED)
            self.assertIsNone(req.receipt)
            self.assertIsNone(req.verification)
        finally:
            storage.close(); shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
