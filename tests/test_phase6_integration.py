"""Phase 6 integration — full governed development lifecycle.

Demonstrates the Phase 6 completion criterion with one bounded, deterministic,
model-free path:

    genuine capability gap
      → structured development goal (DevelopmentNeed)
      → governed preparation (DRAFT proposal) STOPPED at PENDING_APPROVAL
      → sandbox execution refused while unapproved
      → OWNER/manager approval
      → authorized sandbox implementation (scaffolded capability module + test)
      → deterministic test selection + verification (VERIFIED)
      → evidence/history recorded
      → verified run opens a promotion REVIEW (not a promotion)
      → governed capability activation registers the capability
      → CapabilityRegistry/CapabilityModel stay consistent

  ... with no external AI model.

Negative paths (fail-closed): missing approval, failed verification, and invalid
activation.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.capability_activation import (
    CapabilityActivationError,
    CapabilityActivator,
)
from atlas.evolution.development_cycle import (
    DevelopmentCycleController,
    DevelopmentNeed,
)
from atlas.evolution.development_gap import (
    DevelopmentGapKind,
    assess_development_gap,
)
from atlas.evolution.development_models import DevelopmentOutcomeStatus
from atlas.evolution.development_scaffold_supplier import ScaffoldChangeSupplier
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
from atlas.evolution.self_development_loop import SelfDevelopmentLoop
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.self_knowledge.capability_model import build_capability_model

_MODULE = "atlas/example/notes_handlers.py"
_CAPABILITY = "example.notes"


class _CaptureStore:
    def __init__(self):
        self.proposals = []
        self.requests = []

    def store_proposal(self, proposal):
        self.proposals.append(proposal)

    def store_approval_request(self, request):
        self.requests.append(request)


def _prepared_lifecycle():
    """Run gap → goal → governed preparation; return the prepared proposal."""
    gap = assess_development_gap(
        "export notes to markdown", capability_names=["memory_search"]
    )
    assert gap.kind is not DevelopmentGapKind.ALREADY_SUPPORTED

    store = _CaptureStore()
    manager = ApprovalManager()
    controller = DevelopmentCycleController(
        approval_manager=manager,
        change_supplier=ScaffoldChangeSupplier(),
        proposal_store=store,
        approval_request_store=store,
    )
    need = DevelopmentNeed(
        title="add an export-notes capability",
        summary="Export notes to Markdown.",
        evidence_knowledge_ids=("k-1",),
        target_components=(_MODULE,),
        metadata={
            "scaffold": {"module": _MODULE, "capability_name": _CAPABILITY}
        },
    )
    cycle = controller.run_development_cycle(need)
    assert cycle.ok is True
    assert cycle.proposal_status == ProposalStatus.PENDING_APPROVAL.name
    assert store.proposals and store.requests
    return manager, store.proposals[0], store.requests[0]


class TestPhase6Integration:
    def test_full_governed_development_lifecycle(self, tmp_path):
        manager, proposal, request = _prepared_lifecycle()
        assert proposal.status is ProposalStatus.PENDING_APPROVAL

        # Unapproved → sandbox execution is refused (fail-closed).
        refused = SelfDevelopmentLoop().run(proposal, max_iterations=1)
        assert refused.status is DevelopmentOutcomeStatus.GOVERNANCE_DENIED

        # Approval boundary: only the ApprovalManager grants approval.
        manager.approve(request, comment="approved for sandbox")
        manager.update_proposal_from_decision(proposal, request)
        assert proposal.status is ProposalStatus.APPROVED

        # Authorized sandbox implementation + deterministic tests.
        run = SelfDevelopmentLoop().run(proposal, max_iterations=1)
        assert run.status is DevelopmentOutcomeStatus.SUCCESS
        assert run.outcomes[0].test_outcome == "passed"

        # Verification is evidence-based.
        report = DevelopmentVerification().verify(run)
        assert report.status is VerificationStatus.VERIFIED

        # Evidence/history recorded.
        memory = EvolutionMemory()
        memory.store_record(
            EvolutionRecord(
                record_id="DEV-6INT-1",
                event_type="development",
                description="Phase 6 integration run.",
                related_ids=[proposal.proposal_id],
                metadata={"terminal_status": "SUCCESS", "success": True},
            )
        )
        assert memory.get_records_by_type("development")

        # Verified run opens a promotion REVIEW — not a promotion.
        gate = PromotionGate(evolution_memory=memory)
        assessment = gate.assess(run, proposal_id=proposal.proposal_id)
        assert assessment.recommendation is PromotionRecommendation.READY_FOR_PROMOTION
        review = gate.request_review(assessment)
        assert review.status is PromotionStatus.PENDING_REVIEW
        gate.approve(review, comment="owner approval")
        assert review.status is PromotionStatus.APPROVED
        assert review.status is not PromotionStatus.PROMOTED

        # Governed capability activation integrates the capability.
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
        registry = CapabilityRegistry()
        activation = CapabilityActivator(root, registry).activate(artifact)
        assert activation.activated is True
        assert registry.has(_CAPABILITY)

        # Capability registry/model stay consistent.
        model = build_capability_model(ComponentRegistry(), capability_registry=registry)
        assert any(e.name == _CAPABILITY for e in model.entries)

    def test_missing_approval_blocks_execution_and_promotion(self):
        _manager, proposal, request = _prepared_lifecycle()
        assert proposal.status is ProposalStatus.PENDING_APPROVAL

        # No approval → no sandbox execution.
        assert (
            SelfDevelopmentLoop().run(proposal, max_iterations=1).status
            is DevelopmentOutcomeStatus.GOVERNANCE_DENIED
        )
        # The review has not been approved, so it cannot be promoted.
        assert request.decision.name == "PENDING"

    def test_failed_verification_blocks_promotion_and_invalid_activation_is_refused(
        self, tmp_path
    ):
        # A failed/unverified run is never promotable.
        gate = PromotionGate(evolution_memory=EvolutionMemory())
        failed_outcome = SimpleNamespace(
            verification_passed=False,
            rollback_occurred=True,
            test_outcome="failed",
            changed_files=["atlas/example/notes_handlers.py"],
        )
        run_result = SimpleNamespace(
            status=DevelopmentOutcomeStatus.FAILED,
            outcomes=[failed_outcome],
            iterations_used=1,
            message="failed",
            plan=None,
        )
        assessment = gate.assess(run_result, proposal_id="P")
        assert assessment.recommendation is PromotionRecommendation.NOT_PROMOTABLE

        # An invalid capability contract is refused fail-closed.
        root = tmp_path / "repo"
        root.mkdir()
        (root / "bad.py").write_text('CAPABILITY_NAME = "x.y"\n', encoding="utf-8")
        artifact = capture_promotion_artifact(
            [{"path": "bad.py", "content": 'CAPABILITY_NAME = "x.y"\n'}],
            proposal_id="P",
            repo_root=root,
        )
        with pytest.raises(CapabilityActivationError):
            CapabilityActivator(root, CapabilityRegistry()).activate(artifact)
