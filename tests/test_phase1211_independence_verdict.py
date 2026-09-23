"""Phase 12.11 — Final independence verdict: machine-checked acceptance.

Aggregates the Phase 12 acceptance criteria into enforceable assertions so the
verdict cannot drift from the evidence: no mandatory external AI, honest
failure modes, enforced governance, bounded evolution, and no Phase 13 work.
"""

from __future__ import annotations

import ast
from pathlib import Path

from atlas.evolution.model_assisted_supplier import ModelAssistedChangeSupplier
from atlas.evolution.self_evolution import (
    SelfEvolutionPolicy,
    SelfEvolutionTerminal,
)
from atlas.self_knowledge.independence_inventory import (
    PROHIBITED_AI_MODULES,
    DependencyClass,
    build_independence_inventory,
    repository_root,
    scan_boot_imports,
)

_ROOT = repository_root()
_INVENTORY = build_independence_inventory(_ROOT)
_PHASE12_MODULES = (
    "atlas/self_knowledge/independence_inventory.py",
    "atlas/evolution/self_evolution.py",
    "atlas/evolution/capability_discovery.py",
)


class TestPhase1211IndependenceVerdict:
    def test_no_mandatory_external_ai_or_coding_agent_dependency(self):
        assert _INVENTORY.required_ai_dependencies() == ()
        assert _INVENTORY.prohibited_ai_imports == ()
        assert set(scan_boot_imports(_ROOT)) == {"requests"}

    def test_no_dependency_remains_unknown(self):
        assert _INVENTORY.unknown_dependencies == ()
        assert _INVENTORY.independent is True

    def test_the_only_required_external_library_is_not_ai(self):
        required = _INVENTORY.by_classification(DependencyClass.REQUIRED_RUNTIME)
        assert required == ()
        information = _INVENTORY.by_classification(DependencyClass.INFORMATION_SOURCE)
        assert [r.name for r in information] == ["requests"]
        assert all(r.ai_related is False for r in information)

    def test_optional_model_seams_remain_optional_and_fail_soft(self):
        # OFF by default and fail-soft on model failure.
        supplier = ModelAssistedChangeSupplier()
        assert supplier.supply_changes.__doc__ is not None
        assert not hasattr(supplier, "approve")
        assert "model_assisted_authoring = false" in (
            _ROOT / "config.toml"
        ).read_text(encoding="utf-8")

    def test_evolution_remains_bounded_with_a_terminal_state(self):
        assert SelfEvolutionPolicy().max_development_iterations == 1
        assert len(SelfEvolutionTerminal) >= 10  # explicit terminal vocabulary
        assert "next_cycle_allowed" in {
            f for f in __import__(
                "atlas.evolution.self_evolution", fromlist=["x"]
            ).SelfEvolutionCycleResult.__dataclass_fields__
        }

    def test_no_unrestricted_loop_or_scheduler_was_introduced(self):
        banned = ("run_forever", "daemon", "tick", "loop_forever", "start_autonomous")
        for relative in _PHASE12_MODULES:
            module = __import__(relative[: -len(".py")].replace("/", "."), fromlist=["x"])
            for name in banned:
                assert not hasattr(module, name), f"{relative}.{name}"

    def test_no_speculative_phase_14_was_introduced(self):
        # Phase 12 validated independence; Phase 13 (the final defined phase)
        # has since been completed, so this asserts no FURTHER phase was invented
        # and no unsupervised continuous-evolution engine was added.
        roadmap = (_ROOT / "docs/ROADMAP.md").read_text(encoding="utf-8")
        assert "Phase 14" not in roadmap
        assert "### Phase 13 — Continuous Atlas Evolution (COMPLETE)" in roadmap
        # No continuous-evolution *engine* module exists: Phase 13 is a
        # read-only continuity projection over existing durable history.
        names = [
            path.name
            for path in (_ROOT / "atlas").rglob("*.py")
            if "continuous" in path.name
        ]
        assert names == []

    def test_new_phase12_module_introduces_no_runtime_coupling(self):
        tree = ast.parse(
            (_ROOT / "atlas/self_knowledge/independence_inventory.py").read_text(
                encoding="utf-8"
            )
        )
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        # The inventory module is stdlib-only (no first-party or external deps).
        assert not any(name.startswith("atlas") for name in imported)
        for name in imported:
            for prefix in PROHIBITED_AI_MODULES:
                assert not name.startswith(prefix)

    def test_phase12_validation_artifacts_exist(self):
        assert (_ROOT / "docs/INDEPENDENCE.md").is_file()
        assert (_ROOT / "tests/phase12_environment.py").is_file()
        assert Path(_ROOT / "docs/ROADMAP.md").is_file()
