"""Stage A2 — symbol-level repository intelligence (Aider-adapted).

Atlas-native, deterministic, model-free structural intelligence layered onto
the EXISTING ``RepositoryMap``: per-module classes/functions/methods with
bounded signatures, a bounded repo-wide reference count used only for relevance
ordering, deterministic symbol lookup, bounded targeted context, and
architecture self-knowledge integration.

Mechanism source: Aider's repository map (symbol definitions + reference-graph
relevance + token-budgeted context), adapted to Atlas's deterministic,
read-only, model-independent architecture. No model, no network, no execution.
"""

from __future__ import annotations

import json
from pathlib import Path

from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.research.repository_map import (
    MAX_SYMBOLS_PER_MODULE,
    RepositoryMapBuilder,
    SymbolKind,
)
from atlas.self_knowledge.architecture_model import build_architecture_model

_SOURCE = (
    "import json\n"
    "class C:\n"
    "    def m(self, x=1):\n"
    "        return x\n"
    "def f(a, b):\n"
    "    return C().m(a)\n"
)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    (root / "m.py").write_text(_SOURCE, encoding="utf-8")
    return root


def _map(tmp_path: Path):
    return RepositoryMapBuilder(_repo(tmp_path)).build()


# ---------------------------------------------------------------------------
# Deterministic extraction
# ---------------------------------------------------------------------------


class TestSymbolExtraction:
    def test_classes_functions_and_methods_extracted(self, tmp_path):
        mp = _map(tmp_path)
        symbols = {(s.qualified, s.kind) for s in mp.symbols}
        assert ("m.C", SymbolKind.CLASS) in symbols
        assert ("m.f", SymbolKind.FUNCTION) in symbols
        assert ("m.C.m", SymbolKind.METHOD) in symbols

    def test_signatures_are_bounded_and_deterministic(self, tmp_path):
        mp = _map(tmp_path)
        by_q = {s.qualified: s for s in mp.symbols}
        assert by_q["m.f"].signature == "(a, b)"
        assert by_q["m.C.m"].signature == "(self, x=1)"
        assert by_q["m.C"].line >= 1

    def test_reference_counts_are_evidence_only(self, tmp_path):
        mp = _map(tmp_path)
        by_q = {s.qualified: s for s in mp.symbols}
        # C is instantiated and m is called; f is never referenced.
        assert by_q["m.C"].references >= 1
        assert by_q["m.f"].references == 0

    def test_import_graph_still_present(self, tmp_path):
        mp = _map(tmp_path)
        info = next(i for i in mp.modules if i.module == "m")
        assert "json" in info.external_imports

    def test_empty_tree_has_no_symbols(self, tmp_path):
        root = tmp_path / "empty"
        root.mkdir()
        mp = RepositoryMapBuilder(root).build()
        assert mp.symbol_count() == 0
        assert mp.find_symbol("anything") == ()


# ---------------------------------------------------------------------------
# Discovery + targeted lookup
# ---------------------------------------------------------------------------


class TestSymbolLookup:
    def test_exact_qualified_then_name(self, tmp_path):
        mp = _map(tmp_path)
        assert [s.qualified for s in mp.find_symbol("m.C")] == ["m.C"]
        assert [s.qualified for s in mp.find_symbol("C")] == ["m.C"]
        assert [s.qualified for s in mp.find_symbol("m")] == ["m.C.m"]

    def test_unknown_symbol_yields_nothing(self, tmp_path):
        mp = _map(tmp_path)
        assert mp.find_symbol("no_such_symbol") == ()
        assert mp.find_symbol("") == ()

    def test_symbols_in_module_and_context(self, tmp_path):
        mp = _map(tmp_path)
        assert {s.qualified for s in mp.symbols_in_module("m")} == {
            "m.C",
            "m.C.m",
            "m.f",
        }
        ctx = mp.context_for(["m"])
        assert {s.qualified for s in ctx} == {"m.C", "m.C.m", "m.f"}
        # No modules -> degrades to the bounded importance slice.
        assert mp.context_for([]) == mp.important_symbols(
            len(mp.important_symbols())
        )

    def test_importance_is_reference_ordered(self, tmp_path):
        mp = _map(tmp_path)
        top = mp.important_symbols(2)
        assert {s.qualified for s in top} == {"m.C", "m.C.m"}

    def test_module_queries_unaffected(self, tmp_path):
        mp = _map(tmp_path)
        assert mp.dependencies_of("m") == ()


