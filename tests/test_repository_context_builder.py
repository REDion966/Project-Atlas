"""Command 2 (W2) — the ONE bounded repository context builder."""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from atlas.evolution.context_builder import (  # noqa: E402
    DEFAULT_CONTEXT_CHARS,
    RepositoryContextRequest,
    build_repository_context,
    context_sources,
)
from atlas.research.repository_map import RepositoryMapBuilder  # noqa: E402

TREE = {
    "pkg/__init__.py": "",
    "pkg/core.py": (
        "from pkg.support import helper\n"
        "\n"
        "\n"
        "class Engine:\n"
        "    def run(self):\n"
        "        return helper(1)\n"
    ),
    "pkg/support.py": (
        "def helper(value):\n"
        "    return value + 1\n"
    ),
    "tests/test_core.py": (
        "from pkg.core import Engine\n"
        "\n"
        "\n"
        "def test_engine():\n"
        "    assert Engine().run() == 2\n"
    ),
}


@pytest.fixture(scope="module")
def repository_map(tmp_path_factory):
    root = tmp_path_factory.mktemp("context_builder")
    for relative, text in TREE.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return RepositoryMapBuilder(root).build()


class TestSelectionOrder:
    def test_target_region_is_selected_first(self, repository_map):
        context = build_repository_context(
            repository_map, RepositoryContextRequest(module="pkg.support")
        )
        assert context.resolved
        assert context.module == "pkg.support"
        assert context.regions
        assert "region" in " ".join(context.rationale)
        assert "def helper" in context.source

    def test_symbol_request_selects_that_symbol(self, repository_map):
        context = build_repository_context(
            repository_map, RepositoryContextRequest(symbol="pkg.support.helper")
        )
        assert context.module == "pkg.support"
        assert [r.qualified for r in context.regions] == ["pkg.support.helper"]

    def test_callers_are_reported_as_neighbours(self, repository_map):
        context = build_repository_context(
            repository_map, RepositoryContextRequest(symbol="pkg.support.helper")
        )
        assert "pkg.core.Engine.run" in {
            str(getattr(s, "qualified", "")) for s in context.symbols
        }

    def test_dependency_neighbours_are_reported(self, repository_map):
        context = build_repository_context(
            repository_map, RepositoryContextRequest(module="pkg.core")
        )
        assert "pkg.support" in context.dependencies

    def test_relevant_tests_are_reported(self, repository_map):
        context = build_repository_context(
            repository_map, RepositoryContextRequest(module="pkg.core")
        )
        assert any("test_core" in test for test in context.tests)

    def test_repository_path_target_also_resolves(self, repository_map):
        context = build_repository_context(
            repository_map, RepositoryContextRequest(module="pkg/core.py")
        )
        assert context.module == "pkg.core"


class TestBoundsAndDeterminism:
    def test_context_never_exceeds_its_budget(self, repository_map):
        request = RepositoryContextRequest(module="pkg.core", max_chars=10)
        context = build_repository_context(repository_map, request)
        assert len(context.source) <= 10
        assert context.truncated

    def test_identical_request_produces_identical_context(self, repository_map):
        request = RepositoryContextRequest(module="pkg.core")
        assert build_repository_context(
            repository_map, request
        ).to_dict() == build_repository_context(repository_map, request).to_dict()

    def test_default_budget_is_used_when_malformed(self, repository_map):
        context = build_repository_context(
            repository_map, RepositoryContextRequest(module="pkg.core", max_chars=-5)
        )
        assert len(context.source) <= DEFAULT_CONTEXT_CHARS

    def test_rationale_is_bounded(self, repository_map):
        context = build_repository_context(
            repository_map,
            RepositoryContextRequest(module="pkg.core", symbol="pkg.core.Engine.run"),
        )
        assert context.rationale
        assert all(len(reason) <= 200 for reason in context.rationale)


class TestFallback:
    def test_unresolved_target_records_the_fallback(self, repository_map):
        context = build_repository_context(
            repository_map, RepositoryContextRequest(module="nope.missing")
        )
        assert not context.resolved
        assert any("could not be resolved" in reason for reason in context.rationale)

    def test_unresolved_target_with_a_query_uses_the_ranking(self, repository_map):
        context = build_repository_context(
            repository_map, RepositoryContextRequest(module="nope", query="Engine")
        )
        assert context.fallback or context.module == ""
        assert any("ranking fallback" in reason for reason in context.rationale)

    def test_resolved_target_is_never_overridden_by_ranking(self, repository_map):
        context = build_repository_context(
            repository_map,
            RepositoryContextRequest(module="pkg.support", query="Engine"),
        )
        assert context.module == "pkg.support"
        assert not context.fallback


class TestFailingClosed:
    def test_no_map_yields_an_empty_context(self):
        context = build_repository_context(None, RepositoryContextRequest(module="x"))
        assert not context.resolved
        assert context.regions == ()
        assert context.source == ""

    def test_broken_map_yields_an_empty_context(self):
        class _Broken:
            def find_symbol(self, *a, **k):
                raise RuntimeError("map down")

            modules = ()

        context = build_repository_context(_Broken(), RepositoryContextRequest(module="x"))
        assert context.regions == ()

    def test_context_sources_returns_path_to_source(self, repository_map):
        sources = context_sources(
            repository_map, RepositoryContextRequest(module="pkg.support")
        )
        assert list(sources) == ["pkg/support.py"]
        assert "def helper" in sources["pkg/support.py"]

    def test_context_sources_is_empty_when_unresolved(self, repository_map):
        assert context_sources(
            repository_map, RepositoryContextRequest(module="nope.missing")
        ) == {}
