"""
Phase 12.3 — Evolution Insight Persistence Tests.

Tests that EvolutionIntelligenceEngine correctly persists EvolutionInsight
objects through SQLiteEvolutionStorage, and loads them back on restart.

Reuses the same tempfile pattern as test_evolution_persistence.py.
"""

from datetime import datetime, timedelta
from pathlib import Path
import tempfile

import pytest

from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.execution_engine import EvolutionExecutionEngine
from atlas.evolution.insight_scorer import InsightScorer
from atlas.evolution.intelligence_engine import EvolutionIntelligenceEngine
from atlas.evolution.models import (
    EvolutionInsight,
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
)
from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.storage_interface import EvolutionStorage
from atlas.storage.evolution_storage import SQLiteEvolutionStorage
from atlas.experience.experience_repository import ExperienceRepository
from atlas.experience.models import (
    ExperienceOutcome,
    GoalOutcome,
    StructuredExperience,
    TrackedGoal,
)
from atlas.storage import migration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_proposal(proposal_id: str = "PROP-PERSIST-001") -> EvolutionProposal:
    """Create a DRAFT EvolutionProposal."""
    plan = ImprovementPlan(
        plan_id="IMP-PERSIST-001",
        title="Persist Test Plan",
        description="Test plan for insight persistence",
        priority=ImprovementPriority.MEDIUM,
    )
    return EvolutionProposal(
        proposal_id=proposal_id,
        title="Insight Persistence Test Proposal",
        summary="Testing persistence of evolution insights",
        rationale="Need to verify save/load of insights.",
        expected_benefit="Insights survive restarts.",
        risks="None.",
        impact_analysis="Affects evolution intelligence storage.",
        implementation_approach="1. Save. 2. Load. 3. Verify.",
        plan=plan,
        status=ProposalStatus.DRAFT,
    )


def make_experience(
    outcome: ExperienceOutcome = ExperienceOutcome.SUCCESS,
    timestamp: datetime | None = None,
    user_input: str = "",
    reasoning_goal: str = "",
    concepts_extracted: list[str] | None = None,
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
        planning_goal="",
    )


def make_tracked_goal(
    goal_id: str,
    outcome: GoalOutcome = GoalOutcome.IMPLEMENTED,
) -> TrackedGoal:
    """Create a test TrackedGoal."""
    return TrackedGoal(
        goal_id=goal_id,
        recommendation_id=goal_id,
        goal_title="Insight Persistence Test Proposal",
        proposed_at=datetime.now() - timedelta(hours=1),
        outcome=outcome,
        outcome_reason="Observed related activities.",
    )


def setup_storage_with_insight():
    """Create storage with a single persisted insight for load testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_evolution.db"
        storage = SQLiteEvolutionStorage(db_path=db_path)
        storage.initialize()
        yield storage
        storage.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_storage():
    """Provide a temporary SQLiteEvolutionStorage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_evolution.db"
        s = SQLiteEvolutionStorage(db_path=db_path)
        s.initialize()
        yield s
        s.close()


