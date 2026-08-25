"""Atlas Post-Core F11 — Long-Term Self-Management & Recovery tests.

Covers:
  * SelfManagementReview: deterministic bounded reports over durable
    evidence (evolution records, learning signals, request queues, F10
    availability, lifecycle components);
  * stale-authorization / failure-streak / degraded-offline detection;
  * evidence IDs and provenance; bounded needs;
  * empty-store behavior; malformed-input fail-closed behavior;
  * read-only guarantees (source stores never mutated);
  * architecture guards (no atlas.ai/subprocess/threading/asyncio imports,
    no daemon constructs, no approve/reject/authorize/execute/apply/promote);
  * kernel bridge behavior + tick untouched;
  * boot-activation wiring: staged config survives restart and activates at
    startup through the EXISTING BootActivationService over real
    AutonomySQLiteStorage; integrity failure exposes SAFE_MODE.

Pure verification. No live network. No repository mutation.
"""

from __future__ import annotations

import ast
import inspect
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from atlas.ai.availability import ProviderAvailabilityTracker
from atlas.evolution.self_management import (
    MaintenanceNeed,
    SelfManagementPolicy,
    SelfManagementReport,
    SelfManagementReview,
)
from atlas.lifecycle.models import ComponentStatus

_REPO_ROOT = Path(__file__).resolve().parents[1]
_NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _clock():
    return _NOW


@dataclass
class FakeRecord:
    record_id: str
    event_type: str = "operation_cycle"
    description: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class FakeRequest:
    request_id: str
    created_at: datetime | None = None


@dataclass
class FakeComponent:
    name: str
    status: ComponentStatus


def make_review(**overrides) -> SelfManagementReview:
    base = dict(clock=_clock)
    base.update(overrides)
    return SelfManagementReview(**base)


def records_store(records):
    store = MagicMock()
    store.get_records.return_value = list(records)
    return store


class TestDeterministicReport:
    def test_empty_stores_produce_clean_report(self):
        report = make_review().run_review()
        assert report.ok
        assert report.decision == "reviewed"
        assert report.outcome_trend == {}
        assert report.failure_streak == 0
        assert report.needs == ()
        assert json.dumps(report.to_dict())  # JSON-safe

    def test_identical_inputs_and_clock_yield_identical_reports(self):
        records = [
            FakeRecord(f"R{i}", metadata={"failures": [("s", "e")]})
            for i in range(3)
        ]

        def build():
            return make_review(
                evolution_memory=records_store(records),
                schedule_store=MagicMock(pending_authorization=lambda: []),
            ).run_review()

        a, b = build(), build()
        # elapsed_seconds is wall-clock noise; everything else must match.
        strip = lambda r: {k: v for k, v in r.to_dict().items() if k != "elapsed_seconds"}
        assert strip(a) == strip(b)

    def test_outcome_trend_counts_event_types(self):
        records = [
            FakeRecord("A", event_type="operation_cycle"),
            FakeRecord("B", event_type="operation_cycle"),
            FakeRecord("C", event_type="adaptation_cycle"),
        ]
        report = make_review(evolution_memory=records_store(records)).run_review()
        assert report.outcome_trend == {
            "operation_cycle": 2,
            "adaptation_cycle": 1,
        }

    def test_bounded_history_window(self):
        policy = SelfManagementPolicy(max_records=2)
        records = [FakeRecord(f"R{i}") for i in range(50)]
        store = MagicMock()
        store.get_records.side_effect = (
            lambda n=50: list(reversed(records))[:n]
        )
        report = make_review(
            evolution_memory=store, policy=policy
        ).run_review()
        # Only the bounded window is aggregated.
        assert sum(report.outcome_trend.values()) == 2


