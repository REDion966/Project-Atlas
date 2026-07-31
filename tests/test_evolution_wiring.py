"""
Phase 10.0 — Evolution Pipeline Wiring Tests.

Tests that the ImprovementPlanner, ProposalGenerator, ApprovalManager,
and EvolutionMemory are correctly wired into the RuntimeCoordinator's
post-pipeline processing block.

These are integration tests — they verify the wiring, not the pure logic
of each component (which is tested separately in test_evolution_*.py).
"""

from unittest.mock import MagicMock, PropertyMock

import pytest

from atlas.evolution.improvement_planner import ImprovementPlanner
from atlas.evolution.proposal_generator import ProposalGenerator
from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.models import (
    Observation,
    ObservationCategory,
    ProposalStatus,
    ApprovalDecision,
)
from atlas.runtime.runtime_coordinator import RuntimeCoordinator

# --- Phase 13.3: Evolution Scheduler (used instead of inline analysis) ---
from atlas.evolution.scheduler import EvolutionScheduler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_observation():
    """Create a single runtime metrics observation that triggers a weakness."""
    return Observation(
        category=ObservationCategory.RUNTIME_METRICS,
        metric_name="runtime_summary",
        value={
            "avg_response_time_ms": 100.0,
            "request_count": 100,
            "error_count": 30,
            "error_rate_percent": 30.0,
        },
        source="test",
    )


def make_observation_engine(observations=None):
    """Create a SelfObservationEngine-like mock with observations."""
    engine = MagicMock()
    if observations:
        engine.recent_observations.return_value = observations
    else:
        engine.recent_observations.return_value = []
    return engine


def _make_scheduler(observation_engine, improvement_planner,
                    proposal_generator, approval_manager, evolution_memory):
    """Create a scheduler with tick_interval=1 and min_observations=1."""
    return EvolutionScheduler(
        observation_engine=observation_engine,
        improvement_planner=improvement_planner,
        proposal_generator=proposal_generator,
        approval_manager=approval_manager,
        evolution_memory=evolution_memory,
        tick_interval=1,
        min_observations=1,
    )


def make_coordinator(**overrides):
    """Create a RuntimeCoordinator with test defaults.

    Phase 13.3: Also creates and injects an EvolutionScheduler so that
    evolution analysis runs during process() via the scheduler tick.
    """
    defaults = {
        "improvement_planner": ImprovementPlanner(),
        "proposal_generator": ProposalGenerator(),
        "approval_manager": ApprovalManager(),
        "evolution_memory": EvolutionMemory(),
    }
    defaults.update(overrides)
    coordinator = RuntimeCoordinator(**defaults)

    # Phase 13.3: Inject a scheduler only if all evolution components
    # are present. Missing components mean no scheduler is created,
    # preserving graceful degradation behavior.
    if all([
        defaults.get("improvement_planner") is not None,
        defaults.get("proposal_generator") is not None,
        defaults.get("approval_manager") is not None,
        defaults.get("evolution_memory") is not None,
    ]):
        # Use the observation engine from overrides or create a default mock
        obs_engine = overrides.get("evolution_observation_engine") or MagicMock()
        scheduler = EvolutionScheduler(
            observation_engine=obs_engine,
            improvement_planner=defaults.get("improvement_planner"),
            proposal_generator=defaults.get("proposal_generator"),
            approval_manager=defaults.get("approval_manager"),
            evolution_memory=defaults.get("evolution_memory"),
            tick_interval=1,
            min_observations=1,
        )
        coordinator.set_evolution_scheduler(scheduler)

    return coordinator


# ---------------------------------------------------------------------------
# Test: Full evolution pipeline executes
# ---------------------------------------------------------------------------

