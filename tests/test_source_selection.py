"""Phase 3.2 — deterministic authorized source selection tests.

Covers the pure policy (deterministic, bounded, fail-closed, model-free, never
web), integration with the existing research coordinator/resolver/adapter path,
and the kernel wiring. No provider is contacted anywhere in this module.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from atlas.evolution.models import ResearchQuery
from atlas.research.coordinator import ConcreteResearchCoordinator
from atlas.research.repository_map import RepositoryMapBuilder
from atlas.research.source_selection import (
    MAX_SELECTED_SOURCES,
    SourceSelectionPolicy,
    select_repository_sources,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _synthetic_repo(tmp_path: Path) -> RepositoryMapBuilder:
    pkg = tmp_path / "atlas"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "memory_service.py").write_text(
        '"""The memory service stores and retrieves memories.\n\n'
        'It exposes a deterministic search surface.\n"""\n',
        encoding="utf-8",
    )
    (pkg / "cognition_pipeline.py").write_text(
        '"""The cognition pipeline runs staged processing."""\n',
        encoding="utf-8",
    )
    (pkg / "unrelated_widget.py").write_text(
        '"""An unrelated widget with no matching subject."""\n',
        encoding="utf-8",
    )
    return RepositoryMapBuilder(tmp_path)


# ---------------------------------------------------------------------------
# 1. Deterministic selection policy
# ---------------------------------------------------------------------------


class TestSelectionPolicy:
    def test_repository_shaped_question_selects_local_source(self, tmp_path):
        rm = _synthetic_repo(tmp_path).build()
        selected = select_repository_sources("the memory service", rm)
        assert selected
        assert all(s.startswith("code://") for s in selected)
        assert any("memory_service" in s for s in selected)

    def test_deterministic(self, tmp_path):
        rm = _synthetic_repo(tmp_path).build()
        assert select_repository_sources("the memory service", rm) == (
            select_repository_sources("the memory service", rm)
        )

    def test_bounded_by_cap(self, tmp_path):
        rm = _synthetic_repo(tmp_path).build()
        assert len(select_repository_sources("memory service cognition", rm)) <= (
            MAX_SELECTED_SOURCES
        )

    def test_fail_closed_no_match(self, tmp_path):
        rm = _synthetic_repo(tmp_path).build()
        assert select_repository_sources("zeppelin maintenance", rm) == ()

    def test_empty_blank_and_missing_map(self, tmp_path):
        rm = _synthetic_repo(tmp_path).build()
        assert select_repository_sources("", rm) == ()
        assert select_repository_sources("   ", rm) == ()
        assert select_repository_sources("memory", None) == ()

    def test_never_selects_web(self, tmp_path):
        rm = _synthetic_repo(tmp_path).build()
        selected = select_repository_sources("memory service", rm)
        assert not any(s.startswith("http") or s.startswith("web://") for s in selected)

    def test_policy_bounds_validated(self):
        with pytest.raises(ValueError):
            SourceSelectionPolicy(max_sources=0)
        with pytest.raises(ValueError):
            SourceSelectionPolicy(min_token_length=0)

    def test_module_is_model_free(self):
        source = (
            _REPO_ROOT / "atlas" / "research" / "source_selection.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        banned = ("openai", "anthropic", "ollama", "requests", "httpx", "urllib", "atlas.ai")
        for module in imported:
            assert not module.startswith(banned), module


# ---------------------------------------------------------------------------
# 2. Integration with the existing coordinator / resolver / adapters
# ---------------------------------------------------------------------------


class TestCoordinatorIntegration:
    def test_selected_source_reaches_coordinator(self, tmp_path, monkeypatch):
        rm = _synthetic_repo(tmp_path).build()
        monkeypatch.chdir(tmp_path)
        coordinator = ConcreteResearchCoordinator(
            select_sources=lambda q: select_repository_sources(q, rm)
        )
        result = coordinator.run(
            ResearchQuery(query_id="t", question="the memory service")
        )
        assert result.sources  # the selected source reached the adapter path
        assert any("memory_service" in s for s in result.sources)

    def test_selection_is_deterministic_end_to_end(self, tmp_path, monkeypatch):
        rm = _synthetic_repo(tmp_path).build()
        monkeypatch.chdir(tmp_path)
        make = lambda: ConcreteResearchCoordinator(  # noqa: E731
            select_sources=lambda q: select_repository_sources(q, rm)
        ).run(ResearchQuery(query_id="t", question="the memory service"))
        assert make().sources == make().sources

    def test_unrelated_question_is_honest_empty(self, tmp_path, monkeypatch):
        rm = _synthetic_repo(tmp_path).build()
        monkeypatch.chdir(tmp_path)
        coordinator = ConcreteResearchCoordinator(
            select_sources=lambda q: select_repository_sources(q, rm)
        )
        result = coordinator.run(
            ResearchQuery(query_id="t", question="zeppelin maintenance")
        )
        assert not result.sources

    def test_without_selector_behaviour_unchanged(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _synthetic_repo(tmp_path).build()
        coordinator = ConcreteResearchCoordinator()  # no selector
        result = coordinator.run(
            ResearchQuery(query_id="t", question="the memory service")
        )
        assert not result.sources


# ---------------------------------------------------------------------------
# 3. Kernel wiring
# ---------------------------------------------------------------------------


@pytest.fixture
def _kernel(monkeypatch, tmp_path):
    import atlas.kernel.atlas as kernel_mod
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage

    class _Tmp(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107
            super().__init__(db_path=tmp_path / "evolution.db")

    monkeypatch.setattr(kernel_mod, "SQLiteEvolutionStorage", _Tmp)
    atlas = kernel_mod.Atlas()
    atlas.start()
    yield atlas
    atlas.shutdown()


class TestKernelWiring:
    def test_kernel_injects_deterministic_selector(self, _kernel):
        selected = _kernel._select_research_sources("the memory architecture")
        assert selected
        assert all(s.startswith("code://") for s in selected)
        # Deterministic and fail-closed.
        assert selected == _kernel._select_research_sources("the memory architecture")
        assert _kernel._select_research_sources("zeppelin maintenance") == ()

    def test_coordinator_has_selector_bound(self, _kernel):
        assert _kernel._research_coordinator._select_sources is not None
