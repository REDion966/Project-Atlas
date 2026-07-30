"""
Phase 7.0 — Self-Evolution Foundation: Model Tests.

Tests for atlas/evolution/models.py data classes and enums.
"""

import pytest
from datetime import datetime

from atlas.evolution.models import (
    ApprovalDecision,
    ApprovalRequest,
    EvolutionInsight,
    EvolutionProposal,
    EvolutionRecord,
    ImprovementPlan,
    ImprovementPriority,
    ImprovementStatus,
    Observation,
    ObservationCategory,
    ProposalStatus,
    ResearchQuery,
    ResearchResult,
    Weakness,
)


class TestObservationCategory:

    def test_has_expected_categories(self):
        categories = list(ObservationCategory)
        assert ObservationCategory.RUNTIME_METRICS in categories
        assert ObservationCategory.REASONING_QUALITY in categories
        assert ObservationCategory.TOOL_USAGE in categories
        assert ObservationCategory.MEMORY_QUALITY in categories
        assert ObservationCategory.SYSTEM_HEALTH in categories

    def test_enum_values_are_unique(self):
        values = [c.value for c in ObservationCategory]
        assert len(values) == len(set(values))


class TestObservation:

    def test_create_minimal(self):
        obs = Observation(
            category=ObservationCategory.RUNTIME_METRICS,
            metric_name="test_metric",
            value=42,
        )
        assert obs.category == ObservationCategory.RUNTIME_METRICS
        assert obs.metric_name == "test_metric"
        assert obs.value == 42
        assert obs.unit == ""
        assert obs.description == ""
        assert isinstance(obs.timestamp, datetime)
        assert obs.source == ""

    def test_create_full(self):
        now = datetime.now()
        obs = Observation(
            category=ObservationCategory.REASONING_QUALITY,
            metric_name="success_rate",
            value=0.95,
            unit="percent",
            description="High success rate",
            timestamp=now,
            source="test",
            metadata={"key": "value"},
        )
        assert obs.category == ObservationCategory.REASONING_QUALITY
        assert obs.metric_name == "success_rate"
        assert obs.value == 0.95
        assert obs.unit == "percent"
        assert obs.description == "High success rate"
        assert obs.timestamp == now
        assert obs.source == "test"
        assert obs.metadata == {"key": "value"}

    def test_slots(self):
        obs = Observation(
            category=ObservationCategory.TOOL_USAGE,
            metric_name="tool_count",
            value=5,
        )
        with pytest.raises(AttributeError):
            obs.new_attr = "test"


class TestImprovementPriority:

    def test_ordered_by_severity(self):
        assert ImprovementPriority.CRITICAL.value < ImprovementPriority.HIGH.value
        assert ImprovementPriority.HIGH.value < ImprovementPriority.MEDIUM.value
        assert ImprovementPriority.MEDIUM.value < ImprovementPriority.LOW.value


class TestImprovementStatus:

    def test_has_expected_statuses(self):
        assert ImprovementStatus.IDENTIFIED in ImprovementStatus
        assert ImprovementStatus.PLANNED in ImprovementStatus
        assert ImprovementStatus.PROPOSED in ImprovementStatus
        assert ImprovementStatus.APPROVED in ImprovementStatus
        assert ImprovementStatus.COMPLETED in ImprovementStatus
        assert ImprovementStatus.REJECTED in ImprovementStatus
        assert ImprovementStatus.DEFERRED in ImprovementStatus


class TestWeakness:

    def test_create_minimal(self):
        w = Weakness(area="memory", description="Low relevance", severity=ImprovementPriority.MEDIUM)
        assert w.area == "memory"
        assert w.description == "Low relevance"
        assert w.severity == ImprovementPriority.MEDIUM
        assert w.supporting_observations == []
        assert isinstance(w.detected_at, datetime)

    def test_create_with_observations(self):
        w = Weakness(
            area="runtime",
            description="Slow response",
            severity=ImprovementPriority.HIGH,
            supporting_observations=["obs1", "obs2"],
        )
        assert w.supporting_observations == ["obs1", "obs2"]


