"""Phase 9.9 — Self-development lifecycle orchestration: evidence contract.

Investigation result: a single Atlas-owned lifecycle already exists
(``DevelopmentCycleController`` → ``SelfDevelopmentLoop``) and is invocable
without an external coding agent. No new orchestration framework was introduced.
"""

from __future__ import annotations

import inspect

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.development_cycle import (
    DevelopmentCycleController,
    DevelopmentNeed,
)
from atlas.evolution.development_models import DevelopmentOutcomeStatus
from atlas.evolution.development_scaffold_supplier import ScaffoldChangeSupplier
from atlas.evolution.models import ProposalStatus
from atlas.evolution.self_development_loop import SelfDevelopmentLoop

_MODULE = "atlas/example/orch_handlers.py"
_CAPABILITY = "example.orch"


class _Capture:
    def __init__(self):
        self.proposals = []
        self.requests = []

    def store_proposal(self, proposal):
        self.proposals.append(proposal)

    def store_approval_request(self, request):
        self.requests.append(request)


def _prepared():
    store = _Capture()
    manager = ApprovalManager()
    controller = DevelopmentCycleController(
        approval_manager=manager,
        change_supplier=ScaffoldChangeSupplier(),
        proposal_store=store,
        approval_request_store=store,
    )
    cycle = controller.run_development_cycle(
        DevelopmentNeed(
            title="orchestrate a capability",
            evidence_knowledge_ids=("k",),
            metadata={
                "scaffold": {"module": _MODULE, "capability_name": _CAPABILITY}
            },
        )
    )
    return store, manager, cycle


class TestPhase99LifecycleOrchestration:
    def test_atlas_owned_lifecycle_runs_without_an_external_agent(self):
        store, manager, cycle = _prepared()
        assert cycle.ok is True
        assert cycle.proposal_status == ProposalStatus.PENDING_APPROVAL.name

        proposal = store.proposals[0]
        request = store.requests[0]
        manager.approve(request, comment="approved")
        manager.update_proposal_from_decision(proposal, request)
        assert proposal.status is ProposalStatus.APPROVED

        run = SelfDevelopmentLoop().run(proposal, max_iterations=1)
        assert run.status is DevelopmentOutcomeStatus.SUCCESS

    def test_lifecycle_stops_at_the_approval_boundary(self):
        store, _manager, _cycle = _prepared()
        # Unapproved -> the loop refuses before any sandbox work.
        result = SelfDevelopmentLoop().run(store.proposals[0], max_iterations=1)
        assert result.status is DevelopmentOutcomeStatus.GOVERNANCE_DENIED

    def test_lifecycle_has_no_model_seam(self):
        cycle_params = inspect.signature(
            DevelopmentCycleController.__init__
        ).parameters
        assert "ai_service" not in cycle_params
        assert "model" not in cycle_params

        loop_params = inspect.signature(SelfDevelopmentLoop.__init__).parameters
        assert "ai_service" not in loop_params
        assert "model" not in loop_params
