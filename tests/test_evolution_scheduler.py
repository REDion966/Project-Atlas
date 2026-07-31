"""
Phase 13.3 — Evolution Scheduler Tests.

Tests the EvolutionScheduler tick cycle, rate limiting, threshold
gating, concurrent cycle protection, and full analysis pipeline.

Tests use real evolution components (SelfObservationEngine,
ImprovementPlanner, ProposalGenerator, ApprovalManager,
EvolutionMemory) with no mocks for the core flow.

Pure logic tests. No AI. No infrastructure. No storage.
"""

import pytest
from datetime import datetime

from atlas.evolution.models import (
    Observation,
    ObservationCategory,
    ImprovementPriority,
)
from atlas.evolution.self_observation import SelfObservationEngine
from atlas.evolution.improvement_planner import ImprovementPlanner
from atlas.evolution.proposal_generator import ProposalGenerator
from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.scheduler import EvolutionScheduler, EvolutionSchedulerResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_observations(
    engine: SelfObservationEngine,
    count: int = 6,
) -> None:
    """Seed the observation engine with observations that trigger weaknesses.

    Each observation has avg_response_time_ms > 5000 and error_rate_percent
    > 10, which triggers the ImprovementPlanner's runtime weakness detection.
    """
    for i in range(count):
        obs = Observation(
            category=ObservationCategory.RUNTIME_METRICS,
            metric_name="runtime_summary",
            value={
                "avg_response_time_ms": 6000 + i * 500,
                "request_count": 100,
                "error_count": 12 + i,
                "error_rate_percent": 12.0 + i,
            },
            unit="composite",
            description=f"Observation {i} with declining metrics.",
            timestamp=datetime.now(),
            source="test",
        )
        engine.record_observation(obs)


# ---------------------------------------------------------------------------
# Test: EvolutionSchedulerResult
# ---------------------------------------------------------------------------


class TestEvolutionSchedulerResult:

    def test_default_values(self):
        """Default fields are set correctly."""
        result = EvolutionSchedulerResult(cycle_number=1)
        assert result.cycle_number == 1
        assert result.ran_analysis is False
        assert result.observation_count == 0
        assert result.weaknesses_detected == 0
        assert result.proposals_generated == 0
        assert result.proposals_stored == 0
        assert result.is_running is False
        assert isinstance(result.ran_at, datetime)

    def test_is_frozen(self):
        """Result is immutable after creation."""
        result = EvolutionSchedulerResult(cycle_number=1)
        with pytest.raises(AttributeError):
            result.cycle_number = 2  # type: ignore


# ---------------------------------------------------------------------------
# Test: EvolutionScheduler — Tick Cycle
# ---------------------------------------------------------------------------


class TestTickCycle:

    def test_tick_returns_none_on_non_analysis_tick(self):
        """tick() returns None when tick_counter is not at interval."""
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
            tick_interval=10,
            min_observations=1,
        )
        # First 9 ticks should return None (not at interval)
        for _ in range(9):
            result = scheduler.tick()
            assert result is None
        assert scheduler.tick_counter == 9

    def test_analysis_runs_at_interval(self):
        """Analysis runs on the tick_interval-th tick."""
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
            tick_interval=5,
            min_observations=1,
        )
        # Seed observations
        _seed_observations(scheduler._observation_engine, count=6)

        # Tick 5 should trigger analysis
        for _ in range(4):
            scheduler.tick()
        result = scheduler.tick()
        assert result is not None
        assert result.cycle_number == 1
        assert result.ran_analysis is True

    def test_observation_count_tracked(self):
        """Result includes observation count."""
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
            tick_interval=1,  # Run every tick
            min_observations=1,
        )
        _seed_observations(scheduler._observation_engine, count=3)

        result = scheduler.tick()
        assert result is not None
        assert result.observation_count >= 3

    def test_properties_accessible(self):
        """Properties return correct values."""
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
        )
        assert scheduler.total_cycles == 0
        assert scheduler.last_result is None
        assert scheduler.running is False


# ---------------------------------------------------------------------------
# Test: EvolutionScheduler — Threshold Gating
# ---------------------------------------------------------------------------


class TestThresholdGating:

    def test_not_enough_observations_skips_analysis(self):
        """Analysis is skipped when below min_observations threshold."""
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
            tick_interval=1,
            min_observations=10,
        )
        _seed_observations(scheduler._observation_engine, count=3)

        result = scheduler.tick()
        assert result is not None
        assert result.ran_analysis is False
        assert result.observation_count == 3

    def test_threshold_met_runs_analysis(self):
        """Analysis runs when observation count meets threshold."""
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
            tick_interval=1,
            min_observations=3,
        )
        _seed_observations(scheduler._observation_engine, count=5)

        result = scheduler.tick()
        assert result is not None
        assert result.ran_analysis is True

    def test_reset_threshold_syncs_counter(self):
        """reset_threshold() synchronises the observation counter."""
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
            tick_interval=1,
            min_observations=5,
        )
        _seed_observations(scheduler._observation_engine, count=7)
        scheduler.reset_threshold()

        # Now threshold is at 7, so no new observations → skip
        result = scheduler.tick()
        assert result is not None
        assert result.ran_analysis is False


# ---------------------------------------------------------------------------
# Test: EvolutionScheduler — Concurrent Cycle Protection
# ---------------------------------------------------------------------------


