"""Post-Core F7 — Closed Learning Feedback Loop tests.

Verifies governed-execution outcomes (especially failures) are
deterministically recorded and re-ingested into the existing
improvement-analysis cycle:

  execution outcome (EvolutionRecord with success/error/status/
  tracked_goal_id metadata) -> EvolutionIntelligenceEngine (failed
  executions classified as "failure", never success) -> EvolutionInsight
  -> ImprovementPlanner / scheduler cycle.

No new subsystems. No governance changes. 15-stage pipeline untouched.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.execution_engine import EvolutionExecutionEngine
from atlas.evolution.improvement_planner import ImprovementPlanner
from atlas.evolution.insight_scorer import InsightScorer
from atlas.evolution.intelligence_engine import EvolutionIntelligenceEngine
from atlas.evolution.models import (
    EvolutionProposal,
    EvolutionRecord,
    ImprovementPlan,
    ImprovementPriority,
    Observation,
    ObservationCategory,
    ProposalStatus,
)
from atlas.experience.experience_repository import ExperienceRepository
from atlas.experience.models import (
    ExperienceOutcome,
    GoalOutcome,
    StructuredExperience,
    TrackedGoal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_proposal(
    proposal_id: str = "PROP-001",
    status: ProposalStatus = ProposalStatus.PENDING_APPROVAL,
) -> EvolutionProposal:
    """Create a test EvolutionProposal with the given status."""
    plan = ImprovementPlan(
        plan_id="IMP-001",
        title="Test Plan",
        description="A test improvement plan",
        priority=ImprovementPriority.LOW,
    )
    return EvolutionProposal(
        proposal_id=proposal_id,
        title="Test Proposal",
        summary="A test proposal for testing",
        rationale="Testing rationale.",
        expected_benefit="Better testability.",
        risks="Low risk.",
        impact_analysis="Affects test components.",
        implementation_approach="1. Test. 2. Verify.",
        plan=plan,
        status=status,
    )


def make_proposal_no_memory() -> EvolutionProposal:
    """Create a minimal proposal for the no-memory failure path."""
    plan = ImprovementPlan(
        plan_id="IMP-001",
        title="Test Plan",
        description="A test improvement plan",
        priority=ImprovementPriority.LOW,
    )
    return EvolutionProposal(
        proposal_id="PROP-NOMEM",
        title="Test Proposal",
        summary="s",
        rationale="r",
        expected_benefit="b",
        risks="low",
        impact_analysis="i",
        implementation_approach="1. Test.",
        plan=plan,
        status=ProposalStatus.DRAFT,
    )


def make_execution_record(
    proposal_id: str,
    success: bool = True,
    error: str = "",
    tracked_goal_id: str = "",
) -> EvolutionRecord:
    """Create an execution EvolutionRecord with F7 outcome metadata."""
    return EvolutionRecord(
        record_id=f"EVR-{proposal_id}",
        event_type="execution",
        description="execution",
        related_ids=[proposal_id],
        metadata={
            "success": success,
            "error": error,
            "status": ProposalStatus.IMPLEMENTED.name if success else ProposalStatus.DRAFT.name,
            "tracked_goal_id": tracked_goal_id,
        },
    )


def make_engine_with_memory(
    proposal: EvolutionProposal,
) -> tuple[EvolutionExecutionEngine, EvolutionMemory]:
    """Create a real execution engine wired to a real EvolutionMemory."""
    memory = EvolutionMemory()
    engine = EvolutionExecutionEngine(
        approval_manager=ApprovalManager(),
        evolution_memory=memory,
    )
    memory.store_proposal(proposal)
    return engine, memory


def add_positive_evidence(repo: ExperienceRepository, proposal_id: str) -> None:
    """Add strongly-positive experiences + an IMPLEMENTED tracked goal."""
    goal = TrackedGoal(
        goal_id=proposal_id,
        recommendation_id=proposal_id,
        goal_title="Test Proposal",
        proposed_at=datetime.now() - timedelta(hours=1),
        outcome=GoalOutcome.IMPLEMENTED,
        outcome_reason="Confirmed by test.",
    )
    repo.store_tracked_goal(goal)
    for i in range(10):
        exp = StructuredExperience(
            experience_id=f"EXP-F7-{i:04d}",
            timestamp=datetime.now(),
            duration_ms=100.0,
            pipeline_path=["runtime"],
            outcome=ExperienceOutcome.SUCCESS,
            user_input="Improvement from Test Proposal",
            reasoning_goal="improve test proposal",
            concepts_extracted=["retrieval", "memory"],
        )
        repo.store_experience(exp)


# ---------------------------------------------------------------------------
# 1. ExecutionEngine: failure outcomes are recorded, never discarded
# ---------------------------------------------------------------------------


class TestExecutionFailureRecorded:

    def test_failed_execute_stores_failure_record(self):
        """Executing a non-APPROVED proposal records a failure record."""
        proposal = make_proposal(status=ProposalStatus.DRAFT)
        engine, memory = make_engine_with_memory(proposal)

        result = engine.execute(proposal)

        assert result.success is False
        assert memory.record_count == 1
        record = memory.get_records(1)[0]
        assert record.event_type == "execution"
        assert record.metadata["success"] is False
        assert "must be APPROVED" in record.metadata["error"]
        assert record.metadata["status"] == "DRAFT"

    def test_failed_execute_keeps_proposal_status(self):
        """A failed execution never flips the proposal to IMPLEMENTED."""
        proposal = make_proposal(status=ProposalStatus.DRAFT)
        engine, memory = make_engine_with_memory(proposal)

        engine.execute(proposal)

        assert proposal.status == ProposalStatus.DRAFT
        assert "executed_at" not in proposal.metadata

    def test_failure_record_without_memory_is_safe(self):
        """Missing EvolutionMemory does not break the failure path."""
        engine = EvolutionExecutionEngine(approval_manager=ApprovalManager())

        result = engine.execute(make_proposal_no_memory())

        assert result.success is False

    def test_success_record_carries_outcome_metadata(self):
        """Successful execution records carry success/status metadata."""
        proposal = make_proposal(status=ProposalStatus.APPROVED)
        engine, memory = make_engine_with_memory(proposal)

        result = engine.execute(proposal)

        assert result.success is True
        record = memory.get_records(1)[0]
        assert record.metadata["success"] is True
        assert record.metadata["status"] == "IMPLEMENTED"
        assert record.metadata["error"] == ""

    def test_success_record_carries_tracked_goal_id(self):
        """Execution records link to the TrackedGoal created for them."""
        proposal = make_proposal(status=ProposalStatus.APPROVED)
        memory = EvolutionMemory()
        tracker = MagicMock()
        tracker.track_recommendation.return_value.goal_id = "TRK-F7-001"
        engine = EvolutionExecutionEngine(
            approval_manager=ApprovalManager(),
            evolution_memory=memory,
            outcome_tracker=tracker,
        )
        memory.store_proposal(proposal)

        engine.execute(proposal)

        record = memory.get_records(1)[0]
        assert record.metadata["tracked_goal_id"] == "TRK-F7-001"


# ---------------------------------------------------------------------------
# 2. IntelligenceEngine: failed executions are classified as failures
# ---------------------------------------------------------------------------


class TestFailedExecutionAnalysis:

    def test_failed_execution_classified_failure(self):
        """A failure record always yields outcome='failure'."""
        memory = EvolutionMemory()
        repo = ExperienceRepository()
        proposal = make_proposal(status=ProposalStatus.DRAFT)
        memory.store_proposal(proposal)
        memory.store_record(make_execution_record("PROP-001", success=False, error="boom"))
        add_positive_evidence(repo, "PROP-001")

        engine = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            experience_repository=repo,
            insight_scorer=InsightScorer(),
        )

        insight = engine.analyze_proposal("PROP-001")

        assert insight is not None
        assert insight.outcome == "failure"
        assert insight.effectiveness_score == 0.0
        assert insight.regression_risk == 1.0
        assert "boom" in insight.evidence_summary
        assert insight.metadata["execution_success"] is False

    def test_failed_never_success_despite_positive_evidence(self):
        """Overwhelming positive evidence can never override a failure."""
        memory = EvolutionMemory()
        repo = ExperienceRepository()
        proposal = make_proposal(status=ProposalStatus.DRAFT)
        memory.store_proposal(proposal)
        memory.store_record(make_execution_record("PROP-001", success=False, error="refused"))
        add_positive_evidence(repo, "PROP-001")

        engine = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            experience_repository=repo,
            insight_scorer=InsightScorer(),
        )

        insight = engine.analyze_proposal("PROP-001")

        assert insight.outcome == "failure"

    def test_failure_classification_deterministic(self):
        """Two identical runs produce identical failure outcomes."""
        engines = []
        for _ in range(2):
            memory = EvolutionMemory()
            proposal = make_proposal(status=ProposalStatus.DRAFT)
            memory.store_proposal(proposal)
            memory.store_record(
                make_execution_record("PROP-001", success=False, error="refused")
            )
            engines.append(
                EvolutionIntelligenceEngine(evolution_memory=memory)
            )

        a = engines[0].analyze_proposal("PROP-001")
        b = engines[1].analyze_proposal("PROP-001")

        assert a.outcome == b.outcome == "failure"
        assert a.confidence == b.confidence


# ---------------------------------------------------------------------------
# 3. analyze_all: failed executions reach the analysis path
# ---------------------------------------------------------------------------


class TestAnalyzeAllIncludesFailures:

    def test_analyze_all_includes_failed_execution(self):
        """A non-IMPLEMENTED proposal with a failure record is analyzed."""
        memory = EvolutionMemory()
        proposal = make_proposal(status=ProposalStatus.DRAFT)
        memory.store_proposal(proposal)
        memory.store_record(make_execution_record("PROP-001", success=False, error="refused"))

        engine = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            insight_scorer=InsightScorer(),
        )

        insights = engine.analyze_all()

        assert len(insights) == 1
        assert insights[0].proposal_id == "PROP-001"
        assert insights[0].outcome == "failure"

    def test_analyze_all_skips_never_executed(self):
        """A proposal without any execution record stays unanalyzed."""
        memory = EvolutionMemory()
        proposal = make_proposal(status=ProposalStatus.PENDING_APPROVAL)
        memory.store_proposal(proposal)

        engine = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            insight_scorer=InsightScorer(),
        )

        assert engine.analyze_all() == []

    def test_analyze_all_skips_already_analyzed_failure(self):
        """Failed executions are not double-analyzed in later waves."""
        memory = EvolutionMemory()
        proposal = make_proposal(status=ProposalStatus.DRAFT)
        memory.store_proposal(proposal)
        memory.store_record(make_execution_record("PROP-001", success=False, error="refused"))

        engine = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            insight_scorer=InsightScorer(),
        )

        first = engine.analyze_all()
        second = engine.analyze_all()

        assert len(first) == 1
        assert second == []

    def test_success_path_scorer_still_in_control(self):
        """Successful executions still use the InsightScorer heuristic."""
        memory = EvolutionMemory()
        repo = ExperienceRepository()
        proposal = make_proposal(status=ProposalStatus.APPROVED)
        memory.store_proposal(proposal)
        memory.store_record(make_execution_record("PROP-001", success=True))
        add_positive_evidence(repo, "PROP-001")

        engine = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            experience_repository=repo,
            insight_scorer=InsightScorer(),
        )

        insight = engine.analyze_proposal("PROP-001")

        assert insight is not None
        assert insight.outcome in ("success", "partial", "inconclusive")


# ---------------------------------------------------------------------------
# 4. Closed-loop integration: a governed execution outcome reaches the
#    next improvement-analysis cycle
# ---------------------------------------------------------------------------


class TestClosedLoopIntegration:

    def test_failure_outcome_reaches_next_analysis_cycle(self):
        """
        Full F7 loop with real components:
          failed governed execution (execute on non-APPROVED)
          -> failure EvolutionRecord
          -> EvolutionIntelligenceEngine.analyze_all()
          -> EvolutionInsight(outcome="failure")
          -> get_feedback_for_planner() lists it as failed
          -> ImprovementPlanner consumes the insight.
        """
        memory = EvolutionMemory()
        repo = ExperienceRepository()
        proposal = make_proposal(status=ProposalStatus.DRAFT)
        exec_engine = EvolutionExecutionEngine(
            approval_manager=ApprovalManager(),
            evolution_memory=memory,
        )
        memory.store_proposal(proposal)

        # 1. Governed execution attempt fails and is recorded.
        result = exec_engine.execute(proposal)
        assert result.success is False

        # 2. The next analysis cycle consumes it.
        intelligence = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            experience_repository=repo,
            insight_scorer=InsightScorer(),
        )
        insights = intelligence.analyze_all()
        assert len(insights) == 1
        assert insights[0].outcome == "failure"

        # 3. Planner feedback shows the failure.
        feedback = intelligence.get_feedback_for_planner()
        assert feedback["total_analyzed"] == 1
        assert feedback["failed_categories"] == ["Test Proposal"]

        # 4. ImprovementPlanner consumes the failure insight (existing path).
        planner = ImprovementPlanner()
        observations = [
            Observation(
                category=ObservationCategory.TOOL_USAGE,
                metric_name="tool_usage",
                value={"tool_name": "search", "success_rate_percent": 40},
                source="test",
            ),
        ]
        weaknesses = planner.detect_weaknesses(observations, insights=insights)
        plan = planner.create_improvement_plan(weaknesses, insights=insights)
        assert plan is not None or not weaknesses

    def test_success_outcome_still_reaches_planner_as_success(self):
        """Successful executions still flow through the analysis path."""
        memory = EvolutionMemory()
        repo = ExperienceRepository()
        proposal = make_proposal(status=ProposalStatus.APPROVED)
        exec_engine = EvolutionExecutionEngine(
            approval_manager=ApprovalManager(),
            evolution_memory=memory,
        )
        memory.store_proposal(proposal)
        add_positive_evidence(repo, proposal.proposal_id)

        result = exec_engine.execute(proposal)
        assert result.success is True

        intelligence = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            experience_repository=repo,
            insight_scorer=InsightScorer(),
        )
        insights = intelligence.analyze_all()
        assert len(insights) == 1
        assert insights[0].outcome in ("success", "partial", "inconclusive")


# ---------------------------------------------------------------------------
# 5. Governance boundary remains intact
# ---------------------------------------------------------------------------


class TestGovernanceBoundary:

    def test_failed_execution_creates_no_tracked_goal(self):
        """Failure records never fabricate outcome tracking."""
        proposal = make_proposal(status=ProposalStatus.DRAFT)
        tracker = MagicMock()
        memory = EvolutionMemory()
        engine = EvolutionExecutionEngine(
            approval_manager=ApprovalManager(),
            evolution_memory=memory,
            outcome_tracker=tracker,
        )
        memory.store_proposal(proposal)

        engine.execute(proposal)

        tracker.track_recommendation.assert_not_called()

    def test_failure_insight_never_mutates_proposal(self):
        """Generating a failure insight is read-only."""
        memory = EvolutionMemory()
        proposal = make_proposal(status=ProposalStatus.DRAFT)
        memory.store_proposal(proposal)
        memory.store_record(make_execution_record("PROP-001", success=False, error="refused"))

        engine = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            insight_scorer=InsightScorer(),
        )
        engine.analyze_proposal("PROP-001")

        assert proposal.status == ProposalStatus.DRAFT
        assert "executed_at" not in proposal.metadata