class TestDetection:
    def test_failure_streak_detection_and_need(self):
        failures = [
            FakeRecord(
                f"F{i}",
                metadata={"decision": "FAILURE_LIMIT", "failures": [("s", "e")]},
            )
            for i in range(4)
        ]
        report = make_review(evolution_memory=records_store(failures)).run_review()
        assert report.failure_streak == 4
        kinds = [n.kind for n in report.needs]
        assert "investigate_recurring_failures" in kinds
        need = next(n for n in report.needs if n.kind == "investigate_recurring_failures")
        assert len(need.evidence_ids) == 4
        assert all(eid.startswith("F") for eid in need.evidence_ids)

    def test_no_streak_when_successes_intervene(self):
        records = [
            FakeRecord("F0", metadata={"failures": [("s", "e")]}),
            FakeRecord("OK0"),
            FakeRecord("F1", metadata={"failures": [("s", "e")]}),
        ]
        report = make_review(evolution_memory=records_store(records)).run_review()
        assert report.failure_streak == 1
        assert all(
            n.kind != "investigate_recurring_failures" for n in report.needs
        )

    def test_stale_authorization_detection(self):
        old_request = FakeRequest(
            "REQ-OLD", created_at=_NOW - timedelta(hours=48)
        )
        fresh_request = FakeRequest(
            "REQ-NEW", created_at=_NOW - timedelta(minutes=5)
        )
        schedule = MagicMock(pending_authorization=lambda: [old_request, fresh_request])
        report = make_review(schedule_store=schedule).run_review()

        assert report.stale_authorization_count == 1
        assert report.stale_authorization_ids == ("REQ-OLD",)
        need = next(n for n in report.needs if n.kind == "review_stale_authorizations")
        assert need.evidence_ids == ("REQ-OLD",)

    def test_degraded_and_offline_components_detected(self):
        components = [
            FakeComponent("alpha", ComponentStatus.HEALTHY),
            FakeComponent("beta", ComponentStatus.DEGRADED),
            FakeComponent("gamma", ComponentStatus.OFFLINE),
        ]
        report = make_review(components=components).run_review()
        assert report.degraded_components == ("beta",)
        assert report.offline_components == ("gamma",)
        kinds = [n.kind for n in report.needs]
        assert "restore_offline_components" in kinds
        assert "investigate_degraded_components" in kinds

    def test_availability_offline_flagged(self):
        real = ProviderAvailabilityTracker(name="ai_provider", clock=_clock)
        real.record_failure(requests_timeout())
        report = make_review(availability=real).run_review()

        assert report.availability_status == "OFFLINE"
        assert any(
            n.kind == "investigate_provider_availability" for n in report.needs
        )


def requests_timeout():
    import requests

    return requests.Timeout("slow provider")


class TestFailClosedAndReadOnly:
    def test_malformed_policy_fails_closed(self):
        with pytest.raises(ValueError):
            SelfManagementReview(policy="not-a-policy")

    def test_malformed_clock_fails_closed(self):
        with pytest.raises(ValueError):
            SelfManagementReview(clock="not-callable")

    def test_source_failure_is_recorded_not_raised(self):
        broken = MagicMock()
        broken.get_records.side_effect = RuntimeError("store exploded")
        report = make_review(evolution_memory=broken).run_review()
        assert report.ok  # review completes
        assert ("evolution_memory", "store exploded") in report.source_errors

    def test_bounded_needs(self):
        policy = SelfManagementPolicy(max_needs=1, failure_streak_threshold=1)
        records = [
            FakeRecord(
                f"F{i}",
                metadata={"failures": [("s", "e")]},
            )
            for i in range(5)
        ]
        components = [
            FakeComponent(f"comp{i}", ComponentStatus.OFFLINE) for i in range(5)
        ]
        schedule = MagicMock(pending_authorization=lambda: [])
        report = make_review(
            evolution_memory=records_store(records),
            components=components,
            schedule_store=schedule,
            policy=policy,
        ).run_review()
        assert len(report.needs) <= 1

    def test_source_stores_are_never_mutated(self):
        memory = MagicMock()
        memory.get_records.return_value = [FakeRecord("R1")]
        learning = MagicMock()
        learning.get_insights.return_value = []
        learning.get_failures.return_value = []
        schedule = MagicMock(pending_authorization=lambda: [])
        availability = MagicMock(snapshot=lambda: {"status": "UNKNOWN"})

        make_review(
            evolution_memory=memory,
            learning_memory=learning,
            schedule_store=schedule,
            availability=availability,
        ).run_review()

        for store in (memory, learning, schedule, availability):
            for name in dir(store):
                if name.startswith(("store_", "save_", "create_", "delete_")):
                    getattr(store, name).assert_not_called()


_FORBIDDEN_MODULES = (
    "atlas.ai",
    "subprocess",
    "threading",
    "multiprocessing",
    "asyncio",
)

