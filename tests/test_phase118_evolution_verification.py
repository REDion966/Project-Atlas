"""Phase 11.8 — Evolution verification: evidence contract.

Investigation result: verification reuses the EXISTING
``DevelopmentVerification``. Implementation, test execution, verification, and
acceptance stay distinct: a VERIFIED result opens a promotion review and never
activates anything by itself.
"""

from __future__ import annotations

from types import SimpleNamespace

from atlas.evolution.capability_discovery import (
    CapabilityDiscoveryCandidate,
    DiscoveryAssessment,
    DiscoverySignalKind,
    DiscoveryVerdict,
)
from atlas.evolution.development_cycle import SuppliedChanges
from atlas.evolution.development_models import DevelopmentOutcomeStatus
from atlas.evolution.self_evolution import (
    SelfEvolutionLoop,
    SelfEvolutionTerminal,
)
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.reasoning.execution.registry import CapabilityRegistry

_MODULE = "atlas/example/verify_handlers.py"
_CAPABILITY = "example.verified"

_MODULE_BODY = (
    "from __future__ import annotations\n"
    f"CAPABILITY_NAME = {_CAPABILITY!r}\n\n"
    "class Handlers:\n"
    "    def handlers(self):\n"
    f"        return {{{_CAPABILITY!r}: lambda p: {{'status': 'ok'}}}}\n\n"
    "    def register(self, registry):\n"
    f"        registry.register({_CAPABILITY!r}, lambda p: {{'status': 'ok'}})\n"
)

_TEST_BODY = (
    "import importlib.util, pathlib\n\n"
    "def test_registers():\n"
    "    path = pathlib.Path(__file__).resolve().parents[1] / "
    f"{_MODULE!r}\n"
    "    spec = importlib.util.spec_from_file_location('m', path)\n"
    "    module = importlib.util.module_from_spec(spec)\n"
    "    spec.loader.exec_module(module)\n"
    "    assert module.CAPABILITY_NAME\n"
)


class _StaticSupplier:
    def __init__(self, code_changes, test_files=None):
        self._code = tuple(code_changes)
        self._tests = tuple((test_files or {}).items())

    def supply_changes(self, need):  # noqa: ARG002
        return SuppliedChanges(
            code_changes=self._code, test_files=self._tests, origin="test"
        )


class _StubDevelopmentLoop:
    """Injected development seam that returns a fixed run result."""

    def __init__(self, result):
        self._result = result

    def run(self, proposal, max_iterations=None):  # noqa: ARG002
        return self._result


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


def _run(tmp_path, *, supplier=None, development_loop=None, authorized=False):
    loop = SelfEvolutionLoop(
        change_supplier=supplier,
        development_loop=development_loop,
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
        promotion_authorized=authorized,
    )


class TestPhase118EvolutionVerification:
    def test_verified_success_only_opens_a_promotion_review(self, tmp_path):
        supplier = _StaticSupplier(
            [(_MODULE, _MODULE_BODY)],
            {"tests/test_verify_handlers.py": _TEST_BODY},
        )
        result = _run(tmp_path, supplier=supplier)
        assert result.development_status == "SUCCESS"
        assert result.verification_status == "verified"
        assert result.promotion_review_status == "pending_review"
        assert result.terminal is SelfEvolutionTerminal.PENDING_PROMOTION_REVIEW
        assert result.activated_capabilities == ()
        assert not list(tmp_path.rglob("*"))

    def test_implementation_without_verification_is_not_verified(self, tmp_path):
        supplier = _StaticSupplier(
            [(_MODULE, _MODULE_BODY)],
            {"tests/test_verify_handlers.py": "def test_x():\n    assert False\n"},
        )
        result = _run(tmp_path, supplier=supplier)
        assert result.verification_status != "verified"
        assert result.terminal is SelfEvolutionTerminal.SANDBOX_FAILED
        assert result.activated_capabilities == ()

    def test_insufficient_verification_evidence_never_activates(self, tmp_path):
        # A run that reports SUCCESS but carries no iteration evidence cannot
        # be verified (fail-closed UNVERIFIABLE).
        stub = SimpleNamespace(
            status=DevelopmentOutcomeStatus.SUCCESS,
            outcomes=[],
            iterations_used=1,
            message="no evidence",
            plan=None,
        )
        result = _run(
            tmp_path,
            supplier=_StaticSupplier([(_MODULE, _MODULE_BODY)]),
            development_loop=_StubDevelopmentLoop(stub),
            authorized=True,
        )
        assert result.verification_status == "unverifiable"
        assert result.terminal is SelfEvolutionTerminal.VERIFICATION_FAILED
        assert result.activated_capabilities == ()
        assert not list(tmp_path.rglob("*"))

    def test_verification_success_is_not_acceptance(self, tmp_path):
        supplier = _StaticSupplier(
            [(_MODULE, _MODULE_BODY)],
            {"tests/test_verify_handlers.py": _TEST_BODY},
        )
        result = _run(tmp_path, supplier=supplier, authorized=False)
        assert result.verification_status == "verified"
        assert result.terminal is not SelfEvolutionTerminal.ACTIVATED
        assert result.promotion_outcome == ""
