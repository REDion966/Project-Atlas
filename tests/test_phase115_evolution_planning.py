"""Phase 11.5 — Evolution planning: evidence contract.

Investigation result: no self-evolution planner was introduced. The objective is
planned by the EXISTING ``DevelopmentCycleController`` → ``DevelopmentPlanner``
chain, and an invalid/unplannable objective fails closed before execution.
"""

from __future__ import annotations

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.capability_discovery import (
    CapabilityDiscoveryCandidate,
    DiscoveryAssessment,
    DiscoverySignalKind,
    DiscoveryVerdict,
)
from atlas.evolution.development_cycle import (
    DevelopmentCycleController,
    DevelopmentNeed,
)
from atlas.evolution.development_models import StepPhase
from atlas.evolution.development_scaffold_supplier import ScaffoldChangeSupplier
from atlas.evolution.self_development_loop import SelfDevelopmentLoop
from atlas.evolution.self_evolution import (
    SelfEvolutionLoop,
    SelfEvolutionTerminal,
)
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.reasoning.execution.registry import CapabilityRegistry

_MODULE = "atlas/example/plan_handlers.py"
_CAPABILITY = "example.planned"


class _Capture:
    def __init__(self):
        self.proposals = []
        self.requests = []

    def store_proposal(self, proposal):
        self.proposals.append(proposal)

    def store_approval_request(self, request):
        self.requests.append(request)


class _RecordingSupplier:
    """Delegates to the existing scaffold supplier and records the need."""

    def __init__(self):
        self._inner = ScaffoldChangeSupplier()
        self.needs: list[DevelopmentNeed] = []

    def supply_changes(self, need):
        self.needs.append(need)
        return self._inner.supply_changes(need)


class _NoChangeSupplier:
    def supply_changes(self, need):  # noqa: ARG002
        return None


def _discovery():
    evidence = ("capability_model:example.missing",)
    candidate = CapabilityDiscoveryCandidate(
        candidate_id="disc:x",
        kind=DiscoverySignalKind.UNAVAILABLE_CAPABILITY,
        subject="example.missing",
        sources=("capability_model",),
        evidence=evidence,
    )
    assessment = DiscoveryAssessment(
        candidate_id="disc:x",
        subject="example.missing",
        verdict=DiscoveryVerdict.ACTIONABLE_GAP,
        rationale="evidence-backed",
        evidence=evidence,
    )
    return candidate, assessment


def _run(tmp_path, supplier):
    loop = SelfEvolutionLoop(
        change_supplier=supplier,
        component_registry=ComponentRegistry(),
        capability_registry=CapabilityRegistry(),
        repo_root=tmp_path,
    )
    candidate, assessment = _discovery()
    return loop.run(
        candidate,
        assessment,
        target_module=_MODULE,
        capability_name=_CAPABILITY,
        owner_approved=True,
        promotion_authorized=True,
    )


class TestPhase115EvolutionPlanning:
    def test_the_existing_controller_and_planner_are_reused(self, tmp_path):
        supplier = _RecordingSupplier()
        result = _run(tmp_path, supplier)
        assert result.terminal is SelfEvolutionTerminal.ACTIVATED
        # The objective was handed to the EXISTING controller as a
        # DevelopmentNeed carrying the objective's scaffold spec.
        assert supplier.needs
        need = supplier.needs[0]
        assert isinstance(need, DevelopmentNeed)
        assert need.metadata["scaffold"]["module"] == _MODULE
        assert need.metadata["scaffold"]["capability_name"] == _CAPABILITY
        assert need.metadata["evolution_objective"]["objective_id"]

    def test_plan_step_order_follows_the_existing_lifecycle(self):
        store = _Capture()
        controller = DevelopmentCycleController(
            approval_manager=ApprovalManager(),
            change_supplier=ScaffoldChangeSupplier(),
            proposal_store=store,
            approval_request_store=store,
        )
        cycle = controller.run_development_cycle(
            DevelopmentNeed(
                title="plan a capability",
                evidence_knowledge_ids=("k",),
                metadata={
                    "scaffold": {"module": _MODULE, "capability_name": _CAPABILITY}
                },
            )
        )
        assert cycle.ok is True
        proposal = store.proposals[0]
        manager = ApprovalManager()
        request = manager.create_approval_request(proposal)
        manager.approve(request)
        manager.update_proposal_from_decision(proposal, request)
        run = SelfDevelopmentLoop().run(proposal, max_iterations=1)
        assert run.plan is not None
        assert sorted(run.plan.steps, key=lambda s: s.order)[0].phase is StepPhase.INSPECT

    def test_unplannable_objective_fails_closed_before_execution(self, tmp_path):
        result = _run(tmp_path, _NoChangeSupplier())
        assert result.terminal is SelfEvolutionTerminal.PREPARATION_FAILED
        assert not list(tmp_path.rglob("*.py"))
