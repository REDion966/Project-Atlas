"""Phase 4.4 — Planning: evidence contract.

Investigation result: Atlas already constructs executable structured plans from a
goal/decomposition plus capabilities, so no new planner was introduced.

* ``atlas/reasoning/planning/engine.py::PlanningEngine`` — dependency-aware
  ``next_steps`` execution readiness over a ``PlanningPlan``.
* ``atlas/reasoning/execution/routing.py`` / ``dispatcher.py`` — capability
  routing and dispatch producing ``ExecutionResult``.
* ``atlas/evolution/development_planner.py`` — a structurally executable
  development plan (ordered phases, dependency chain, affected files).

These tests pin that a plan is structured enough for governed execution.
"""

from __future__ import annotations

from datetime import datetime

from atlas.evolution.development_planner import DevelopmentPlanner
from atlas.evolution.improvement_planner import ImprovementPlanner, ImprovementPriority
from atlas.evolution.models import ProposalStatus, Weakness
from atlas.evolution.proposal_generator import ProposalGenerator
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.planning.engine import PlanningEngine
from atlas.reasoning.planning.models import PlanningPlan, PlanningStep


def _approved_proposal(pid="PROP-P44"):
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
    proposal.metadata["affected_files"] = ["atlas/example/mod.py"]
    proposal.status = ProposalStatus.APPROVED
    proposal.approved_at = datetime.now()
    return proposal


class TestPhase44Planning:
    def test_next_steps_is_dependency_aware(self):
        planner = PlanningEngine()
        plan = PlanningPlan(
            goal="g",
            steps=[
                PlanningStep(id="step-1", action="a"),
                PlanningStep(id="step-2", action="b", depends_on=["step-1"]),
            ],
        )
        assert [s.id for s in planner.next_steps(plan)] == ["step-1"]

        plan.steps[0].status = "completed"
        assert [s.id for s in planner.next_steps(plan)] == ["step-2"]

    def test_capability_routing_and_dispatch_produce_executable_results(self):
        registry = CapabilityRegistry()
        registry.register(
            "conversation",
            lambda params: ExecutionResult(
                capability="conversation", success=True, output={"ok": True}
            ),
        )
        capabilities = [
            Capability(name="conversation", priority=10),
            Capability(name="missing", priority=5),
        ]

        routes = CapabilityRouter(registry).route(capabilities)
        assert [r.capability for r in routes] == ["conversation"]

        results = CapabilityDispatcher(registry).dispatch(capabilities)
        assert results[0].success is True and results[0].output == {"ok": True}
        # A capability with no registered handler fails honestly (no fabrication).
        assert results[1].success is False and "No handler" in results[1].error

    def test_development_plan_is_structurally_executable(self):
        plan = DevelopmentPlanner().plan(_approved_proposal())
        assert plan.plan_id and plan.proposal_id
        assert [step.order for step in plan.steps] == [1, 2, 3, 4, 5, 6, 7]
        assert plan.steps[0].depends_on == []
        assert plan.steps[-1].depends_on == ["STEP-006"]
        assert plan.affected_files
