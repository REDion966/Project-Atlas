"""
Phase 12.2 — EvolutionIntelligenceEngine Tests.

Tests for atlas/evolution/intelligence_engine.py orchestration logic.
Uses real EvolutionMemory, ExperienceRepository, and InsightScorer
with hand-crafted test data. No mocks for core dependencies.

No storage, no SQLite, no infrastructure.
"""

from datetime import datetime, timedelta

import pytest

from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.execution_engine import EvolutionExecutionEngine
from atlas.evolution.insight_scorer import InsightScorer
from atlas.evolution.intelligence_engine import EvolutionIntelligenceEngine
from atlas.evolution.models import (
    ApprovalDecision,
    ApprovalRequest,
    EvolutionInsight,
    EvolutionProposal,
    EvolutionRecord,
    ExecutionLevel,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
)
from atlas.evolution.approval_manager import ApprovalManager
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
    title: str = "Improve Memory Retrieval Ranking",
    summary: str = "Improve the ranking algorithm for memory retrieval using relevance scores",
    status: ProposalStatus = ProposalStatus.DRAFT,
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
        title=title,
        summary=summary,
        rationale="Testing rationale.",
        expected_benefit="Better testability.",
        risks="Low risk.",
        impact_analysis="Affects test components.",
        implementation_approach="1. Test. 2. Verify.",
        plan=plan,
        status=status,
        metadata={},
    )


def make_experience(
    outcome: ExperienceOutcome = ExperienceOutcome.SUCCESS,
    timestamp: datetime | None = None,
    user_input: str = "",
    reasoning_goal: str = "",
    planning_goal: str = "",
    concepts_extracted: list[str] | None = None,
    tool_name: str = "",
    tool_success: bool = True,
) -> StructuredExperience:
    """Create a test StructuredExperience."""
    return StructuredExperience(
        experience_id=f"EXP-{id(outcome)}-{datetime.now().timestamp()}",
        timestamp=timestamp or datetime.now(),
        duration_ms=100.0,
        pipeline_path=["cognitive"],
        outcome=outcome,
        user_input=user_input,
        concepts_extracted=concepts_extracted or [],
        reasoning_goal=reasoning_goal,
        planning_goal=planning_goal,
        tool_name=tool_name,
        tool_success=tool_success,
    )


def make_tracked_goal(
    goal_id: str,
    proposal_id: str = "",
    outcome: GoalOutcome = GoalOutcome.IMPLEMENTED,
    title: str = "",
) -> TrackedGoal:
    """Create a test TrackedGoal linked to a proposal."""
    return TrackedGoal(
        goal_id=goal_id,
        recommendation_id=proposal_id or goal_id,
        goal_title=title or "Improve Memory Retrieval Ranking",
        proposed_at=datetime.now() - timedelta(hours=1),
        outcome=outcome,
        outcome_reason="Observed related activities.",
    )


