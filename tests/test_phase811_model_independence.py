"""Phase 8.11 — Model independence and Phase 8 boundary verification.

Investigation result: the acquisition strategy/validation layer and the existing
governed acquisition path are deterministic and require no external AI model.
The strategic layer is advisory only — it never installs, executes, promotes, or
activates anything.
"""

from __future__ import annotations

import ast
from pathlib import Path

from atlas.evolution.capability_acquisition import (
    AcquisitionNeed,
    determine_acquisition_strategy,
    validate_internalized_capability,
)
from atlas.reasoning.execution.registry import CapabilityRegistry

_REPO_ROOT = Path(__file__).resolve().parents[1]

_PHASE8_MODULES = (
    "atlas/evolution/capability_acquisition.py",
    "atlas/evolution/capability_activation.py",
    "atlas/evolution/development_cycle.py",
    "atlas/evolution/development_planner.py",
    "atlas/evolution/development_verification.py",
    "atlas/evolution/development_scaffold_supplier.py",
    "atlas/evolution/promotion_gate.py",
    "atlas/evolution/promotion_executor.py",
    "atlas/evolution/self_development_loop.py",
    "atlas/evolution/development_authorization.py",
    "atlas/evolution/development_envelope.py",
    "atlas/evolution/autonomy/code_sandbox.py",
)


class TestPhase811ModelIndependence:
    def test_phase8_modules_have_no_provider_or_network_imports(self):
        banned = ("openai", "anthropic", "ollama", "requests", "httpx")
        for relative in _PHASE8_MODULES:
            tree = ast.parse((_REPO_ROOT / relative).read_text(encoding="utf-8"))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            for module in imported:
                assert not module.startswith(banned), f"{relative} imports {module}"

    def test_strategy_and_validation_are_model_free(self):
        strategy = determine_acquisition_strategy(
            AcquisitionNeed(
                request="acquire widget search capability",
                target_capability="widget.search",
                knowledge_available=True,
            )
        )
        registry = CapabilityRegistry()
        registry.register("widget.search", lambda params: None)
        validation = validate_internalized_capability(
            "widget.search", capability_registry=registry
        )
        assert strategy.acquirable is True
        assert validation.ok is True

    def test_acquisition_layer_is_advisory_only(self):
        import atlas.evolution.capability_acquisition as acquisition

        # Phase 8 adds no installer/executor/activator: those are the existing
        # governed mechanisms. The strategy layer only classifies and advises.
        for banned in (
            "install",
            "execute",
            "apply",
            "promote",
            "activate",
            "write",
            "subprocess",
        ):
            assert not hasattr(acquisition, banned)
