"""Phase 4.3 — Problem decomposition: evidence contract.

Investigation result: Atlas already decomposes goals/problems into structured
sub-goals and steps, so no second planner was introduced.

* ``atlas/reasoning/planning/engine.py::PlanningEngine.decompose`` — turns a
  ``ReasoningPlan`` into a ``PlanningPlan`` with sub-goals, ordered steps,
  a dependency graph, and validation (unknown/circular deps, empty actions).
* ``atlas/evolution/development_planner.py::DevelopmentPlanner`` — decomposes an
  approved proposal into seven ordered lifecycle phases
  (INSPECT → DEFINE → IDENTIFY → TEST_SPEC → IMPLEMENT → VERIFY → ACCEPT).

These tests pin deterministic, model-free decomposition.
"""

from __future__ import annotations

from datetime import datetime

from atlas.evolution.development_models import StepPhase
from atlas.evolution.development_planner import DevelopmentPlanner
from atlas.evolution.improvement_planner import ImprovementPlanner, ImprovementPriority
from atlas.evolution.models import ProposalStatus, Weakness
from atlas.evolution.proposal_generator import ProposalGenerator
from atlas.reasoning.models import ReasoningPlan, ReasoningStep
from atlas.reasoning.planning.engine import PlanningEngine
from atlas.reasoning.planning.models import PlanningPlan, PlanningStep


def _approved_proposal(targets=("atlas/example/mod.py",), pid="PROP-P43"):
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
    proposal.proposal_id = pid
    proposal.metadata["affected_files"] = list(targets)
    proposal.status = ProposalStatus.APPROVED
    proposal.approved_at = datetime.now()
    return proposal


class TestPhase43ProblemDecomposition:
    def test_multi_step_plan_is_decomposed_with_dependencies(self):
        plan = ReasoningPlan(
            goal="respond",
            steps=[
                ReasoningStep(description="query knowledge", action="query"),
                ReasoningStep(description="analyse results", action="analyze"),
            ],
        )
        planning_plan = PlanningEngine().decompose(plan)

        assert isinstance(planning_plan, PlanningPlan)
        assert len(planning_plan.steps) == 2
        assert planning_plan.sub_goals
        # Sequential dependency: step-2 depends on step-1.
        assert planning_plan.dependencies["step-2"] == ["step-1"]
        assert planning_plan.validation_errors == []

    def test_validation_detects_unknown_and_invalid_steps(self):
        planner = PlanningEngine()
        plan = PlanningPlan(
            goal="g",
            steps=[PlanningStep(id="step-1", action="a", depends_on=["missing"])],
        )
        errors = planner.validate(plan)
        assert any("unknown step" in e for e in errors)

        empty_action = PlanningPlan(
            goal="g", steps=[PlanningStep(id="step-1", action="")]
        )
        assert any("empty action" in e for e in planner.validate(empty_action))

    def test_development_planner_decomposes_into_seven_ordered_phases(self):
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
        assert plan.affected_files == ["atlas/example/mod.py"]
