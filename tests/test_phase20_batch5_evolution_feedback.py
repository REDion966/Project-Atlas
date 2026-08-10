"""
Phase 20 Batch 5 — Governed Evolution feedback closure.

Tests proving the EvolutionScheduler activates
EvolutionIntelligenceEngine.analyze_all() inside the real evolution
runtime path:

  A. A scheduler with an injected fake/spy intelligence engine invokes
     analyze_all() during the appropriate analysis lifecycle.
  B. The invocation occurs after relevant evolution execution state is
     available (threshold gate passed).
  C. Existing scheduler behavior remains intact.
  D. Missing/None intelligence engine remains fail-soft.
  E. Insights produced by analyze_all() flow into the existing
     insight-aware planning path (not bypassed or duplicated).

Deterministic fakes/spies only. No real external model providers.
"""

from datetime import datetime

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.improvement_planner import ImprovementPlanner
from atlas.evolution.models import (
    EvolutionInsight,
    EvolutionProposal,
    EvolutionRecord,
    ImprovementPlan,
    ImprovementPriority,
    Observation,
    ObservationCategory,
    ProposalStatus,
)
from atlas.evolution.proposal_generator import ProposalGenerator
from atlas.evolution.scheduler import EvolutionScheduler
from atlas.evolution.self_observation import SelfObservationEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_observations(
    engine: SelfObservationEngine,
    count: int = 6,
) -> None:
    """Seed the observation engine with observations that trigger weaknesses."""
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


class SpyIntelligenceEngine:
    """Spy that records lifecycle calls and returns fixed insights."""

    def __init__(self, insights=None):
        self.calls: list[str] = []
        self._insights = insights if insights is not None else []

    def analyze_all(self):
        self.calls.append("analyze_all")
        return list(self._insights)

    def get_insights(self):
        self.calls.append("get_insights")
        return list(self._insights)


def _make_real_insight(
    proposal_id: str = "PROP-1",
    title: str = "Improve Runtime Performance",
) -> EvolutionInsight:
    """Create a deterministic EvolutionInsight for planner consumption."""
    return EvolutionInsight(
        insight_id="INS-1",
        proposal_id=proposal_id,
        execution_record_id="EVR-1",
        tracked_goal_id="TRK-1",
        outcome="success",
        confidence=0.8,
        effectiveness_score=0.85,
        evidence_summary="Improvement succeeded.",
        evidence_count=5,
        evidence_quality=0.8,
        regression_risk=0.1,
        analyzed_at=datetime.now(),
        proposal_title=title,
        proposal_summary=title,
    )


def _make_scheduler(
    intelligence_engine,
    memory: EvolutionMemory | None = None,
    observation_engine: SelfObservationEngine | None = None,
    tick_interval: int = 1,
    min_observations: int = 1,
) -> EvolutionScheduler:
    """Create a scheduler wired with the given intelligence engine."""
    return EvolutionScheduler(
        observation_engine=observation_engine or SelfObservationEngine(),
        improvement_planner=ImprovementPlanner(),
        proposal_generator=ProposalGenerator(),
        approval_manager=ApprovalManager(),
        evolution_memory=memory or EvolutionMemory(),
        intelligence_engine=intelligence_engine,
        tick_interval=tick_interval,
        min_observations=min_observations,
    )


# ---------------------------------------------------------------------------
# A: analyze_all() invoked during the analysis lifecycle
# ---------------------------------------------------------------------------


class TestAnalyzeAllInvocation:

    def test_analyze_all_invoked_during_analysis(self):
        """An analysis cycle calls analyze_all() exactly once."""
        spy = SpyIntelligenceEngine()
        scheduler = _make_scheduler(spy)
        _seed_observations(scheduler._observation_engine, count=6)

        scheduler.tick()

        assert spy.calls.count("analyze_all") == 1

    def test_analyze_all_only_on_analysis_tick(self):
        """analyze_all is not called on non-analysis ticks."""
        spy = SpyIntelligenceEngine()
        scheduler = _make_scheduler(spy, tick_interval=2)
        _seed_observations(scheduler._observation_engine, count=6)

        # Tick 1: not an analysis tick.
        scheduler.tick()
        assert spy.calls == []

        # Tick 2: analysis tick → analyze_all then get_insights.
        scheduler.tick()
        assert spy.calls == ["analyze_all", "get_insights"]

    def test_analyze_all_not_called_below_threshold(self):
        """Threshold gating prevents analyze_all when observations are few."""
        spy = SpyIntelligenceEngine()
        scheduler = _make_scheduler(spy, min_observations=10)
        _seed_observations(scheduler._observation_engine, count=3)

        scheduler.tick()

        assert spy.calls == []

    def test_analyze_all_precedes_get_insights(self):
        """analyze_all runs before the existing get_insights() read."""
        spy = SpyIntelligenceEngine()
        scheduler = _make_scheduler(spy)
        _seed_observations(scheduler._observation_engine, count=6)

        scheduler.tick()

        assert spy.calls == ["analyze_all", "get_insights"]


# ---------------------------------------------------------------------------
# B: invocation occurs after relevant execution state is available
# ---------------------------------------------------------------------------


