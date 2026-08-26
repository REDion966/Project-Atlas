"""Evolution Decision Pipeline — observation-to-record closure (Phase 13.5).

Verifies the complete governed decision pipeline:

    Observation → Analysis → Weakness → ImprovementPlan → EvolutionProposal
    → ApprovalRequest → Decision → Execution → EvolutionRecord → Insights

with EvolutionMemory as the central state store and best-effort durable
persistence at every transition:

- decided approval requests survive a restart (no resurrected PENDING),
- rejected/deferred proposals keep their post-decision status,
- runtime Stage-13 observations are mirrored into EvolutionMemory,
- restored observations are seeded back into the scheduler working set.
"""

from datetime import datetime, timedelta

import pytest

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.execution_engine import EvolutionExecutionEngine
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.improvement_planner import ImprovementPlan, ImprovementPlanner
from atlas.evolution.intelligence_engine import EvolutionIntelligenceEngine
from atlas.evolution.models import (
    ApprovalDecision,
    EvolutionProposal,
    ImprovementPriority,
    Observation,
    ObservationCategory,
    ProposalStatus,
    Weakness,
)
from atlas.evolution.proposal_generator import ProposalGenerator
from atlas.evolution.scheduler import EvolutionScheduler
from atlas.evolution.self_observation import SelfObservationEngine
from atlas.runtime.runtime_coordinator import RuntimeCoordinator
from atlas.storage.evolution_storage import SQLiteEvolutionStorage
from tests.test_evolution_memory_knowledge_persistence import _ExplodingStorage
from tests.test_postcore_f1_runtime_observations import StubMetrics, make_state


@pytest.fixture
def sqlite_storage(tmp_path):
    storage = SQLiteEvolutionStorage(db_path=tmp_path / "evolution.db")
    storage.initialize()
    yield storage
    storage.close()


def _make_pipeline(sqlite_storage):
    """Real components wired exactly like Atlas._init_evolution_pipeline."""
    memory = EvolutionMemory(storage=sqlite_storage)
    scheduler = EvolutionScheduler(
        observation_engine=SelfObservationEngine(),
        improvement_planner=ImprovementPlanner(),
        proposal_generator=ProposalGenerator(),
        approval_manager=ApprovalManager(),
        evolution_memory=memory,
        tick_interval=1,
        min_observations=1,
    )
    engine = EvolutionExecutionEngine(
        approval_manager=scheduler._approval_manager,
        evolution_memory=memory,
    )
    return memory, scheduler, engine


def _collect_weakness_observations(engine: SelfObservationEngine) -> None:
    """Produce observations known to trigger a 'tools' weakness (F1)."""
    from atlas.evolution.runtime_observations import collect_runtime_observations

    collect_runtime_observations(
        engine,
        make_state(reasoning=True, tool=True, memory=True),
        StubMetrics(),
        1.0,
    )


def _obs(metric: str, minutes_ago: int = 0) -> Observation:
    return Observation(
        category=ObservationCategory.RUNTIME_METRICS,
        metric_name=metric,
        value=1.0,
        description="seeded",
        timestamp=datetime.now() - timedelta(minutes=minutes_ago),
        source="test",
    )


def _proposal_with_request(memory: EvolutionMemory, pid: str):
    """Create and store a DRAFT proposal plus its PENDING request."""
    weakness = Weakness(
        area="testing",
        description="synthetic weakness",
        severity=ImprovementPriority.HIGH,
        supporting_observations=[],
        detected_at=datetime.now(),
    )
    plan = ImprovementPlanner().create_improvement_plan([weakness])
    proposal = ProposalGenerator().generate_proposal(plan)
    proposal.proposal_id = pid
    memory.store_proposal(proposal)
    request = ApprovalManager().create_approval_request(proposal)
    memory.store_approval_request(request)
    return proposal, request


# ---------------------------------------------------------------------------
# Full pipeline: observation → ... → record, with restart durability
# ---------------------------------------------------------------------------


