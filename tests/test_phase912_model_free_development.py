"""Phase 9.12 — Complete model-independent development demonstration.

The principal Phase 9 acceptance test: Atlas itself performs the full governed
development lifecycle for a controlled capability — with no Command Code, Cline,
external LLM, or other external coding agent.

    inventory (Atlas-owned) → missing capability → DevelopmentNeed
      → architecture self-inspection → governed preparation (DRAFT, PENDING_APPROVAL)
      → unapproved sandbox refused → approval → own change generation
      → sandbox implementation + selected tests → verification → diagnosis
      → evidence/history → promotion review (not promoted) → governed activation
      → registry/model consistency → routing → execution
"""

from __future__ import annotations

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.autonomy.code_sandbox import CodeChangeSet, SandboxPathError
from atlas.evolution.capability_activation import CapabilityActivator
from atlas.evolution.development_cycle import (
    DevelopmentCycleController,
    DevelopmentNeed,
)
from atlas.evolution.development_diagnostic import DevelopmentDiagnostic
from atlas.evolution.development_gap import (
    DevelopmentGapKind,
    assess_development_gap,
)
from atlas.evolution.development_models import (
    DevelopmentOutcomeStatus,
    StepPhase,
)
from atlas.evolution.development_scaffold_supplier import ScaffoldChangeSupplier
from atlas.evolution.development_test_selection import select_relevant_tests
from atlas.evolution.development_verification import (
    DevelopmentVerification,
    VerificationStatus,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.models import EvolutionRecord, ProposalStatus
from atlas.evolution.promotion_artifact import capture_promotion_artifact
from atlas.evolution.promotion_gate import (
    PromotionGate,
    PromotionRecommendation,
    PromotionStatus,
)
from atlas.evolution.self_development_inventory import build_inventory
from atlas.evolution.self_development_loop import SelfDevelopmentLoop
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.self_knowledge.architecture_model import build_architecture_model
from atlas.self_knowledge.capability_model import build_capability_model

_MODULE = "atlas/example/indep_handlers.py"
_CAPABILITY = "example.independent"


class _Capture:
    def __init__(self):
        self.proposals = []
        self.requests = []

    def store_proposal(self, proposal):
        self.proposals.append(proposal)

    def store_approval_request(self, request):
        self.requests.append(request)


def _prepare():
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
            title="add the independent-example capability",
            evidence_knowledge_ids=("k",),
            target_components=(_MODULE,),
            metadata={
                "scaffold": {"module": _MODULE, "capability_name": _CAPABILITY}
            },
        )
    )
    return store, manager, cycle