class TestInsightStorageAdapter:

    def test_store_and_load_insight(self, tmp_storage):
        """Insight stored and loaded correctly through storage adapter."""
        insight_dict = {
            "insight_id": "INS-TEST-001",
            "proposal_id": "PROP-TEST-001",
            "execution_record_id": "EVR-TEST-001",
            "tracked_goal_id": "TRK-TEST-001",
            "outcome": "success",
            "confidence": 0.85,
            "effectiveness_score": 0.72,
            "evidence_summary": "Reduced retrieval corrections by 40%",
            "evidence_count": 30,
            "evidence_quality": 0.9,
            "regression_risk": 0.15,
            "analyzed_at": datetime.now().isoformat(),
            "proposal_title": "Test Proposal",
            "proposal_summary": "A test proposal summary",
            "metadata": {"source": "test"},
        }
        tmp_storage.store_insight(insight_dict)

        loaded = tmp_storage.load_insights()
        assert len(loaded) == 1
        assert loaded[0]["insight_id"] == "INS-TEST-001"
        assert loaded[0]["proposal_id"] == "PROP-TEST-001"
        assert loaded[0]["outcome"] == "success"
        assert loaded[0]["confidence"] == 0.85
        assert loaded[0]["effectiveness_score"] == 0.72
        assert loaded[0]["evidence_count"] == 30
        assert loaded[0]["metadata"] == {"source": "test"}

    def test_multiple_insights(self, tmp_storage):
        """Multiple insights stored and loaded correctly."""
        for i in range(5):
            insight_dict = {
                "insight_id": f"INS-MULTI-{i:03d}",
                "proposal_id": f"PROP-MULTI-{i:03d}",
                "execution_record_id": f"EVR-MULTI-{i:03d}",
                "tracked_goal_id": f"TRK-MULTI-{i:03d}",
                "outcome": "success" if i % 2 == 0 else "failure",
                "confidence": 0.8,
                "effectiveness_score": 0.7,
                "evidence_summary": f"Evidence for proposal {i}",
                "evidence_count": 10 + i,
                "evidence_quality": 0.7,
                "regression_risk": 0.1,
                "analyzed_at": datetime.now().isoformat(),
                "proposal_title": f"Proposal {i}",
                "proposal_summary": f"Summary {i}",
                "metadata": {},
            }
            tmp_storage.store_insight(insight_dict)

        loaded = tmp_storage.load_insights()
        assert len(loaded) == 5

    def test_proposal_filter(self, tmp_storage):
        """load_insights filters by proposal_id when provided."""
        # Store insights for two different proposals
        for pid in ["PROP-FILTER-A", "PROP-FILTER-B"]:
            insight_dict = {
                "insight_id": f"INS-{pid}",
                "proposal_id": pid,
                "execution_record_id": f"EVR-{pid}",
                "tracked_goal_id": f"TRK-{pid}",
                "outcome": "success",
                "confidence": 0.8,
                "effectiveness_score": 0.7,
                "evidence_summary": f"Evidence for {pid}",
                "evidence_count": 10,
                "evidence_quality": 0.7,
                "regression_risk": 0.1,
                "analyzed_at": datetime.now().isoformat(),
                "proposal_title": f"Proposal {pid}",
                "proposal_summary": f"Summary {pid}",
                "metadata": {},
            }
            tmp_storage.store_insight(insight_dict)

        # Filter by one proposal
        filtered = tmp_storage.load_insights(proposal_id="PROP-FILTER-A")
        assert len(filtered) == 1
        assert filtered[0]["proposal_id"] == "PROP-FILTER-A"

        # Filter by nonexistent proposal
        empty = tmp_storage.load_insights(proposal_id="NONEXISTENT")
        assert empty == []

    def test_metadata_roundtrip(self, tmp_storage):
        """Metadata JSON serialization/deserialization preserves data."""
        metadata = {
            "scorer_available": True,
            "tracked_goal_found": True,
            "experience_count": 30,
            "nested": {"key": "value"},
        }
        insight_dict = {
            "insight_id": "INS-META-001",
            "proposal_id": "PROP-META-001",
            "execution_record_id": "EVR-META-001",
            "tracked_goal_id": "TRK-META-001",
            "outcome": "partial",
            "confidence": 0.6,
            "effectiveness_score": 0.5,
            "evidence_summary": "Moderate evidence",
            "evidence_count": 15,
            "evidence_quality": 0.6,
            "regression_risk": 0.2,
            "analyzed_at": datetime.now().isoformat(),
            "proposal_title": "Metadata Test",
            "proposal_summary": "Testing metadata roundtrip",
            "metadata": metadata,
        }
        tmp_storage.store_insight(insight_dict)

        loaded = tmp_storage.load_insights()
        assert len(loaded) == 1
        assert loaded[0]["metadata"] == metadata
        assert loaded[0]["metadata"]["scorer_available"] is True
        assert loaded[0]["metadata"]["nested"]["key"] == "value"

    def test_empty_storage(self, tmp_storage):
        """Empty storage returns empty list."""
        loaded = tmp_storage.load_insights()
        assert loaded == []

    def test_schema_version_8(self, tmp_storage):
        """Schema version is 11 after Track D reasoning tables and Persistent Learning."""
        assert tmp_storage.get_schema_version() == 11


