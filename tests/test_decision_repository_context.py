"""Stage A1.3 — repository context in DecisionIntelligence planning.

Verifies the additive ``repository_map_provider`` seam:

- default behavior (no provider) is byte-identical to before,
- an already-built map appears as a bounded ``"repository"`` metadata
  section in ``get_planning_context()``,
- missing maps and failing providers degrade to empty sections,
- the kernel's provider is cache-only (it must never trigger a scan).
"""

from pathlib import Path

import pytest

from atlas.evolution.decision_intelligence import DecisionIntelligenceEngine
from atlas.kernel.atlas import Atlas
from atlas.research.repository_map import RepositoryMapBuilder


@pytest.fixture
def small_map(tmp_path):
    root = tmp_path / "repo"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (pkg / "m.py").write_text("from pkg.core import VALUE\n", encoding="utf-8")
    return RepositoryMapBuilder(root).build()


class _StubQuery:
    """Knowledge-query stand-in exposing the read-only surface as empty."""

    def get_patterns_by_area(self, area, n=-1):
        return []

    def get_bottlenecks(self, n=-1):
        return []

    def get_bottlenecks_by_area(self, area, n=-1):
        return []

    def get_effective_strategies(self, n=-1):
        return []

    def get_ineffective_strategies(self, n=-1):
        return []

    def get_capabilities(self, n=-1):
        return []


class TestDefaultBehaviorUnchanged:
    def test_no_provider_no_query_returns_neutral_context(self):
        engine = DecisionIntelligenceEngine()
        context = engine.get_planning_context()
        assert context.metadata == {}
        assert context.area_adjustments == {}
        assert context.overall_confidence == 0.0

    def test_provider_none_explicit_same_behavior(self):
        engine = DecisionIntelligenceEngine(
            knowledge_query=None,
            repository_map_provider=None,
        )
        assert engine.get_planning_context().metadata == {}

    def test_existing_knowledge_only_behavior_unchanged(self):
        engine = DecisionIntelligenceEngine(knowledge_query=_StubQuery())
        context = engine.get_planning_context()
        # Neutral-but-computed path; no repository section without a map.
        assert "repository" not in context.metadata


class TestRepositoryContextSection:
    def test_built_map_appears_in_metadata(self, small_map):
        engine = DecisionIntelligenceEngine(
            knowledge_query=None,
            repository_map_provider=lambda: small_map,
        )
        context = engine.get_planning_context()

        repo_meta = context.metadata["repository"]
        # pkg, pkg.core, pkg.m discovered; one internal edge m→pkg.core.
        assert repo_meta["module_count"] == 3
        assert repo_meta["edge_count"] == 1
        assert "truncated" in repo_meta
        assert "architecture_summary" in repo_meta

    def test_none_from_provider_degrades_to_empty(self):
        engine = DecisionIntelligenceEngine(
            knowledge_query=None,
            repository_map_provider=lambda: None,
        )
        assert engine.get_planning_context().metadata == {}

    def test_raising_provider_is_swallowed(self):
        def boom():
            raise RuntimeError("no scanning from here")

        engine = DecisionIntelligenceEngine(
            knowledge_query=None,
            repository_map_provider=boom,
        )
        assert engine.get_planning_context().metadata == {}

    def test_repository_section_coexists_with_knowledge_path(self, small_map):
        engine = DecisionIntelligenceEngine(
            knowledge_query=_StubQuery(),
            repository_map_provider=lambda: small_map,
        )
        context = engine.get_planning_context()
        assert "repository" in context.metadata
        assert context.metadata["repository"]["module_count"] == 3

    def test_non_map_return_value_ignored(self):
        engine = DecisionIntelligenceEngine(
            knowledge_query=None,
            repository_map_provider=lambda: "not a map",
        )
        assert engine.get_planning_context().metadata == {}


class TestKernelProviderIsCacheOnly:
    def test_kernel_wires_cache_backed_provider(self):
        """The kernel's provider reads only the already-built cache; before
        any explicit build/refresh it yields None (no scan triggered)."""
        atlas = Atlas()
        atlas.start()
        try:
            engine = atlas._decision_intelligence
            if engine is None:
                pytest.fail("kernel did not wire decision intelligence")
            provider = engine._repository_map_provider
            if provider is None:
                pytest.fail("kernel did not wire a repository map provider")

            # Lazy world: nothing built yet -> provider returns None, no scan.
            assert provider() is None

            fresh = atlas.refresh_repository_map()
            assert fresh is not None
            assert provider() is fresh  # same cached snapshot, zero rescans
        finally:
            atlas.shutdown()