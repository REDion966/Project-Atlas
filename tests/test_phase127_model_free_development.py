"""Phase 12.7 — Model-Free Capability Acquisition, Development & Self-Evolution.

Validation result: the complete capability lifecycle — discovery, evolution
candidate, eligibility, objective, need, evidence gate, planning, human
approval, sandbox implementation, focused tests, verification, promotion review,
promotion authorization, activation, self-model validation, outcome learning —
runs with every external AI ecosystem unimportable and the network refused, and
spawns only local Python/pytest processes (never an external coding agent).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from atlas.evolution.capability_discovery import (
    CapabilityDiscoveryCandidate,
    DiscoveryAssessment,
    DiscoverySignalKind,
    DiscoveryVerdict,
)
from atlas.evolution.development_scaffold_supplier import ScaffoldChangeSupplier
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.self_evolution import (
    SelfEvolutionCycleResult,
    SelfEvolutionLoop,
    SelfEvolutionTerminal,
)
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.registry import CapabilityRegistry
from tests.phase12_environment import model_free_environment

_MODULE = "atlas/example/independent_handlers.py"
_CAPABILITY = "example.independent"

#: Executables that would indicate an external coding agent was invoked.
_AGENT_EXECUTABLES = (
    "cline",
    "copilot",
    "commandcode",
    "command-code",
    "codex",
    "aider",
    "claude",
    "cursor-agent",
    "ollama",
    "llm",
    "continue",
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


def _run(tmp_path, *, owner_approved=True, promotion_authorized=True, recorder=None):
    capabilities = CapabilityRegistry()
    components = ComponentRegistry()
    loop = SelfEvolutionLoop(
        change_supplier=ScaffoldChangeSupplier(),
        evolution_memory=EvolutionMemory(),
        component_registry=components,
        capability_registry=capabilities,
        repo_root=tmp_path,
    )
    candidate, assessment = _discovery()
    result = loop.run(
        candidate,
        assessment,
        target_module=_MODULE,
        capability_name=_CAPABILITY,
        capability_names=(),
        owner_approved=owner_approved,
        promotion_authorized=promotion_authorized,
    )
    return result, capabilities, components


class TestPhase127ModelFreeDevelopment:
    def test_complete_lifecycle_runs_without_any_external_ai(self, tmp_path):
        with model_free_environment() as attempts:
            result, capabilities, components = _run(tmp_path)

            assert result.terminal is SelfEvolutionTerminal.ACTIVATED
            assert result.ok is True
            # Full chain, each stage a distinct, preserved fact.
            assert result.candidate.status.value == "validated"  # proposed
            assert result.eligibility.state.value == "eligible"
            assert result.objective is not None
            assert result.development_status == "SUCCESS"  # implemented + tested
            assert result.verification_status == "verified"  # verified
            assert result.approval_status == "APPROVED"  # approved
            assert result.promotion_review_status == "approved"  # review != promotion
            assert result.promotion_outcome == "promoted"  # promoted
            assert result.activated_capabilities == (_CAPABILITY,)  # activated
            assert result.self_model.consistent is True
            assert result.outcome.value == "successful_evolution"  # learned
            assert result.next_cycle_allowed is False

            assert attempts == []
            assert capabilities.registered_names == [_CAPABILITY]
            assert (tmp_path / _MODULE).is_file()

    def test_activated_capability_is_routable_and_executable(self, tmp_path):
        with model_free_environment():
            _result, capabilities, _components = _run(tmp_path)
            results = CapabilityDispatcher(capabilities).dispatch(
                [Capability(name=_CAPABILITY)]
            )
            assert results[0].success is True

    def test_no_external_coding_agent_is_ever_spawned(self, tmp_path, monkeypatch):
        real_run = subprocess.run
        spawned: list[list[str]] = []

        def _recording_run(*args, **kwargs):
            argv = args[0] if args else kwargs.get("args")
            if isinstance(argv, (list, tuple)):
                spawned.append([str(a) for a in argv])
            return real_run(*args, **kwargs)

        monkeypatch.setattr(subprocess, "run", _recording_run)
        with model_free_environment():
            result, _capabilities, _components = _run(tmp_path)

        assert result.terminal is SelfEvolutionTerminal.ACTIVATED
        assert spawned  # the sandbox genuinely executed the focused tests
        for argv in spawned:
            basenames = [Path(part).name.lower() for part in argv if part]
            for name in _AGENT_EXECUTABLES:
                assert name not in basenames, argv
            assert any("python" in name or "pytest" in name for name in basenames), argv

    def test_production_is_not_mutated_by_the_development_engine(self, tmp_path):
        with model_free_environment():
            # Without promotion authorization nothing is written to production.
            result, capabilities, _components = _run(
                tmp_path, promotion_authorized=False
            )
            assert result.terminal is SelfEvolutionTerminal.PENDING_PROMOTION_REVIEW
            assert result.verification_status == "verified"
            assert capabilities.registered_names == []
            assert not list(tmp_path.rglob("*.py"))

    def test_verification_is_distinct_from_approval_and_promotion(self, tmp_path):
        with model_free_environment():
            verified_only, _capabilities, _components = _run(
                tmp_path, promotion_authorized=False
            )
            assert isinstance(verified_only, SelfEvolutionCycleResult)
            assert verified_only.verification_status == "verified"
            assert verified_only.promotion_outcome == ""
            assert verified_only.activated_capabilities == ()
            assert verified_only.terminal is not SelfEvolutionTerminal.ACTIVATED

    def test_unapproved_evolution_never_reaches_the_sandbox(self, tmp_path):
        with model_free_environment():
            stopped, capabilities, _components = _run(
                tmp_path, owner_approved=False
            )
            assert stopped.terminal is SelfEvolutionTerminal.STOPPED_AT_APPROVAL
            assert stopped.approval_status == "PENDING_APPROVAL"
            assert capabilities.registered_names == []
            assert not list(tmp_path.rglob("*.py"))