class TestEvolutionPipelineExecutes:

    def test_full_pipeline_with_observations(self):
        """Observations flow through planner → proposal generator → approval manager → memory."""
        obs_engine = make_observation_engine([make_observation()])
        memory = EvolutionMemory()
        coordinator = make_coordinator(
            evolution_observation_engine=obs_engine,
            evolution_memory=memory,
        )

        # Process a simple pipeline execution
        result = coordinator.process(
            user_input="test input",
            metadata={"test": True},
        )

        # The pipeline should succeed (no real dependencies)
        assert result.success is True

        # EvolutionMemory should have stored the proposal and approval request
        assert memory.proposal_count >= 1
        assert memory.approval_request_count >= 1

        # Verify the proposal is in DRAFT → PENDING_APPROVAL flow
        proposal = memory.get_all_proposals()[0]
        assert proposal.status == ProposalStatus.PENDING_APPROVAL
        assert proposal.proposal_id.startswith("PROP-")

        # Verify the approval request is pending
        pending = memory.get_pending_approval_requests()
        assert len(pending) >= 1
        assert pending[0].decision == ApprovalDecision.PENDING

    def test_empty_observations_no_evolution(self):
        """No observations → no weaknesses detected → no proposals generated."""
        obs_engine = make_observation_engine([])
        memory = EvolutionMemory()
        coordinator = make_coordinator(
            evolution_observation_engine=obs_engine,
            evolution_memory=memory,
        )

        result = coordinator.process(
            user_input="test input",
            metadata={"test": True},
        )

        assert result.success is True
        assert memory.proposal_count == 0
        assert memory.approval_request_count == 0

    def test_healthy_observations_no_weaknesses(self):
        """
        Observations with normal metrics → no weaknesses detected
        → no proposals generated.
        """
        healthy_obs = Observation(
            category=ObservationCategory.RUNTIME_METRICS,
            metric_name="runtime_summary",
            value={
                "avg_response_time_ms": 100.0,
                "request_count": 100,
                "error_count": 1,
                "error_rate_percent": 1.0,
            },
            source="test",
        )
        obs_engine = make_observation_engine([healthy_obs])
        memory = EvolutionMemory()
        coordinator = make_coordinator(
            evolution_observation_engine=obs_engine,
            evolution_memory=memory,
        )

        result = coordinator.process(
            user_input="test input",
            metadata={"test": True},
        )

        assert result.success is True
        assert memory.proposal_count == 0
        assert memory.approval_request_count == 0


# ---------------------------------------------------------------------------
# Test: Graceful degradation when components are missing
# ---------------------------------------------------------------------------

class TestGracefulDegradation:

    def test_no_improvement_planner(self):
        """Missing ImprovementPlanner → entire evolution block skips."""
        obs_engine = make_observation_engine([make_observation()])
        coordinator = make_coordinator(
            improvement_planner=None,
            evolution_observation_engine=obs_engine,
        )

        result = coordinator.process(
            user_input="test input",
            metadata={"test": True},
        )

        assert result.success is True

    def test_no_proposal_generator(self):
        """Missing ProposalGenerator → planner runs, no proposal created."""
        obs_engine = make_observation_engine([make_observation()])
        memory = EvolutionMemory()
        coordinator = make_coordinator(
            proposal_generator=None,
            evolution_observation_engine=obs_engine,
            evolution_memory=memory,
        )

        result = coordinator.process(
            user_input="test input",
            metadata={"test": True},
        )

        assert result.success is True
        assert memory.proposal_count == 0

    def test_no_approval_manager(self):
        """
        Missing ApprovalManager → proposal generated but not stored
        (storage only occurs when the complete pipeline has run,
        including the approval request step).
        """
        obs_engine = make_observation_engine([make_observation()])
        memory = EvolutionMemory()
        coordinator = make_coordinator(
            approval_manager=None,
            evolution_observation_engine=obs_engine,
            evolution_memory=memory,
        )

        result = coordinator.process(
            user_input="test input",
            metadata={"test": True},
        )

        assert result.success is True
        # Without ApprovalManager, storage is skipped (the proposal is
        # generated as part of the pipeline but only stored when the full
        # evolution cycle including approval_request creation completes)
        assert memory.proposal_count == 0

    def test_no_evolution_memory(self):
        """Missing EvolutionMemory → pipeline runs, nothing stored."""
        obs_engine = make_observation_engine([make_observation()])
        coordinator = make_coordinator(
            evolution_memory=None,
            evolution_observation_engine=obs_engine,
        )

        result = coordinator.process(
            user_input="test input",
            metadata={"test": True},
        )

        assert result.success is True

    def test_no_observation_engine(self):
        """Missing observation engine → entire evolution block skips."""
        coordinator = make_coordinator(
            evolution_observation_engine=None,
        )

        result = coordinator.process(
            user_input="test input",
            metadata={"test": True},
        )

        assert result.success is True

    def test_all_evolution_components_missing(self):
        """No evolution dependencies at all → everything skips gracefully."""
        coordinator = RuntimeCoordinator()

        result = coordinator.process(
            user_input="test input",
            metadata={"test": True},
        )

        assert result.success is True


# ---------------------------------------------------------------------------
# Test: Observations accumulate across multiple pipeline runs
# ---------------------------------------------------------------------------