def setup_happy_path(
    proposal_id: str = "PROP-001",
    experience_count: int = 30,
) -> tuple[EvolutionIntelligenceEngine, EvolutionMemory, ExperienceRepository]:
    """Create a fully-wired engine with a proposal ready for analysis."""
    memory = EvolutionMemory()
    repo = ExperienceRepository()
    scorer = InsightScorer()
    am = ApprovalManager()
    engine_exec = EvolutionExecutionEngine(
        approval_manager=am,
        evolution_memory=memory,
        outcome_tracker=None,
    )

    # Create and execute a proposal
    proposal = make_proposal(proposal_id=proposal_id)
    memory.store_proposal(proposal)
    request = am.create_approval_request(proposal)
    memory.store_approval_request(request)

    result = engine_exec.approve_proposal(proposal, request)
    assert result.success

    # Add experiences after execution
    exec_time = datetime.now()
    for i in range(experience_count):
        exp = make_experience(
            ExperienceOutcome.SUCCESS,
            timestamp=exec_time + timedelta(seconds=i),
            user_input="Memory retrieval ranking improved significantly",
            reasoning_goal="Evaluate memory ranking system",
            concepts_extracted=["retrieval", "memory", "ranking"],
        )
        repo.store_experience(exp)

    # Add a tracked goal
    goal = make_tracked_goal(
        goal_id=proposal_id,
        proposal_id=proposal_id,
        outcome=GoalOutcome.IMPLEMENTED,
        title=proposal.title,
    )
    repo.store_tracked_goal(goal)

    # Create the intelligence engine
    engine = EvolutionIntelligenceEngine(
        evolution_memory=memory,
        experience_repository=repo,
        insight_scorer=scorer,
    )

    return engine, memory, repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAnalyzeProposal:

    def test_analyze_proposal_creates_insight(self):
        """Analyzing an executed proposal produces a valid EvolutionInsight."""
        engine, _, _ = setup_happy_path()

        insight = engine.analyze_proposal("PROP-001")

        assert insight is not None
        assert isinstance(insight, EvolutionInsight)
        assert insight.insight_id.startswith("INS-")
        assert insight.proposal_id == "PROP-001"
        assert insight.execution_record_id.startswith("EVR-")
        assert insight.tracked_goal_id == "PROP-001"
        assert insight.outcome in ("success", "partial")
        assert 0.0 <= insight.confidence <= 1.0
        assert 0.0 <= insight.effectiveness_score <= 1.0
        assert insight.evidence_count == 30
        assert insight.proposal_title == "Improve Memory Retrieval Ranking"

    def test_execution_record_lookup(self):
        """Engine finds the correct execution EvolutionRecord."""
        engine, memory, _ = setup_happy_path()

        # Internally verify the record lookup
        record = engine._find_execution_record("PROP-001")

        assert record is not None
        assert record.event_type == "execution"
        assert "PROP-001" in record.related_ids

    def test_tracked_goal_matching(self):
        """Engine matches the TrackedGoal by goal_id or title."""
        engine, _, _ = setup_happy_path()

        goal = engine._find_tracked_goal("PROP-001")

        assert goal is not None
        assert goal.goal_id == "PROP-001"
        assert goal.outcome == GoalOutcome.IMPLEMENTED

    def test_analyze_nonexistent_proposal_returns_none(self):
        """Analyzing a nonexistent proposal returns None."""
        memory = EvolutionMemory()
        repo = ExperienceRepository()
        scorer = InsightScorer()

        engine = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            experience_repository=repo,
            insight_scorer=scorer,
        )

        insight = engine.analyze_proposal("NONEXISTENT")
        assert insight is None

    def test_analyze_not_implemented_proposal_returns_none(self):
        """Analyzing a non-executed proposal returns None (no execution record)."""
        memory = EvolutionMemory()
        repo = ExperienceRepository()
        scorer = InsightScorer()

        # Store a proposal but don't execute it
        proposal = make_proposal(proposal_id="PROP-DRAFT")
        proposal.status = ProposalStatus.DRAFT
        memory.store_proposal(proposal)

        engine = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            experience_repository=repo,
            insight_scorer=scorer,
        )

        insight = engine.analyze_proposal("PROP-DRAFT")
        assert insight is None


class TestAnalyzeAll:

    def test_analyze_all_multiple_proposals(self):
        """analyze_all processes all executed proposals."""
        memory = EvolutionMemory()
        repo = ExperienceRepository()
        scorer = InsightScorer()
        am = ApprovalManager()
        exec_engine = EvolutionExecutionEngine(
            approval_manager=am,
            evolution_memory=memory,
            outcome_tracker=None,
        )

        # Execute two proposals
        for pid in ["PROP-A", "PROP-B"]:
            proposal = make_proposal(proposal_id=pid)
            memory.store_proposal(proposal)
            request = am.create_approval_request(proposal)
            memory.store_approval_request(request)
            exec_engine.approve_proposal(proposal, request)

            # Add experiences and tracked goals
            exp = make_experience(
                ExperienceOutcome.SUCCESS,
                user_input=f"Improvement from {pid}",
                concepts_extracted=["retrieval", "memory"],
            )
            repo.store_experience(exp)
            goal = make_tracked_goal(
                goal_id=pid,
                proposal_id=pid,
                outcome=GoalOutcome.IMPLEMENTED,
            )
            repo.store_tracked_goal(goal)

        engine = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            experience_repository=repo,
            insight_scorer=scorer,
        )

        insights = engine.analyze_all()

        assert len(insights) == 2
        proposal_ids = {ins.proposal_id for ins in insights}
        assert proposal_ids == {"PROP-A", "PROP-B"}

    def test_skips_existing_insights(self):
        """analyze_all skips proposals that already have insights."""
        engine, _, _ = setup_happy_path()

        # First call creates insights
        first_batch = engine.analyze_all()
        assert len(first_batch) == 1

        # Second call should skip already-analyzed
        second_batch = engine.analyze_all()
        assert len(second_batch) == 0


