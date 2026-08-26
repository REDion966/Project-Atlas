"""Repository Self-Knowledge Map — Stage A1 unit tests.

Covers discovery, AST import extraction (absolute / relative / external),
graph queries, boundedness, fail-soft behavior, determinism, and purity of
``atlas/research/repository_map.py`` on synthetic tmp_path trees.
"""

import json
from pathlib import Path

import pytest

from atlas.research.repository_map import (
    MAX_MODULES,
    RepositoryMapBuilder,
)


@pytest.fixture
def repo(tmp_path):
    """A small synthetic repository with packages and imports."""
    root = tmp_path / "repo"
    pkg = root / "pkg"
    sub = pkg / "sub"
    sub.mkdir(parents=True)
    (root / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (sub / "__init__.py").write_text("", encoding="utf-8")
    (root / "alpha.py").write_text(
        "import json\n"
        "from pkg import beta\n"
        "from pkg.sub.gamma import G\n",
        encoding="utf-8",
    )
    (pkg / "beta.py").write_text("import os\nVALUE = 2\n", encoding="utf-8")
    (sub / "gamma.py").write_text(
        "from ..beta import VALUE\nG = VALUE\n", encoding="utf-8"
    )
    return root


def _builder(root, **overrides):
    return RepositoryMapBuilder(root, **overrides)


def _module(map_, name):
    return {info.module: info for info in map_.modules}[name]


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    def test_discovers_all_python_modules_with_dotted_names(self, repo):
        map_ = _builder(repo).build()
        names = {info.module for info in map_.modules}
        assert names == {
            "alpha",           # root-level module
            "pkg",             # package __init__
            "pkg.beta",
            "pkg.sub",         # nested package __init__
            "pkg.sub.gamma",
        }

    def test_init_files_map_to_package_names_and_flagged(self, repo):
        map_ = _builder(repo).build()
        index = {info.module: info for info in map_.modules}
        # Root __init__.py is intentionally skipped (no dotted name);
        # nested package __init__ files map to their package names.
        assert index["pkg"].is_package is True
        assert index["pkg.sub"].is_package is True
        assert index["alpha"].is_package is False

    def test_excludes_hidden_and_cache_directories(self, tmp_path):
        root = tmp_path / "repo"
        (root / "__pycache__").mkdir(parents=True)
        (root / ".venv" / "lib").mkdir(parents=True)
        (root / ".git").mkdir()
        (root / "keep").mkdir(parents=True)
        (root / "__pycache__" / "junk.py").write_text("X = 1\n", encoding="utf-8")
        (root / ".venv" / "lib" / "v.py").write_text("X = 1\n", encoding="utf-8")
        (root / ".git" / "h.py").write_text("X = 1\n", encoding="utf-8")
        (root / "hidden_mod.py").touch()
        (root / "keep" / "real.py").write_text("Y = 2\n", encoding="utf-8")

        map_ = _builder(root).build()
        paths = [info.path for info in map_.modules]
        assert "keep/real.py" in paths
        assert all(not p.startswith("__pycache__") for p in paths)
        assert all(not p.startswith(".venv") for p in paths)

    def test_empty_tree_yields_valid_empty_map(self, tmp_path):
        root = tmp_path / "empty"
        root.mkdir()
        map_ = _builder(root).build()
        assert map_.module_count() == 0
        assert map_.edge_count() == 0
        assert json.dumps(map_.to_dict())

    def test_missing_root_fails_soft(self, tmp_path):
        map_ = _builder(tmp_path / "does-not-exist").build()
        assert map_.module_count() == 0
        assert any("not an existing directory" in e for e in map_.errors)


# ---------------------------------------------------------------------------
# Import extraction
# ---------------------------------------------------------------------------


class TestImportExtraction:
    def test_absolute_internal_imports_resolved(self, repo):
        map_ = _builder(repo).build()
        alpha = _module(map_, "alpha")
        # "from pkg import beta" resolves to the pkg.beta module via
        # longest-prefix matching; "from pkg.sub.gamma import G" likewise.
        assert "pkg" in alpha.internal_imports or "pkg.beta" in (
            alpha.internal_imports
        )
        assert "pkg.sub.gamma" in alpha.internal_imports
        assert "json" in alpha.external_imports

    def test_relative_imports_resolved_against_package_context(self, repo):
        map_ = _builder(repo).build()
        gamma = _module(map_, "pkg.sub.gamma")
        assert "pkg.beta" in gamma.internal_imports

    def test_external_roots_collected(self, repo):
        map_ = _builder(repo).build()
        beta = _module(map_, "pkg.beta")
        assert beta.external_imports == ("os",)
        alpha = _module(map_, "alpha")
        assert "json" in alpha.external_imports

    def test_syntax_error_file_recorded_not_raised(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        (root / "broken.py").write_text("def broken(:\n", encoding="utf-8")
        (root / "good.py").write_text("OK = 1\n", encoding="utf-8")

        map_ = _builder(root).build()
        assert {i.module for i in map_.modules} == {"good"}
        assert any("broken" in e and "syntax error" in e for e in map_.errors)

    def test_function_scoped_imports_are_seen(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        (root / "lazy.py").write_text(
            "def f():\n    import json\n", encoding="utf-8"
        )
        map_ = _builder(root).build()
        assert _module(map_, "lazy").external_imports == ("json",)

    def test_circular_imports_are_stored_as_plain_edges(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        (root / "a_mod.py").write_text("import b_mod\n", encoding="utf-8")
        (root / "b_mod.py").write_text("import a_mod\n", encoding="utf-8")

        map_ = _builder(root).build()
        assert "b_mod" in _module(map_, "a_mod").internal_imports
        assert "a_mod" in _module(map_, "b_mod").internal_imports
        # Impact traversal must terminate.
        assert isinstance(map_.impact_set("a_mod"), frozenset)


# ---------------------------------------------------------------------------
# Graph queries
# ---------------------------------------------------------------------------


class TestGraphQueries:
    def test_forward_and_reverse_queries(self, repo):
        map_ = _builder(repo).build()
        assert "pkg.sub.gamma" in map_.dependencies_of("alpha")
        dependents = map_.dependents_of("pkg.beta")
        # gamma imports beta relatively; alpha's "from pkg import beta"
        # resolves to the package prefix.
        assert "pkg.sub.gamma" in dependents

    def test_dependents_of_unknown_module_empty(self, repo):
        map_ = _builder(repo).build()
        assert map_.dependents_of("nope") == ()
        assert map_.dependencies_of("nope") == ()

    def test_impact_set_transitive_with_depth_bound(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        (root / "base.py").write_text("B = 1\n", encoding="utf-8")
        (root / "mid.py").write_text("import base\n", encoding="utf-8")
        (root / "top.py").write_text("import mid\n", encoding="utf-8")

        map_ = _builder(root).build()
        depth1 = map_.impact_set("base", max_depth=1)
        assert depth1 == frozenset({"mid"})

        full = map_.impact_set("base", max_depth=3)
        assert full == frozenset({"mid", "top"})

    def test_impact_zero_depth_is_empty(self, repo):
        map_ = _builder(repo).build()
        assert map_.impact_set("alpha", max_depth=0) == frozenset()

    def test_counts_and_json_safety(self, repo):
        import json as jsonlib

        map_ = _builder(repo).build()
        assert map_.module_count() == len(map_.modules)
        assert map_.edge_count() == sum(
            len(i.internal_imports) for i in map_.modules
        )
        payload = jsonlib.dumps(map_.to_dict())  # must not raise
        assert '"module": "alpha"' in payload or '"module":"alpha"' in (
            jsonlib.dumps(map_.to_dict(), separators=(",", ":"))
        )


# ---------------------------------------------------------------------------
# Determinism and boundedness
# ---------------------------------------------------------------------------


class TestDeterminismAndBounds:
    def test_identical_trees_produce_identical_maps(self, tmp_path):
        roots = []
        for name in ("r1", "r2"):
            root = tmp_path / name
            (root / "pkg").mkdir(parents=True)
            (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
            (root / "pkg" / "m.py").write_text(
                "import json\n", encoding="utf-8"
            )
            roots.append(root)

        first = _builder(roots[0]).build()
        second = _builder(roots[1]).build()
        a, b = first.to_dict(), second.to_dict()
        a.pop("built_at"), b.pop("built_at")
        a.pop("root_label"), b.pop("root_label")
        assert a == b

    def test_max_modules_truncates_and_flags(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        for index in range(MAX_MODULES + 10):
            (root / f"mod_{index:05d}.py").write_text(
                f"X = {index}\n", encoding="utf-8"
            )

        map_ = _builder(root).build()
        assert map_.module_count() == MAX_MODULES
        assert map_.truncated is True

    def test_oversize_files_skipped(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        big = root / "big.py"
        big.write_text("X = 1\n" * 300_000, encoding="utf-8")  # > 1 MB
        (root / "small.py").write_text("Y = 2\n", encoding="utf-8")

        builder = RepositoryMapBuilder(root, max_file_bytes=10_000)
        map_ = builder.build()
        names = {info.module for info in map_.modules}
        assert names == {"small"}

    def test_language_from_catalog(self, repo):
        from atlas.research.source_catalog import LANGUAGE_BY_EXTENSION

        map_ = _builder(repo).build()
        alpha = _module(map_, "alpha")
        assert alpha.language == LANGUAGE_BY_EXTENSION[".py"]