class TestImprovementPlan:

    def test_create_minimal(self):
        plan = ImprovementPlan(
            plan_id="IMP-001",
            title="Test Plan",
            description="A test plan",
            priority=ImprovementPriority.MEDIUM,
        )
        assert plan.plan_id == "IMP-001"
        assert plan.title == "Test Plan"
        assert plan.priority == ImprovementPriority.MEDIUM
        assert plan.weaknesses == []
        assert plan.target_components == []

    def test_create_with_weaknesses(self):
        w = Weakness(area="tools", description="Tool failure", severity=ImprovementPriority.LOW)
        plan = ImprovementPlan(
            plan_id="IMP-002",
            title="Fix Tools",
            description="Fix failing tools",
            priority=ImprovementPriority.HIGH,
            weaknesses=[w],
            expected_benefit="Better reliability",
            complexity_estimate="low",
            target_components=["tools"],
        )
        assert len(plan.weaknesses) == 1
        assert plan.expected_benefit == "Better reliability"
        assert plan.complexity_estimate == "low"
        assert plan.target_components == ["tools"]


class TestResearchQuery:

    def test_create(self):
        q = ResearchQuery(query_id="RQ-001", question="What is the best approach?")
        assert q.query_id == "RQ-001"
        assert q.question == "What is the best approach?"
        assert q.context == {}
        assert isinstance(q.created_at, datetime)


class TestResearchResult:

    def test_create(self):
        r = ResearchResult(
            query_id="RQ-001",
            findings="Found evidence",
            sources=["source1"],
            confidence=0.9,
        )
        assert r.query_id == "RQ-001"
        assert r.findings == "Found evidence"
        assert r.sources == ["source1"]
        assert r.confidence == 0.9


class TestProposalStatus:

    def test_has_expected_statuses(self):
        assert ProposalStatus.DRAFT in ProposalStatus
        assert ProposalStatus.PENDING_APPROVAL in ProposalStatus
        assert ProposalStatus.APPROVED in ProposalStatus
        assert ProposalStatus.REJECTED in ProposalStatus
        assert ProposalStatus.DEFERRED in ProposalStatus
        assert ProposalStatus.IMPLEMENTED in ProposalStatus
        assert ProposalStatus.SUPERSEDED in ProposalStatus


class TestEvolutionProposal:

    def test_create_minimal(self):
        plan = ImprovementPlan(
            plan_id="IMP-001",
            title="Test",
            description="Test plan",
            priority=ImprovementPriority.LOW,
        )
        proposal = EvolutionProposal(
            proposal_id="PROP-001",
            title="Test Proposal",
            summary="A test",
            rationale="Why",
            expected_benefit="Benefit",
            risks="Risks",
            impact_analysis="Impact",
            implementation_approach="Approach",
            plan=plan,
        )
        assert proposal.proposal_id == "PROP-001"
        assert proposal.title == "Test Proposal"
        assert proposal.status == ProposalStatus.DRAFT
        assert proposal.plan == plan

    def test_default_status_is_draft(self):
        plan = ImprovementPlan(
            plan_id="IMP-002",
            title="Test",
            description="Test",
            priority=ImprovementPriority.LOW,
        )
        proposal = EvolutionProposal(
            proposal_id="PROP-002",
            title="Test",
            summary="Test",
            rationale="Test",
            expected_benefit="Test",
            risks="Test",
            impact_analysis="Test",
            implementation_approach="Test",
            plan=plan,
        )
        assert proposal.status == ProposalStatus.DRAFT


class TestApprovalDecision:

    def test_has_expected_decisions(self):
        assert ApprovalDecision.PENDING in ApprovalDecision
        assert ApprovalDecision.APPROVED in ApprovalDecision
        assert ApprovalDecision.REJECTED in ApprovalDecision
        assert ApprovalDecision.DEFERRED in ApprovalDecision


class TestApprovalRequest:

    def test_create_minimal(self):
        req = ApprovalRequest(
            request_id="APPR-001",
            proposal_id="PROP-001",
            title="Approve Change",
            description="Description",
            rationale="Why",
            risks="Risks",
            expected_benefit="Benefit",
        )
        assert req.request_id == "APPR-001"
        assert req.proposal_id == "PROP-001"
        assert req.decision == ApprovalDecision.PENDING
        assert req.decision_comment == ""


class TestEvolutionRecord:

    def test_create_minimal(self):
        rec = EvolutionRecord(
            record_id="EV-001",
            event_type="proposal_created",
            description="A new proposal was created",
        )
        assert rec.record_id == "EV-001"
        assert rec.event_type == "proposal_created"
        assert rec.description == "A new proposal was created"
        assert rec.related_ids == []
        assert isinstance(rec.timestamp, datetime)