class TestObservationsAccumulate:

    def test_multiple_executions_accumulate_observations(self):
        """
        Each pipeline execution adds an observation via Stage 13.
        After enough executions with error data, the planner detects it.
        """
        # Use real SelfObservationEngine so observations persist across runs
        from atlas.evolution.self_observation import SelfObservationEngine
        obs_engine = SelfObservationEngine()
        memory = EvolutionMemory()
        coordinator = make_coordinator(
            evolution_observation_engine=obs_engine,
            evolution_memory=memory,
        )

        # Run pipeline 5 times — Stage 13 adds 1 observation each time
        for i in range(5):
            result = coordinator.process(
                user_input=f"test input {i}",
                metadata={"test": True},
            )
            assert result.success is True

        # After 5 runs, 5 observations should be in the engine
        assert obs_engine.observation_count == 5

    def test_observations_persist_across_runs(self):
        """Stage 13 observations persist in the engine between pipeline runs."""
        from atlas.evolution.self_observation import SelfObservationEngine
        obs_engine = SelfObservationEngine()
        coordinator = make_coordinator(
            evolution_observation_engine=obs_engine,
        )

        # First run
        coordinator.process(user_input="first", metadata={"test": True})
        assert obs_engine.observation_count == 1

        # Second run
        coordinator.process(user_input="second", metadata={"test": True})
        assert obs_engine.observation_count == 2

        # Third run
        coordinator.process(user_input="third", metadata={"test": True})
        assert obs_engine.observation_count == 3


# ---------------------------------------------------------------------------
# Test: EvolutionMemory stores results correctly
# ---------------------------------------------------------------------------

class TestEvolutionMemoryStorage:

    def test_proposals_stored_and_retrievable(self):
        """Proposals generated by the pipeline are stored in EvolutionMemory."""
        obs_engine = make_observation_engine([make_observation()])
        memory = EvolutionMemory()
        coordinator = make_coordinator(
            evolution_observation_engine=obs_engine,
            evolution_memory=memory,
        )

        coordinator.process(user_input="test", metadata={"test": True})

        proposals = memory.get_all_proposals()
        assert len(proposals) >= 1

        # Proposal should have all standard fields
        proposal = proposals[0]
        assert proposal.title != ""
        assert proposal.summary != ""
        assert proposal.rationale != ""
        assert proposal.risks != ""
        assert proposal.impact_analysis != ""

    def test_approval_requests_retrievable(self):
        """Approval requests are stored and retrievable."""
        obs_engine = make_observation_engine([make_observation()])
        memory = EvolutionMemory()
        coordinator = make_coordinator(
            evolution_observation_engine=obs_engine,
            evolution_memory=memory,
        )

        coordinator.process(user_input="test", metadata={"test": True})

        requests = memory.get_all_approval_requests()
        assert len(requests) >= 1

        request = requests[0]
        assert request.request_id.startswith("APPR-")
        assert request.decision == ApprovalDecision.PENDING

    def test_pending_approvals_accessible(self):
        """Pending approval requests are accessible via dedicated method."""
        obs_engine = make_observation_engine([make_observation()])
        memory = EvolutionMemory()
        coordinator = make_coordinator(
            evolution_observation_engine=obs_engine,
            evolution_memory=memory,
        )

        coordinator.process(user_input="test", metadata={"test": True})

        pending = memory.get_pending_approval_requests()
        assert len(pending) >= 1

    def test_proposal_count_tracking(self):
        """proposal_count property reflects stored proposals."""
        obs_engine = make_observation_engine([make_observation()])
        memory = EvolutionMemory()
        coordinator = make_coordinator(
            evolution_observation_engine=obs_engine,
            evolution_memory=memory,
        )

        assert memory.proposal_count == 0
        coordinator.process(user_input="test", metadata={"test": True})
        assert memory.proposal_count >= 1


# ---------------------------------------------------------------------------
# Test: Existing pipeline is not broken by evolution wiring
# ---------------------------------------------------------------------------

class TestNoRegression:

    def test_basic_pipeline_still_works(self):
        """
        With all evolution components wired, the base pipeline still
        produces a successful result with correct stage ordering.
        """
        coordinator = make_coordinator()

        result = coordinator.process(
            user_input="hello",
            metadata={"test": True},
        )

        assert result.success is True
        assert result.final_response is not None
        assert len(result.stages) > 0

        # Stage types should be in order
        stage_names = [s.stage.name for s in result.stages]
        assert "CONVERSATION_CONTEXT" in stage_names
        assert "AI_RESPONSE" in stage_names
