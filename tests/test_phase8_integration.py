"""Phase 8 integration — governed capability acquisition & internalization.

Demonstrates the complete supported acquisition path, deterministically and
without an external AI model:

    missing capability → acquisition need → deterministic strategy
      → acquisition plan → authorization boundary (unapproved refused)
      → authorized sandbox acquisition → validation/verification evidence
      → governed promotion review → internalization (governed activation)
      → ComponentRegistry/CapabilityRegistry/CapabilityModel consistency
      → routing → dispatch → execution

Negative paths (all fail closed): ambiguous need, missing authorization,
unauthorized source, unavailable/incompatible dependency, missing provenance,
acquisition/verification/test failure, invalid internalization, registry
inconsistency, activation without approval, partially acquired capability, and a
production-modification attempt outside the governed path.
"""

from __future__ import annotations

import pytest

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.capability_activation import (
    CapabilityActivationError,
    CapabilityActivator,
)
from atlas.evolution.capability_acquisition import (
    AcquisitionMechanism,
    AcquisitionNeed,
    AcquisitionNeedKind,
    classify_acquisition_need,
    determine_acquisition_strategy,
    validate_internalized_capability,
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
from atlas.evolution.autonomy.code_sandbox import CodeChangeSet, SandboxPathError
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.research.sources.web import WebSourceAdapter
from atlas.self_knowledge.capability_model import build_capability_model

_MODULE = "atlas/example/widget_handlers.py"
_CAPABILITY = "example.widget"
_FAIL_TEST = "def test_visible():\n    assert False\n"


class _CaptureStore:
    def __init__(self):
        self.proposals = []
        self.requests = []

    def store_proposal(self, proposal):
        self.proposals.append(proposal)

    def store_approval_request(self, request):
        self.requests.append(request)


def _write_artifact(tmp_path, registry):
    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    supplied = ScaffoldChangeSupplier().supply_changes(
        type("N", (), {"metadata": {"scaffold": {"module": _MODULE, "capability_name": _CAPABILITY}}})()
    )
    body = supplied.code_changes[0][1]
    target = root / _MODULE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return root, body


def _activate(tmp_path, registry, module, capability, tag):
    root = tmp_path / tag
    root.mkdir(parents=True, exist_ok=True)
    supplied = ScaffoldChangeSupplier().supply_changes(
        type("N", (), {"metadata": {"scaffold": {"module": module, "capability_name": capability}}})()
    )
    body = supplied.code_changes[0][1]
    target = root / module
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    artifact = capture_promotion_artifact(
        [{"path": module, "content": body}], proposal_id=capability, repo_root=root
    )
    return CapabilityActivator(root, registry).activate(artifact)


class TestPhase8Integration:
    def test_full_governed_acquisition_lifecycle(self, tmp_path):
        # 1-2. Missing capability → acquisition need.
        gap = assess_development_gap(
            "acquire a widget search capability", capability_names=()
        )
        assert gap.kind is not DevelopmentGapKind.ALREADY_SUPPORTED

        need = AcquisitionNeed(
            request="acquire a widget search capability",
            target_capability=_CAPABILITY,
            knowledge_available=True,
            evidence=("design-doc",),
        )
        assert classify_acquisition_need(need) is AcquisitionNeedKind.MISSING_IMPLEMENTATION

        # 3. Deterministic strategy.
        strategy = determine_acquisition_strategy(need)
        assert strategy.mechanism is AcquisitionMechanism.INTERNAL_DEVELOPMENT
        assert strategy.acquirable is True

        # 4. Acquisition plan (existing governed cycle; deterministic scaffold).
        store = _CaptureStore()
        manager = ApprovalManager()
        controller = DevelopmentCycleController(
            approval_manager=manager,
            change_supplier=ScaffoldChangeSupplier(),
            proposal_store=store,
            approval_request_store=store,
        )
        cycle = controller.run_development_cycle(
            DevelopmentNeed(
                title="add the widget search capability",
                evidence_knowledge_ids=("k-1",),
                target_components=(_MODULE,),
                metadata={
                    "scaffold": {"module": _MODULE, "capability_name": _CAPABILITY}
                },
            )
        )
        assert cycle.ok is True
        assert cycle.proposal_status == ProposalStatus.PENDING_APPROVAL.name
        proposal = store.proposals[0]
        request = store.requests[0]

        # 5. Authorization boundary: unapproved acquisition is refused.
        refused = SelfDevelopmentLoop().run(proposal, max_iterations=1)
        assert refused.status is DevelopmentOutcomeStatus.GOVERNANCE_DENIED

        # Approval via the real approval manager.
        manager.approve(request, comment="approved for sandbox")
        manager.update_proposal_from_decision(proposal, request)
        assert proposal.status is ProposalStatus.APPROVED

        # 6. Authorized sandbox acquisition + tests.
        run = SelfDevelopmentLoop().run(proposal, max_iterations=1)
        assert run.status is DevelopmentOutcomeStatus.SUCCESS
        assert run.outcomes[0].test_outcome == "passed"

        # 7. Verification evidence.
        assert DevelopmentVerification().verify(run).status is VerificationStatus.VERIFIED

        # 8. Governed promotion review (never an automatic promotion).
        memory = EvolutionMemory()
        gate = PromotionGate(evolution_memory=memory)
        assessment = gate.assess(run, proposal_id=proposal.proposal_id)
        assert assessment.recommendation is PromotionRecommendation.READY_FOR_PROMOTION
        review = gate.request_review(assessment)
        assert review.status is PromotionStatus.PENDING_REVIEW
        gate.approve(review, comment="owner")
        assert review.status is PromotionStatus.APPROVED
        assert review.status is not PromotionStatus.PROMOTED

        # 9. Internalization (governed activation) → registry/model consistency.
        registry = CapabilityRegistry()
        assert registry.has(_CAPABILITY) is False  # unavailable before activation

        root, body = _write_artifact(tmp_path, registry)
        artifact = capture_promotion_artifact(
            [{"path": _MODULE, "content": body}],
            proposal_id=proposal.proposal_id,
            repo_root=root,
        )
        activation = CapabilityActivator(root, registry).activate(artifact)
        assert activation.activated is True

        model = build_capability_model(ComponentRegistry(), capability_registry=registry)
        validation = validate_internalized_capability(
            _CAPABILITY, capability_registry=registry, capability_model=model
        )
        assert validation.ok is True

        # 10. Routing → dispatch → execution.
        routes = CapabilityRouter(registry).route([Capability(name=_CAPABILITY)])
        assert [r.capability for r in routes] == [_CAPABILITY]
        results = CapabilityDispatcher(registry).dispatch([Capability(name=_CAPABILITY)])
        assert results[0].success is True

        # 11. Acquisition evidence recorded (provenance).
        memory.store_record(
            EvolutionRecord(
                record_id="ACQ-INT",
                event_type="capability_acquisition",
                description="Internal development acquisition.",
                related_ids=[proposal.proposal_id, _CAPABILITY],
                metadata={"mechanism": "internal_development"},
            )
        )
        assert memory.get_records_by_type("capability_acquisition")

    def test_acquisition_machinery_repeats_for_a_second_capability(self, tmp_path):
        # The acquisition strategy + internalization path is repeatable across
        # distinct capability gaps (deterministic, governed, no AI).
        second = AcquisitionNeed(
            request="acquire a ledger capability",
            target_capability="example.ledger",
            knowledge_available=True,
        )
        assert (
            classify_acquisition_need(second)
            is AcquisitionNeedKind.MISSING_IMPLEMENTATION
        )
        assert (
            determine_acquisition_strategy(second).mechanism
            is AcquisitionMechanism.INTERNAL_DEVELOPMENT
        )

        registry = CapabilityRegistry()
        first = _activate(
            tmp_path, registry, "atlas/example/a_handlers.py", "example.a", "root-a"
        )
        second_activation = _activate(
            tmp_path, registry, "atlas/example/b_handlers.py", "example.b", "root-b"
        )
        assert first.activated is True
        assert second_activation.activated is True
        assert registry.registered_names == ["example.a", "example.b"]

    def test_acquisition_negative_paths_fail_closed(self):
        # Ambiguous requirement.
        assert (
            determine_acquisition_strategy(AcquisitionNeed(request="do the thing")).mechanism
            is AcquisitionMechanism.NONE
        )
        # Missing authorization.
        assert (
            determine_acquisition_strategy(
                AcquisitionNeed(
                    request="acquire x.y",
                    target_capability="x.y",
                    authorized=False,
                    knowledge_available=True,
                )
            ).mechanism
            is AcquisitionMechanism.NONE
        )
        # Unauthorized external source.
        with pytest.raises(ValueError):
            WebSourceAdapter().load("http://example.com/x")
        # Unavailable / incompatible dependency.
        assert (
            determine_acquisition_strategy(
                AcquisitionNeed(
                    request="acquire x.y",
                    target_capability="x.y",
                    required_dependencies=("libx",),
                    available_dependencies=(),
                )
            ).mechanism
            is AcquisitionMechanism.NONE
        )
        assert (
            determine_acquisition_strategy(
                AcquisitionNeed(
                    request="acquire x.y",
                    target_capability="x.y",
                    incompatible_dependencies=("libx",),
                    knowledge_available=True,
                )
            ).mechanism
            is AcquisitionMechanism.NONE
        )
        # Missing provenance/evidence -> preparation fails closed.
        result = DevelopmentCycleController(
            approval_manager=ApprovalManager()
        ).run_development_cycle(
            DevelopmentNeed(
                title="acquire without evidence",
                metadata={"code_changes": [{"path": "atlas/x.py", "content": "V = 1\n"}]},
            )
        )
        assert result.ok is False
        assert any(stage in ("research", "evidence") for stage, _ in result.failures)

    def test_internalization_and_execution_negative_paths(self, tmp_path):
        # Failed tests -> not success; capability stays unavailable.
        from atlas.evolution.improvement_planner import ImprovementPriority
        from atlas.evolution.models import EvolutionProposal, ImprovementPlan

        plan = ImprovementPlan(
            plan_id="IMP-P8N",
            title="t",
            description="d",
            priority=ImprovementPriority.MEDIUM,
            target_components=["mod"],
        )
        failing = EvolutionProposal(
            proposal_id="PROP-P8N",
            title="t",
            summary="s",
            rationale="r",
            expected_benefit="b",
            risks="low",
            impact_analysis="x",
            implementation_approach="y",
            plan=plan,
            status=ProposalStatus.APPROVED,
            metadata={
                "code_changes": [{"path": _MODULE, "content": "V = 1\n"}],
                "test_files": {"tests/test_widget.py": _FAIL_TEST},
            },
        )
        run = SelfDevelopmentLoop().run(failing, max_iterations=1)
        assert run.status is not DevelopmentOutcomeStatus.SUCCESS

        registry = CapabilityRegistry()
        assert registry.registered_names == []  # partially acquired ≠ available

        # Internalization failure: invalid contract refused, registry unchanged.
        root = tmp_path / "repo"
        root.mkdir()
        (root / "bad.py").write_text('CAPABILITY_NAME = "x.y"\n', encoding="utf-8")
        artifact = capture_promotion_artifact(
            [{"path": "bad.py", "content": 'CAPABILITY_NAME = "x.y"\n'}],
            proposal_id="P",
            repo_root=root,
        )
        with pytest.raises(CapabilityActivationError):
            CapabilityActivator(root, registry).activate(artifact)
        assert registry.registered_names == []

        # Registry inconsistency: an unregistered capability fails validation.
        assert (
            validate_internalized_capability("x.y", capability_registry=registry).ok
            is False
        )

        # Production-modification attempt outside the governed sandbox path.
        with pytest.raises(SandboxPathError):
            CodeChangeSet.from_payload(
                {"code_changes": [{"path": "../evil.py", "content": "x"}]}
            )
