"""Phase 6.12 — Model-independent development engine: evidence contract.

Investigation result: the core development lifecycle is deterministic and works
with no external AI model. No production change was needed.

Verification: (a) static — no provider SDK/network imports on the development
modules (the optional model-assisted supplier is an injected, opt-in seam and is
never a required dependency); (b) runtime — the governed preparation cycle runs
with no AI service involved.
"""

from __future__ import annotations

import ast
from pathlib import Path

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.development_cycle import (
    DevelopmentCycleController,
    DevelopmentNeed,
)
from atlas.evolution.development_scaffold_supplier import ScaffoldChangeSupplier

_REPO_ROOT = Path(__file__).resolve().parents[1]

_DEVELOPMENT_MODULES = (
    "atlas/evolution/development_cycle.py",
    "atlas/evolution/development_planner.py",
    "atlas/evolution/development_models.py",
    "atlas/evolution/development_verification.py",
    "atlas/evolution/development_test_selection.py",
    "atlas/evolution/development_diagnostic.py",
    "atlas/evolution/development_recovery.py",
    "atlas/evolution/development_driver.py",
    "atlas/evolution/development_usefulness.py",
    "atlas/evolution/development_report.py",
    "atlas/evolution/development_scaffold_supplier.py",
    "atlas/evolution/development_authorization.py",
    "atlas/evolution/development_envelope.py",
    "atlas/evolution/development_gap.py",
    "atlas/evolution/self_development_loop.py",
    "atlas/evolution/promotion_gate.py",
    "atlas/evolution/promotion_executor.py",
    "atlas/evolution/capability_activation.py",
    "atlas/evolution/approval_manager.py",
    "atlas/evolution/autonomy/code_sandbox.py",
    "atlas/evolution/autonomy/code_execution.py",
)


class _CaptureStore:
    def __init__(self):
        self.proposals = []

    def store_proposal(self, proposal):
        self.proposals.append(proposal)


class TestPhase612ModelIndependence:
    def test_development_modules_have_no_provider_or_network_imports(self):
        banned = ("openai", "anthropic", "ollama", "requests", "httpx")
        for relative in _DEVELOPMENT_MODULES:
            tree = ast.parse((_REPO_ROOT / relative).read_text(encoding="utf-8"))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            for module in imported:
                assert not module.startswith(banned), f"{relative} imports {module}"

    def test_scaffold_authoring_is_deterministic(self):
        need = DevelopmentNeed(
            title="t",
            metadata={
                "scaffold": {
                    "module": "atlas/example/widget_handlers.py",
                    "capability_name": "example.widget",
                }
            },
        )
        first = ScaffoldChangeSupplier().supply_changes(need)
        second = ScaffoldChangeSupplier().supply_changes(need)
        assert first.code_changes == second.code_changes
        assert first.test_files == second.test_files

    def test_development_preparation_runs_without_any_ai_service(self):
        store = _CaptureStore()
        controller = DevelopmentCycleController(
            approval_manager=ApprovalManager(),
            change_supplier=ScaffoldChangeSupplier(),
            proposal_store=store,
        )
        result = controller.run_development_cycle(
            DevelopmentNeed(
                title="add a widget capability",
                evidence_knowledge_ids=("k",),
                metadata={
                    "scaffold": {
                        "module": "atlas/example/widget_handlers.py",
                        "capability_name": "example.widget",
                    }
                },
            )
        )
        assert result.ok is True
        assert result.proposal_status == "PENDING_APPROVAL"
        assert store.proposals