# ---------------------------------------------------------------------------
# Stability, bounds, JSON safety
# ---------------------------------------------------------------------------


class TestStabilityAndBounds:
    def test_identical_trees_produce_identical_symbols(self, tmp_path):
        # build two independent trees with identical content
        roots = []
        for name in ("r1", "r2"):
            root = tmp_path / name
            root.mkdir(parents=True, exist_ok=True)
            (root / "m.py").write_text(_SOURCE, encoding="utf-8")
            roots.append(root)
        a = RepositoryMapBuilder(roots[0]).build().to_dict()
        b = RepositoryMapBuilder(roots[1]).build().to_dict()
        a.pop("built_at"), b.pop("built_at")
        a.pop("root_label"), b.pop("root_label")
        a["metadata"].pop("files_scanned", None)
        b["metadata"].pop("files_scanned", None)
        assert a == b

    def test_symbols_are_bounded_per_module(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        body = "".join(f"def fn_{i}():\n    return {i}\n" for i in range(200))
        (root / "many.py").write_text(body, encoding="utf-8")
        mp = RepositoryMapBuilder(root).build()
        assert len(mp.symbols_in_module("many")) <= MAX_SYMBOLS_PER_MODULE

    def test_to_dict_is_json_safe_and_reports_symbol_count(self, tmp_path):
        mp = _map(tmp_path)
        payload = mp.to_dict()
        rendered = json.dumps(payload)
        assert payload["symbol_count"] == mp.symbol_count() == 3
        assert '"symbols"' in rendered and '"qualified"' in rendered


# ---------------------------------------------------------------------------
# Integration — architecture self-knowledge resolves symbols
# ---------------------------------------------------------------------------


class TestArchitectureIntegration:
    def test_locate_resolves_a_symbol(self, tmp_path):
        mp = _map(tmp_path)
        model = build_architecture_model(ComponentRegistry(), repository_map=mp)

        result = model.locate("m.C")
        assert result.found is True
        assert result.matched_kind == "symbol"
        assert result.symbol == "m.C"
        assert result.module == "m"

        short = model.locate("f")
        assert short.found is True and short.matched_kind == "symbol"

    def test_locate_does_not_invent_unknown_symbols(self, tmp_path):
        mp = _map(tmp_path)
        model = build_architecture_model(ComponentRegistry(), repository_map=mp)
        assert model.locate("definitely_not_defined").found is False

    def test_symbol_count_surfaces_in_architecture_summary(self, tmp_path):
        mp = _map(tmp_path)
        model = build_architecture_model(ComponentRegistry(), repository_map=mp)
        assert model.symbol_count == 3
        assert model.to_dict()["symbol_count"] == 3
        assert "Repository symbols: 3" in model.to_markdown()


# ---------------------------------------------------------------------------
# Kernel integration
# ---------------------------------------------------------------------------


def _started_atlas(monkeypatch, tmp_path):
    import atlas.kernel.atlas as kernel_mod
    from atlas.storage.research_storage import ResearchSQLiteStorage
    from tests.test_durable_guided_improvement import _storage_class

    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage", _storage_class(tmp_path)
    )

    class _TmpResearch(ResearchSQLiteStorage):
        def __init__(self, db_path=None):  # noqa: D107
            super().__init__(db_path=tmp_path / "research.db")

    monkeypatch.setattr("atlas.kernel.atlas.ResearchSQLiteStorage", _TmpResearch)
    atlas = kernel_mod.Atlas()
    atlas.start()
    return atlas


class TestKernelIntegration:
    def test_kernel_repository_symbol_lookup(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            # The real Atlas repository map must resolve a real symbol.
            found = atlas.repository_symbol("RepositoryMapBuilder")
            assert found  # deterministic lookup over the real tree
            assert all(hasattr(s, "qualified") for s in found)
            assert atlas.repository_symbol("no_such_symbol_xyz") == ()
        finally:
            atlas.shutdown()
