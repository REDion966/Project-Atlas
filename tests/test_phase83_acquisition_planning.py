"""Phase 8.3 — Acquisition planning: evidence contract.

Investigation result: the acquisition strategy connects to the EXISTING
development planning architecture (no new planner). ``DevelopmentPlanner``
produces the structurally executable seven-phase plan; a plan never implies
authority.
"""

from __future__ import annotations

from datetime import datetime

from atlas.evolution.capability_acquisition import (
    AcquisitionMechanism,
    AcquisitionNeed,
    determine_acquisition_strategy,
)
from atlas.evolution.development_models import StepPhase
from atlas.evolution.development_planner import DevelopmentPlanner
from atlas.evolution.improvement_planner import ImprovementPlanner, ImprovementPriority
from atlas.evolution.models import ProposalStatus, Weakness
from atlas.evolution.proposal_generator import ProposalGenerator


def _approved(targets=("atlas/example/widget_handlers.py",)):
    weakness = Weakness(
        area="capabilities",
        description="synthetic",
        severity=ImprovementPriority.MEDIUM,
        supporting_observations=[],
        detected_at=datetime.now(),
    )
    proposal = ProposalGenerator().generate_proposal(
        ImprovementPlanner().create_improvement_plan([weakness])
    )
    proposal.proposal_id = "PROP-P83"
    proposal.metadata["affected_files"] = list(targets)
    proposal.status = ProposalStatus.APPROVED
    proposal.approved_at = datetime.now()
    return proposal


class TestPhase83AcquisitionPlanning:
    def test_strategy_connects_to_the_existing_development_plan(self):
        strategy = determine_acquisition_strategy(
            AcquisitionNeed(
                request="acquire widget search capability",
                target_capability="widget.search",
                knowledge_available=True,
            )
        )
        assert strategy.mechanism is AcquisitionMechanism.INTERNAL_DEVELOPMENT

        plan = DevelopmentPlanner().plan(_approved())
        assert [step.phase for step in plan.steps] == [
            StepPhase.INSPECT,
            StepPhase.DEFINE,
            StepPhase.IDENTIFY,
            StepPhase.TEST_SPEC,
            StepPhase.IMPLEMENT,
            StepPhase.VERIFY,
            StepPhase.ACCEPT,
        ]
        assert plan.affected_files == ["atlas/example/widget_handlers.py"]

    def test_plan_preserves_dependency_ordering(self):
        plan = DevelopmentPlanner().plan(_approved())
        assert plan.steps[0].depends_on == []
        assert plan.steps[-1].depends_on == ["STEP-006"]

    def test_plan_does_not_imply_authority(self):
        plan = DevelopmentPlanner().plan(_approved())
        for banned in ("approve", "authorize", "execute", "promote", "activate"):
            assert not hasattr(plan, banned)
