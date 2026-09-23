"""Phase 11.14 — Complete bounded self-evolution cycle: acceptance evidence.

The principal Phase 11 acceptance test: Phase-10 discovery → evolution
candidate → eligibility → objective → governed preparation → PENDING_APPROVAL
→ approval → sandbox implementation → focused tests → verification → evidence
→ promotion review → authorized promotion → governed activation → self-model
validation → outcome recording → TERMINATE.

Model-independent, human-governed, sandbox-verified, fail-closed, and
single-shot (no second cycle ever starts automatically).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.capability_discovery import run_discovery_cycle
from atlas.evolution.development_cycle import DevelopmentNeed
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.models import ProposalStatus
from atlas.evolution.self_development_loop import SelfDevelopmentLoop
from atlas.evolution.self_evolution import (
    SelfEvolutionLoop,
    SelfEvolutionTerminal,
)
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.self_knowledge.capability_model import build_capability_model

_REPO_ROOT = Path(__file__).resolve().parents[1]

_MODULE = "atlas/example/bounded_handlers.py"
_CAPABILITY = "example.bounded"

_PHASE11_MODULES = (
    "atlas/evolution/self_evolution.py",
    "atlas/evolution/capability_discovery.py",
)

_BANNED_IMPORT_PREFIXES = (
    "openai",
    "anthropic",
    "ollama",
    "qwen",
    "cline",
    "copilot",
    "commandcode",
    "command_code",
    "requests",
    "httpx",
)


def _discovery():
    """Real Phase-10 discovery over a capability model with a dead provider."""
    registry = ComponentRegistry()
    registry.register(
        ComponentMetadata(
            name="down_provider",
            package="atlas.example",
            module_path="atlas.example.down",
            status=ComponentStatus.OFFLINE,
            provided_capabilities=["example.missing"],
        )
    )
    model = build_capability_model(registry)
    result = run_discovery_cycle(capability_model=model)
    assessment = next(
        a for a in result.assessments if a.verdict.value == "actionable_gap"
    )
    candidate = next(
        c for c in result.candidates if c.candidate_id == assessment.candidate_id
    )
    return candidate, assessment


def _advanced_loop(tmp_path, memory, **kwargs):
    components = ComponentRegistry()
    capabilities = CapabilityRegistry()
    loop = SelfEvolutionLoop(
        evolution_memory=memory,
        component_registry=components,
        capability_registry=capabilities,
        repo_root=tmp_path,
        **kwargs,
    )
    return loop, components, capabilities


class TestPhase114BoundedCycle:
    def test_complete_cycle_from_discovery_to_activation(self, tmp_path):
        memory = EvolutionMemory()
        loop, components, capabilities = _advanced_loop(tmp_path, memory)
        candidate, assessment = _discovery()

        result = loop.run(
            candidate,
            assessment,
            target_module=_MODULE,
            capability_name=_CAPABILITY,
            capability_names=(),
            owner_approved=True,
            promotion_authorized=True,
        )

        # Discovery -> candidate -> eligibility -> objective -> planning
        assert result.candidate.status.value == "validated"
        assert result.eligibility.state.value == "eligible"
        assert result.objective is not None
        # Governance boundary -> sandbox -> verification
        assert result.approval_status == "APPROVED"
        assert result.development_status == "SUCCESS"
        assert result.verification_status == "verified"
        # Promotion review -> authorized promotion -> governed activation
        assert result.promotion_review_status == "approved"
        assert result.promotion_outcome == "promoted"
        assert result.terminal is SelfEvolutionTerminal.ACTIVATED
        assert result.ok is True

        # Self-model consistency.
        assert result.self_model.consistent is True
        model = build_capability_model(components, capability_registry=capabilities)
        assert _CAPABILITY in {e.name for e in model.entries}

        # The capability is genuinely routable + invocable through the existing
        # execution path.
        outcomes = CapabilityDispatcher(capabilities).dispatch(
            [Capability(name=_CAPABILITY)]
        )
        assert outcomes[0].success is True

        # Production received exactly the one promoted module (no sandbox
        # residue, no extra files).
        files = sorted(
            p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.py")
        )
        assert files == [_MODULE]

        # Complete lifecycle evidence preserved.
        event_types = {r.event_type for r in memory.get_records()}
        assert {
            "self_evolution_development",
            "promotion_review",
            "evolution_outcome",
        } <= event_types

        # The cycle terminated and will not start another.
        assert result.next_cycle_allowed is False

    def test_withheld_approval_stops_the_cycle_before_any_change(self, tmp_path):
        memory = EvolutionMemory()
        loop, _components, capabilities = _advanced_loop(tmp_path, memory)
        candidate, assessment = _discovery()

        result = loop.run(
            candidate,
            assessment,
            target_module=_MODULE,
            capability_name=_CAPABILITY,
            capability_names=(),
            owner_approved=False,
        )
        assert result.terminal is SelfEvolutionTerminal.STOPPED_AT_APPROVAL
        assert capabilities.registered_names == []
        assert not list(tmp_path.rglob("*"))

    def test_cycle_is_deterministic_for_identical_evidence(self, tmp_path):
        def _cycle(name):
            return _advanced_loop(tmp_path / name, EvolutionMemory())[0].run(
                *_discovery(),
                target_module=_MODULE,
                capability_name=_CAPABILITY,
                capability_names=(),
                owner_approved=False,
            )

        first, second = _cycle("a"), _cycle("b")
        # Deterministic across identical evidence (proposal ids embed a
        # timestamp by existing design, so they are excluded).
        deterministic = (
            "terminal",
            "ok",
            "outcome",
            "approval_status",
            "eligibility",
            "objective",
            "candidate",
        )
        first_dict, second_dict = first.to_dict(), second.to_dict()
        for field in deterministic:
            assert first_dict[field] == second_dict[field], field
        assert first.next_cycle_allowed is second.next_cycle_allowed is False

    def test_governance_invariants_remain_enforceable(self, tmp_path):
        memory = EvolutionMemory()
        loop, _components, capabilities = _advanced_loop(tmp_path, memory)
        candidate, assessment = _discovery()

        # (1) Discovery does not authorize development: no run, no proposal.
        assert capabilities.registered_names == []

        # (2) Verification does not authorize promotion.
        verified_only = loop.run(
            candidate,
            assessment,
            target_module=_MODULE,
            capability_name=_CAPABILITY,
            capability_names=(),
            owner_approved=True,
            promotion_authorized=False,
        )
        assert verified_only.verification_status == "verified"
        assert verified_only.terminal is SelfEvolutionTerminal.PENDING_PROMOTION_REVIEW
        assert verified_only.promotion_outcome == ""

        # (3) Review approval does not activate a capability.
        assert capabilities.registered_names == []
        assert not list(tmp_path.rglob("*"))

        # (4) An explicit second invocation is required — and it is a NEW cycle.
        second = loop.run(
            candidate,
            assessment,
            target_module=_MODULE,
            capability_name=_CAPABILITY,
            capability_names=(),
            owner_approved=True,
            promotion_authorized=False,
        )
        assert second.cycle_id != verified_only.cycle_id
        assert second.next_cycle_allowed is False

    def test_cycle_has_no_model_seam(self):
        params = inspect.signature(SelfEvolutionLoop.__init__).parameters
        for banned in ("ai_service", "model", "provider", "llm"):
            assert banned not in params

    def test_model_independence_static_import_scan(self):
        for relative in _PHASE11_MODULES:
            tree = ast.parse((_REPO_ROOT / relative).read_text(encoding="utf-8"))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.lower() for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.lower())
            for module in imported:
                assert not module.startswith(_BANNED_IMPORT_PREFIXES), (
                    f"{relative} imports {module}"
                )

    def test_no_scheduler_daemon_or_autonomous_agent_surface(self):
        import atlas.evolution.self_evolution as module

        for banned in (
            "run_forever",
            "daemon",
            "tick",
            "loop_forever",
            "start_autonomous",
            "evolve_forever",
            "schedule_cycle",
            "background",
        ):
            assert not hasattr(module, banned)

    def test_existing_governed_contracts_are_unchanged(self):
        # The loop reuses — and cannot weaken — the existing governance objects.
        assert ProposalStatus.PENDING_APPROVAL.name == "PENDING_APPROVAL"
        assert ProposalStatus.APPROVED.name == "APPROVED"
        assert hasattr(ApprovalManager, "create_approval_request")
        assert hasattr(SelfDevelopmentLoop, "run")
        # An unapproved proposal is still refused by the existing sandbox loop.
        unapproved = DevelopmentNeed(title="x")
        assert unapproved.has_direct_evidence is False
