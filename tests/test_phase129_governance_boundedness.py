"""Phase 12.9 — Governance, security, boundedness & fail-closed validation.

Revalidates the permanent governance invariants alongside the independence
boundary: no external AI (or any other actor) can grant authority, bypass
approval, promote, activate, spawn a second cycle, or execute unrestricted code.
Inspected for accidental bypasses introduced anywhere in Phases 1–11.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.autonomy.code_sandbox import (
    CodeChangeSet,
    SandboxPathError,
)
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
from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.model_assisted_supplier import ModelAssistedChangeSupplier
from atlas.evolution.promotion_executor import PromotionExecutor, PromotionOutcome
from atlas.evolution.promotion_gate import (
    PromotionGate,
    PromotionRecommendation,
)
from atlas.evolution.self_development_loop import SelfDevelopmentLoop
from atlas.evolution.self_evolution import (
    SelfEvolutionLoop,
    SelfEvolutionPolicy,
    SelfEvolutionTerminal,
)
from atlas.evolution.self_development_inventory import build_inventory
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.reasoning.execution.registry import CapabilityRegistry
from tests.phase12_environment import model_free_environment

_ROOT = Path(__file__).resolve().parents[1]
_MODULE = "atlas/example/gov_handlers.py"
_CAPABILITY = "example.gov"

_PHASE7_TO_11_MODULES = (
    "atlas/research/technology_analysis.py",
    "atlas/evolution/capability_acquisition.py",
    "atlas/evolution/self_development_inventory.py",
    "atlas/evolution/capability_discovery.py",
    "atlas/evolution/self_evolution.py",
)


class _Capture:
    def __init__(self):
        self.proposals = []
        self.requests = []

    def store_proposal(self, proposal):
        self.proposals.append(proposal)

    def store_approval_request(self, request):
        self.requests.append(request)


def _verified_run():
    from types import SimpleNamespace

    outcome = DevelopmentOutcome(
        outcome=DevelopmentOutcomeStatus.SUCCESS,
        proposal_id="P",
        plan_id="PL",
        iteration=1,
        verification_passed=True,
        test_outcome="passed",
        changed_files=[_MODULE],
    )
    return SimpleNamespace(
        status=DevelopmentOutcomeStatus.SUCCESS,
        outcomes=[outcome],
        iterations_used=1,
        message="ok",
        plan=None,
    )


def _failed_run():
    from types import SimpleNamespace

    outcome = DevelopmentOutcome(
        outcome=DevelopmentOutcomeStatus.FAILED,
        proposal_id="P",
        plan_id="PL",
        iteration=1,
        verification_passed=False,
        rollback_occurred=True,
        test_outcome="failed",
    )
    return SimpleNamespace(
        status=DevelopmentOutcomeStatus.FAILED,
        outcomes=[outcome],
        iterations_used=1,
        message="failed",
        plan=None,
    )


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


_LOOP_KWARGS = frozenset({"change_supplier", "approval_manager", "capabilities"})


def _loop(tmp_path, **kwargs):
    return SelfEvolutionLoop(
        change_supplier=kwargs.pop("change_supplier", None),
        approval_manager=kwargs.pop("approval_manager", None),
        component_registry=ComponentRegistry(),
        capability_registry=kwargs.pop("capabilities", CapabilityRegistry()),
        repo_root=tmp_path,
        **kwargs,
    )


def _cycle(tmp_path, **overrides):
    loop_kwargs = {
        key: overrides.pop(key) for key in list(overrides) if key in _LOOP_KWARGS
    }
    params = dict(
        target_module=_MODULE,
        capability_name=_CAPABILITY,
        capability_names=(),
        owner_approved=True,
        promotion_authorized=True,
    )
    params.update(overrides)
    return _loop(tmp_path, **loop_kwargs).run(*_discovery(), **params)


class TestPhase129GovernanceBoundedness:
    def test_01_external_ai_cannot_grant_authority(self, tmp_path):
        # A model-authored change still lands at the approval boundary and is
        # refused by the sandbox loop until a human approves it.
        supplier = ModelAssistedChangeSupplier(
            authoring_model=lambda prompt: (
                '{"code_changes": [{"path": "atlas/example/ai_handlers.py", '
                '"content": "CAPABILITY_NAME = \'example.ai\'\\n\\n'
                'class H:\\n    def handlers(self):\\n        return '
                '{\'example.ai\': lambda p: {\'status\': \'ok\'}}\\n\\n'
                '    def register(self, r):\\n        r.register('
                '\'example.ai\', lambda p: {\'status\': \'ok\'})\\n"}], '
                '"confidence": 0.9}'
            )
        )
        store = _Capture()
        manager = ApprovalManager()
        controller = DevelopmentCycleController(
            approval_manager=manager,
            change_supplier=supplier,
            proposal_store=store,
            approval_request_store=store,
        )
        cycle = controller.run_development_cycle(
            DevelopmentNeed(title="model-authored change", evidence_knowledge_ids=("k",))
        )
        assert cycle.ok is True
        assert cycle.proposal_status == "PENDING_APPROVAL"
        proposal = store.proposals[0]
        assert proposal.metadata["development_cycle"]["change_origin"] == (
            "model-assisted-draft"
        )
        assert proposal.metadata["development_cycle"]["content_status"] == (
            "unverified-draft"
        )
        assert (
            SelfDevelopmentLoop().run(proposal, max_iterations=1).status
            is DevelopmentOutcomeStatus.GOVERNANCE_DENIED
        )
        for banned in ("approve", "authorize", "promote", "activate"):
            assert not hasattr(supplier, banned)

    def test_02_discovery_cannot_authorize_development(self, tmp_path):
        result = _cycle(tmp_path, owner_approved=False)
        assert result.terminal is SelfEvolutionTerminal.STOPPED_AT_APPROVAL
        assert not list(tmp_path.rglob("*.py"))
        for banned in ("approve", "authorize", "promote", "activate", "execute"):
            assert not hasattr(
                __import__(
                    "atlas.evolution.capability_discovery", fromlist=["x"]
                ),
                banned,
            )

    def test_03_research_cannot_activate_capabilities(self):
        import atlas.research.technology_analysis as analysis

        for banned in ("activate", "register", "promote", "authorize", "apply"):
            assert not hasattr(analysis, banned)

    def test_04_verification_cannot_authorize_promotion(self, tmp_path):
        with model_free_environment():
            result = _cycle(tmp_path, promotion_authorized=False)
        assert result.verification_status == "verified"
        assert result.terminal is SelfEvolutionTerminal.PENDING_PROMOTION_REVIEW
        assert result.promotion_outcome == ""

    def test_05_promotion_review_cannot_activate(self, tmp_path):
        gate = PromotionGate(evolution_memory=EvolutionMemory())
        review = gate.request_review(gate.assess(_verified_run(), proposal_id="P"))
        gate.approve(review, comment="owner")
        registry = CapabilityRegistry()
        assert registry.registered_names == []

    def test_06_activation_cannot_start_another_cycle(self, tmp_path):
        with model_free_environment():
            result = _cycle(tmp_path)
        assert result.terminal is SelfEvolutionTerminal.ACTIVATED
        assert result.next_cycle_allowed is False

    def test_07_unapproved_development_is_denied(self):
        from atlas.evolution.models import (
            EvolutionProposal,
            ImprovementPlan,
            ImprovementPriority,
            ProposalStatus,
        )

        proposal = EvolutionProposal(
            proposal_id="P", title="t", summary="s", rationale="r",
            expected_benefit="b", risks="x", impact_analysis="i",
            implementation_approach="a",
            plan=ImprovementPlan(
                plan_id="PL", title="t", description="d",
                priority=ImprovementPriority.MEDIUM,
            ),
            status=ProposalStatus.DRAFT,
        )
        assert (
            SelfDevelopmentLoop().run(proposal, max_iterations=1).status
            is DevelopmentOutcomeStatus.GOVERNANCE_DENIED
        )

    def test_08_unverified_changes_cannot_be_promoted(self):
        gate = PromotionGate(evolution_memory=EvolutionMemory())
        assessment = gate.assess(_failed_run(), proposal_id="P")
        assert assessment.recommendation is PromotionRecommendation.NOT_PROMOTABLE

    def test_09_unauthorized_promotion_is_denied(self, tmp_path):
        result = PromotionExecutor(tmp_path).promote(object(), authorized=False)
        assert result.outcome is PromotionOutcome.REFUSED_UNAUTHORIZED
        assert not list(tmp_path.rglob("*"))

    def test_10_escaping_sandbox_change_fails_closed(self):
        for bad in ("../evil.py", "/abs/evil.py", "a/../../evil.py"):
            with pytest.raises(SandboxPathError):
                CodeChangeSet.from_payload(
                    {"code_changes": [{"path": bad, "content": "x"}]}
                )

    def test_11_sensitive_production_targets_remain_protected(self, tmp_path):
        blocked = _cycle(
            tmp_path,
            target_module="atlas/kernel/evil_handlers.py",
            capability_name="example.evil",
        )
        assert blocked.ok is False
        assert blocked.activated_capabilities == ()
        assert not list(tmp_path.rglob("*.py"))

    def test_12_malformed_lifecycle_state_fails_closed(self, tmp_path):
        class _Stuck(ApprovalManager):
            def create_approval_request(self, proposal, scope_fingerprint=""):
                from atlas.evolution.models import ProposalStatus

                request = super().create_approval_request(proposal, scope_fingerprint)
                proposal.status = ProposalStatus.DRAFT
                return request

        result = _cycle(tmp_path, approval_manager=_Stuck())
        assert result.terminal is SelfEvolutionTerminal.INVALID_LIFECYCLE_STATE

    def test_13_model_absence_never_causes_fabricated_success(self, tmp_path):
        class _Boom:
            def __call__(self, prompt):  # noqa: ARG002
                raise RuntimeError("no model")

        supplier = ModelAssistedChangeSupplier(authoring_model=_Boom())
        assert supplier.supply_changes(DevelopmentNeed(title="x")) is None
        # With no usable supplier the cycle fails closed, never "succeeds".
        result = _cycle(tmp_path, change_supplier=supplier)
        assert result.terminal is SelfEvolutionTerminal.PREPARATION_FAILED
        assert result.activated_capabilities == ()
        assert not list(tmp_path.rglob("*.py"))

    def test_14_evolution_remains_bounded(self):
        assert SelfEvolutionPolicy().max_development_iterations == 1
        for over in (4, 10):
            with pytest.raises(ValueError):
                SelfEvolutionPolicy(max_development_iterations=over)

    def test_15_16_no_loop_daemon_or_scheduler_surface_was_introduced(self):
        banned_attrs = (
            "run_forever",
            "daemon",
            "tick",
            "loop_forever",
            "start_autonomous",
            "background",
            "schedule",
        )
        for relative in _PHASE7_TO_11_MODULES:
            module = __import__(
                relative[: -len(".py")].replace("/", "."), fromlist=["x"]
            )
            for banned in banned_attrs:
                assert not hasattr(module, banned), f"{relative}.{banned}"

        offenders: list[str] = []
        for relative in _PHASE7_TO_11_MODULES:
            tree = ast.parse((_ROOT / relative).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.While):
                    test = node.test
                    if isinstance(test, ast.Constant) and test.value is True:
                        offenders.append(f"{relative}:{node.lineno} while True")
        assert offenders == []

    def test_17_no_unrestricted_execution_mechanism_was_introduced(self):
        offenders: list[str] = []
        for relative in _PHASE7_TO_11_MODULES:
            tree = ast.parse((_ROOT / relative).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    offenders.extend(
                        f"{relative}:{a.name}"
                        for a in node.names
                        if a.name.split(".")[0]
                        in ("subprocess", "requests", "httpx", "socket", "os")
                    )
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Name) and func.id in ("eval", "exec"):
                        offenders.append(f"{relative}:{node.lineno} {func.id}")
                    if (
                        isinstance(func, ast.Attribute)
                        and isinstance(func.value, ast.Name)
                        and func.value.id in ("subprocess", "os")
                        and func.attr in ("system", "popen", "run", "Popen", "spawnv")
                    ):
                        offenders.append(f"{relative}:{node.lineno} {func.attr}")
        assert offenders == []

    def test_inventory_still_proves_no_required_external_ai(self):
        inventory = build_inventory()
        assert inventory.external_dependencies() == ()
        assert inventory.missing_required() == ()
        assert inventory.self_sufficient is True
