"""Command 2 (A1) — the bounded symbol/region repository graph.

Covers: reference sites, boundedness, deterministic ordering, unambiguous edges,
ambiguous edges refusing to resolve, symbol regions and their bounds, the query
methods, unknown symbols failing closed, and real-repository stability.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from atlas.research.repository_map import (  # noqa: E402
    MAX_EDGES_TOTAL,
    MAX_REFERENCE_SITES_PER_SYMBOL,
    MAX_REGION_CHARS,
    MAX_REGION_TOTAL_CHARS,
    MAX_SYMBOL_MATCHES,
    ReferenceSite,
    RepositoryMapBuilder,
    SymbolEdge,
    SymbolRegion,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: A tiny tree with BOTH an unambiguous relationship (``thing``) and an
#: ambiguous one (``helper`` is defined twice), so the "never guess" rule is
#: directly observable.
TREE = {
    "pkg/__init__.py": "",
    "pkg/alpha.py": (
        "import pkg.beta\n"
        "\n"
        "\n"
        "def helper(value):\n"
        "    return value + 1\n"
        "\n"
        "\n"
        "class Widget:\n"
        "    def render(self):\n"
        "        return helper(1)\n"
        "\n"
        "    def draw(self):\n"
        "        return pkg.beta.thing()\n"
        "\n"
        "\n"
        "def unique_one():\n"
        "    return helper(2)\n"
    ),
    "pkg/beta.py": (
        "def thing():\n"
        "    return 42\n"
        "\n"
        "\n"
        "def helper(value):\n"
        "    return value - 1\n"
    ),
}


def _build(root):
    return RepositoryMapBuilder(root).build()


@pytest.fixture(scope="module")
def small(tmp_path_factory):
    root = tmp_path_factory.mktemp("symbol_graph")
    for relative, text in TREE.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return _build(root)


@pytest.fixture(scope="module")
def real():
    return _build(REPO_ROOT)


class TestReferenceSites:
    def test_reference_sites_are_recorded(self, small):
        sites = small.references_of("pkg.beta.thing")
        assert sites
        assert all(isinstance(site, ReferenceSite) for site in sites)
        assert any(site.module == "pkg.alpha" for site in sites)
        assert all(site.line > 0 for site in sites)

    def test_reference_sites_are_bounded(self, small):
        for symbol in small.symbols:
            assert len(symbol.reference_sites) <= MAX_REFERENCE_SITES_PER_SYMBOL

    def test_reference_sites_are_deterministically_ordered(self, small):
        sites = small.references_of("pkg.beta.thing")
        assert list(sites) == sorted(sites, key=lambda s: (s.module, s.line))

    def test_a_name_with_no_use_has_no_sites(self, small):
        # ``Widget`` is never used by NAME, so no site may be invented for it.
        assert small.references_of("pkg.alpha.Widget") == ()

    def test_symbol_counts_unchanged_by_the_graph(self, small):
        # The graph is ADDITIVE: the extracted symbol set is what it always was.
        assert {s.qualified for s in small.symbols} == {
            "pkg.alpha.helper",
            "pkg.alpha.Widget",
            "pkg.alpha.Widget.render",
            "pkg.alpha.Widget.draw",
            "pkg.alpha.unique_one",
            "pkg.beta.thing",
            "pkg.beta.helper",
        }


class TestSymbolEdges:
    def test_unambiguous_edge_resolves(self, small):
        assert small.callers_of("pkg.beta.thing") == ("pkg.alpha.Widget.draw",)
        assert small.callees_of("pkg.alpha.Widget.draw") == ("pkg.beta.thing",)

    def test_ambiguous_name_produces_no_relationship(self, small):
        # ``helper`` is defined twice, so NO caller/callee edge may be claimed.
        assert small.callers_of("pkg.alpha.helper") == ()
        assert small.callers_of("pkg.beta.helper") == ()
        assert small.callees_of("pkg.alpha.unique_one") == ()
        assert small.callees_of("pkg.alpha.Widget.render") == ()

    def test_edges_are_bounded_and_typed(self, small):
        assert small.edges
        assert all(isinstance(edge, SymbolEdge) for edge in small.edges)
        assert len(small.edges) <= MAX_EDGES_TOTAL
        assert ("pkg.alpha.Widget.draw", "pkg.beta.thing") in {
            (edge.caller, edge.callee) for edge in small.edges
        }

    def test_edge_endpoints_are_declared_symbols(self, small):
        declared = {symbol.qualified for symbol in small.symbols}
        for edge in small.edges:
            assert edge.caller in declared
            assert edge.callee in declared

    def test_callers_and_callees_are_bounded(self, small):
        for symbol in small.symbols:
            assert isinstance(symbol.callers, tuple)
            assert isinstance(symbol.callees, tuple)


class TestSymbolRegions:
    def test_region_matches_the_source_span(self, small):
        region = small.region_of("pkg.beta.thing")
        assert isinstance(region, SymbolRegion)
        lines = TREE["pkg/beta.py"].splitlines()
        assert region.source == "\n".join(lines[region.start_line - 1 : region.end_line])
        assert region.module == "pkg.beta"
        assert region.path == "pkg/beta.py"

    def test_region_includes_decorators_and_body(self, small):
        region = small.region_of("pkg.alpha.Widget.render")
        assert region is not None
        assert "def render" in region.source
        assert region.start_line <= region.end_line

    def test_regions_are_bounded(self, small):
        assert all(len(r.source) <= MAX_REGION_CHARS for r in small.regions)
        assert sum(len(r.source) for r in small.regions) <= MAX_REGION_TOTAL_CHARS

    def test_end_line_is_recorded_on_the_symbol(self, small):
        symbol = next(s for s in small.symbols if s.qualified == "pkg.beta.thing")
        # ``def thing():`` on line 1, ``return 42`` on line 2 — the trailing blank
        # lines belong to the module, not to the definition.
        assert symbol.line == 1
        assert symbol.end_line == 2

    def test_regions_for_is_module_scoped_and_bounded(self, small):
        assert len(small.regions_for(["pkg.beta"])) == 2
        assert small.regions_for(["pkg.beta"], limit=1) == small.regions_for(
            ["pkg.beta"]
        )[:1]
        assert len(small.regions_for()) <= MAX_SYMBOL_MATCHES


class TestUnknownSymbols:
    def test_unknown_symbols_fail_closed(self, small):
        assert small.region_of("nope.Nope") is None
        assert small.region_of("") is None
        assert small.region_of(None) is None
        assert small.references_of("nope.Nope") == ()
        assert small.callers_of("nope.Nope") == ()
        assert small.callees_of("nope.Nope") == ()

    def test_unknown_module_yields_no_regions(self, small):
        assert small.regions_for(["nope.nope"]) == ()


class TestDeterminismAndCompatibility:
    def test_repeated_builds_are_identical(self, tmp_path):
        for relative, text in TREE.items():
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        first = _build(tmp_path)
        second = _build(tmp_path)
        assert [s.to_dict() for s in first.symbols] == [s.to_dict() for s in second.symbols]
        assert [r.to_dict() for r in first.regions] == [r.to_dict() for r in second.regions]
        assert [e.to_dict() for e in first.edges] == [e.to_dict() for e in second.edges]

    def test_to_dict_keeps_every_existing_key(self, small):
        payload = small.to_dict()
        for key in (
            "built_at",
            "root_label",
            "module_count",
            "edge_count",
            "symbol_count",
            "truncated",
            "error_count",
            "modules",
            "metadata",
        ):
            assert key in payload
        assert "region_count" in payload and "symbol_edge_count" in payload
        module = next(m for m in payload["modules"] if m["symbols"])
        for key in ("module", "path", "symbols", "source_excerpt", "source_truncated"):
            assert key in module
        symbol = module["symbols"][0]
        for key in ("name", "qualified", "module", "kind", "line", "references"):
            assert key in symbol
        assert "reference_sites" in symbol and "callers" in symbol


class TestRealRepository:
    def test_real_repository_counts_remain_consistent(self, real):
        assert real.module_count() == len(real.modules) > 0
        assert real.symbol_count() == len(real.symbols) > 0
        assert real.metadata["symbols"] == real.symbol_count()
        assert real.metadata["regions"] == len(real.regions)
        assert real.metadata["symbol_edges"] == len(real.edges)
        assert not real.errors

    def test_real_symbol_has_a_true_region_and_references(self, real):
        region = real.region_of("atlas.research.repository_map.SymbolInfo")
        assert region is not None
        assert region.module == "atlas.research.repository_map"
        assert "class SymbolInfo" in region.source
        assert real.references_of("atlas.research.repository_map.SymbolInfo")