class TestDecisionPipelineEndToEnd:
    def test_approve_flow_persists_decided_state(self, sqlite_storage):
        memory, scheduler, engine = _make_pipeline(sqlite_storage)

        # Observation → weaknesses → plan → proposal → approval request.
        _collect_weakness_observations(scheduler._observation_engine)
        result = scheduler.tick()
        assert result is not None and result.ran_analysis is True
        assert result.proposals_generated == 1

        request = memory.get_all_approval_requests()[0]
        proposal = memory.get_proposal(request.proposal_id)
        assert proposal.status == ProposalStatus.PENDING_APPROVAL
        assert request.decision == ApprovalDecision.PENDING

        # Human decision → execution → record.
        execution = engine.approve_proposal(proposal, request, comment="ok")
        assert execution.success is True

        # --- Restart simulation: fresh memory over the same storage ---
        fresh = EvolutionMemory(storage=sqlite_storage)
        fresh.restore()

        restored_proposal = fresh.get_proposal(proposal.proposal_id)
        assert restored_proposal.status == ProposalStatus.IMPLEMENTED

        restored_request = fresh.get_approval_request(request.request_id)
        assert restored_request.decision == ApprovalDecision.APPROVED
        assert restored_request.decision_comment == "ok"
        # The executed proposal must not resurrect as pending work.
        assert fresh.get_pending_approval_requests() == []
        assert fresh.record_count >= 1

    def test_reject_flow_persists_decision_and_status(self, sqlite_storage):
        memory, scheduler, engine = _make_pipeline(sqlite_storage)
        _collect_weakness_observations(scheduler._observation_engine)
        scheduler.tick()

        request = memory.get_all_approval_requests()[0]
        proposal = memory.get_proposal(request.proposal_id)

        result = engine.reject_proposal(proposal, request, reason="not now")
        assert result.success is True

        fresh = EvolutionMemory(storage=sqlite_storage)
        fresh.restore()

        rejected = fresh.get_proposal(proposal.proposal_id)
        assert rejected.status == ProposalStatus.REJECTED
        assert rejected.rejection_reason == "not now"
        assert (
            fresh.get_approval_request(request.request_id).decision
            == ApprovalDecision.REJECTED
        )

    def test_defer_flow_persists_decision_and_status(self, sqlite_storage):
        memory, scheduler, engine = _make_pipeline(sqlite_storage)
        _collect_weakness_observations(scheduler._observation_engine)
        scheduler.tick()

        request = memory.get_all_approval_requests()[0]
        proposal = memory.get_proposal(request.proposal_id)

        result = engine.defer_proposal(proposal, request, reason="later")
        assert result.success is True

        fresh = EvolutionMemory(storage=sqlite_storage)
        fresh.restore()

        assert fresh.get_proposal(proposal.proposal_id).status == (
            ProposalStatus.DEFERRED
        )
        assert (
            fresh.get_approval_request(request.request_id).decision
            == ApprovalDecision.DEFERRED
        )

    def test_learning_feedback_reaches_insights(self, sqlite_storage):
        """Execution records become insights via analyze_all (F7 closure)."""
        memory, scheduler, engine = _make_pipeline(sqlite_storage)
        _collect_weakness_observations(scheduler._observation_engine)
        scheduler.tick()

        request = memory.get_all_approval_requests()[0]
        proposal = memory.get_proposal(request.proposal_id)
        engine.approve_proposal(proposal, request)

        intelligence = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            insight_scorer=None,
            storage=sqlite_storage,
        )
        insights = intelligence.analyze_all()
        assert len(insights) >= 1
        assert insights[0].proposal_id == proposal.proposal_id


# ---------------------------------------------------------------------------
# update_approval_request semantics
# ---------------------------------------------------------------------------