_FORBIDDEN_CALLS = (
    "approve",
    "reject",
    "authorize",
    "execute",
    "apply",
    "promote",
    "schedule_request",
    "rollback",
)


class TestArchitecturalGuards:
    def _tree(self):
        source = (_REPO_ROOT / "atlas/evolution/self_management.py").read_text(
            encoding="utf-8"
        )
        return ast.parse(source, filename="self_management.py")

    def test_no_forbidden_imports(self):
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(
                        alias.name == p or alias.name.startswith(p + ".")
                        for p in _FORBIDDEN_MODULES
                    ), f"F11 imports {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not any(
                    node.module == p or node.module.startswith(p + ".")
                    for p in _FORBIDDEN_MODULES
                ), f"F11 imports {node.module}"

    def test_no_governance_or_execution_calls(self):
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "attr", getattr(func, "id", ""))
                assert name not in _FORBIDDEN_CALLS, f"F11 calls {name}()"

    def test_no_background_or_daemon_constructs(self):
        source = (_REPO_ROOT / "atlas/evolution/self_management.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "Thread(",
            "daemon",
            "async def",
            "Timer(",
        ):
            assert forbidden not in source, f"self_management.py uses {forbidden}"


class TestBootActivationWiring:
    """Restart/recovery wiring over REAL AutonomySQLiteStorage (tmp path)."""

    def _make_storage(self, tmp_path: Path, name: str) -> Any:
        from atlas.storage.autonomy_storage import AutonomySQLiteStorage

        storage = AutonomySQLiteStorage(db_path=tmp_path / f"{name}.db")
        storage.initialize()
        return storage

    def _make_request(self, request_id: str, with_snapshot: bool = True):
        from atlas.evolution.autonomy.models import (
            ChangeReceipt,
            EvolutionRequest,
            EvolutionRequestStatus,
            RollbackPlan,
            RollbackStrategy,
            ScopeType,
        )

        return EvolutionRequest(
            request_id=request_id,
            source="test",
            target_scope=ScopeType.CONFIG,
            change_payload={
                "entries": [{"key": "logging.level", "value": "DEBUG"}]
            },
            status=EvolutionRequestStatus.PENDING_EFFECTIVE,
            receipt=ChangeReceipt(
                request_id=request_id,
                changed_keys=["logging.level"],
                target_tags=["config"],
            ),
            rollback=(
                RollbackPlan(
                    strategy=RollbackStrategy.SNAPSHOT,
                    snapshot_ref=f"snap-{request_id}",
                )
                if with_snapshot
                else None
            ),
        )

    def _stage_entry(self, storage: Any, request_id: str) -> None:
        from atlas.evolution.autonomy.models import StagedConfigEntry

        storage.store_request(self._make_request(request_id))
        storage.store_staged_config(
            StagedConfigEntry(
                entry_id=f"entry-{request_id}",
                request_id=request_id,
                key="logging.level",
                value="DEBUG",
                activated_at=None,
                applied_at=_NOW.replace(tzinfo=None),
            )
        )

    def test_restart_activates_staged_config_and_completes_request(
        self, tmp_path
    ):
        from atlas.evolution.autonomy.models import EvolutionRequestStatus
        from atlas.kernel.autonomy_wiring import init_boot_activation

        # First session: stage a config change, then "crash".
        first = self._make_storage(tmp_path, "restart")
        self._stage_entry(first, "REQ-F11-1")

        # Second session ("restart"): boot activation activates + verifies.
        second = self._make_storage(tmp_path, "restart")
        # Rollback snapshot captured by the first session (D8 mandatory).
        second.store_snapshot(
            "snap-REQ-F11-1",
            "REQ-F11-1",
            {"domain": "config"},
            checksum="test-checksum",
            created_at=_NOW.replace(tzinfo=None).isoformat(),
        )
        overlay: dict = {}
        service = init_boot_activation(storage=second, config_overlay=overlay)

        integrity = service.check_integrity()
        assert not integrity.safe_mode
        report = service.activate_staged_configs()

        assert report.completed_request_ids == ["REQ-F11-1"]
        request = second.load_request("REQ-F11-1")
        assert request.status is EvolutionRequestStatus.COMPLETED
        # The session overlay received the activated value.
        assert overlay.get("logging.level") == "DEBUG"

    def test_no_duplicate_activation_on_second_boot(self, tmp_path):
        from atlas.kernel.autonomy_wiring import init_boot_activation

        first = self._make_storage(tmp_path, "dup")
        self._stage_entry(first, "REQ-DUP")
        first.store_snapshot(
            "snap-REQ-DUP",
            "REQ-DUP",
            {"domain": "config"},
            checksum="test-checksum",
            created_at=_NOW.replace(tzinfo=None).isoformat(),
        )

        second = self._make_storage(tmp_path, "dup")
        service_a = init_boot_activation(
            storage=second, config_overlay={}, clock=lambda: _NOW.replace(tzinfo=None)
        )
        service_a.activate_staged_configs()

        third = self._make_storage(tmp_path, "dup")
        service_b = init_boot_activation(
            storage=third, config_overlay={}, clock=lambda: _NOW.replace(tzinfo=None)
        )
        report_b = service_b.activate_staged_configs()
        # F11 guarantee: repeated boots NEVER duplicate the activation write.
        # (Re-verification of an already-activated entry happens exactly once
        # per boot; the durable entry keeps its original activation marker.)
        entries = third.load_staged_configs()
        assert len(entries) == 1
        assert entries[0].entry_id == "entry-REQ-DUP"
        assert entries[0].activated_at is not None
        reverified = [
            r for r in report_b.activations if r.entry_id == "entry-REQ-DUP"
        ]
        assert len(reverified) == 1

    def test_corrupted_entry_exposes_safe_mode_and_suppresses_dispatch(
        self, tmp_path, monkeypatch
    ):
        """SAFE_MODE narrows capabilities only: base config is used, the
        governed dispatcher is not wired, and nothing else changes."""
        from atlas.evolution.autonomy.models import AutonomyPolicy, StagedConfigEntry
        from atlas.evolution.autonomy.schedule_store import ScheduleStore
        from atlas.storage.autonomy_storage import AutonomySQLiteStorage

        storage = AutonomySQLiteStorage(db_path=tmp_path / "safe.db")
        storage.initialize()
        storage.store_request(self._make_request("REQ-BAD", with_snapshot=False))
        storage.store_staged_config(
            StagedConfigEntry(
                entry_id="entry-REQ-BAD",
                request_id="REQ-BAD",
                key="logging.level",
                value="DEBUG",
                activated_at=None,
                applied_at=_NOW.replace(tzinfo=None),
            )
        )
        schedule_store = ScheduleStore(storage=storage, policy=AutonomyPolicy())

        def fake_persistence(event_bus):
            return storage, schedule_store

        monkeypatch.setattr(
            "atlas.kernel.atlas.init_autonomy_persistence", fake_persistence
        )
        dispatcher_calls: list[Any] = []
        monkeypatch.setattr(
            "atlas.kernel.atlas.init_autonomy_dispatcher",
            lambda **kwargs: dispatcher_calls.append(kwargs) or MagicMock(),
        )

        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            assert atlas.boot_safe_mode is True
            assert atlas.boot_report.safe_mode_reason
            # Autonomous advancement suppressed for the session.
            assert atlas._autonomy_dispatcher is None  # noqa: SLF001
            assert dispatcher_calls == []
            # The review still works in SAFE_MODE (read-only evidence).
            report = atlas.run_self_management_review()
            assert report.ok
        finally:
            atlas.shutdown()


class TestKernelBridge:
    def test_bridge_review_and_tick_untouched(self):
        from atlas.kernel.atlas import Atlas

        tick_src = inspect.getsource(Atlas.tick)
        assert "run_self_management_review" not in tick_src
        assert "self_management_review" not in tick_src

        atlas = Atlas()
        try:
            atlas.start()
            report = atlas.run_self_management_review()
            assert report is not None
            assert report.ok
            assert report.review_id == "SMR-000001"
            assert json.dumps(report.to_dict())
            assert atlas.self_management_review is not None
        finally:
            atlas.shutdown()
        assert atlas.self_management_review is None

    def test_bridge_fail_closed_before_start(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        with pytest.raises(RuntimeError):
            atlas.run_self_management_review()

    def test_boot_wiring_present_after_start(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            # Boot activation ran once; a clean tree boots without SAFE_MODE.
            assert atlas.boot_activation is not None
            assert atlas.boot_report is not None
            assert atlas.boot_safe_mode is False
        finally:
            atlas.shutdown()