class TestExecutionStateAvailable:

    def test_analyze_all_runs_with_executed_proposal_state(self):
        """The scheduler invokes analyze_all() only after the threshold gate
        passes; executed proposals (IMPLEMENTED + execution record) already in
        EvolutionMemory are available to the intelligence engine."""
        memory = EvolutionMemory()
        plan = ImprovementPlan(
            plan_id="IMP-1",
            title="Test Plan",
            description="A test improvement plan",
            priority=ImprovementPriority.LOW,
        )
        proposal = EvolutionProposal(
            proposal_id="PROP-1",
            title="Runtime Improvement",
            summary="Summary",
            rationale="Rationale",
            expected_benefit="Benefit",
            risks="Risks",
            impact_analysis="Impact",
            implementation_approach="Approach",
            plan=plan,
            status=ProposalStatus.IMPLEMENTED,
        )
        memory.store_proposal(proposal)
        memory.store_record(EvolutionRecord(
            record_id="EVR-1",
            event_type="execution",
            description="Executed",
            related_ids=["PROP-1"],
        ))

        spy = SpyIntelligenceEngine()
        scheduler = _make_scheduler(spy, memory=memory)
        _seed_observations(scheduler._observation_engine, count=6)

        scheduler.tick()

        # analyze_all runs on the real cycle with the executed state present.
        assert spy.calls.count("analyze_all") == 1
        # The pre-seeded executed proposal remains intact (the scheduler
        # does not bypass or drop it). proposal_count is 2 because the
        # normal analysis cycle also generates and stores its own proposal
        # from the seeded observations (existing behavior intact).
        assert memory.get_proposal("PROP-1") is not None
        assert memory.get_proposal("PROP-1").status == ProposalStatus.IMPLEMENTED
        assert memory.proposal_count == 2
        assert memory.record_count == 1


# ---------------------------------------------------------------------------
# C: existing scheduler behavior remains intact
# ---------------------------------------------------------------------------


class TestExistingBehaviorIntact:

    def test_full_pipeline_still_runs_with_intelligence_engine(self):
        """Proposals and approval requests are still generated and stored."""
        spy = SpyIntelligenceEngine()
        memory = EvolutionMemory()
        scheduler = _make_scheduler(spy, memory=memory)
        _seed_observations(scheduler._observation_engine, count=6)

        result = scheduler.tick()

        assert result is not None
        assert result.ran_analysis is True
        assert result.weaknesses_detected >= 1
        assert result.proposals_generated >= 1
        assert result.proposals_stored >= 1
        assert memory.proposal_count >= 1
        assert memory.approval_request_count >= 1

    def test_analyze_all_exception_is_swallowed(self):
        """A failing analyze_all must not break the scheduler cycle."""

        class BrokenEngine(SpyIntelligenceEngine):
            def analyze_all(self):
                self.calls.append("analyze_all")
                raise RuntimeError("simulated failure")

        spy = BrokenEngine()
        memory = EvolutionMemory()
        scheduler = _make_scheduler(spy, memory=memory)
        _seed_observations(scheduler._observation_engine, count=6)

        result = scheduler.tick()

        assert result is not None
        assert result.ran_analysis is True
        assert result.proposals_generated >= 1


# ---------------------------------------------------------------------------
# D: missing/None intelligence engine stays fail-soft
# ---------------------------------------------------------------------------


class TestMissingEngineFailSoft:

    def test_none_intelligence_engine_keeps_existing_behavior(self):
        """Without an intelligence engine, analysis still runs normally."""
        scheduler = _make_scheduler(None)
        _seed_observations(scheduler._observation_engine, count=6)

        result = scheduler.tick()

        assert result is not None
        assert result.ran_analysis is True
        assert result.proposals_generated >= 1


# ---------------------------------------------------------------------------
# E: evolution insight behavior is not bypassed or duplicated
# ---------------------------------------------------------------------------


class TestNotBypassedOrDuplicated:

    def test_insights_flow_to_planner_once_per_cycle(self):
        """get_insights output is passed into the planner; analyze_all is
        called exactly once per analysis cycle (no duplication)."""
        seen: list = []

        class RecordingPlanner(ImprovementPlanner):
            def detect_weaknesses(self, observations, insights=None, planning_context=None):
                seen.append(insights)
                return super().detect_weaknesses(
                    observations,
                    insights=insights,
                    planning_context=planning_context,
                )

        insight = _make_real_insight()
        spy = SpyIntelligenceEngine(insights=[insight])
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=RecordingPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
            intelligence_engine=spy,
            tick_interval=1,
            min_observations=1,
        )
        _seed_observations(scheduler._observation_engine, count=6)

        scheduler.tick()

        # One analyze_all per cycle, one planner consumption of the results.
        assert spy.calls.count("analyze_all") == 1
        assert len(seen) == 1
        assert seen[0] == [insight]

    def test_second_cycle_records_second_analyze_all(self):
        """Each analysis cycle triggers its own analyze_all invocation."""
        spy = SpyIntelligenceEngine()
        scheduler = _make_scheduler(spy)
        _seed_observations(scheduler._observation_engine, count=6)

        scheduler.tick()
        scheduler._last_observation_count = 0  # simulate new data
        scheduler.tick()

        assert spy.calls.count("analyze_all") == 2


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
