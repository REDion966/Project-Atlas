"""Command 4 — bounded, deterministic fault localization.

Pure and model-free: every test injects a small repository map.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from atlas.evolution.fault_localization import (  # noqa: E402
    DEFAULT_MAX_SUSPECTS,
    MAX_SUSPECTS_LIMIT,
    FaultLocalization,
    SuspectKind,
    localize_fault,
    module_of_path,
)
from atlas.research.repository_map import RepositoryMapBuilder  # noqa: E402

TREE = {
    "pkg/__init__.py": "",
    "pkg/core.py": (
        "from pkg.support import helper\n"
        "\n"
        "\n"
        "def run(value):\n"
        "    return helper(value)\n"
    ),
    "pkg/support.py": (
        "def helper(value):\n"
        "    return value + 1\n"
    ),
    "pkg/other.py": (
        "from pkg.core import run\n"
        "\n"
        "\n"
        "def caller():\n"
        "    return run(1)\n"
    ),
    "tests/test_core.py": (
        "from pkg.core import run\n"
        "\n"
        "\n"
        "def test_run():\n"
        "    assert run(1) == 2\n"
    ),
}


@pytest.fixture(scope="module")
def repository_map(tmp_path_factory):
    root = tmp_path_factory.mktemp("fault_localization")
    for relative, text in TREE.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return RepositoryMapBuilder(root).build()


class TestPathToModule:
    def test_paths_map_to_dotted_modules(self):
        assert module_of_path("pkg/core.py") == "pkg.core"
        assert module_of_path("pkg\\core.py") == "pkg.core"
        assert module_of_path("pkg/__init__.py") == "pkg"

    def test_non_modules_map_to_nothing(self):
        for bad in ("README.md", "", None, "pkg/core.txt"):
            assert module_of_path(bad) == ""


class TestRanking:
    def test_a_changed_symbol_outranks_a_changed_module(self, repository_map):
        result = localize_fault(
            repository_map=repository_map,
            changed_paths=["pkg/support.py"],
            changed_symbols=["pkg.support.helper"],
        )
        assert result.available
        assert result.suspects[0].qualified == "pkg.support.helper"
        assert SuspectKind.CHANGED_SYMBOL in result.suspects[0].kinds

    def test_callers_are_reported_as_suspects(self, repository_map):
        result = localize_fault(
            repository_map=repository_map,
            changed_paths=["pkg/support.py"],
            changed_symbols=["pkg.support.helper"],
        )
        kinds = {kind for suspect in result.suspects for kind in suspect.kinds}
        assert SuspectKind.CALLER_OF_CHANGED in kinds
        assert any(s.qualified == "pkg.core.run" for s in result.suspects)

    def test_every_suspect_carries_a_reason(self, repository_map):
        result = localize_fault(
            repository_map=repository_map,
            changed_paths=["pkg/core.py"],
            changed_symbols=["pkg.core.run"],
        )
        assert result.suspects
        for suspect in result.suspects:
            assert suspect.reasons
            assert all(len(reason) <= 200 for reason in suspect.reasons)

    def test_the_verification_target_contributes_suspects(self, repository_map):
        result = localize_fault(
            repository_map=repository_map,
            changed_paths=["pkg/support.py"],
            verify_target="tests/test_core.py",
        )
        kinds = {kind for suspect in result.suspects for kind in suspect.kinds}
        assert SuspectKind.TEST_REFERENCED in kinds

    def test_the_ranking_is_deterministic(self, repository_map):
        first = localize_fault(
            repository_map=repository_map,
            changed_paths=["pkg/core.py"],
            changed_symbols=["pkg.core.run"],
            verify_target="tests/test_core.py",
        ).to_dict()
        second = localize_fault(
            repository_map=repository_map,
            changed_paths=["pkg/core.py"],
            changed_symbols=["pkg.core.run"],
            verify_target="tests/test_core.py",
        ).to_dict()
        assert first == second

    def test_scores_are_descending(self, repository_map):
        result = localize_fault(
            repository_map=repository_map,
            changed_paths=["pkg/core.py"],
            changed_symbols=["pkg.core.run"],
        )
        scores = [suspect.score for suspect in result.suspects]
        assert scores == sorted(scores, reverse=True)

    def test_a_changed_symbol_carries_its_region(self, repository_map):
        result = localize_fault(
            repository_map=repository_map,
            changed_paths=["pkg/support.py"],
            changed_symbols=["pkg.support.helper"],
        )
        top = result.top()
        assert top is not None
        assert top.start_line == 1
        assert top.end_line >= top.start_line
        assert top.path == "pkg/support.py"


class TestBoundsAndFailingClosed:
    def test_no_evidence_yields_an_empty_result(self, repository_map):
        result = localize_fault(repository_map=repository_map)
        assert result.available is False
        assert result.suspects == ()
        assert result.reasons

    def test_no_map_yields_an_empty_result(self):
        result = localize_fault(repository_map=None, changed_paths=["pkg/x.py"])
        assert result.available is False

    def test_a_broken_map_yields_an_empty_result(self):
        class _Broken:
            def symbols_in_module(self, *a, **k):
                raise RuntimeError("map down")

            def callers_of(self, *a, **k):
                raise RuntimeError("map down")

            modules = ()
            symbols = ()

        result = localize_fault(
            repository_map=_Broken(), changed_paths=["pkg/x.py"]
        )
        assert isinstance(result, FaultLocalization)

    def test_the_suspect_list_is_bounded(self, repository_map):
        result = localize_fault(
            repository_map=repository_map,
            changed_paths=["pkg/core.py"],
            max_suspects=1,
        )
        assert len(result.suspects) <= 1
        assert result.truncated is True

    def test_a_malformed_bound_falls_back(self, repository_map):
        result = localize_fault(
            repository_map=repository_map,
            changed_paths=["pkg/core.py"],
            max_suspects="lots",
        )
        assert len(result.suspects) <= DEFAULT_MAX_SUSPECTS

    def test_the_hard_ceiling_holds(self, repository_map):
        result = localize_fault(
            repository_map=repository_map,
            changed_paths=["pkg/core.py"],
            max_suspects=10_000,
        )
        assert len(result.suspects) <= MAX_SUSPECTS_LIMIT

    def test_malformed_inputs_never_raise(self, repository_map):
        for bad in (None, 5, "text", [None], [""]):
            result = localize_fault(
                repository_map=repository_map, changed_paths=bad, changed_symbols=bad
            )
            assert isinstance(result.suspects, tuple)


class TestContract:
    def test_to_dict_is_json_safe_and_grants_nothing(self, repository_map):
        result = localize_fault(
            repository_map=repository_map, changed_paths=["pkg/core.py"]
        )
        payload = result.to_dict()
        for forbidden in ("authorized", "approved", "execute", "promote", "apply"):
            assert forbidden not in payload
        assert "suspects" in payload and "available" in payload

    def test_the_inputs_are_echoed_for_auditability(self, repository_map):
        result = localize_fault(
            repository_map=repository_map,
            changed_paths=["pkg/core.py"],
            failure_category="assertion_failure",
            verify_target="tests/test_core.py",
        )
        assert result.changed_modules == ("pkg.core",)
        assert result.failure_category == "assertion_failure"
        assert result.verify_target == "tests/test_core.py"

    def test_the_result_is_immutable(self, repository_map):
        result = localize_fault(repository_map=repository_map, changed_paths=["pkg/core.py"])
        with pytest.raises(Exception):
            result.suspects = ()  # type: ignore[misc]
