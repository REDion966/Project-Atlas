"""Phase 13.9 — Continuous evolution without external AI: evidence contract.

Validation result: the continuation mechanism introduces no external AI, model,
or coding-agent dependency, and the whole continuity path runs under the Phase
12 model-free environment.
"""

from __future__ import annotations

import ast
from pathlib import Path

from atlas.evolution.evolution_continuity import (
    EvolutionOpportunityState,
    continuation_view,
    gate_candidates,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.self_knowledge.independence_inventory import (
    PROHIBITED_AI_MODULES,
    build_independence_inventory,
    repository_root,
)
from tests.phase12_environment import BLOCKED_MODULES, model_free_environment
from tests.phase13_support import candidate, record_outcome, run_cycle

_ROOT = Path(__file__).resolve().parents[1]
_NEW_MODULES = (
    "atlas/evolution/evolution_continuity.py",
)


class TestPhase139Independence:
    def test_new_module_imports_nothing_external_or_prohibited(self):
        for relative in _NEW_MODULES:
            tree = ast.parse((_ROOT / relative).read_text(encoding="utf-8"))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0].lower() for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0].lower())
            for name in imported:
                for prefix in PROHIBITED_AI_MODULES:
                    assert not name.startswith(prefix), f"{relative} -> {name}"
                assert name.split(".")[0] not in BLOCKED_MODULES, name

    def test_repository_inventory_still_reports_no_required_ai(self):
        inventory = build_independence_inventory(repository_root())
        assert inventory.required_ai_dependencies() == ()
        assert inventory.prohibited_ai_imports == ()
        assert inventory.unknown_dependencies == ()

    def test_continuity_and_a_full_cycle_run_with_every_ai_blocked(self, tmp_path):
        with model_free_environment() as attempts:
            memory = EvolutionMemory()
            record_outcome(
                memory,
                cycle_id="SEV-1",
                subject="cap.prior",
                terminal="activated",
                outcome_kind="successful_evolution",
            )
            view = continuation_view(memory)
            assert view.for_subject("cap.prior").state is (
                EvolutionOpportunityState.COMPLETED
            )
            assert gate_candidates([candidate("cap.prior")[0]], view).admitted == ()

            result = run_cycle(
                memory,
                tmp_path,
                subject="cap.fresh",
                capability="example.independent",
                module="atlas/example/independent_handlers.py",
                promotion_authorized=False,
            )
            assert result.verification_status == "verified"
            assert result.next_cycle_allowed is False
            assert attempts == []

    def test_no_ai_sdk_is_imported_by_the_continuity_path(self):
        import sys

        leaked = [
            name
            for name in sys.modules
            if any(
                name == p or name.startswith(p + ".")
                for p in ("openai", "anthropic", "ollama", "litellm")
            )
        ]
        assert leaked == []
