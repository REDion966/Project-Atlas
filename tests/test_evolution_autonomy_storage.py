"""
Atlas Evolution Autonomy — Storage Tests — Phase 16.4

Verifies ``AutonomySQLiteStorage`` persistence of:

- EvolutionRequests (including nested validation, risk, authorization, schedule).
- AtlasStateVersion manifests.
- ChangeReceipts.
- Snapshot artifacts.
- EvolutionOutcomeRecords.
- StagedConfigEntry records.
- Schema migration to the current version.
- Atomic CAS status updates.
- Version-safe serialization round-trips.

All tests use a temporary SQLite database to avoid touching the project DB.
"""

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from atlas.evolution.autonomy.models import (
    AtlasStateVersion,
    AuthorizationMode,
    ChangeReceipt,
    EvolutionAuthorization,
    EvolutionOutcomeRecord,
    EvolutionRequest,
    EvolutionRequestStatus,
    EvolutionSchedule,
    EvolutionWindow,
    RiskAssessment,
    RiskLevel,
    RollbackPlan,
    RollbackStrategy,
    StagedConfigEntry,
    TargetKind,
    ValidationReport,
    VerificationResult,
    VersionTarget,
)
from atlas.evolution.autonomy.serialization import from_serializable, to_serializable

from atlas.evolution.governance.models import ScopeType
from atlas.evolution.models import ExecutionLevel
from atlas.storage.autonomy_storage import AutonomySQLiteStorage