class TestConcurrentCycleGuard:

    def test_concurrent_tick_returns_is_running(self):
        """A tick while already running returns is_running=True."""
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
            tick_interval=1,
            min_observations=1,
        )
        _seed_observations(scheduler._observation_engine, count=3)

        # Manually set running flag
        scheduler._running = True
        result = scheduler.tick()
        assert result is not None
        assert result.is_running is True
        assert result.ran_analysis is False


# ---------------------------------------------------------------------------
# Test: EvolutionScheduler — Full Analysis Pipeline
# ---------------------------------------------------------------------------


class TestFullAnalysisPipeline:

    def test_weaknesses_detected_and_proposals_created(self):
        """Full pipeline: observations → weaknesses → proposals → stored."""
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
            tick_interval=1,
            min_observations=1,
        )
        _seed_observations(scheduler._observation_engine, count=6)

        result = scheduler.tick()
        assert result is not None
        assert result.ran_analysis is True
        assert result.weaknesses_detected >= 1
        assert result.proposals_generated >= 1
        assert result.proposals_stored >= 1

    def test_proposals_stored_in_memory(self):
        """Proposals generated by the scheduler are stored in EvolutionMemory."""
        memory = EvolutionMemory()
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=memory,
            tick_interval=1,
            min_observations=1,
        )
        _seed_observations(scheduler._observation_engine, count=6)

        scheduler.tick()
        assert memory.proposal_count >= 1
        assert memory.approval_request_count >= 1

    def test_last_result_stored(self):
        """last_result is updated after each tick cycle."""
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
            tick_interval=1,
            min_observations=1,
        )
        _seed_observations(scheduler._observation_engine, count=6)

        assert scheduler.last_result is None
        scheduler.tick()
        assert scheduler.last_result is not None
        assert scheduler.last_result.cycle_number == 1

    def test_multiple_cycles_increment_counter(self):
        """total_cycles increments across multiple analysis runs."""
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
            tick_interval=1,
            min_observations=1,
        )
        _seed_observations(scheduler._observation_engine, count=10)

        # First analysis cycle
        scheduler.tick()
        assert scheduler.total_cycles == 1

        # Second analysis cycle (more observations since last)
        scheduler._last_observation_count = 0  # Reset to simulate new data
        scheduler.tick()
        assert scheduler.total_cycles == 2


# ---------------------------------------------------------------------------
# Test: EvolutionScheduler — Reset
# ---------------------------------------------------------------------------


class TestReset:

    def test_reset_clears_all_state(self):
        """reset() clears counters and guards."""
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
            tick_interval=1,
            min_observations=1,
        )
        _seed_observations(scheduler._observation_engine, count=3)
        scheduler.tick()

        scheduler.reset()
        assert scheduler.tick_counter == 0
        assert scheduler.total_cycles == 0
        assert scheduler.running is False
        assert scheduler.last_result is None


# ---------------------------------------------------------------------------
# Test: EvolutionScheduler — No Weaknesses (Healthy System)
# ---------------------------------------------------------------------------


class TestHealthySystem:

    def test_no_weaknesses_returns_zero_detected(self):
        """Healthy observations produce no weaknesses."""
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
            tick_interval=1,
            min_observations=1,
        )
        now = datetime.now()
        # Record healthy observations only
        for i in range(6):
            obs = Observation(
                category=ObservationCategory.RUNTIME_METRICS,
                metric_name="runtime_summary",
                value={
                    "avg_response_time_ms": 500,
                    "request_count": 100,
                    "error_count": 1,
                    "error_rate_percent": 1.0,
                },
                unit="composite",
                description=f"Healthy observation {i}.",
                timestamp=now,
                source="test",
            )
            scheduler._observation_engine.record_observation(obs)

        result = scheduler.tick()
        assert result is not None
        assert result.ran_analysis is True
        assert result.weaknesses_detected == 0
        assert result.proposals_generated == 0


# ---------------------------------------------------------------------------
# Test: EvolutionScheduler — Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:

    def test_tick_clears_running_flag_on_error(self):
        """The running flag is always cleared even if analysis raises."""
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
            tick_interval=1,
            min_observations=1,
        )
        _seed_observations(scheduler._observation_engine, count=3)

        # Simulate an error in _run_analysis
        original = scheduler._run_analysis

        def broken_run():
            raise RuntimeError("Simulated failure")

        scheduler._run_analysis = broken_run  # type: ignore
        try:
            with pytest.raises(RuntimeError):
                scheduler.tick()
        finally:
            scheduler._run_analysis = original  # type: ignore

        # Running flag should be cleared
        assert scheduler.running is False


# ---------------------------------------------------------------------------
# Test: EvolutionScheduler — Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:

    def test_tick_while_never_having_observations(self):
        """tick() handles empty observation engine gracefully."""
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
            tick_interval=1,
            min_observations=1,
        )
        # No observations recorded
        result = scheduler.tick()
        assert result is not None
        assert result.ran_analysis is False

    def test_tick_interval_of_one(self):
        """tick_interval=1 runs analysis on every tick."""
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
            tick_interval=1,
            min_observations=1,
        )
        _seed_observations(scheduler._observation_engine, count=3)

        # Every tick should return a result with tick_counter incrementing
        result1 = scheduler.tick()
        assert result1 is not None
        assert scheduler.tick_counter == 1

        scheduler._last_observation_count = 0
        result2 = scheduler.tick()
        assert result2 is not None
        assert scheduler.tick_counter == 2

    def test_tick_interval_minimum_one(self):
        """tick_interval below 1 is clamped to 1."""
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
            tick_interval=0,  # Invalid
            min_observations=0,  # Invalid
        )
        assert scheduler._tick_interval == 1
        assert scheduler._min_observations == 1