class TestUpdateApprovalRequest:
    def test_replace_in_place_no_duplicates(self):
        memory = EvolutionMemory()
        proposal, request = _proposal_with_request(memory, "PROP-U1")
        before = memory.approval_request_count

        request.decision = ApprovalDecision.APPROVED
        memory.update_approval_request(request)

        assert memory.approval_request_count == before
        assert memory.get_pending_approval_requests() == []
        stored = memory.get_approval_request(request.request_id)
        assert stored.decision == ApprovalDecision.APPROVED

    def test_append_when_unknown(self):
        memory = EvolutionMemory()
        proposal, request = _proposal_with_request(memory, "PROP-U2")
        memory.update_approval_request(request)  # never stored before
        assert memory.approval_request_count == 1

    def test_survives_exploding_storage(self):
        memory = EvolutionMemory(storage=_ExplodingStorage())
        proposal, request = _proposal_with_request(memory, "PROP-U3")
        memory.store_approval_request(request)

        request.decision = ApprovalDecision.REJECTED
        memory.update_approval_request(request)  # adapter raises; swallowed
        assert memory.get_pending_approval_requests() == []


# ---------------------------------------------------------------------------
# Runtime Stage 13 → EvolutionMemory observation persistence
# ---------------------------------------------------------------------------


class TestRuntimeObservationPersistence:
    def test_stage_mirrors_observations_into_memory(self, sqlite_storage):
        memory = EvolutionMemory(storage=sqlite_storage)
        engine = SelfObservationEngine()
        coordinator = RuntimeCoordinator(
            evolution_observation_engine=engine,
            evolution_memory=memory,
        )
        result = coordinator.process("hello")
        assert result is not None

        assert memory.observation_count >= 2
        rows = sqlite_storage.load_observations()
        assert len(rows) == memory.observation_count

    def test_stage_survives_memory_failure(self):
        class _RaisingPersistMemory:
            def persist_observation(self, observation):
                raise RuntimeError("storage exploded")

        engine = SelfObservationEngine()
        coordinator = RuntimeCoordinator(
            evolution_observation_engine=engine,
            evolution_memory=_RaisingPersistMemory(),
        )
        result = coordinator.process("hello")  # must not raise
        assert result is not None
        assert engine.observation_count >= 2  # in-memory path intact

    def test_no_memory_configured_is_noop(self):
        engine = SelfObservationEngine()
        coordinator = RuntimeCoordinator(evolution_observation_engine=engine)
        result = coordinator.process("hello")
        assert result is not None


# ---------------------------------------------------------------------------
# Post-restart seeding of the scheduler working set
# ---------------------------------------------------------------------------


class TestObservationSeedContinuity:
    def test_seed_returns_count_and_preserves_order(self):
        engine = SelfObservationEngine()
        oldest = _obs("first", minutes_ago=10)
        newest = _obs("second", minutes_ago=1)
        count = engine.seed([oldest, newest])
        assert count == 2
        assert [o.metric_name for o in engine.recent_observations(2)] == [
            "second",
            "first",
        ]

    def test_seed_empty_is_noop(self):
        engine = SelfObservationEngine()
        assert engine.seed([]) == 0
        assert engine.observation_count == 0

    def test_kernel_seeding_round_trip(self, sqlite_storage):
        """Restored observations feed the scheduler working set (kernel path)."""
        writer = EvolutionMemory(storage=sqlite_storage)
        writer.persist_observation(_obs("hist-a", minutes_ago=5))
        writer.persist_observation(_obs("hist-b", minutes_ago=2))

        reader_engine = SelfObservationEngine()
        reader_memory = EvolutionMemory(storage=sqlite_storage)
        reader_memory.restore()
        restored = reader_memory.get_observations(n=1000)
        if restored:
            reader_engine.seed(list(reversed(restored)))

        assert reader_engine.observation_count == 2
        names = {o.metric_name for o in reader_engine.recent_observations(10)}
        assert names == {"hist-a", "hist-b"}
