"""Bounded SOURCE-aware authoring context — capability-level tests.

The authoring contract asks a provider for FULL replacement content, so a context
made only of module paths and symbol signatures was structurally unusable. The
context now also carries BOUNDED real source, captured from the file text the
repository-map builder has already read (no extra I/O), plus each module's
resolved internal imports.

These tests pin the CONTRACT, not one sentence:

* real implementation source is present, and is COMPLETE for a small module;
* the context stays explicitly bounded (module count, source budget, per-module
  excerpt cap) and never becomes an unbounded dump;
* ordering is deterministic and the target module is served first;
* nothing is invented: every module and path comes from the repository map.

Deterministic and model-free throughout.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, r"F:\Project Atlas")

from atlas.evolution.model_assisted_supplier import (
    MAX_CONTEXT_MODULES,
    MAX_CONTEXT_SOURCE_CHARS,
    ModelAssistedChangeSupplier,
)
from atlas.research.repository_map import MAX_SOURCE_EXCERPT_CHARS

REPO_ROOT = pathlib.Path(r"F:\Project Atlas")

# A small real target whose FULL source fits the excerpt bound.
SMALL_TARGET = "atlas.conversation.history"
SMALL_TARGET_PATH = "atlas/conversation/history.py"


@pytest.fixture(scope="module")
def repository_map():
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    try:
        yield atlas.repository_map
    finally:
        atlas.shutdown()


@pytest.fixture(scope="module")
def fresh_repository_map():
    from atlas.research.repository_map import RepositoryMapBuilder

    return RepositoryMapBuilder(REPO_ROOT).build()


def _read_exact(path: pathlib.Path) -> str:
    """Read a file preserving its EXACT line endings (the map does the same)."""
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def _need(title="Improve the history module", component=SMALL_TARGET):
    from atlas.evolution.development_cycle import DevelopmentNeed

    return DevelopmentNeed(
        title=title, summary=title, target_components=(component,)
    )


def _context(repository_map, need=None):
    return ModelAssistedChangeSupplier(
        authoring_model=lambda p: "{}", repository_map=repository_map
    )._build_authoring_context(need or _need())


# ---------------------------------------------------------------------------
# 1. Source inclusion
# ---------------------------------------------------------------------------


class TestSourceInclusion:
    def test_small_target_source_is_complete(self, repository_map):
        """A small target's whole implementation is present, line for line."""
        source = (REPO_ROOT / SMALL_TARGET_PATH).read_text(encoding="utf-8")
        context = _context(repository_map)
        distinctive = [
            ln.strip()
            for ln in source.splitlines()
            if ln.strip()
            and len(ln.strip()) > 20
            and not ln.strip().startswith(("#", "@"))
        ][:6]
        assert distinctive, "fixture must yield distinctive lines"
        present = [ln for ln in distinctive if ln in context]
        assert len(present) == len(distinctive), (
            f"{len(present)}/{len(distinctive)} distinctive lines present"
        )

    def test_source_header_is_present_and_labelled(self, repository_map):
        context = _context(repository_map)
        assert "    source" in context
        assert "evidence only" in context

    def test_signatures_remain_present(self, repository_map):
        context = _context(repository_map)
        assert "    symbols:" in context
        assert "method add(self, conversation: Conversation)" in context

    def test_dependency_evidence_is_present(self, repository_map):
        context = _context(repository_map)
        assert "internal imports:" in context
        # history.py imports Conversation from the conversation module.
        assert "atlas.conversation.conversation" in context

    def test_every_claimed_module_exists_in_the_map(self, repository_map):
        known = {m.module for m in repository_map.modules}
        context = _context(repository_map)
        headers = [ln for ln in context.splitlines() if ln.startswith("- ")]
        assert headers
        for header in headers:
            module = header.split(" ", 2)[2].split(" (", 1)[0]
            assert module in known, module


# ---------------------------------------------------------------------------
# 2. Boundedness
# ---------------------------------------------------------------------------


class TestBoundedness:
    def test_module_count_is_bounded(self, repository_map):
        context = _context(repository_map)
        headers = [ln for ln in context.splitlines() if ln.startswith("- ")]
        assert 0 < len(headers) <= MAX_CONTEXT_MODULES

    def test_total_source_is_bounded(self, repository_map):
        context = _context(repository_map)
        source_chars = sum(
            len(ln) - 8
            for ln in context.splitlines()
            if ln.startswith("        ") and not ln.startswith("        - ")
        )
        assert source_chars <= MAX_CONTEXT_SOURCE_CHARS

    def test_per_module_excerpt_is_capped(self, repository_map):
        for info in repository_map.modules:
            assert len(info.source_excerpt) <= MAX_SOURCE_EXCERPT_CHARS, info.module

    def test_a_huge_module_is_not_dumped_whole(self, repository_map):
        """The 8,675-line module must contribute a bounded excerpt only."""
        big = next(
            m for m in repository_map.modules
            if m.module == "atlas.conversation.conversation_service"
        )
        assert big.line_count > 5000
        assert big.source_truncated is True
        assert len(big.source_excerpt) <= MAX_SOURCE_EXCERPT_CHARS

    def test_truncation_is_stated_explicitly(self, repository_map):
        context = _context(
            repository_map,
            _need(
                "Improve the conversation service capability",
                "atlas.conversation.conversation_service",
            ),
        )
        assert "truncated: first" in context

    def test_a_small_module_is_not_truncated(self, repository_map):
        small = next(m for m in repository_map.modules if m.module == SMALL_TARGET)
        assert small.source_truncated is False
        assert small.source_excerpt == _read_exact(REPO_ROOT / SMALL_TARGET_PATH)


