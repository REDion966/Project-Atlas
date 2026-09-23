"""Phase 10.8 — Governed self-directed discovery cycle: evidence contract.

Investigation result: ``run_discovery_cycle`` is ONE bounded, deterministic,
model-independent invocation: landscape → signals → candidates → assessments →
optional research requests → advisory hand-off. It is read-only and never
develops, approves, promotes, activates, or loops.
"""

from __future__ import annotations

import ast
from pathlib import Path

from atlas.evolution.capability_discovery import (
    DiscoverySignal,
    DiscoverySignalKind,
    DiscoverySourceKind,
    run_discovery_cycle,
)
from atlas.reasoning.execution.registry import CapabilityRegistry

_REPO_ROOT = Path(__file__).resolve().parents[1]

_PHASE10_MODULES = (
    "atlas/evolution/capability_discovery.py",
    "atlas/evolution/self_development_inventory.py",
    "atlas/evolution/capability_acquisition.py",
)


def _signal(subject="cap.x"):
    return DiscoverySignal(
        DiscoverySignalKind.OBSERVED_FAILURE,
        subject,
        DiscoverySourceKind.EXPERIENCE,
        evidence=(f"experience:{subject}",),
    )


class TestPhase108DiscoveryCycle:
    def test_bounded_single_cycle_is_deterministic(self):
        first = run_discovery_cycle(extra_signals=[_signal()]).to_dict()
        second = run_discovery_cycle(extra_signals=[_signal()]).to_dict()
        assert first == second

    def test_cycle_is_read_only_and_never_activates(self):
        registry = CapabilityRegistry()
        result = run_discovery_cycle(human_goal="add a scheduling capability")
        assert result.handoffs  # advisory hand-off produced
        # But nothing was registered/activated anywhere.
        assert registry.registered_names == []

    def test_no_evidence_yields_no_candidates(self):
        bare = DiscoverySignal(
            DiscoverySignalKind.OBSERVED_FAILURE, "cap.x", DiscoverySourceKind.EXPERIENCE
        )
        result = run_discovery_cycle(extra_signals=[bare])
        assert result.candidates == ()
        assert result.assessments == ()

    def test_blank_or_vague_goal_yields_nothing(self):
        assert run_discovery_cycle(human_goal="   ").candidates == ()

    def test_unavailable_dependency_blocks_a_candidate(self):
        result = run_discovery_cycle(
            extra_signals=[_signal("cap.x")], dependency_blocked_subjects=["cap.x"]
        )
        assert result.assessments[0].verdict.value == "blocked_dependency"
        assert result.handoffs == ()

    def test_model_independence_import_scan(self):
        banned = (
            "openai",
            "anthropic",
            "ollama",
            "qwen",
            "cline",
            "copilot",
            "commandcode",
            "requests",
            "httpx",
        )
        for relative in _PHASE10_MODULES:
            tree = ast.parse((_REPO_ROOT / relative).read_text(encoding="utf-8"))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.lower() for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.lower())
            for module in imported:
                assert not module.startswith(banned), f"{relative} imports {module}"

    def test_no_autonomous_loop_surface(self):
        import atlas.evolution.capability_discovery as discovery

        for banned in ("run_forever", "daemon", "tick", "loop_forever"):
            assert not hasattr(discovery, banned)