class TestMissingDependencies:

    def test_missing_dependencies_graceful(self):
        """Engine degrades gracefully when no dependencies are injected."""
        engine = EvolutionIntelligenceEngine()

        # analyze_proposal should return None
        insight = engine.analyze_proposal("PROP-001")
        assert insight is None

        # analyze_all should return empty
        insights = engine.analyze_all()
        assert insights == []

        # get_insights should return empty
        results = engine.get_insights()
        assert results == []

        # get_feedback_for_planner should return defaults
        feedback = engine.get_feedback_for_planner()
        assert feedback["total_analyzed"] == 0
        assert feedback["average_effectiveness"] == 0.0
        assert feedback["average_confidence"] == 0.0

    def test_missing_scorer_uses_defaults(self):
        """Without InsightScorer, engine produces insight with default values."""
        memory = EvolutionMemory()
        repo = ExperienceRepository()
        am = ApprovalManager()
        exec_engine = EvolutionExecutionEngine(
            approval_manager=am,
            evolution_memory=memory,
            outcome_tracker=None,
        )

        proposal = make_proposal()
        memory.store_proposal(proposal)
        request = am.create_approval_request(proposal)
        memory.store_approval_request(request)
        exec_engine.approve_proposal(proposal, request)

        # Add experiences and tracked goal
        exp = make_experience(ExperienceOutcome.SUCCESS)
        repo.store_experience(exp)
        goal = make_tracked_goal(goal_id="PROP-001")
        repo.store_tracked_goal(goal)

        # Engine WITHOUT scorer
        engine = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            experience_repository=repo,
            insight_scorer=None,
        )

        insight = engine.analyze_proposal("PROP-001")

        assert insight is not None
        assert insight.outcome == "inconclusive"
        assert insight.confidence == 0.0
        assert insight.effectiveness_score == 0.0
        assert insight.evidence_summary == "No InsightScorer available."


class TestGetInsights:

    def test_get_insights_filter(self):
        """get_insights filters by proposal_id when provided."""
        engine, _, _ = setup_happy_path()

        # Analyze two proposals
        engine.analyze_proposal("PROP-001")

        # Get all insights
        all_insights = engine.get_insights()
        assert len(all_insights) >= 1

        # Get filtered by proposal_id
        filtered = engine.get_insights(proposal_id="PROP-001")
        assert len(filtered) >= 1
        for ins in filtered:
            assert ins.proposal_id == "PROP-001"

        # Get filtered by nonexistent proposal
        empty = engine.get_insights(proposal_id="NONEXISTENT")
        assert empty == []

    def test_get_insights_limit(self):
        """get_insights respects the limit parameter."""
        engine, _, _ = setup_happy_path()
        engine.analyze_proposal("PROP-001")

        limited = engine.get_insights(limit=1)
        assert len(limited) <= 1


class TestFeedbackSummary:

    def test_feedback_summary(self):
        """get_feedback_for_planner returns correct summary."""
        engine, _, _ = setup_happy_path()
        engine.analyze_proposal("PROP-001")

        feedback = engine.get_feedback_for_planner()

        assert feedback["total_analyzed"] >= 1
        assert isinstance(feedback["average_effectiveness"], float)
        assert isinstance(feedback["average_confidence"], float)
        assert isinstance(feedback["successful_categories"], list)
        assert isinstance(feedback["failed_categories"], list)

    def test_feedback_summary_empty(self):
        """get_feedback_for_planner returns defaults when no insights exist."""
        engine = EvolutionIntelligenceEngine()

        feedback = engine.get_feedback_for_planner()

        assert feedback["total_analyzed"] == 0
        assert feedback["average_effectiveness"] == 0.0
        assert feedback["average_confidence"] == 0.0
        assert feedback["successful_categories"] == []
        assert feedback["failed_categories"] == []