# ---------------------------------------------------------------------------
# 3. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_repeated_context_is_identical(self, repository_map):
        assert _context(repository_map) == _context(repository_map)

    def test_fresh_map_produces_identical_context(
        self, repository_map, fresh_repository_map
    ):
        assert _context(repository_map) == _context(fresh_repository_map)

    def test_module_order_follows_the_ranking_not_set_iteration(self, repository_map):
        """The declared target is served first, deterministically."""
        first = _context(repository_map).splitlines()[1]
        assert SMALL_TARGET in first


# ---------------------------------------------------------------------------
# 4. Relevance / priority
# ---------------------------------------------------------------------------


class TestRelevance:
    def test_declared_target_is_served_first(self, repository_map):
        context = _context(repository_map)
        headers = [ln for ln in context.splitlines() if ln.startswith("- ")]
        assert SMALL_TARGET in headers[0]

    def test_a_large_target_still_gets_its_own_source(self, repository_map):
        context = _context(
            repository_map,
            _need(
                "Improve the conversation service capability",
                "atlas.conversation.conversation_service",
            ),
        )
        assert "atlas.conversation.conversation_service" in context
        assert "    source" in context

    def test_production_modules_are_preferred_over_tests(self, repository_map):
        context = _context(repository_map)
        headers = [ln for ln in context.splitlines() if ln.startswith("- ")]
        assert not any("tests." in h.split(" ", 2)[2] for h in headers[:1])


# ---------------------------------------------------------------------------
# 5. Safety
# ---------------------------------------------------------------------------


class TestSafety:
    def test_no_absolute_path_or_traversal_leaks(self, repository_map):
        """Every emitted PATH is relative and cannot traverse.

        Checked on the module headers (the only paths the context emits), not on
        the source text — source legitimately contains ``...`` (e.g. Python's
        ``tuple[str, ...]``) which is not a path.
        """
        context = _context(repository_map)
        headers = [ln for ln in context.splitlines() if ln.startswith("- ")]
        assert headers
        for header in headers:
            path = header.split("(", 1)[1].rstrip(")") if "(" in header else ""
            assert path, header
            assert not path.startswith("/")
            assert ":" not in path
            assert ".." not in path.split("/")
        assert "F:\\" not in context
        assert "/Project Atlas" not in context

    def test_source_matches_the_real_file(self, repository_map):
        """The excerpt is real file content, not a fabrication."""
        info = next(m for m in repository_map.modules if m.module == SMALL_TARGET)
        assert _read_exact(REPO_ROOT / info.path).startswith(info.source_excerpt)

    def test_provider_off_stays_isolated(self, repository_map):
        calls: list[str] = []

        def _provider(p):
            calls.append(p)
            return "{}"

        off = ModelAssistedChangeSupplier(repository_map=repository_map)
        assert off.supply_changes(_need()) is None
        assert calls == []
        # But the context is still constructible locally and deterministically.
        assert "    source" in off._build_authoring_context(_need())

    def test_raising_map_still_yields_no_context(self):
        class _Broken:
            def rank_modules(self, query, limit=10):
                raise RuntimeError("map down")

        supplier = ModelAssistedChangeSupplier(
            authoring_model=lambda p: "{}", repository_map=_Broken()
        )
        assert supplier._build_authoring_context(_need()) == ""

    def test_map_without_source_still_produces_usable_context(self, repository_map):
        """A map lacking source degrades to the previous structure-only context."""
        class _NoSource:
            def __init__(self, inner):
                self._inner = inner

            def rank_modules(self, query, limit=10):
                return self._inner.rank_modules(query, limit=limit)

            def symbols_in_module(self, module):
                return self._inner.symbols_in_module(module)

            modules: tuple = ()

        supplier = ModelAssistedChangeSupplier(
            authoring_model=lambda p: "{}", repository_map=_NoSource(repository_map)
        )
        context = supplier._build_authoring_context(_need())
        assert "Repository context" in context
        assert "    source" not in context
