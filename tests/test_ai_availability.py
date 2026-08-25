"""Atlas Post-Core F10 - Provider availability & model-optional chain tests.

Covers:
  * ProviderAvailabilityTracker state derivation (UNKNOWN/HEALTHY/DEGRADED/
    OFFLINE) over bounded recent outcomes;
  * deterministic injected-clock behavior;
  * failure reasons reused from the existing classify_failure taxonomy;
  * bounded history (window maxlen);
  * JSON-safe snapshot contents;
  * observation-only wiring: no background monitoring, no forbidden imports;
  * ProviderHealthObserver PROVIDER-domain adaptation (duck-typed);
  * ONE composite model-off invariant: F7 -> F8 -> F9 preparation still works
    end-to-end with every optional AI/model assistance disabled.

Pure verification. No live network. No repository mutation.
"""

from __future__ import annotations

import ast
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from atlas.ai.availability import ProviderAvailabilityTracker
from atlas.evolution.development_cycle import DevelopmentNeed
from atlas.lifecycle.models import ComponentStatus

_REPO_ROOT = Path(__file__).resolve().parents[1]


class _FixedClock:
    """Deterministic UTC clock advancing by a fixed step per call."""

    def __init__(self, start: str = "2026-01-01T00:00:00+00:00", step_s: int = 1):
        self._t = datetime.fromisoformat(start)
        self._step = step_s

    def __call__(self) -> datetime:
        current = self._t
        self._t = datetime.fromtimestamp(
            self._t.timestamp() + self._step, tz=timezone.utc
        )
        return current


def make_tracker(**overrides) -> ProviderAvailabilityTracker:
    base = dict(name="test_provider", clock=_FixedClock())
    base.update(overrides)
    return ProviderAvailabilityTracker(**base)


class TestAvailabilityStates:
    def test_empty_history_is_unknown(self):
        tracker = make_tracker()
        assert tracker.status() is ComponentStatus.UNKNOWN

    def test_successes_only_is_healthy(self):
        tracker = make_tracker()
        tracker.record_success()
        tracker.record_success()
        assert tracker.status() is ComponentStatus.HEALTHY

    def test_mixed_outcomes_are_degraded(self):
        tracker = make_tracker()
        tracker.record_success()
        tracker.record_failure(reason="timeout")
        assert tracker.status() is ComponentStatus.DEGRADED

    def test_failures_only_are_offline(self):
        tracker = make_tracker()
        tracker.record_failure(reason="connection")
        tracker.record_failure(reason="rate_limited")
        assert tracker.status() is ComponentStatus.OFFLINE

    def test_recovery_via_bounded_window(self):
        tracker = make_tracker(window=3)
        tracker.record_failure(reason="timeout")
        tracker.record_failure(reason="timeout")
        assert tracker.status() is ComponentStatus.OFFLINE
        # Old failures age out of the bounded window -> healthy again.
        tracker.record_success()
        tracker.record_success()
        tracker.record_success()
        assert tracker.status() is ComponentStatus.HEALTHY


class TestFailureClassificationReuse:
    def test_timeout_exception_reuses_existing_taxonomy(self):
        tracker = make_tracker()
        tracker.record_failure(requests.Timeout("slow"))
        snapshot = tracker.snapshot()
        assert snapshot["failure_reasons"] == {"timeout": 1}
        assert snapshot["status"] == "OFFLINE"

    def test_rate_limit_exception_classified(self):
        class _FakeResponse:
            status_code = 429

        exc = requests.HTTPError("429")
        exc.response = _FakeResponse()
        tracker = make_tracker()
        tracker.record_failure(exc)
        assert "rate_limited" in tracker.snapshot()["failure_reasons"]

    def test_unknown_exception_recorded_conservatively(self):
        tracker = make_tracker()

        class WeirdError(Exception):
            pass

        tracker.record_failure(WeirdError("???"))
        assert tracker.status() is ComponentStatus.OFFLINE
        assert tracker.snapshot()["failure_reasons"] == {"unknown": 1}