class TestEnginePersistenceIntegration:

    def test_engine_persists_generated_insight(self, tmp_storage):
        """EvolutionIntelligenceEngine persists insight to storage after analysis."""
        memory = EvolutionMemory()
        repo = ExperienceRepository()
        scorer = InsightScorer()
        am = ApprovalManager()
        exec_engine = EvolutionExecutionEngine(
            approval_manager=am,
            evolution_memory=memory,
            outcome_tracker=None,
        )

        # Execute a proposal
        proposal = make_proposal("PROP-ENGINE-PERSIST")
        memory.store_proposal(proposal)
        request = am.create_approval_request(proposal)
        memory.store_approval_request(request)
        exec_engine.approve_proposal(proposal, request)

        # Add experiences and tracked goal
        for i in range(30):
            exp = make_experience(
                ExperienceOutcome.SUCCESS,
                user_input="Memory retrieval ranking improved significantly",
                reasoning_goal="Evaluate memory ranking system",
            )
            repo.store_experience(exp)
        goal = make_tracked_goal(goal_id="PROP-ENGINE-PERSIST")
        repo.store_tracked_goal(goal)

        # Create intelligence engine WITH storage
        engine = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            experience_repository=repo,
            insight_scorer=scorer,
            storage=tmp_storage,
        )

        # Analyze
        insight = engine.analyze_proposal("PROP-ENGINE-PERSIST")
        assert insight is not None

        # Verify insight is in storage
        loaded = tmp_storage.load_insights()
        assert len(loaded) == 1
        assert loaded[0]["insight_id"] == insight.insight_id
        assert loaded[0]["proposal_id"] == "PROP-ENGINE-PERSIST"
        assert loaded[0]["outcome"] in ("success", "partial")

    def test_engine_loads_persisted_insights(self, tmp_storage):
        """Engine can load insights from storage after restart."""
        memory = EvolutionMemory()
        repo = ExperienceRepository()
        scorer = InsightScorer()
        am = ApprovalManager()
        exec_engine = EvolutionExecutionEngine(
            approval_manager=am,
            evolution_memory=memory,
            outcome_tracker=None,
        )

        # Execute proposal
        proposal = make_proposal("PROP-RESTART-LOAD")
        memory.store_proposal(proposal)
        request = am.create_approval_request(proposal)
        memory.store_approval_request(request)
        exec_engine.approve_proposal(proposal, request)

        for i in range(30):
            exp = make_experience(
                ExperienceOutcome.SUCCESS,
                user_input="Memory retrieval ranking improved",
                reasoning_goal="Evaluate memory ranking system",
            )
            repo.store_experience(exp)
        goal = make_tracked_goal(goal_id="PROP-RESTART-LOAD")
        repo.store_tracked_goal(goal)

        # First session: analyze and persist
        engine1 = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            experience_repository=repo,
            insight_scorer=scorer,
            storage=tmp_storage,
        )
        insight = engine1.analyze_proposal("PROP-RESTART-LOAD")
        assert insight is not None

        # Second session: fresh engine with same storage
        # Use the same memory/repo since they're in-memory only
        engine2 = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            experience_repository=repo,
            insight_scorer=scorer,
            storage=tmp_storage,
        )
        # Verify insight can be found in storage
        loaded = engine2.get_insights()
        assert len(loaded) >= 1
        matching = [i for i in loaded if i.proposal_id == "PROP-RESTART-LOAD"]
        assert len(matching) == 1
        assert matching[0].insight_id == insight.insight_id
