"""Phase 11 — Negative-path verification: every failure mode fails closed.

Covers the required negative paths for the bounded self-evolution loop. Each
case must terminate without success, preserve evidence, and leave production
untouched.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.capability_discovery import (
    CapabilityDiscoveryCandidate,
    DiscoveryAssessment,
    DiscoverySignalKind,
    DiscoveryVerdict,
)
from atlas.evolution.development_cycle import SuppliedChanges
from atlas.evolution.development_models import DevelopmentOutcomeStatus
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.models import ProposalStatus
from atlas.evolution.promotion_gate import (
    PromotionGate,
    PromotionRecommendation,
)
from atlas.evolution.self_evolution import (
    SelfEvolutionLoop,
    SelfEvolutionPolicy,
    SelfEvolutionTerminal,
)
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.reasoning.execution.registry import CapabilityRegistry

_MODULE = "atlas/example/negative_handlers.py"
_CAPABILITY = "example.negative"

_MODULE_BODY = (
    "from __future__ import annotations\n"
    f"CAPABILITY_NAME = {_CAPABILITY!r}\n\n"
    "class Handlers:\n"
    "    def handlers(self):\n"
    f"        return {{{_CAPABILITY!r}: lambda p: {{'status': 'ok'}}}}\n\n"
    "    def register(self, registry):\n"
    f"        registry.register({_CAPABILITY!r}, lambda p: {{'status': 'ok'}})\n"
)

_FAILING_TEST = {"tests/test_negative_handlers.py": "def test_x():\n    assert False\n"}


class _StaticSupplier:
    def __init__(self, code_changes=None, test_files=None):
        self._code = tuple(code_changes or ((_MODULE, _MODULE_BODY),))
        self._tests = tuple((test_files or {}).items())

    def supply_changes(self, need):  # noqa: ARG002
        return SuppliedChanges(
            code_changes=self._code, test_files=self._tests, origin="test"
        )


class _NoChangeSupplier:
    def supply_changes(self, need):  # noqa: ARG002
        return None


class _StubDevelopmentLoop:
    def __init__(self, result):
        self._result = result

    def run(self, proposal, max_iterations=None):  # noqa: ARG002
        return self._result


class _RaisingApprovalManager(ApprovalManager):
    def approve(self, request, comment=""):  # noqa: ARG002
        raise ValueError("authorization service unavailable")


class _StuckApprovalManager(ApprovalManager):
    """Simulates an inconsistent lifecycle state at the approval boundary."""

    def create_approval_request(self, proposal, scope_fingerprint=""):
        request = super().create_approval_request(proposal, scope_fingerprint)
        proposal.status = ProposalStatus.DRAFT
        return request


class _NotReadyGate:
    def __init__(self):
        self._inner = PromotionGate()

    def assess(self, run_result, proposal_id="", change_manifest=None):
        assessment = self._inner.assess(
            run_result, proposal_id=proposal_id, change_manifest=change_manifest
        )
        return replace(
            assessment, recommendation=PromotionRecommendation.NOT_PROMOTABLE
        )

    def request_review(self, assessment, development_record_id=""):
        return self._inner.request_review(assessment, development_record_id)

    def approve(self, request, comment=""):
        return self._inner.approve(request, comment)


class _RaisingRetriever:
    def retrieve(self, query):  # noqa: ARG002
        raise RuntimeError("unverified knowledge source")


class _EmptyRetriever:
    def retrieve(self, query):  # noqa: ARG002
        return SimpleNamespace(items=[])


def _discovery(verdict=DiscoveryVerdict.ACTIONABLE_GAP, subject="example.missing"):
    evidence = (f"capability_model:{subject}",)
    candidate = CapabilityDiscoveryCandidate(
        candidate_id="disc:x",
        kind=DiscoverySignalKind.UNAVAILABLE_CAPABILITY,
        subject=subject,
        sources=("capability_model",),
        evidence=evidence,
    )
    assessment = DiscoveryAssessment(
        candidate_id="disc:x",
        subject=subject,
        verdict=verdict,
        rationale="evidence-backed",
        evidence=evidence,
        research_question=f"what is required to {subject}",
    )
    return candidate, assessment


def _loop(tmp_path, **kwargs):
    return SelfEvolutionLoop(
        component_registry=kwargs.pop("components", ComponentRegistry()),
        capability_registry=kwargs.pop("capabilities", CapabilityRegistry()),
        repo_root=tmp_path,
        **kwargs,
    )


def _run(
    tmp_path,
    *,
    verdict=DiscoveryVerdict.ACTIONABLE_GAP,
    target_module=_MODULE,
    capability_name=_CAPABILITY,
    supplier=None,
    development_loop=None,
    policy=None,
    gate=None,
    manager=None,
    memory=None,
    capabilities=None,
    knowledge_retriever=None,
    subject="example.missing",
    capability_names=(),
    dependency_blocked=False,
    governance_blocked=False,
    owner_approved=True,
    promotion_authorized=True,
):
    loop = _loop(
        tmp_path,
        change_supplier=supplier,
        development_loop=development_loop,
        policy=policy,
        promotion_gate=gate,
        approval_manager=manager,
        evolution_memory=memory,
        capabilities=capabilities,
        researcher=None,
    )
    candidate, assessment = _discovery(verdict=verdict, subject=subject)
    return loop.run(
        candidate,
        assessment,
        target_module=target_module,
        capability_name=capability_name,
        capability_names=capability_names,
        knowledge_retriever=knowledge_retriever,
        dependency_blocked=dependency_blocked,
        governance_blocked=governance_blocked,
        owner_approved=owner_approved,
        promotion_authorized=promotion_authorized,
    )


def _untouched(tmp_path):
    """True when no source file was written into the live repository root.

    Python bytecode caches (``__pycache__``/``.pyc``) created by importing an
    artifact during a REFUSED promotion are not source changes.
    """
    return [
        p for p in tmp_path.rglob("*") if p.is_file() and p.suffix != ".pyc"
    ] == []


class TestPhase11NegativePaths:
    def test_01_insufficient_evidence_is_rejected(self, tmp_path):
        result = _run(tmp_path, verdict=DiscoveryVerdict.INSUFFICIENT_EVIDENCE)
        assert result.terminal is SelfEvolutionTerminal.REJECTED_CANDIDATE
        assert _untouched(tmp_path)

    def test_02_malformed_candidate_fails_closed(self, tmp_path):
        loop = _loop(tmp_path)
        result = loop.run(None, None, target_module=_MODULE, capability_name=_CAPABILITY)
        assert result.terminal is SelfEvolutionTerminal.REJECTED_CANDIDATE
        assert _untouched(tmp_path)

    def test_03_already_supported_capability_is_ineligible(self, tmp_path):
        result = _run(tmp_path, capability_names=("example.missing",))
        assert result.terminal is SelfEvolutionTerminal.INELIGIBLE
        assert result.eligibility.state.value == "already_supported"
        assert _untouched(tmp_path)

    def test_04_missing_required_research_blocks_development(self, tmp_path):
        result = _run(tmp_path, verdict=DiscoveryVerdict.REQUIRES_RESEARCH)
        assert result.terminal is SelfEvolutionTerminal.RESEARCH_REQUIRED
        assert _untouched(tmp_path)

    def test_05_unverified_research_cannot_become_evidence(self, tmp_path):
        for retriever in (_RaisingRetriever(), _EmptyRetriever()):
            result = _run(
                tmp_path,
                verdict=DiscoveryVerdict.REQUIRES_RESEARCH,
                knowledge_retriever=retriever,
            )
            assert result.terminal is SelfEvolutionTerminal.RESEARCH_REQUIRED
        assert _untouched(tmp_path)

    def test_06_unavailable_dependency_blocks_the_candidate(self, tmp_path):
        result = _run(tmp_path, dependency_blocked=True)
        assert result.terminal is SelfEvolutionTerminal.INELIGIBLE
        assert result.eligibility.state.value == "blocked_dependency"
        assert _untouched(tmp_path)

    def test_07_invalid_objective_fails_closed(self, tmp_path):
        result = _run(tmp_path, target_module="../escape.py")
        assert result.terminal is SelfEvolutionTerminal.INVALID_OBJECTIVE
        assert _untouched(tmp_path)

    def test_08_invalid_development_plan_fails_closed(self, tmp_path):
        result = _run(tmp_path, supplier=_NoChangeSupplier())
        assert result.terminal is SelfEvolutionTerminal.PREPARATION_FAILED
        assert _untouched(tmp_path)

    def test_09_missing_approval_blocks_development(self, tmp_path):
        result = _run(tmp_path, owner_approved=False)
        assert result.terminal is SelfEvolutionTerminal.STOPPED_AT_APPROVAL
        assert result.approval_status == "PENDING_APPROVAL"
        assert _untouched(tmp_path)

    def test_10_invalid_authorization_fails_closed(self, tmp_path):
        result = _run(tmp_path, manager=_RaisingApprovalManager())
        assert result.terminal is SelfEvolutionTerminal.INVALID_LIFECYCLE_STATE
        assert _untouched(tmp_path)

    def test_11_sandbox_path_escape_is_rejected(self, tmp_path):
        result = _run(tmp_path, target_module="/etc/passwd")
        assert result.terminal is SelfEvolutionTerminal.INVALID_OBJECTIVE
        result = _run(
            tmp_path,
            supplier=_StaticSupplier([("../evil.py", "X = 1\n")]),
        )
        assert result.terminal is SelfEvolutionTerminal.SANDBOX_FAILED
        assert _untouched(tmp_path)

    def test_12_invalid_change_set_fails_closed(self, tmp_path):
        result = _run(
            tmp_path,
            supplier=_StaticSupplier(code_changes=(("", "X = 1\n"),)),
        )
        assert result.ok is False
        assert result.terminal is not SelfEvolutionTerminal.ACTIVATED
        assert _untouched(tmp_path)

    def test_13_implementation_failure_is_not_success(self, tmp_path):
        result = _run(
            tmp_path,
            supplier=_StaticSupplier(
                [(_MODULE, "raise RuntimeError('boom')\n")], _FAILING_TEST
            ),
        )
        assert result.terminal is SelfEvolutionTerminal.SANDBOX_FAILED
        assert result.outcome.value != "successful_evolution"

    def test_14_failing_test_is_not_success(self, tmp_path):
        result = _run(
            tmp_path, supplier=_StaticSupplier(test_files=_FAILING_TEST)
        )
        assert result.terminal is SelfEvolutionTerminal.SANDBOX_FAILED
        assert result.ok is False
        assert _untouched(tmp_path)

    def test_15_insufficient_verification_evidence_is_not_verified(self, tmp_path):
        stub = SimpleNamespace(
            status=DevelopmentOutcomeStatus.SUCCESS,
            outcomes=[],
            iterations_used=1,
            message="no evidence",
            plan=None,
        )
        result = _run(
            tmp_path,
            supplier=_StaticSupplier(),
            development_loop=_StubDevelopmentLoop(stub),
        )
        assert result.verification_status == "unverifiable"
        assert result.terminal is SelfEvolutionTerminal.VERIFICATION_FAILED
        assert _untouched(tmp_path)

    def test_16_nonretryable_diagnosis_stops_the_cycle(self, tmp_path):
        from atlas.evolution.self_development_loop import SelfDevelopmentLoop

        refusing = SelfDevelopmentLoop(promotion_gate=lambda proposal, outcome: False)
        result = _run(tmp_path, development_loop=refusing)
        assert result.terminal is SelfEvolutionTerminal.SANDBOX_FAILED
        assert result.failure_class == "governance"
        assert result.recovery_strategy == "no_recovery"
        assert _untouched(tmp_path)

    def test_17_bounded_retry_exhaustion_never_succeeds(self, tmp_path):
        result = _run(
            tmp_path,
            supplier=_StaticSupplier(test_files=_FAILING_TEST),
            policy=SelfEvolutionPolicy(max_development_iterations=3),
        )
        assert result.development_status == "ITERATIONS_EXHAUSTED"
        assert result.ok is False
        assert result.terminal is SelfEvolutionTerminal.SANDBOX_FAILED
        assert _untouched(tmp_path)

    def test_18_promotion_without_a_valid_review_is_refused(self, tmp_path):
        result = _run(tmp_path, gate=_NotReadyGate())
        assert result.terminal is SelfEvolutionTerminal.PROMOTION_NOT_READY
        assert result.promotion_outcome == ""
        assert _untouched(tmp_path)

    def test_19_activation_without_authorized_promotion_is_refused(self, tmp_path):
        capabilities = CapabilityRegistry()
        result = _run(tmp_path, promotion_authorized=False, capabilities=capabilities)
        assert result.terminal is SelfEvolutionTerminal.PENDING_PROMOTION_REVIEW
        assert capabilities.registered_names == []
        assert _untouched(tmp_path)

    def test_20_duplicate_capability_activation_fails_closed(self, tmp_path):
        capabilities = CapabilityRegistry()
        capabilities.register(_CAPABILITY, lambda params: None)
        result = _run(tmp_path, capabilities=capabilities)
        assert result.terminal is SelfEvolutionTerminal.PROMOTION_FAILED
        assert result.activated_capabilities == ()
        assert _untouched(tmp_path)

    def test_21_registry_or_model_inconsistency_fails_closed(self, tmp_path):
        from atlas.reasoning.execution.registry import CapabilityRegistry as _R

        class _Inert(_R):
            def register(self, name, handler):  # noqa: ARG002
                return None

            def unregister(self, name):  # noqa: ARG002
                return None

        result = _run(tmp_path, capabilities=_Inert())
        assert result.terminal is SelfEvolutionTerminal.SELF_MODEL_INCONSISTENT
        assert result.self_model.consistent is False
        assert result.ok is False

    def test_22_production_mutation_attempt_fails_closed(self, tmp_path):
        # Unauthorized cycle: nothing written anywhere.
        assert _untouched(tmp_path)
        _run(tmp_path, owner_approved=False)
        assert _untouched(tmp_path)
        # Protected surfaces cannot be targeted.
        blocked = _run(
            tmp_path,
            target_module="atlas/kernel/evil_handlers.py",
            capability_name="example.evil",
        )
        assert blocked.ok is False
        assert not (tmp_path / "atlas" / "kernel").exists()
        assert _untouched(tmp_path)

    def test_23_external_model_unavailable_still_completes(self, tmp_path):
        # No AI provider seam exists: the deterministic path completes anyway.
        result = _run(tmp_path)
        assert result.terminal is SelfEvolutionTerminal.ACTIVATED
        assert result.activated_capabilities == (_CAPABILITY,)

    def test_24_malformed_lifecycle_state_fails_closed(self, tmp_path):
        result = _run(tmp_path, manager=_StuckApprovalManager())
        assert result.terminal is SelfEvolutionTerminal.INVALID_LIFECYCLE_STATE
        assert _untouched(tmp_path)

    def test_25_no_automatic_second_evolution_cycle(self, tmp_path):
        memory = EvolutionMemory()
        result = _run(tmp_path, memory=memory)
        assert result.terminal is SelfEvolutionTerminal.ACTIVATED
        assert result.next_cycle_allowed is False
        # Exactly one cycle's worth of outcome records exists; nothing chained.
        records = memory.get_records_by_type("evolution_outcome")
        assert len(records) == 1
        assert records[0].metadata["cycle_id"] == result.cycle_id

    def test_every_negative_path_preserves_evidence(self, tmp_path):
        memory = EvolutionMemory()
        for kwargs in (
            {"owner_approved": False},
            {"verdict": DiscoveryVerdict.INSUFFICIENT_EVIDENCE},
            {"verdict": DiscoveryVerdict.REQUIRES_RESEARCH},
            {"dependency_blocked": True},
        ):
            result = _run(tmp_path / "evidence", memory=memory, **kwargs)
            assert result.outcome is not None
            assert result.terminal is not SelfEvolutionTerminal.ACTIVATED
        assert memory.get_records_by_type("evolution_outcome")
