"""
Atlas Evolution Autonomy — Schedule Store Tests — Phase 16.4

Verifies ``ScheduleStore`` behavior:

- Lifecycle transitions (DRAFTED → VALIDATED → RISK_ASSESSED → AUTHORIZED → SCHEDULED).
- Atomic CAS status updates.
- Atomic claim with version anchor (success and SUPERSEDED).
- Queue queries: pending authorization, scheduled, due, in-flight.
- Quota accounting for autonomous requests.
- Status report generation.
- Deterministic behavior with injected clock.

Uses an isolated temporary SQLite database.
"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from atlas.evolution.autonomy.models import (
    AtlasStateVersion,
    AuthorizationMode,
    AutonomyPolicy,
    EvolutionAuthorization,
    EvolutionRequest,
    EvolutionRequestStatus,
    EvolutionSchedule,
    EvolutionWindow,
    RiskAssessment,
    RiskLevel,
    TargetKind,
    ValidationReport,
    VersionTarget,
)
from atlas.evolution.autonomy.schedule_store import ClaimResult, ScheduleStore
from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import ExecutionLevel
from atlas.storage.autonomy_storage import AutonomySQLiteStorage


class ScheduleStoreTestCase(unittest.TestCase):
    """Base test case providing an isolated schedule store instance."""

    def setUp(self) -> None:
        self.now = datetime(2026, 1, 1, 12, 0, 0)
        self.tmp_dir = tempfile.mkdtemp(prefix="atlas_schedule_store_")
        self.db_path = Path(self.tmp_dir) / "test_schedule.db"
        self.storage = AutonomySQLiteStorage(db_path=self.db_path)
        self.storage.initialize()
        self.policy = AutonomyPolicy(
            enabled=True,
            version="v1",
            effective_execution_level=ExecutionLevel.ADMINISTRATIVE,
            allowed_scopes=[ScopeType.CONFIG, ScopeType.MEMORY],
            max_risk_level=RiskLevel.MEDIUM,
            max_requests_per_window=3,
            window=EvolutionWindow(
                window_start=self.now,
                window_end=self.now + timedelta(hours=1),
            ),
            requires_user_approval_scopes=[ScopeType.CODE],
            hot_reload_allowlist=[],
            authorization_ttl_minutes=60,
        )
        self.store = ScheduleStore(
            storage=self.storage,
            policy=self.policy,
            clock=lambda: self.now,
        )

    def tearDown(self) -> None:
        self.storage.close()
        try:
            os.remove(self.db_path)
        except FileNotFoundError:
            pass
        os.rmdir(self.tmp_dir)

    def _advance(self, seconds: int = 1) -> None:
        self.now += timedelta(seconds=seconds)

    def _assert_status(
        self, request_id: str, expected: EvolutionRequestStatus
    ) -> EvolutionRequest:
        req = self.store.get_request(request_id)
        self.assertIsNotNone(req)
        self.assertEqual(req.status, expected)
        return req


class TestLifecycleTransitions(ScheduleStoreTestCase):
    """Request lifecycle via schedule store helpers."""

    def test_create_request_is_drafted(self):
        req = self.store.create_request(
            request_id="REQ-1",
            source="cli",
            target_scope=ScopeType.CONFIG,
            change_payload={"x": 1},
            now=self.now,
        )
        self.assertEqual(req.status, EvolutionRequestStatus.DRAFTED)
        self._assert_status("REQ-1", EvolutionRequestStatus.DRAFTED)

    def test_record_validation(self):
        self.store.create_request(
            "REQ-1", "cli", ScopeType.CONFIG, {"x": 1}, now=self.now
        )
        updated = self.store.record_validation(
            "REQ-1",
            ValidationReport(valid=True, violations=[], warnings=[]),
            now=self.now,
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, EvolutionRequestStatus.VALIDATED)
        self.assertTrue(updated.validation.valid)

    def test_record_validation_rejected(self):
        self.store.create_request(
            "REQ-1", "cli", ScopeType.CONFIG, {"x": 1}, now=self.now
        )
        updated = self.store.record_validation(
            "REQ-1",
            ValidationReport(valid=False, violations=["bad"], warnings=[]),
            now=self.now,
        )
        self.assertEqual(updated.status, EvolutionRequestStatus.REJECTED)

    def test_record_risk(self):
        self.store.create_request(
            "REQ-1", "cli", ScopeType.CONFIG, {"x": 1}, now=self.now
        )
        updated = self.store.record_risk(
            "REQ-1",
            RiskAssessment(
                risk_level=RiskLevel.LOW,
                score=0.2,
                factors={},
            ),
            now=self.now,
        )
        self.assertEqual(updated.status, EvolutionRequestStatus.RISK_ASSESSED)
        self.assertEqual(updated.risk.risk_level, RiskLevel.LOW)

    def test_record_authorization(self):
        self.store.create_request(
            "REQ-1", "cli", ScopeType.CONFIG, {"x": 1}, now=self.now
        )
        updated = self.store.record_authorization(
            "REQ-1",
            EvolutionAuthorization(
                request_id="REQ-1",
                authorized_by="user:alice",
                mode=AuthorizationMode.EXPLICIT,
                granted_at=self.now,
                expires_at=self.now + timedelta(hours=1),
            ),
            now=self.now,
        )
        self.assertEqual(updated.status, EvolutionRequestStatus.AUTHORIZED)

    def test_schedule_request(self):
        self.store.create_request(
            "REQ-1", "cli", ScopeType.CONFIG, {"x": 1}, now=self.now
        )
        self.store.record_authorization(
            "REQ-1",
            EvolutionAuthorization(
                request_id="REQ-1",
                authorized_by="system:autonomy",
                mode=AuthorizationMode.AUTONOMY,
                granted_at=self.now,
                expires_at=self.now + timedelta(hours=1),
            ),
            now=self.now,
        )
        scheduled = self.store.schedule_request("REQ-1", now=self.now)
        self.assertEqual(scheduled.status, EvolutionRequestStatus.SCHEDULED)
        self.assertEqual(scheduled.schedule.scheduled_at, self.now)


class TestAtomicStatusUpdate(ScheduleStoreTestCase):
    """CAS status transitions."""

    def test_cas_success(self):
        self.store.create_request(
            "REQ-1", "cli", ScopeType.CONFIG, {"x": 1}, now=self.now
        )
        ok = self.store.update_status(
            "REQ-1",
            EvolutionRequestStatus.DRAFTED,
            EvolutionRequestStatus.VALIDATED,
            now=self.now,
        )
        self.assertTrue(ok)
        self._assert_status("REQ-1", EvolutionRequestStatus.VALIDATED)

    def test_cas_failure_wrong_expected(self):
        self.store.create_request(
            "REQ-1", "cli", ScopeType.CONFIG, {"x": 1}, now=self.now
        )
        ok = self.store.update_status(
            "REQ-1",
            EvolutionRequestStatus.SCHEDULED,
            EvolutionRequestStatus.APPLIED,
            now=self.now,
        )
        self.assertFalse(ok)
        self._assert_status("REQ-1", EvolutionRequestStatus.DRAFTED)


class TestAtomicClaim(ScheduleStoreTestCase):
    """Atomic SCHEDULED → APPLIED claim with version anchor."""

    def _schedule_with_version(self, request_id: str, anchor: str) -> EvolutionRequest:
        self.store.create_request(
            request_id,
            "cli",
            ScopeType.CONFIG,
            {"x": 1},
            version_target=VersionTarget(
                target_kind=TargetKind.CONFIG,
                current_version="1.0.0",
                target_version="1.0.1",
                state_version_at_creation=anchor,
            ),
            now=self.now,
        )
        self.store.record_authorization(
            request_id,
            EvolutionAuthorization(
                request_id=request_id,
                authorized_by="system:autonomy",
                mode=AuthorizationMode.AUTONOMY,
                granted_at=self.now,
                expires_at=self.now + timedelta(hours=1),
            ),
            now=self.now,
        )
        return self.store.schedule_request(request_id, now=self.now)

    def test_claim_success(self):
        self._schedule_with_version("REQ-1", "1.0.0")
        result = self.store.claim_scheduled("REQ-1", "1.0.0", now=self.now)
        self.assertTrue(result.claimed)
        self.assertFalse(result.superseded)
        self._assert_status("REQ-1", EvolutionRequestStatus.APPLIED)

    def test_claim_superseded_on_version_mismatch(self):
        self._schedule_with_version("REQ-1", "1.0.0")
        result = self.store.claim_scheduled("REQ-1", "1.1.0", now=self.now)
        self.assertFalse(result.claimed)
        self.assertTrue(result.superseded)
        self._assert_status("REQ-1", EvolutionRequestStatus.SUPERSEDED)

    def test_claim_fails_when_not_scheduled(self):
        self.store.create_request(
            "REQ-1", "cli", ScopeType.CONFIG, {"x": 1}, now=self.now
        )
        result = self.store.claim_scheduled("REQ-1", "1.0.0", now=self.now)
        self.assertFalse(result.claimed)
        self.assertFalse(result.superseded)

    def test_claim_returns_none_for_missing_request(self):
        result = self.store.claim_scheduled("MISSING", "1.0.0", now=self.now)
        self.assertIsNone(result.request)
        self.assertFalse(result.claimed)


class TestQueues(ScheduleStoreTestCase):
    """Queue queries."""

    def test_pending_authorization(self):
        self.store.create_request(
            "REQ-1", "cli", ScopeType.CONFIG, {"x": 1}, now=self.now
        )
        self.store.update_status(
            "REQ-1",
            EvolutionRequestStatus.DRAFTED,
            EvolutionRequestStatus.PENDING_AUTHORIZATION,
            now=self.now,
        )
        self.store.create_request(
            "REQ-2", "cli", ScopeType.CONFIG, {"x": 2}, now=self.now
        )
        pending = self.store.pending_authorization()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].request_id, "REQ-1")

    def test_scheduled_and_due_queue(self):
        self._authorize_and_schedule("REQ-1")
        self._authorize_and_schedule("REQ-2")
        self.assertEqual(len(self.store.scheduled()), 2)
        self.assertEqual(len(self.store.due_queue(now=self.now)), 2)

    def test_due_queue_respects_cooldown(self):
        self._authorize_and_schedule("REQ-1")
        req = self.store.get_request("REQ-1")
        schedule = EvolutionSchedule(
            scheduled_at=self.now,
            cooldown_until=self.now + timedelta(minutes=5),
        )
        self.store.save_request(
            ScheduleStore._replace(req, schedule=schedule, status=EvolutionRequestStatus.SCHEDULED)
        )
        self.assertEqual(len(self.store.due_queue(now=self.now)), 0)
        self.assertEqual(
            len(self.store.due_queue(now=self.now + timedelta(minutes=10))),
            1,
        )

    def test_due_queue_respects_window(self):
        self._authorize_and_schedule("REQ-1")
        req = self.store.get_request("REQ-1")
        schedule = EvolutionSchedule(
            scheduled_at=self.now,
            window_start=self.now + timedelta(minutes=5),
            window_end=self.now + timedelta(minutes=10),
        )
        self.store.save_request(
            ScheduleStore._replace(req, schedule=schedule, status=EvolutionRequestStatus.SCHEDULED)
        )
        self.assertEqual(len(self.store.due_queue(now=self.now)), 0)
        self.assertEqual(
            len(self.store.due_queue(now=self.now + timedelta(minutes=7))),
            1,
        )
        self.assertEqual(
            len(self.store.due_queue(now=self.now + timedelta(minutes=15))),
            0,
        )

    def test_in_flight(self):
        self._authorize_and_schedule_with_version("REQ-1", "1.0.0")
        result = self.store.claim_scheduled("REQ-1", "1.0.0", now=self.now)
        self.assertTrue(result.claimed)
        in_flight = self.store.in_flight()
        self.assertEqual(len(in_flight), 1)
        self.assertEqual(in_flight[0].status, EvolutionRequestStatus.APPLIED)

    def _authorize_and_schedule_with_version(
        self, request_id: str, anchor: str
    ) -> EvolutionRequest:
        self.store.create_request(
            request_id,
            "cli",
            ScopeType.CONFIG,
            {"x": 1},
            version_target=VersionTarget(
                target_kind=TargetKind.CONFIG,
                current_version="1.0.0",
                target_version="1.0.1",
                state_version_at_creation=anchor,
            ),
            now=self.now,
        )
        self.store.record_authorization(
            request_id,
            EvolutionAuthorization(
                request_id=request_id,
                authorized_by="system:autonomy",
                mode=AuthorizationMode.AUTONOMY,
                granted_at=self.now,
                expires_at=self.now + timedelta(hours=1),
            ),
            now=self.now,
        )
        return self.store.schedule_request(request_id, now=self.now)

    def _authorize_and_schedule(self, request_id: str) -> None:
        self.store.create_request(
            request_id, "cli", ScopeType.CONFIG, {"x": 1}, now=self.now
        )
        self.store.record_authorization(
            request_id,
            EvolutionAuthorization(
                request_id=request_id,
                authorized_by="system:autonomy",
                mode=AuthorizationMode.AUTONOMY,
                granted_at=self.now,
                expires_at=self.now + timedelta(hours=1),
            ),
            now=self.now,
        )
        self.store.schedule_request(request_id, now=self.now)


class TestQuotaAccounting(ScheduleStoreTestCase):
    """Autonomous request quota within the policy window."""

    def test_quota_used_counts_scheduled_autonomous_requests(self):
        self._schedule_autonomous("REQ-1")
        self._schedule_autonomous("REQ-2")
        self.assertEqual(self.store.quota_used_this_window(self.policy.window), 2)

    def test_quota_ignores_explicit_authorization(self):
        self._schedule_explicit("REQ-1")
        self.assertEqual(self.store.quota_used_this_window(self.policy.window), 0)

    def test_quota_ignores_outside_window(self):
        self._schedule_autonomous("REQ-1")
        future_window = EvolutionWindow(
            window_start=self.now + timedelta(days=1),
            window_end=self.now + timedelta(days=2),
        )
        self.assertEqual(self.store.quota_used_this_window(future_window), 0)

    def _schedule_autonomous(self, request_id: str) -> None:
        self.store.create_request(
            request_id, "cli", ScopeType.CONFIG, {"x": 1}, now=self.now
        )
        self.store.record_authorization(
            request_id,
            EvolutionAuthorization(
                request_id=request_id,
                authorized_by="system:autonomy",
                mode=AuthorizationMode.AUTONOMY,
                granted_at=self.now,
                expires_at=self.now + timedelta(hours=1),
            ),
            now=self.now,
        )
        self.store.schedule_request(request_id, now=self.now)

    def _schedule_explicit(self, request_id: str) -> None:
        self.store.create_request(
            request_id, "cli", ScopeType.CONFIG, {"x": 1}, now=self.now
        )
        self.store.record_authorization(
            request_id,
            EvolutionAuthorization(
                request_id=request_id,
                authorized_by="user:alice",
                mode=AuthorizationMode.EXPLICIT,
                granted_at=self.now,
                expires_at=self.now + timedelta(hours=1),
            ),
            now=self.now,
        )
        self.store.schedule_request(request_id, now=self.now)


class TestStatusReport(ScheduleStoreTestCase):
    """EvolutionStatusReport from storage."""

    def test_status_report_counts_and_lists(self):
        self.store.create_request(
            "REQ-1", "cli", ScopeType.CONFIG, {"x": 1}, now=self.now
        )
        self.store.update_status(
            "REQ-1",
            EvolutionRequestStatus.DRAFTED,
            EvolutionRequestStatus.PENDING_AUTHORIZATION,
            now=self.now,
        )
        self._schedule_autonomous("REQ-2")
        self._schedule_autonomous("REQ-3")

        report = self.store.status_report()
        self.assertEqual(report.pending_authorizations, 1)
        self.assertEqual(sorted(report.scheduled), ["REQ-2", "REQ-3"])
        self.assertEqual(report.in_flight, [])
        self.assertEqual(report.window_quota_used, 2)
        self.assertFalse(report.hold)
        self.assertEqual(report.policy_version, "v1")
        self.assertIn("effective_execution_level", report.envelope)

    def test_status_report_detects_hold(self):
        self.store.create_request(
            "REQ-1", "cli", ScopeType.CONFIG, {"x": 1}, now=self.now
        )
        self.store.update_status(
            "REQ-1",
            EvolutionRequestStatus.DRAFTED,
            EvolutionRequestStatus.EVOLUTION_HOLD,
            now=self.now,
        )
        report = self.store.status_report()
        self.assertTrue(report.hold)

    def test_status_report_state_version(self):
        self.storage.store_version(
            AtlasStateVersion(
                major=2,
                minor=0,
                patch=1,
                manifest_id="v2.0.1",
                created_at=self.now,
            )
        )
        report = self.store.status_report()
        self.assertEqual(report.state_version, "2.0.1")

    def _schedule_autonomous(self, request_id: str) -> None:
        self.store.create_request(
            request_id, "cli", ScopeType.CONFIG, {"x": 1}, now=self.now
        )
        self.store.record_authorization(
            request_id,
            EvolutionAuthorization(
                request_id=request_id,
                authorized_by="system:autonomy",
                mode=AuthorizationMode.AUTONOMY,
                granted_at=self.now,
                expires_at=self.now + timedelta(hours=1),
            ),
            now=self.now,
        )
        self.store.schedule_request(request_id, now=self.now)


class TestConstruction(ScheduleStoreTestCase):
    """Dependency injection validation."""

    def test_requires_storage(self):
        with self.assertRaises(ValueError):
            ScheduleStore(storage=None, policy=self.policy)

    def test_requires_policy(self):
        with self.assertRaises(ValueError):
            ScheduleStore(storage=self.storage, policy=None)


if __name__ == "__main__":
    unittest.main()