class StorageTestCase(unittest.TestCase):
    """Base test case providing an isolated temporary storage instance."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp(prefix="atlas_autonomy_storage_")
        self.db_path = Path(self.tmp_dir) / "test_autonomy.db"
        self.storage = AutonomySQLiteStorage(db_path=self.db_path)
        self.storage.initialize()

    def tearDown(self) -> None:
        self.storage.close()
        try:
            os.remove(self.db_path)
        except FileNotFoundError:
            pass
        os.rmdir(self.tmp_dir)

    def _make_request(
        self,
        request_id: str = "REQ-1",
        status: EvolutionRequestStatus = EvolutionRequestStatus.DRAFTED,
        scope: ScopeType = ScopeType.CONFIG,
    ) -> EvolutionRequest:
        now = datetime(2026, 1, 1, 12, 0, 0)
        return EvolutionRequest(
            request_id=request_id,
            source="cli",
            target_scope=scope,
            change_payload={"key": "x", "value": 1},
            intended_level=ExecutionLevel.SELF_CONFIG,
            status=status,
            created_at=now,
            updated_at=now,
        )


class TestSchemaMigration(StorageTestCase):
    """Storage initializes the Phase 16.4 schema."""

    def test_schema_version_is_current(self):
        # Phase 19.x added additive long-term tables (migration version 9);
        # Track D added the advanced_reasoning_traces tables (version 10);
        # Persistent Learning added learning_insights (version 11).
        self.assertEqual(self.storage.schema_version(), 11)

    def test_tables_exist(self):
        cursor = self.storage._execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        names = {row["name"] for row in cursor.fetchall()}
        for table in (
            "evolution_requests",
            "evolution_versions",
            "evolution_receipts",
            "evolution_snapshots",
            "evolution_outcomes",
            "staged_config",
        ):
            self.assertIn(table, names)


class TestRequestPersistence(StorageTestCase):
    """Round-trip ``EvolutionRequest`` objects."""

    def test_store_and_load_minimal_request(self):
        req = self._make_request()
        self.storage.store_request(req)
        loaded = self.storage.load_request("REQ-1")

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.request_id, req.request_id)
        self.assertEqual(loaded.source, req.source)
        self.assertEqual(loaded.target_scope, req.target_scope)
        self.assertEqual(loaded.change_payload, req.change_payload)
        self.assertEqual(loaded.intended_level, req.intended_level)
        self.assertEqual(loaded.status, req.status)
        self.assertEqual(loaded.created_at, req.created_at)
        self.assertEqual(loaded.updated_at, req.updated_at)

    def test_store_and_load_full_request(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        req = EvolutionRequest(
            request_id="REQ-FULL",
            source="scheduler",
            target_scope=ScopeType.MEMORY,
            change_payload={"operation": "add", "memory_id": "M-1"},
            intended_level=ExecutionLevel.INFORMATION,
            status=EvolutionRequestStatus.SCHEDULED,
            validation=ValidationReport(
                valid=True, violations=[], warnings=["minor"]
            ),
            risk=RiskAssessment(
                risk_level=RiskLevel.LOW,
                score=0.25,
                factors={"scope": 0.1},
                requires_user_approval=False,
                requires_rollback=False,
            ),
            authorization=EvolutionAuthorization(
                request_id="REQ-FULL",
                authorized_by="system:autonomy",
                mode=AuthorizationMode.AUTONOMY,
                granted_at=now,
                expires_at=now,
                policy_ref="v1",
                comment="auto",
            ),
            schedule=EvolutionSchedule(
                scheduled_at=now,
                window_start=now,
                window_end=now,
                max_attempts=1,
                cooldown_until=None,
                expired_at=None,
            ),
            version_target=VersionTarget(
                target_kind=TargetKind.MEMORY,
                current_version="1.0.0",
                target_version="1.0.1",
                state_version_at_creation="1.0.0",
            ),
            rollback=RollbackPlan(
                strategy=RollbackStrategy.SNAPSHOT,
                snapshot_ref="snap-1",
                inverse_description="remove M-1",
                steps=["remove M-1"],
                cascade_targets=[],
                requires_user_approval=False,
            ),
            receipt=ChangeReceipt(
                request_id="REQ-FULL",
                changed_keys=["memory.M-1"],
                before_refs={},
                after_refs={"memory.M-1": "x"},
                version_delta="patch+1",
                target_tags=["memory"],
                applied_at=now,
            ),
            verification=VerificationResult(
                passed=True, checks=[], details="ok", scope=ScopeType.MEMORY
            ),
            parent_request_ids=["REQ-PARENT"],
            created_at=now,
            updated_at=now,
            metadata={"trace": "test"},
        )
        self.storage.store_request(req)
        loaded = self.storage.load_request("REQ-FULL")

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.status, EvolutionRequestStatus.SCHEDULED)
        self.assertEqual(loaded.validation.valid, True)
        self.assertEqual(loaded.risk.risk_level, RiskLevel.LOW)
        self.assertEqual(loaded.authorization.mode, AuthorizationMode.AUTONOMY)
        self.assertEqual(loaded.schedule.scheduled_at, now)
        self.assertEqual(loaded.version_target.state_version_at_creation, "1.0.0")
        self.assertEqual(loaded.rollback.strategy, RollbackStrategy.SNAPSHOT)
        self.assertEqual(loaded.receipt.changed_keys, ["memory.M-1"])
        self.assertEqual(loaded.verification.passed, True)
        self.assertEqual(loaded.parent_request_ids, ["REQ-PARENT"])
        self.assertEqual(loaded.metadata, {"trace": "test"})

    def test_load_missing_request_returns_none(self):
        self.assertIsNone(self.storage.load_request("MISSING"))

    def test_load_requests_by_status(self):
        self.storage.store_request(self._make_request("REQ-A", EvolutionRequestStatus.DRAFTED))
        self.storage.store_request(self._make_request("REQ-B", EvolutionRequestStatus.SCHEDULED))
        self.storage.store_request(self._make_request("REQ-C", EvolutionRequestStatus.SCHEDULED))

        scheduled = self.storage.load_requests(status=EvolutionRequestStatus.SCHEDULED.name)
        self.assertEqual(len(scheduled), 2)
        self.assertEqual({r.request_id for r in scheduled}, {"REQ-B", "REQ-C"})

    def test_load_requests_by_scope(self):
        self.storage.store_request(self._make_request("REQ-A", scope=ScopeType.CONFIG))
        self.storage.store_request(self._make_request("REQ-B", scope=ScopeType.MEMORY))

        memory = self.storage.load_requests(target_scope=ScopeType.MEMORY.name)
        self.assertEqual(len(memory), 1)
        self.assertEqual(memory[0].request_id, "REQ-B")

    def test_delete_request(self):
        self.storage.store_request(self._make_request())
        self.storage.delete_request("REQ-1")
        self.assertIsNone(self.storage.load_request("REQ-1"))

    def test_update_status_cas_success(self):
        self.storage.store_request(self._make_request())
        now = datetime(2026, 1, 2, 12, 0, 0)
        ok = self.storage.update_status(
            "REQ-1",
            EvolutionRequestStatus.DRAFTED.name,
            EvolutionRequestStatus.VALIDATED.name,
            now.isoformat(),
        )
        self.assertTrue(ok)
        loaded = self.storage.load_request("REQ-1")
        self.assertEqual(loaded.status, EvolutionRequestStatus.VALIDATED)
        self.assertEqual(loaded.updated_at, now)

    def test_update_status_cas_failure_wrong_status(self):
        self.storage.store_request(self._make_request())
        ok = self.storage.update_status(
            "REQ-1",
            EvolutionRequestStatus.SCHEDULED.name,
            EvolutionRequestStatus.APPLIED.name,
            datetime.now().isoformat(),
        )
        self.assertFalse(ok)
        loaded = self.storage.load_request("REQ-1")
        self.assertEqual(loaded.status, EvolutionRequestStatus.DRAFTED)

    def test_count_requests(self):
        self.storage.store_request(self._make_request("REQ-A", EvolutionRequestStatus.SCHEDULED))
        self.storage.store_request(self._make_request("REQ-B", EvolutionRequestStatus.SCHEDULED))
        self.storage.store_request(self._make_request("REQ-C", EvolutionRequestStatus.DRAFTED))
        self.assertEqual(
            self.storage.count_requests(status=EvolutionRequestStatus.SCHEDULED.name),
            2,
        )

    def test_count_requests_by_authorization_mode(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        req = self._make_request("REQ-A", EvolutionRequestStatus.SCHEDULED)
        req = EvolutionRequest(
            request_id=req.request_id,
            source=req.source,
            target_scope=req.target_scope,
            change_payload=req.change_payload,
            intended_level=req.intended_level,
            status=req.status,
            authorization=EvolutionAuthorization(
                request_id="REQ-A",
                authorized_by="system:autonomy",
                mode=AuthorizationMode.AUTONOMY,
                granted_at=now,
                expires_at=now,
            ),
            created_at=now,
            updated_at=now,
        )
        self.storage.store_request(req)
        self.assertEqual(
            self.storage.count_requests(authorization_mode=AuthorizationMode.AUTONOMY.name),
            1,
        )


class TestVersionPersistence(StorageTestCase):
    """``AtlasStateVersion`` manifest persistence."""

    def test_store_and_load_latest_version(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        version = AtlasStateVersion(
            major=1,
            minor=2,
            patch=3,
            manifest_id="v1.2.3",
            applied_request_ids=["REQ-1"],
            parent_version="1.2.2",
            scope_versions={"config": "c1"},
            tags=["test"],
            created_at=now,
        )
        self.storage.store_version(version)
        loaded = self.storage.load_latest_version()

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.major, 1)
        self.assertEqual(loaded.minor, 2)
        self.assertEqual(loaded.patch, 3)
        self.assertEqual(loaded.manifest_id, "v1.2.3")
        self.assertEqual(loaded.applied_request_ids, ["REQ-1"])
        self.assertEqual(loaded.parent_version, "1.2.2")
        self.assertEqual(loaded.scope_versions, {"config": "c1"})
        self.assertEqual(loaded.tags, ["test"])
        self.assertEqual(loaded.created_at, now)

    def test_load_latest_version_missing_returns_none(self):
        self.assertIsNone(self.storage.load_latest_version())


class TestReceiptPersistence(StorageTestCase):
    """``ChangeReceipt`` persistence."""

    def test_store_and_load_receipt(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        receipt = ChangeReceipt(
            request_id="REQ-R",
            changed_keys=["config.x"],
            before_refs={"config.x": 0},
            after_refs={"config.x": 1},
            version_delta="patch+1",
            target_tags=["config"],
            applied_at=now,
        )
        self.storage.store_receipt(receipt)
        loaded = self.storage.load_receipt("REQ-R")

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.request_id, "REQ-R")
        self.assertEqual(loaded.changed_keys, ["config.x"])
        self.assertEqual(loaded.before_refs, {"config.x": 0})
        self.assertEqual(loaded.after_refs, {"config.x": 1})
        self.assertEqual(loaded.applied_at, now)


class TestSnapshotPersistence(StorageTestCase):
    """Rollback snapshot artifact persistence."""

    def test_store_and_load_snapshot(self):
        now_str = datetime(2026, 1, 1, 12, 0, 0).isoformat()
        self.storage.store_snapshot(
            snapshot_id="snap-1",
            request_id="REQ-S",
            snapshot_data={"config": {"x": 0}, "checksum": "abc"},
            checksum="sha256:abc",
            created_at=now_str,
        )
        loaded = self.storage.load_snapshot("snap-1")

        self.assertEqual(loaded, {"config": {"x": 0}, "checksum": "abc"})


class TestOutcomePersistence(StorageTestCase):
    """``EvolutionOutcomeRecord`` persistence."""

    def test_store_and_load_outcome(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        outcome = EvolutionOutcomeRecord(
            outcome_record_id="OUT-1",
            request_id="REQ-O",
            scope=ScopeType.CAPABILITY,
            area="capability",
            risk_level=RiskLevel.MEDIUM,
            intended_level=ExecutionLevel.SELF_CONFIG,
            authorization_mode=AuthorizationMode.AUTONOMY,
            outcome="COMPLETED",
            verification_passed=True,
            rollback_occurred=False,
            effectiveness_proxy=1.0,
            started_at=now,
            finished_at=now,
            related_ids=["goal-1"],
            strategy_key="S1",
            strategy_name="Test strategy",
            planning_context_version="pcv-1",
            metadata={"note": "x"},
        )
        self.storage.store_outcome(outcome)
        loaded = self.storage.load_outcome("REQ-O")

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.outcome_record_id, "OUT-1")
        self.assertEqual(loaded.scope, ScopeType.CAPABILITY)
        self.assertEqual(loaded.risk_level, RiskLevel.MEDIUM)
        self.assertEqual(loaded.authorization_mode, AuthorizationMode.AUTONOMY)
        self.assertEqual(loaded.outcome, "COMPLETED")
        self.assertTrue(loaded.verification_passed)
        self.assertFalse(loaded.rollback_occurred)
        self.assertEqual(loaded.effectiveness_proxy, 1.0)
        self.assertEqual(loaded.related_ids, ["goal-1"])
        self.assertEqual(loaded.strategy_key, "S1")
        self.assertEqual(loaded.planning_context_version, "pcv-1")


class TestStagedConfigPersistence(StorageTestCase):
    """``StagedConfigEntry`` persistence."""

    def test_store_and_load_staged_config(self):
        now = datetime(2026, 1, 1, 12, 0, 0)
        entry = StagedConfigEntry(
            entry_id="SC-1",
            request_id="REQ-C",
            key="feature_flag_x",
            value=True,
            schema_status="valid",
            activated_at=None,
            applied_at=now,
        )
        self.storage.store_staged_config(entry)
        loaded = self.storage.load_staged_configs(request_id="REQ-C")

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].entry_id, "SC-1")
        self.assertEqual(loaded[0].key, "feature_flag_x")
        self.assertEqual(loaded[0].value, True)
        self.assertEqual(loaded[0].schema_status, "valid")
        self.assertIsNone(loaded[0].activated_at)
        self.assertEqual(loaded[0].applied_at, now)


class TestSerializationRoundTrip(StorageTestCase):
    """Enums, datetimes, and nested dataclasses survive JSON round-trip."""

    def test_window_round_trip(self):
        start = datetime(2026, 1, 1, 9, 0, 0)
        end = datetime(2026, 1, 1, 17, 0, 0)
        req = EvolutionRequest(
            request_id="REQ-W",
            source="cli",
            target_scope=ScopeType.CONFIG,
            schedule=EvolutionSchedule(
                scheduled_at=start,
                window_start=start,
                window_end=end,
            ),
            created_at=start,
            updated_at=start,
        )
        self.storage.store_request(req)
        loaded = self.storage.load_request("REQ-W")
        self.assertEqual(loaded.schedule.window_start, start)
        self.assertEqual(loaded.schedule.window_end, end)

    def test_optional_datetime_is_datetime_not_string(self):
        """PEP 604 ``datetime | None`` fields must deserialize to real datetimes
        on Python 3.11, not remain as ISO strings."""
        start = datetime(2026, 3, 15, 9, 30, 45)
        auth = EvolutionAuthorization(
            request_id="REQ-OPT",
            authorized_by="user:cli",
            mode=AuthorizationMode.EXPLICIT,
            granted_at=start,
            expires_at=start,
        )
        ser = to_serializable(auth)
        # Sanity: serialization turns the datetime into an ISO string.
        self.assertEqual(ser["expires_at"], start.isoformat())
        restored = from_serializable(ser, EvolutionAuthorization)
        self.assertIsInstance(restored.expires_at, datetime)
        self.assertEqual(restored.expires_at, start)

    def test_optional_datetime_none_stays_none(self):
        """``None`` expiry must round-trip as ``None``, not as a string."""
        auth = EvolutionAuthorization(
            request_id="REQ-NONE",
            authorized_by="user:cli",
            mode=AuthorizationMode.EXPLICIT,
        )
        ser = to_serializable(auth)
        self.assertIsNone(ser["expires_at"])
        restored = from_serializable(ser, EvolutionAuthorization)
        self.assertIsNone(restored.expires_at)

    def test_schedule_window_optional_datetimes_round_trip(self):
        """All ``datetime | None`` schedule fields deserialize correctly."""
        start = datetime(2026, 1, 1, 9, 0, 0)
        end = datetime(2026, 1, 1, 17, 0, 0)
        sched = EvolutionSchedule(
            scheduled_at=start,
            window_start=start,
            window_end=end,
            cooldown_until=start,
            expired_at=None,
        )
        ser = to_serializable(sched)
        restored = from_serializable(ser, EvolutionSchedule)
        self.assertIsInstance(restored.window_start, datetime)
        self.assertIsInstance(restored.window_end, datetime)
        self.assertIsInstance(restored.cooldown_until, datetime)
        self.assertIsNone(restored.expired_at)
        self.assertEqual(restored.window_start, start)
        self.assertEqual(restored.window_end, end)


if __name__ == "__main__":
    unittest.main()
