"""Phase 13.8 — Human-governed continuation: evidence contract.

Validation result: continuing evolution never weakens governance. Each cycle
needs its OWN explicit approval and its OWN promotion authorization; a previous
approval or authorization never carries forward, and a successful cycle grants
Atlas no new authority.
"""

from __future__ import annotations

import inspect

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
from atlas.evolution.development_scaffold_supplier import ScaffoldChangeSupplier
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.self_evolution import SelfEvolutionLoop, SelfEvolutionTerminal
from tests.phase13_support import run_cycle

_MODULE = "atlas/example/governed_handlers.py"


class _Capture:
    def __init__(self):
        self.proposals = []
        self.requests = []

    def store_proposal(self, proposal):
        self.proposals.append(proposal)

    def store_approval_request(self, request):
        self.requests.append(request)


class TestPhase138HumanGovernedContinuation:
    def test_a_previous_approval_does_not_authorize_a_future_cycle(self, tmp_path):
        memory = EvolutionMemory()
        first = run_cycle(
            memory,
            tmp_path,
            subject="cap.a",
            capability="example.governed_a",
            module="atlas/example/governed_a_handlers.py",
        )
        assert first.terminal is SelfEvolutionTerminal.ACTIVATED

        # Cycle 2 is a NEW invocation: it must earn its own approval.
        second = run_cycle(
            memory,
            tmp_path,
            subject="cap.b",
            capability="example.governed_b",
            module="atlas/example/governed_b_handlers.py",
            owner_approved=False,
        )
        assert second.terminal is SelfEvolutionTerminal.STOPPED_AT_APPROVAL
        assert second.approval_status == "PENDING_APPROVAL"
        assert second.proposal_id != first.proposal_id

    def test_a_previous_promotion_authorization_is_not_permanent(self, tmp_path):
        memory = EvolutionMemory()
        first = run_cycle(
            memory,
            tmp_path,
            subject="cap.a",
            capability="example.gov_a",
            module="atlas/example/gov_a_handlers.py",
        )
        assert first.promotion_outcome == "promoted"

        second = run_cycle(
            memory,
            tmp_path,
            subject="cap.b",
            capability="example.gov_b",
            module="atlas/example/gov_b_handlers.py",
            promotion_authorized=False,
        )
        assert second.terminal is SelfEvolutionTerminal.PENDING_PROMOTION_REVIEW
        assert second.promotion_outcome == ""
        assert second.activated_capabilities == ()

    def test_each_cycle_requires_its_own_decisions(self):
        params = inspect.signature(SelfEvolutionLoop.run).parameters
        assert params["owner_approved"].default is False
        assert params["promotion_authorized"].default is False

    def test_every_cycle_opens_its_own_approval_request(self):
        store = _Capture()
        manager = ApprovalManager()
        controller = DevelopmentCycleController(
            approval_manager=manager,
            change_supplier=ScaffoldChangeSupplier(),
            proposal_store=store,
            approval_request_store=store,
        )
        for index in (1, 2):
            controller.run_development_cycle(
                DevelopmentNeed(
                    title=f"governed need {index}",
                    evidence_knowledge_ids=("k",),
                    metadata={
                        "scaffold": {
                            "module": f"atlas/example/gov{index}_handlers.py",
                            "capability_name": f"example.gov{index}",
                        }
                    },
                )
            )
        assert len(store.requests) == 2
        first_request, second_request = store.requests
        assert first_request.request_id != second_request.request_id
        manager.approve(first_request, comment="cycle 1")
        assert second_request.decision.name == "PENDING"  # unaffected

    def test_a_successful_cycle_grants_no_new_authority(self, tmp_path):
        memory = EvolutionMemory()
        loop = SelfEvolutionLoop(
            evolution_memory=memory,
            repo_root=tmp_path,
        )
        candidate = CapabilityDiscoveryCandidate(
            candidate_id="disc:x",
            kind=DiscoverySignalKind.UNAVAILABLE_CAPABILITY,
            subject="cap.authority",
            sources=("capability_model",),
            evidence=("capability_model:cap.authority",),
        )
        assessment = DiscoveryAssessment(
            candidate_id="disc:x",
            subject="cap.authority",
            verdict=DiscoveryVerdict.ACTIONABLE_GAP,
            rationale="evidence-backed",
            evidence=("capability_model:cap.authority",),
        )
        first = loop.run(
            candidate,
            assessment,
            target_module=_MODULE,
            capability_name="example.authority",
            capability_names=(),
            owner_approved=True,
            promotion_authorized=False,
        )
        assert first.verification_status == "verified"

        # The same loop instance still refuses to develop without a fresh
        # approval: authority is per-invocation, never accumulated.
        second = loop.run(
            candidate,
            assessment,
            target_module=_MODULE,
            capability_name="example.authority",
            capability_names=(),
            owner_approved=False,
        )
        assert second.terminal is SelfEvolutionTerminal.STOPPED_AT_APPROVAL
        assert "approve" not in dir(loop)  # the loop cannot approve anything

    def test_sandbox_verification_remains_mandatory_for_continuation(
        self, tmp_path
    ):
        from tests.phase13_support import FailingSupplier

        memory = EvolutionMemory()
        result = run_cycle(
            memory,
            tmp_path,
            subject="cap.fail",
            capability="example.gov_fail",
            module="atlas/example/gov_fail_handlers.py",
            supplier=FailingSupplier("atlas/example/gov_fail_handlers.py"),
        )
        assert result.verification_status != "verified"
        assert result.terminal is SelfEvolutionTerminal.SANDBOX_FAILED
        assert result.activated_capabilities == ()
        assert not list(tmp_path.rglob("*.py"))
