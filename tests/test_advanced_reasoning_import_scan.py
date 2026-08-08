"""Track D — Prohibited-import scan (Batch 2).

Enforces TRACK_D §3.3 / ATLAS_STATE §12: pure ``atlas/advanced_reasoning/``
modules must never import kernel, runtime, dispatcher, gateway, AI
providers, EventBus, scheduler, storage adapters, or ``atlas.reasoning``
implementation modules beyond the two stable public surfaces already used
by Track A/B/C (``atlas.reasoning.execution.models`` and
``atlas.reasoning.execution.registry``).

The only new module importing ``sqlite3`` is the storage adapter
(``atlas/storage/advanced_reasoning_storage.py``).
"""

from __future__ import annotations

import ast
import pathlib

#: Pure package modules that must respect the import boundary.
_PURE_MODULES: tuple[str, ...] = (
    "atlas.advanced_reasoning.models",
    "atlas.advanced_reasoning.catalog",
    "atlas.advanced_reasoning.protocols",
    "atlas.advanced_reasoning.storage_protocol",
    "atlas.advanced_reasoning.multi_step",
    "atlas.advanced_reasoning.causal",
    "atlas.advanced_reasoning.hypotheses",
    "atlas.advanced_reasoning.verify",
    "atlas.advanced_reasoning.meta",
    "atlas.advanced_reasoning.trace_repository",
    "atlas.advanced_reasoning.trace_recorder",
    "atlas.advanced_reasoning.service",
    "atlas.advanced_reasoning.capability_handlers",
    "atlas.advanced_reasoning.evolution_integration",
    "atlas.advanced_reasoning.wiring",
)

#: Forbidden package prefixes (any import starting with these is a violation).
_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "atlas.kernel",
    "atlas.runtime",
    "atlas.events",
    "atlas.ai.providers",
    "atlas.ai.router",
    "atlas.evolution.autonomy.dispatcher",
    "atlas.evolution.execution_gateway",
    "atlas.evolution.scheduler",
    "atlas.storage",
)

#: Stable ``atlas.reasoning`` public surfaces already consumed by Tracks A/B/C.
_ALLOWED_REASONING_IMPORTS: frozenset[str] = frozenset(
    {
        "atlas.reasoning.execution.models",
        "atlas.reasoning.execution.registry",
    }
)

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _module_path(module_name: str) -> str:
    return str(_ROOT / (module_name.replace(".", "/") + ".py"))


def _imported_modules(tree: ast.AST) -> set[str]:
    """Collect every top-level module imported by an AST (transitively)."""
    imported: set[str] = set()

    def _walk(node: ast.AST) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
            for alias in node.names:
                if alias.name != "*":
                    imported.add(alias.name)
        for child in ast.iter_child_nodes(node):
            _walk(child)

    _walk(tree)
    return imported


class TestPureModules:
    def test_all_pure_modules_exist(self):
        for module_name in _PURE_MODULES:
            assert pathlib.Path(_module_path(module_name)).exists(), f"missing {module_name}"

    def test_no_forbidden_imports(self):
        violations: list[str] = []
        for module_name in _PURE_MODULES:
            path = pathlib.Path(_module_path(module_name))
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for imported in _imported_modules(tree):
                for forbidden in _FORBIDDEN_PREFIXES:
                    if imported == forbidden or imported.startswith(forbidden + "."):
                        violations.append(f"{module_name} -> {imported}")
        assert not violations, f"forbidden imports: {violations}"

    def test_atlas_reasoning_imports_are_stable_public_only(self):
        violations: list[str] = []
        for module_name in _PURE_MODULES:
            path = pathlib.Path(_module_path(module_name))
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for imported in _imported_modules(tree):
                if imported.startswith("atlas.reasoning"):
                    if imported not in _ALLOWED_REASONING_IMPORTS:
                        violations.append(f"{module_name} -> {imported}")
        assert not violations, f"unstable reasoning imports: {violations}"

    def test_no_sqlite3_in_pure_modules(self):
        for module_name in _PURE_MODULES:
            path = pathlib.Path(_module_path(module_name))
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            assert "sqlite3" not in _imported_modules(tree), module_name


class TestStorageAdapter:
    def test_storage_adapter_exists(self):
        path = _ROOT / "atlas" / "storage" / "advanced_reasoning_storage.py"
        assert path.exists()

    def test_storage_adapter_imports_sqlite3(self):
        path = _ROOT / "atlas" / "storage" / "advanced_reasoning_storage.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert "sqlite3" in _imported_modules(tree)
