"""Phase 9.13 — Independence audit and boundary verification.

Static/structural audit of the development path: no external coding-agent or
model dependency, no governance bypass surface, no speculative autonomy, and a
self-sufficient Atlas-owned lifecycle.
"""

from __future__ import annotations

import ast
from pathlib import Path

from atlas.evolution.self_development_inventory import build_inventory

_REPO_ROOT = Path(__file__).resolve().parents[1]

_DEVELOPMENT_MODULES = (
    "atlas/evolution/development_cycle.py",
    "atlas/evolution/development_planner.py",
    "atlas/evolution/development_scaffold_supplier.py",
    "atlas/evolution/development_test_selection.py",
    "atlas/evolution/development_verification.py",
    "atlas/evolution/development_diagnostic.py",
    "atlas/evolution/development_recovery.py",
    "atlas/evolution/development_report.py",
    "atlas/evolution/development_gap.py",
    "atlas/evolution/self_development_loop.py",
    "atlas/evolution/self_development_inventory.py",
    "atlas/evolution/capability_acquisition.py",
    "atlas/evolution/capability_activation.py",
    "atlas/evolution/promotion_gate.py",
    "atlas/evolution/promotion_executor.py",
    "atlas/evolution/approval_manager.py",
    "atlas/evolution/autonomy/code_sandbox.py",
    "atlas/evolution/autonomy/code_execution.py",
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


class TestPhase913IndependenceAudit:
    def test_no_external_coding_agent_or_model_imports(self):
        for relative in _DEVELOPMENT_MODULES:
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

    def test_inventory_proves_no_required_external_dependency(self):
        inventory = build_inventory()
        assert inventory.external_dependencies() == ()
        assert inventory.missing_required() == ()
        assert inventory.self_sufficient is True

    def test_advisory_layers_have_no_mutating_surface(self):
        import atlas.evolution.capability_acquisition as acquisition
        import atlas.evolution.self_development_inventory as inventory

        for module in (acquisition, inventory):
            for banned in (
                "register",
                "activate",
                "promote",
                "apply",
                "write",
                "install",
                "execute",
            ):
                assert not hasattr(module, banned), f"{module.__name__}.{banned}"

    def test_no_speculative_autonomy_surface(self):
        from atlas.evolution.self_development_loop import SelfDevelopmentLoop

        for banned in (
            "run_forever",
            "daemon",
            "tick",
            "loop_forever",
            "start_autonomous",
        ):
            assert not hasattr(SelfDevelopmentLoop, banned)
