"""Phase 11.9 — Failure diagnosis and bounded recovery: evidence contract.

Investigation result: diagnosis/recovery reuse the EXISTING
``DevelopmentDiagnostic``/``DevelopmentRecovery``. Retries are bounded by the
existing iteration budget; non-retryable failures stop early; a failure is
never represented as success, and no self-debugging agent is introduced.
"""

from __future__ import annotations

from atlas.evolution.capability_discovery import (
    CapabilityDiscoveryCandidate,
    DiscoveryAssessment,
    DiscoverySignalKind,
    DiscoveryVerdict,
)
from atlas.evolution.development_cycle import SuppliedChanges
from atlas.evolution.self_development_loop import SelfDevelopmentLoop
from atlas.evolution.self_evolution import (
    SelfEvolutionLoop,
    SelfEvolutionPolicy,
    SelfEvolutionTerminal,
)
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.reasoning.execution.registry import CapabilityRegistry

_MODULE = "atlas/example/recover_handlers.py"
_CAPABILITY = "example.recovered"

_MODULE_BODY = (
    "from __future__ import annotations\n"
    f"CAPABILITY_NAME = {_CAPABILITY!r}\n\n"
    "class Handlers:\n"
    "    def handlers(self):\n"
    f"        return {{{_CAPABILITY!r}: lambda p: {{'status': 'ok'}}}}\n\n"
    "    def register(self, registry):\n"
    f"        registry.register({_CAPABILITY!r}, lambda p: {{'status': 'ok'}})\n"
)


class _StaticSupplier:
    def __init__(self, code_changes, test_files=None):
        self._code = tuple(code_changes)
        self._tests = tuple((test_files or {}).items())

    def supply_changes(self, need):  # noqa: ARG002
        return SuppliedChanges(
            code_changes=self._code, test_files=self._tests, origin="test"
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


def _run(tmp_path, *, supplier=None, development_loop=None, policy=None):
    loop = SelfEvolutionLoop(
        change_supplier=supplier,
        development_loop=development_loop,
        policy=policy,
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


_FAILING_SUPPLIER = _StaticSupplier(
    [(_MODULE, _MODULE_BODY)],
    {"tests/test_recover_handlers.py": "def test_x():\n    assert False\n"},
)


class TestPhase119FailureRecovery:
    def test_failed_development_is_diagnosed_and_never_success(self, tmp_path):
        result = _run(tmp_path, supplier=_FAILING_SUPPLIER)
        assert result.terminal is SelfEvolutionTerminal.SANDBOX_FAILED
        assert result.failure_class
        assert result.recovery_strategy
        assert result.outcome.value != "successful_evolution"
        assert not list(tmp_path.rglob("*"))

    def test_nonretryable_governance_failure_stops_early(self, tmp_path):
        # A REAL SelfDevelopmentLoop whose injected promotion gate refuses:
        # the run ends GOVERNANCE_DENIED, which the diagnostic classifies as
        # non-retryable (governance / NO_RECOVERY).
        refusing = SelfDevelopmentLoop(promotion_gate=lambda proposal, outcome: False)
        result = _run(tmp_path, development_loop=refusing)
        assert result.development_status == "GOVERNANCE_DENIED"
        assert result.failure_class == "governance"
        assert result.recovery_strategy == "no_recovery"
        assert result.terminal is SelfEvolutionTerminal.SANDBOX_FAILED

    def test_bounded_retry_exhaustion_never_claims_success(self, tmp_path):
        result = _run(
            tmp_path,
            supplier=_FAILING_SUPPLIER,
            policy=SelfEvolutionPolicy(max_development_iterations=2),
        )
        assert result.development_status == "ITERATIONS_EXHAUSTED"
        assert result.ok is False
        assert result.terminal is SelfEvolutionTerminal.SANDBOX_FAILED

    def test_iteration_budget_is_hard_bounded(self):
        import pytest

        for bad in (3, 4, 10):
            if bad > 3:
                with pytest.raises(ValueError):
                    SelfEvolutionPolicy(max_development_iterations=bad)
            else:
                assert SelfEvolutionPolicy(max_development_iterations=bad)

    def test_no_unrestricted_self_debugging_agent(self):
        import atlas.evolution.self_evolution as module

        for banned in (
            "debug_loop",
            "retry_forever",
            "auto_fix",
            "run_forever",
            "daemon",
            "tick",
        ):
            assert not hasattr(module, banned)