class TestDeterminismAndBounds:
    def test_injected_clock_is_deterministic(self):
        clock = _FixedClock()
        tracker = make_tracker(clock=clock)
        tracker.record_success()
        first = tracker.snapshot()
        # observed_at is sampled at snapshot time (call #2 of the clock).
        assert first["observed_at"] == "2026-01-01T00:00:01+00:00"
        tracker.record_failure(reason="timeout")
        second = tracker.snapshot()
        assert second["observed_at"] == "2026-01-01T00:00:03+00:00"
        assert first["observed_at"] < second["observed_at"]

    def test_identical_sequences_yield_identical_snapshots(self):
        def build():
            tracker = make_tracker()
            for _ in range(3):
                tracker.record_success()
            tracker.record_failure(reason="timeout")
            return tracker

        a, b = build(), build()
        assert a.snapshot() == b.snapshot()
        assert a.status() is b.status()

    def test_history_is_bounded(self):
        tracker = make_tracker(window=4)
        for _ in range(50):
            tracker.record_success()
        snapshot = tracker.snapshot()
        assert snapshot["window"] == 4
        assert snapshot["window_max"] == 4
        assert snapshot["recent_successes"] == 4
        assert snapshot["recorded_total"] == 50

    def test_snapshot_is_json_safe_and_complete(self):
        tracker = make_tracker(name="prov")
        tracker.record_success()
        tracker.record_failure(requests.ConnectionError("down"))
        snapshot = tracker.snapshot()
        for key in (
            "name",
            "status",
            "window",
            "window_max",
            "recent_successes",
            "recent_failures",
            "failure_reasons",
            "recorded_total",
            "observed_at",
        ):
            assert key in snapshot
        encoded = json.dumps(snapshot)  # must not raise
        assert isinstance(encoded, str)

    def test_constructor_validation(self):
        import pytest

        with pytest.raises(ValueError):
            ProviderAvailabilityTracker(name="  ")
        with pytest.raises(ValueError):
            ProviderAvailabilityTracker(window=0)


_FORBIDDEN_MODULES = (
    "subprocess",
    "threading",
    "multiprocessing",
    "asyncio",
    "socket",
)


class TestArchitecturalGuards:
    def test_no_forbidden_imports(self):
        source = (_REPO_ROOT / "atlas/ai/availability.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source, filename="availability.py")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in _FORBIDDEN_MODULES, (
                        f"availability.py imports {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in _FORBIDDEN_MODULES, (
                    f"availability.py imports {node.module}"
                )

    def test_no_background_or_daemon_constructs(self):
        source = (_REPO_ROOT / "atlas/ai/availability.py").read_text(
            encoding="utf-8"
        )
        for forbidden in ("Thread(", "daemon", "async def", "Timer(", "EventBus"):
            assert forbidden not in source, f"availability.py uses {forbidden}"


class TestProviderHealthObserver:
    def test_adapts_tracker_into_provider_domain_state(self):
        from atlas.evolution.environment.models import EnvironmentDomain
        from atlas.evolution.environment.providers import ProviderHealthObserver

        tracker = make_tracker(name="prov")
        tracker.record_success()
        observer = ProviderHealthObserver(tracker)
        assert observer.provider_name() == "provider_health"

        states = observer.observe()
        assert len(states) == 1
        state = states[0]
        assert state.entity.domain is EnvironmentDomain.PROVIDER
        assert state.entity.entity_id == "prov"
        assert state.source == "provider_health"
        assert state.state["status"] == "HEALTHY"
        assert "name" not in state.state

    def test_duck_typed_tracker_accepted(self):
        from atlas.evolution.environment.providers import ProviderHealthObserver

        class DuckTracker:
            def snapshot(self):
                return {"name": "duck", "status": "UNKNOWN"}

        states = ProviderHealthObserver(DuckTracker()).observe()
        assert states[0].state["status"] == "UNKNOWN"


class TestModelOffCompositeChain:
    def test_f7_f8_f9_chain_works_with_ai_disabled(self):
        """The F10 invariant: with no model assistance anywhere, the
        deterministic F7 -> F8 -> F9 preparation chain still works and the
        availability tracker remains untouched (UNKNOWN)."""
        from atlas.kernel.atlas import Atlas

        tick_src = inspect.getsource(Atlas.tick)
        assert "run_operation_cycle" not in tick_src
        assert "run_information_acquisition" not in tick_src
        assert "run_development_cycle" not in tick_src
        assert "ai_availability" not in tick_src

        atlas = Atlas()
        try:
            atlas.start()

            # F7 — bounded operation cycle (deterministic; may be no-work).
            operation = atlas.run_operation_cycle()
            assert operation is not None
            assert operation.status in ("ok", "partial", "failed", "no_work")

            # F8 — bounded acquisition (deny-by-default web; no model).
            acquisition = atlas.run_information_acquisition(
                question="bounded research sources", query_id="f10comp1"
            )
            assert acquisition is not None
            assert acquisition.decision in ("research", "noop")

            # F9 — governed development preparation stops at approval.
            need = DevelopmentNeed(
                title="F10 composite preparation need",
                summary="Deterministic chain verification.",
                candidate_id="CAND-F10-001",
                evidence_change_ids=("CHG-F10-1",),
                metadata={
                    "code_changes": [
                        {"path": "docs/f10_note.md", "content": "# note\n"}
                    ],
                },
            )
            development = atlas.run_development_cycle(need)
            assert development.ok
            assert development.proposal_status == "PENDING_APPROVAL"

            # Availability untouched by the deterministic chain.
            snapshot = atlas.ai_availability.snapshot()
            assert snapshot["status"] == "UNKNOWN"
            assert snapshot["recorded_total"] == 0
        finally:
            atlas.shutdown()
        assert atlas.ai_availability is None