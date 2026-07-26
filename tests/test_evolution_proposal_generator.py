"""
Phase 7.0 — Self-Evolution Foundation: ProposalGenerator Tests.
"""

from atlas.evolution.models import (
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
    Weakness,
)
from atlas.evolution.proposal_generator import ProposalGenerator


class TestProposalGenerator:

    def test_generate_proposal(self):
        generator = ProposalGenerator()
        weaknesses = [
            Weakness(area="runtime", description="High error rate", severity=ImprovementPriority.CRITICAL),
        ]
        plan = ImprovementPlan(
            plan_id="IMP-001",
            title="Improve Runtime Performance",
            description="Address high error rate",
            priority=ImprovementPriority.CRITICAL,
            weaknesses=weaknesses,
            expected_benefit="Better reliability",
            complexity_estimate="medium",
            target_components=["runtime"],
        )
        proposal = generator.generate_proposal(plan)
        assert proposal.proposal_id.startswith("PROP-")
        assert proposal.title == "Improve Runtime Performance"
        assert proposal.status == ProposalStatus.DRAFT
        assert proposal.plan == plan
        assert proposal.summary != ""
        assert proposal.rationale != ""
        assert proposal.risks != ""
        assert proposal.impact_analysis != ""
        assert proposal.implementation_approach != ""

    def test_generate_proposals_multiple(self):
        generator = ProposalGenerator()
        plans = [
            ImprovementPlan(
                plan_id="IMP-001", title="Critical Fix", description="Fix",
                priority=ImprovementPriority.CRITICAL,
            ),
            ImprovementPlan(
                plan_id="IMP-002", title="Low Priority", description="Low",
                priority=ImprovementPriority.LOW,
            ),
        ]
        proposals = generator.generate_proposals(plans)
        assert len(proposals) == 2
        # Should be sorted by priority ascending (CRITICAL=1 before LOW=4)
        assert proposals[0].plan.priority == ImprovementPriority.CRITICAL
        assert proposals[1].plan.priority == ImprovementPriority.LOW

    def test_generate_proposals_empty(self):
        generator = ProposalGenerator()
        proposals = generator.generate_proposals([])
        assert proposals == []

    def test_proposal_contains_rationale(self):
        generator = ProposalGenerator()
        weaknesses = [
            Weakness(area="runtime", description="Slow", severity=ImprovementPriority.HIGH),
        ]
        plan = ImprovementPlan(
            plan_id="IMP-001", title="Fix Runtime", description="Fix it",
            priority=ImprovementPriority.HIGH,
            weaknesses=weaknesses,
            target_components=["runtime"],
        )
        proposal = generator.generate_proposal(plan)
        assert "runtime" in proposal.rationale.lower()
        assert "Slow" in proposal.rationale

    def test_proposal_risks_reflect_complexity(self):
        generator = ProposalGenerator()
        plan_high = ImprovementPlan(
            plan_id="IMP-001", title="Complex", description="Complex",
            priority=ImprovementPriority.MEDIUM,
            complexity_estimate="high",
        )
        proposal_high = generator.generate_proposal(plan_high)
        assert "High complexity" in proposal_high.risks

        plan_low = ImprovementPlan(
            plan_id="IMP-002", title="Simple", description="Simple",
            priority=ImprovementPriority.LOW,
            complexity_estimate="low",
        )
        proposal_low = generator.generate_proposal(plan_low)
        assert "Low complexity" in proposal_low.risks

    def test_proposal_impact_analysis(self):
        generator = ProposalGenerator()
        plan = ImprovementPlan(
            plan_id="IMP-001", title="Test", description="Test",
            priority=ImprovementPriority.MEDIUM,
            target_components=["runtime", "memory"],
        )
        proposal = generator.generate_proposal(plan)
        assert "runtime" in proposal.impact_analysis
        assert "memory" in proposal.impact_analysis
        assert "backward compatibility" in proposal.impact_analysis.lower()

    def test_proposal_implementation_approach(self):
        generator = ProposalGenerator()
        plan = ImprovementPlan(
            plan_id="IMP-001", title="Test", description="Test",
            priority=ImprovementPriority.MEDIUM,
            target_components=["reasoning"],
        )
        proposal = generator.generate_proposal(plan)
        assert len(proposal.implementation_approach) > 0
        assert "reasoning" in proposal.implementation_approach.lower()