class TestEvolutionInsight:

    def test_create_minimal(self):
        """Create an EvolutionInsight with only required fields."""
        insight = EvolutionInsight(
            insight_id="INS-001",
            proposal_id="PROP-001",
            execution_record_id="EVR-001",
            tracked_goal_id="TRK-001",
        )
        assert insight.insight_id == "INS-001"
        assert insight.proposal_id == "PROP-001"
        assert insight.execution_record_id == "EVR-001"
        assert insight.tracked_goal_id == "TRK-001"
        assert insight.outcome == "inconclusive"
        assert insight.confidence == 0.0
        assert insight.effectiveness_score == 0.0
        assert insight.evidence_summary == ""
        assert insight.evidence_count == 0
        assert insight.evidence_quality == 0.0
        assert insight.regression_risk == 0.0
        assert isinstance(insight.analyzed_at, datetime)
        assert insight.proposal_title == ""
        assert insight.proposal_summary == ""

    def test_create_full(self):
        """Create an EvolutionInsight with all fields populated."""
        now = datetime.now()
        insight = EvolutionInsight(
            insight_id="INS-002",
            proposal_id="PROP-002",
            execution_record_id="EVR-002",
            tracked_goal_id="TRK-002",
            outcome="success",
            confidence=0.85,
            effectiveness_score=0.72,
            evidence_summary="Reduced retrieval corrections by 40%",
            evidence_count=15,
            evidence_quality=0.9,
            regression_risk=0.15,
            analyzed_at=now,
            proposal_title="Improve Memory Retrieval Ranking",
            proposal_summary="Improve the ranking algorithm for memory retrieval",
            metadata={"source": "trend_analysis", "window_size": 50},
        )
        assert insight.insight_id == "INS-002"
        assert insight.proposal_id == "PROP-002"
        assert insight.execution_record_id == "EVR-002"
        assert insight.tracked_goal_id == "TRK-002"
        assert insight.outcome == "success"
        assert insight.confidence == 0.85
        assert insight.effectiveness_score == 0.72
        assert insight.evidence_summary == "Reduced retrieval corrections by 40%"
        assert insight.evidence_count == 15
        assert insight.evidence_quality == 0.9
        assert insight.regression_risk == 0.15
        assert insight.analyzed_at == now
        assert insight.proposal_title == "Improve Memory Retrieval Ranking"
        assert insight.proposal_summary == "Improve the ranking algorithm for memory retrieval"
        assert insight.metadata == {"source": "trend_analysis", "window_size": 50}

    def test_slots(self):
        """EvolutionInsight uses __slots__ and rejects unknown attributes."""
        insight = EvolutionInsight(
            insight_id="INS-003",
            proposal_id="PROP-003",
            execution_record_id="EVR-003",
            tracked_goal_id="TRK-003",
        )
        with pytest.raises(AttributeError):
            insight.new_attr = "test"

    def test_default_outcome_is_inconclusive(self):
        """Default outcome is 'inconclusive' when no value is provided."""
        insight = EvolutionInsight(
            insight_id="INS-004",
            proposal_id="PROP-004",
            execution_record_id="EVR-004",
            tracked_goal_id="TRK-004",
        )
        assert insight.outcome == "inconclusive"

    def test_default_confidence_is_zero(self):
        """Default confidence is 0.0 when no value is provided."""
        insight = EvolutionInsight(
            insight_id="INS-005",
            proposal_id="PROP-005",
            execution_record_id="EVR-005",
            tracked_goal_id="TRK-005",
        )
        assert insight.confidence == 0.0

    def test_default_evidence_count_is_zero(self):
        """Default evidence_count is 0 when no value is provided."""
        insight = EvolutionInsight(
            insight_id="INS-006",
            proposal_id="PROP-006",
            execution_record_id="EVR-006",
            tracked_goal_id="TRK-006",
        )
        assert insight.evidence_count == 0

    def test_analyzed_at_defaults_to_now(self):
        """analyzed_at defaults to current datetime when not provided."""
        before = datetime.now()
        insight = EvolutionInsight(
            insight_id="INS-007",
            proposal_id="PROP-007",
            execution_record_id="EVR-007",
            tracked_goal_id="TRK-007",
        )
        after = datetime.now()
        assert before <= insight.analyzed_at <= after

    def test_partial_outcome_values(self):
        """EvolutionInsight accepts any string outcome value."""
        insight = EvolutionInsight(
            insight_id="INS-008",
            proposal_id="PROP-008",
            execution_record_id="EVR-008",
            tracked_goal_id="TRK-008",
            outcome="partial",
        )
        assert insight.outcome == "partial"

    def test_failure_outcome_values(self):
        """EvolutionInsight accepts failure as a valid outcome value."""
        insight = EvolutionInsight(
            insight_id="INS-009",
            proposal_id="PROP-009",
            execution_record_id="EVR-009",
            tracked_goal_id="TRK-009",
            outcome="failure",
        )
        assert insight.outcome == "failure"
