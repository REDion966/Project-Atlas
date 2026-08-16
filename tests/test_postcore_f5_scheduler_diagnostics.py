"""Post-Core F5 — Scheduler fail-soft diagnostics.

Verifies the minimal observable scheduler error state added for the
remaining F5 gap: the evolution insight / decision intelligence /
knowledge pipeline integrations stay fail-soft (best-effort), but the
most recent integration error is now observable via
``EvolutionSchedulerResult.last_error`` and ``EvolutionScheduler.last_error``.

No failure record type, no logging framework, no governance change:
diagnostics only, fail-soft semantics unchanged.
"""

from datetime import datetime

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.improvement_planner import ImprovementPlanner
from atlas.evolution.models import Observation, ObservationCategory
from atlas.evolution.proposal_generator import ProposalGenerator
from atlas.evolution.scheduler import EvolutionScheduler, EvolutionSchedulerResult
from atlas.evolution.self_observation import SelfObservationEngine


def _seed_observations(engine: SelfObservationEngine, count: int = 6) -> None:
    """Seed observations that trigger the planner's runtime weakness."""
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


def make_scheduler(
    intelligence_engine=None,
    knowledge_pipeline=None,
    decision_intelligence=None,
    min_observations: int = 1,
    observation_engine=None,
) -> EvolutionScheduler:
    """Build a scheduler with real components and optional fakes."""
    return EvolutionScheduler(
        observation_engine=observation_engine or SelfObservationEngine(),
        improvement_planner=ImprovementPlanner(),
        proposal_generator=ProposalGenerator(),
        approval_manager=ApprovalManager(),
        evolution_memory=EvolutionMemory(),
        intelligence_engine=intelligence_engine,
        knowledge_pipeline=knowledge_pipeline,
        decision_intelligence=decision_intelligence,
        tick_interval=1,
        min_observations=min_observations,
    )


class FailingAnalyzeAll:
    """Intelligence engine whose analyze_all() raises; get_insights() works."""

    def analyze_all(self):
        raise RuntimeError("analyze_all exploded")

    def get_insights(self):
        return []


class FailingGetInsights:
    """Intelligence engine whose get_insights() raises; analyze_all() works."""

    def analyze_all(self):
        return None

    def get_insights(self):
        raise RuntimeError("get_insights exploded")


class FailingDecisionIntelligence:
    """Decision intelligence whose get_planning_context() raises."""

    def get_planning_context(self, weaknesses=None):
        raise RuntimeError("planning context exploded")


class FailingKnowledgePipeline:
    """Knowledge pipeline whose consolidation methods raise."""

    def record_weaknesses(self, weaknesses):
        raise RuntimeError("knowledge pipeline exploded")

    def consolidate(self):
        raise RuntimeError("consolidate exploded")


class TestSchedulerResultContract:
    def test_last_error_default_empty(self):
        result = EvolutionSchedulerResult(cycle_number=1)
        assert result.last_error == ""

    def test_last_error_property_default_empty(self):
        scheduler = make_scheduler()
        assert scheduler.last_error == ""

    def test_reset_clears_last_error(self):
        scheduler = make_scheduler(intelligence_engine=FailingAnalyzeAll())
        _seed_observations(scheduler._observation_engine)
        scheduler.tick()
        assert scheduler.last_error != ""
        scheduler.reset()
        assert scheduler.last_error == ""


class TestIntegrationErrorVisibility:
    def test_analyze_all_failure_recorded(self):
        scheduler = make_scheduler(intelligence_engine=FailingAnalyzeAll())
        _seed_observations(scheduler._observation_engine)
        result = scheduler.tick()
        assert result is not None
        assert result.ran_analysis is True
        assert "intelligence_engine.analyze_all" in result.last_error
        assert scheduler.last_error == result.last_error
        # Fail-soft preserved: proposal still generated
        assert result.proposals_generated >= 1

    def test_get_insights_failure_recorded(self):
        scheduler = make_scheduler(intelligence_engine=FailingGetInsights())
        _seed_observations(scheduler._observation_engine)
        result = scheduler.tick()
        assert "intelligence_engine.get_insights" in result.last_error
        # Fail-soft preserved: weakness detection proceeds without insights
        assert result.weaknesses_detected >= 1

    def test_decision_intelligence_failure_recorded(self):
        scheduler = make_scheduler(
            decision_intelligence=FailingDecisionIntelligence()
        )
        _seed_observations(scheduler._observation_engine)
        result = scheduler.tick()
        assert "decision_intelligence" in result.last_error
        assert result.proposals_generated >= 1

    def test_knowledge_pipeline_failure_recorded(self):
        scheduler = make_scheduler(knowledge_pipeline=FailingKnowledgePipeline())
        _seed_observations(scheduler._observation_engine)
        result = scheduler.tick()
        assert "knowledge_pipeline" in result.last_error
        # Storage already happened before consolidation; fail-soft preserved
        assert result.proposals_generated >= 1
        assert result.proposals_stored >= 1

    def test_successful_cycle_clears_last_error(self):
        scheduler = make_scheduler()
        _seed_observations(scheduler._observation_engine)
        result = scheduler.tick()
        assert result is not None
        assert result.last_error == ""
        assert scheduler.last_error == ""

    def test_error_cleared_at_next_successful_cycle(self):
        scheduler = make_scheduler(intelligence_engine=FailingAnalyzeAll())
        _seed_observations(scheduler._observation_engine)
        scheduler.tick()
        assert scheduler.last_error != ""

        # Second cycle with a healthy engine and new data
        scheduler._intelligence_engine = None
        _seed_observations(scheduler._observation_engine, count=3)
        result = scheduler.tick()
        assert result is not None
        assert result.last_error == ""

    def test_threshold_skip_has_no_error(self):
        scheduler = make_scheduler(min_observations=10)
        _seed_observations(scheduler._observation_engine, count=3)
        result = scheduler.tick()
        assert result is not None
        assert result.ran_analysis is False
        assert result.last_error == ""
