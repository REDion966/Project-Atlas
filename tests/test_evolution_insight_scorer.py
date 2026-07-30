"""
Phase 12.1 — InsightScorer Tests.

Tests for atlas/evolution/insight_scorer.py deterministic scoring logic.
All tests use pure function calls with hand-crafted inputs.

No mocks, no infrastructure, no storage.
"""

from datetime import datetime, timedelta

import pytest

from atlas.evolution.insight_scorer import InsightScorer
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
)
from atlas.experience.models import (
    ExperienceOutcome,
    GoalOutcome,
    StructuredExperience,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_proposal(
    title: str = "Improve Memory Retrieval Ranking",
    summary: str = "Improve the ranking algorithm for memory retrieval using relevance scores",
) -> EvolutionProposal:
    """Create a test EvolutionProposal with sensible defaults."""
    plan = ImprovementPlan(
        plan_id="IMP-001",
        title="Test Plan",
        description="A test improvement plan",
        priority=ImprovementPriority.LOW,
    )
    return EvolutionProposal(
        proposal_id="PROP-001",
        title=title,
        summary=summary,
        rationale="Testing rationale.",
        expected_benefit="Better testability.",
        risks="Low risk.",
        impact_analysis="Affects test components.",
        implementation_approach="1. Test. 2. Verify.",
        plan=plan,
        status=ProposalStatus.IMPLEMENTED,
    )


def make_experience(
    outcome: ExperienceOutcome = ExperienceOutcome.SUCCESS,
    user_input: str = "",
    reasoning_goal: str = "",
    planning_goal: str = "",
    concepts_extracted: list[str] | None = None,
    tool_name: str = "",
    tool_success: bool = True,
    planning_validation_errors: int = 0,
    timestamp: datetime | None = None,
) -> StructuredExperience:
    """Create a test StructuredExperience with selective defaults."""
    return StructuredExperience(
        experience_id=f"EXP-{datetime.now().timestamp()}",
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
        planning_validation_errors=planning_validation_errors,
    )


def make_tracked_goal(outcome: GoalOutcome = GoalOutcome.IMPLEMENTED) -> object:
    """Create a minimal tracked-goal-like object."""
    return type("TrackedGoal", (), {"outcome": outcome})()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScoreEffectiveness:

    def test_high_effectiveness_success_case(self):
        """High effectiveness when tracked goal is IMPLEMENTED and experiences succeed."""
        scorer = InsightScorer()
        proposal = make_proposal()
        goal = make_tracked_goal(GoalOutcome.IMPLEMENTED)
        experiences = [make_experience(ExperienceOutcome.SUCCESS) for _ in range(20)]

        score = scorer.score_effectiveness(proposal, goal, experiences)

        assert 0.6 <= score <= 1.0
        # 20 experiences plus IMPLEMENTED base of 0.7 combined with high success rate
        assert score >= 0.7

    def test_low_effectiveness_failure_case(self):
        """Low effectiveness when tracked goal is REJECTED and experiences fail."""
        scorer = InsightScorer()
        proposal = make_proposal()
        goal = make_tracked_goal(GoalOutcome.REJECTED)
        experiences = [make_experience(ExperienceOutcome.FAILURE) for _ in range(20)]

        score = scorer.score_effectiveness(proposal, goal, experiences)

        assert 0.0 <= score <= 0.5
        # REJECTED base is 0.25, success rate is 0.0, so min(0.25, 1.0) = 0.25
        assert score == 0.25

    def test_insufficient_evidence_returns_default(self):
        """Fewer than 5 experiences returns conservative 0.3."""
        scorer = InsightScorer()
        proposal = make_proposal()
        goal = make_tracked_goal(GoalOutcome.IMPLEMENTED)
        experiences = [make_experience(ExperienceOutcome.SUCCESS) for _ in range(3)]

        score = scorer.score_effectiveness(proposal, goal, experiences)

        assert score == 0.3

    def test_effectiveness_with_zero_experiences(self):
        """Zero experiences returns conservative 0.3."""
        scorer = InsightScorer()
        proposal = make_proposal()
        goal = make_tracked_goal(GoalOutcome.IMPLEMENTED)

        score = scorer.score_effectiveness(proposal, goal, [])

        assert score == 0.3


class TestScoreConfidence:

    def test_confidence_scaling(self):
        """Confidence scales with experience count."""
        scorer = InsightScorer()

        # Zero → 0.0
        assert scorer.score_confidence([]) == 0.0

        # Few → low confidence
        few = scorer.score_confidence([make_experience() for _ in range(3)])
        assert 0.0 <= few <= 0.3

        # Moderate → moderate confidence
        moderate = scorer.score_confidence([make_experience() for _ in range(25)])
        assert 0.25 <= moderate <= 0.75

        # Many → high confidence
        many = scorer.score_confidence([make_experience() for _ in range(50)])
        assert many == 1.0


class TestScoreEvidenceQuality:

    def test_keyword_evidence_matching(self):
        """Keyword overlap between proposal and experiences drives quality score."""
        scorer = InsightScorer()
        proposal = make_proposal(
            title="Improve Memory Retrieval Ranking",
            summary="Improve the ranking algorithm for memory retrieval using relevance scores",
        )
        # Experiences that explicitly reference the same topic
        experiences = [
            make_experience(
                user_input="The memory retrieval ranking seems much better now",
                reasoning_goal="Evaluate memory relevance ranking improvements",
            )
            for _ in range(10)
        ]

        score = scorer.score_evidence_quality(proposal, experiences)

        # Should detect keyword overlap (memory, retrieval, ranking, relevance, improve)
        assert score > 0.3
        assert score <= 1.0

    def test_low_evidence_quality(self):
        """Unrelated experiences produce low quality score."""
        scorer = InsightScorer()
        proposal = make_proposal(
            title="Memory Retrieval",
            summary="Memory retrieval improvements",
        )
        # Experiences about completely unrelated topic
        experiences = [
            make_experience(
                user_input="The weather is nice today",
                reasoning_goal="Greeting the user",
                planning_goal="Respond politely",
            )
            for _ in range(10)
        ]

        score = scorer.score_evidence_quality(proposal, experiences)

        # Minimal keyword overlap expected
        assert score < 0.3

    def test_evidence_quality_empty_experiences(self):
        """Empty experience list returns 0.0."""
        scorer = InsightScorer()
        proposal = make_proposal()

        score = scorer.score_evidence_quality(proposal, [])

        assert score == 0.0


class TestScoreRegressionRisk:

    def test_regression_detection(self):
        """Failures, tool errors, and planning errors increase regression risk."""
        scorer = InsightScorer()
        experiences = [
            make_experience(
                ExperienceOutcome.FAILURE,
                tool_name="search",
                tool_success=False,
                planning_validation_errors=2,
            )
            for _ in range(5)
        ] + [
            make_experience(ExperienceOutcome.SUCCESS) for _ in range(5)
        ]

        score = scorer.score_regression_risk(experiences)

        # 50% failures, 50% tool failures, 50% planning errors
        assert score > 0.3

    def test_no_regression_risk(self):
        """All successful experiences produce low regression risk."""
        scorer = InsightScorer()
        experiences = [
            make_experience(
                ExperienceOutcome.SUCCESS,
                tool_name="search",
                tool_success=True,
            )
            for _ in range(10)
        ]

        score = scorer.score_regression_risk(experiences)

        assert score == 0.0

    def test_regression_risk_empty_experiences(self):
        """Empty experience list returns 0.0."""
        scorer = InsightScorer()

        score = scorer.score_regression_risk([])

        assert score == 0.0


class TestClassifyOutcome:

    def test_classification_success(self):
        """High effectiveness + high confidence → 'success'."""
        scorer = InsightScorer()
        outcome = scorer.classify_outcome(effectiveness=0.85, confidence=0.7)
        assert outcome == "success"

    def test_classification_failure(self):
        """Low effectiveness + high confidence → 'failure'."""
        scorer = InsightScorer()
        outcome = scorer.classify_outcome(effectiveness=0.2, confidence=0.7)
        assert outcome == "failure"

    def test_classification_inconclusive(self):
        """Low confidence regardless of effectiveness → 'inconclusive'."""
        scorer = InsightScorer()
        outcome = scorer.classify_outcome(effectiveness=0.85, confidence=0.05)
        assert outcome == "inconclusive"

    def test_classification_partial(self):
        """Moderate confidence but borderline effectiveness → 'partial'."""
        scorer = InsightScorer()
        # effectiveness 0.5 fails success (needs >= 0.75) and fails failure (needs <= 0.3)
        # confidence 0.2 is >= 0.1 threshold (5/50) → partial
        outcome = scorer.classify_outcome(effectiveness=0.5, confidence=0.2)
        assert outcome == "partial"


# ---------------------------------------------------------------------------
# Full-pipeline scenario tests
# ---------------------------------------------------------------------------


class TestWorkflowIntegration:

    def test_full_scenario_success(self):
        """Simulate a well-executed proposal with strong evidence."""
        scorer = InsightScorer()
        proposal = make_proposal()
        goal = make_tracked_goal(GoalOutcome.IMPLEMENTED)
        experiences = [
            make_experience(
                ExperienceOutcome.SUCCESS,
                user_input="Memory ranking is working better than before",
                reasoning_goal="Evaluate memory retrieval quality",
            )
            for _ in range(30)
        ]

        effectiveness = scorer.score_effectiveness(proposal, goal, experiences)
        confidence = scorer.score_confidence(experiences)
        quality = scorer.score_evidence_quality(proposal, experiences)
        risk = scorer.score_regression_risk(experiences)
        outcome = scorer.classify_outcome(effectiveness, confidence)

        assert effectiveness >= 0.7
        assert confidence >= 0.5
        assert quality > 0.0
        assert risk < 0.3
        assert outcome in ("success", "partial")

    def test_full_scenario_failure(self):
        """Simulate a poorly-executed proposal with negative evidence."""
        scorer = InsightScorer()
        proposal = make_proposal()
        goal = make_tracked_goal(GoalOutcome.OBSOLETE)
        experiences = [
            make_experience(
                ExperienceOutcome.FAILURE,
                user_input="Nothing changed",
                tool_name="search",
                tool_success=False,
                planning_validation_errors=3,
            )
            for _ in range(30)
        ]

        effectiveness = scorer.score_effectiveness(proposal, goal, experiences)
        confidence = scorer.score_confidence(experiences)
        quality = scorer.score_evidence_quality(proposal, experiences)
        risk = scorer.score_regression_risk(experiences)
        outcome = scorer.classify_outcome(effectiveness, confidence)

        assert effectiveness <= 0.5
        assert confidence >= 0.5
        assert risk > 0.3
        assert outcome in ("failure", "partial")
