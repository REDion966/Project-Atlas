"""Phase 11.7 — Sandbox evolution execution: evidence contract.

Investigation result: development execution reuses the EXISTING
``SelfDevelopmentLoop`` (disposable ``CodeSandbox`` + ``CodeChangeSet`` +
``CodeApplier`` + E4 pytest). Production is untouched, path escapes fail
closed, and sandbox application is never equated with successful evolution.
"""

from __future__ import annotations

from atlas.evolution.capability_discovery import (
    CapabilityDiscoveryCandidate,
    DiscoveryAssessment,
    DiscoverySignalKind,
    DiscoveryVerdict,
)
from atlas.evolution.development_cycle import SuppliedChanges
from atlas.evolution.self_evolution import (
    SelfEvolutionLoop,
    SelfEvolutionTerminal,
)
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.reasoning.execution.registry import CapabilityRegistry

_MODULE = "atlas/example/sandbox_handlers.py"
_CAPABILITY = "example.sandboxed"

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


def _discovery(subject="example.missing"):
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
        verdict=DiscoveryVerdict.ACTIONABLE_GAP,
        rationale="evidence-backed",
        evidence=evidence,
    )
    return candidate, assessment


def _run(tmp_path, *, supplier=None, target_module=_MODULE, capability_name=_CAPABILITY):
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
        target_module=target_module,
        capability_name=capability_name,
        owner_approved=True,
        promotion_authorized=False,
    )


class TestPhase117SandboxExecution:
    def test_development_runs_only_inside_the_disposable_sandbox(self, tmp_path):
        result = _run(tmp_path)
        assert result.development_status == "SUCCESS"
        assert result.terminal is SelfEvolutionTerminal.PENDING_PROMOTION_REVIEW
        # Production (the live repository root) was never written to, and the
        # sandbox left nothing behind.
        assert not list(tmp_path.rglob("*"))

    def test_path_escape_is_rejected_before_execution(self, tmp_path):
        result = _run(tmp_path, target_module="../evil_handlers.py")
        assert result.terminal is SelfEvolutionTerminal.INVALID_OBJECTIVE
        assert not list(tmp_path.rglob("*"))

    def test_escaping_change_set_fails_closed(self, tmp_path):
        supplier = _StaticSupplier([("../evil.py", "VALUE = 1\n")])
        result = _run(tmp_path, supplier=supplier)
        assert result.terminal is SelfEvolutionTerminal.SANDBOX_FAILED
        assert result.ok is False
        assert not list(tmp_path.rglob("*"))

    def test_failing_change_is_recorded_and_never_success(self, tmp_path):
        supplier = _StaticSupplier(
            [(_MODULE, _MODULE_BODY)],
            {"tests/test_sandbox_handlers.py": "def test_x():\n    assert False\n"},
        )
        result = _run(tmp_path, supplier=supplier)
        assert result.terminal is SelfEvolutionTerminal.SANDBOX_FAILED
        assert result.ok is False
        assert result.failure_class  # evidence preserved
        assert not list(tmp_path.rglob("*"))

    def test_sandbox_application_alone_is_not_authorized_evolution(self, tmp_path):
        # A sandbox-applied change with no test evidence is never success.
        supplier = _StaticSupplier([(_MODULE, _MODULE_BODY)], {})
        result = _run(tmp_path, supplier=supplier)
        assert result.development_status != "SUCCESS"
        assert result.terminal is not SelfEvolutionTerminal.ACTIVATED
        assert result.activated_capabilities == ()
        assert not list(tmp_path.rglob("*"))