class TestPhase912ModelFreeDevelopment:
    def test_atlas_completes_governed_development_without_an_external_agent(
        self, tmp_path
    ):
        # 0. Capability inventory: the lifecycle is Atlas-owned; no required
        #    external dependency.
        inventory = build_inventory()
        assert inventory.self_sufficient is True
        assert inventory.external_dependencies() == ()

        # 1-2. Identify a missing capability and build a DevelopmentNeed.
        gap = assess_development_gap(
            "add an independent-example capability", capability_names=()
        )
        assert gap.kind is not DevelopmentGapKind.ALREADY_SUPPORTED

        # 3. Architecture self-inspection.
        registry = ComponentRegistry()
        registry.register(
            ComponentMetadata(
                name="example_component",
                package="atlas.example",
                module_path="atlas.example.mod.Thing",
                status=ComponentStatus.HEALTHY,
                provided_capabilities=["example.thing"],
            )
        )
        assert build_architecture_model(registry).locate("example_component").found

        # 4. Governed preparation → DRAFT proposal at the approval boundary.
        store, manager, cycle = _prepare()
        assert cycle.ok is True
        assert cycle.proposal_status == ProposalStatus.PENDING_APPROVAL.name
        proposal = store.proposals[0]
        request = store.requests[0]

        # 5. Unapproved sandbox development is refused.
        assert (
            SelfDevelopmentLoop().run(proposal, max_iterations=1).status
            is DevelopmentOutcomeStatus.GOVERNANCE_DENIED
        )

        # 6. Atlas generates its OWN change set (deterministic scaffold).
        change_set = CodeChangeSet.from_payload(
            {"code_changes": list(proposal.metadata["code_changes"])}
        )
        assert change_set.changes[0].path == _MODULE
        assert 'CAPABILITY_NAME = "example.independent"' in change_set.changes[0].content

        # 7. Authorization (human/governance).
        manager.approve(request, comment="approved")
        manager.update_proposal_from_decision(proposal, request)
        assert proposal.status is ProposalStatus.APPROVED

        # 8. Sandbox implementation + selected tests.
        run = SelfDevelopmentLoop().run(proposal, max_iterations=1)
        assert run.status is DevelopmentOutcomeStatus.SUCCESS
        assert [step.phase for step in run.plan.steps][0] is StepPhase.INSPECT

        selected = select_relevant_tests(
            [_MODULE], list(proposal.metadata["test_files"].keys())
        )
        assert selected  # Atlas selected its own test

        # 9. Verification + diagnosis.
        assert DevelopmentVerification().verify(run).status is VerificationStatus.VERIFIED
        diagnostic = DevelopmentDiagnostic().diagnose(run)
        assert diagnostic.failure_class is not None

        # 10. Evidence/history.
        memory = EvolutionMemory()
        memory.store_record(
            EvolutionRecord(
                record_id="DEV-P912",
                event_type="development",
                description="Phase 9 model-free development run.",
                related_ids=[proposal.proposal_id, _CAPABILITY],
                metadata={"terminal_status": "SUCCESS"},
            )
        )
        assert memory.get_records_by_type("development")

        # 11. Promotion review (not an automatic promotion).
        gate = PromotionGate(evolution_memory=memory)
        assessment = gate.assess(run, proposal_id=proposal.proposal_id)
        assert assessment.recommendation is PromotionRecommendation.READY_FOR_PROMOTION
        review = gate.request_review(assessment)
        assert review.status is PromotionStatus.PENDING_REVIEW
        gate.approve(review, comment="owner")
        assert review.status is PromotionStatus.APPROVED
        assert review.status is not PromotionStatus.PROMOTED

        # 12. Governed activation.
        registry_caps = CapabilityRegistry()
        root = tmp_path / "repo"
        root.mkdir()
        body = proposal.metadata["code_changes"][0]["content"]
        target = root / _MODULE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        artifact = capture_promotion_artifact(
            list(proposal.metadata["code_changes"]),
            proposal_id=proposal.proposal_id,
            repo_root=root,
        )
        activation = CapabilityActivator(root, registry_caps).activate(artifact)
        assert activation.activated is True

        # 13. Registry/model consistency.
        model = build_capability_model(registry, capability_registry=registry_caps)
        assert any(e.name == _CAPABILITY for e in model.entries)

        # 14. Routing + execution.
        routes = CapabilityRouter(registry_caps).route([Capability(name=_CAPABILITY)])
        assert [r.capability for r in routes] == [_CAPABILITY]
        results = CapabilityDispatcher(registry_caps).dispatch(
            [Capability(name=_CAPABILITY)]
        )
        assert results[0].success is True

    def test_negative_paths_fail_closed_without_an_external_agent(self, tmp_path):
        # Ambiguous need -> preparation fails closed.
        result = DevelopmentCycleController(
            approval_manager=ApprovalManager()
        ).run_development_cycle(DevelopmentNeed(title="   "))
        assert result.ok is False
        assert any(stage == "need" for stage, _ in result.failures)

        # Missing authorization -> sandbox development refused.
        store, _manager, _cycle = _prepare()
        assert (
            SelfDevelopmentLoop().run(store.proposals[0], max_iterations=1).status
            is DevelopmentOutcomeStatus.GOVERNANCE_DENIED
        )

        # Invalid change set (sandbox escape) -> rejected.
        import pytest

        with pytest.raises(SandboxPathError):
            CodeChangeSet.from_payload(
                {"code_changes": [{"path": "../evil.py", "content": "x"}]}
            )

        # Failing test -> never SUCCESS.
        _store2, manager2, _cycle2 = _prepare()
        proposal2 = _store2.proposals[0]
        manager2.approve(_store2.requests[0])
        manager2.update_proposal_from_decision(proposal2, _store2.requests[0])
        proposal2.metadata["test_files"] = {
            "tests/test_indep_handlers.py": "def test_x():\n    assert False\n"
        }
        failing = SelfDevelopmentLoop().run(proposal2, max_iterations=1)
        assert failing.status is not DevelopmentOutcomeStatus.SUCCESS
