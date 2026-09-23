"""Phase 6.2 — Development planning: evidence contract.

Investigation result: Atlas already creates a structured development plan, so no
second planning architecture was introduced.

* ``atlas/evolution/development_planner.py::DevelopmentPlanner`` — decomposes an
  APPROVED proposal into seven ordered lifecycle steps
  (INSPECT → DEFINE → IDENTIFY → TEST_SPEC → IMPLEMENT → VERIFY → ACCEPT) with
  dependencies and affected files.
* ``atlas/evolution/development_models.py::DevelopmentPlan`` — the structured,
  inspectable plan (steps, affected files, metadata).
* A plan is structural only: it carries no approval, execution, or promotion
  capability.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from atlas.evolution.development_models import StepPhase
from atlas.evolution.development_planner import (
    DevelopmentPlanner,
    DevelopmentPlannerError,
)
from atlas.evolution.improvement_planner import ImprovementPlanner, ImprovementPriority
from atlas.evolution.models import ProposalStatus, Weakness
from atlas.evolution.proposal_generator import ProposalGenerator


def _approved_proposal(targets=("atlas/example/mod.py",), status=ProposalStatus.APPROVED):
    weakness = Weakness(
        area="testing",
        description="synthetic",
        severity=ImprovementPriority.MEDIUM,
        supporting_observations=[],
        detected_at=datetime.now(),
    )
    proposal = ProposalGenerator().generate_proposal(
        ImprovementPlanner().create_improvement_plan([weakness])
    )
    proposal.proposal_id = "PROP-P62"
    proposal.metadata["affected_files"] = list(targets)
    proposal.status = status
    proposal.approved_at = datetime.now()
    return proposal


class TestPhase62DevelopmentPlanning:
    def test_plan_has_ordered_lifecycle_phases(self):
        plan = DevelopmentPlanner().plan(_approved_proposal())
        assert [step.phase for step in plan.steps] == [
            StepPhase.INSPECT,
            StepPhase.DEFINE,
            StepPhase.IDENTIFY,
            StepPhase.TEST_SPEC,
            StepPhase.IMPLEMENT,
            StepPhase.VERIFY,
            StepPhase.ACCEPT,
        ]
        assert [step.order for step in plan.steps] == [1, 2, 3, 4, 5, 6, 7]

    def test_plan_carries_affected_files_and_dependency_chain(self):
        plan = DevelopmentPlanner().plan(_approved_proposal())
        assert plan.affected_files == ["atlas/example/mod.py"]
        assert plan.steps[0].depends_on == []
        assert plan.steps[-1].depends_on == ["STEP-006"]

    def test_non_approved_proposal_is_refused(self):
        proposal = _approved_proposal(status=ProposalStatus.DRAFT)
        with pytest.raises(DevelopmentPlannerError):
            DevelopmentPlanner().plan(proposal)

    def test_plan_does_not_imply_authority(self):
        plan = DevelopmentPlanner().plan(_approved_proposal())
        assert plan.steps  # structurally executable/processable
        for banned in ("approve", "execute", "apply", "promote", "authorize"):
            assert not hasattr(plan, banned)
