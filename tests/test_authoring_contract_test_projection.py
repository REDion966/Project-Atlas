"""Gap 2 — deterministic contract + relevant-test projections.

Pins the bounded projections added to the authoring context and verification
selection. Everything here reuses EXISTING Atlas structures:

  * ``RepositoryMap.tests_for_module`` — a projection over the existing
    reverse-import index (no ``is_test`` classification, no test registry);
  * the owning component's DECLARED boundary from the existing architecture
    model (no new contract representation, no behavioural inference);
  * ``select_relevant_tests`` gaining caller-supplied ``derived_tests``
    alongside the existing name convention.

No provider is contacted, nothing is executed, and nothing is promoted.
"""

from __future__ import annotations

import pathlib

import pytest

from atlas.evolution.development_cycle import DevelopmentNeed
from atlas.evolution.development_test_selection import select_relevant_tests
from atlas.evolution.model_assisted_supplier import (
    MAX_CONTEXT_CONTRACT_ITEMS,
    MAX_CONTEXT_TESTS,
    ModelAssistedChangeSupplier,
)
from atlas.research.repository_map import (
    RepositoryMapBuilder,
    TEST_MODULE_PREFIX,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = "atlas.evolution.development_gap"
TARGET_PATH = "atlas/evolution/development_gap.py"


@pytest.fixture(scope="module")
def repository_map():
    return RepositoryMapBuilder(REPO_ROOT).build()


@pytest.fixture(scope="module")
def rebuilt_repository_map():
    return RepositoryMapBuilder(REPO_ROOT).build()


@pytest.fixture(scope="module")
def kernel():
    import tempfile
    import pkgutil

    import atlas.storage as storage_pkg

    tmp = pathlib.Path(tempfile.mkdtemp())
    db = tmp / "kernel.db"
    saved: list[tuple[type, object]] = []
    for info in pkgutil.iter_modules(storage_pkg.__path__):
        try:
            module = __import__(f"atlas.storage.{info.name}", fromlist=["*"])
        except Exception:  # noqa: BLE001
            continue
        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and hasattr(obj, "DEFAULT_DB_PATH"):
                saved.append((obj, obj.DEFAULT_DB_PATH))
                obj.DEFAULT_DB_PATH = db
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    try:
        yield atlas
    finally:
        atlas.shutdown()
        for obj, original in saved:
            obj.DEFAULT_DB_PATH = original


def _need(target=TARGET, title="Improve the development gap adjudication"):
    return DevelopmentNeed(
        title=title,
        summary="Modify the implementation while preserving its interface.",
        target_components=(target,),
    )


def _context(repository_map, architecture_model=None, need=None):
    return ModelAssistedChangeSupplier(
        authoring_model=lambda p: "{}",
        repository_map=repository_map,
        architecture_model=architecture_model,
    )._build_authoring_context(need or _need())


# ---------------------------------------------------------------------------
# A/B. RepositoryMap test projection
# ---------------------------------------------------------------------------


class TestTestProjection:
    def test_real_test_modules_are_returned(self, repository_map):
        tests = repository_map.tests_for_module(TARGET)
        assert tests, "a real module with import dependents must be nonempty"
        known = {module.path for module in repository_map.modules}
        for path in tests:
            assert path in known, f"{path} is not a real repository module"
            assert path.startswith("tests/"), path
            assert path.endswith(".py"), path

    def test_only_tests_prefix_modules_are_returned(self, repository_map):
        for path in repository_map.tests_for_module("atlas.research.repository_map"):
            assert path.startswith("tests/"), path
        # A module with no test importer yields nothing rather than a guess.
        assert repository_map.tests_for_module("atlas.does.not.exist") == ()

    def test_result_is_bounded(self, repository_map):
        everything = repository_map.tests_for_module(TARGET, limit=1000)
        assert len(repository_map.tests_for_module(TARGET, limit=2)) == 2
        assert len(everything) >= 2
        assert len(repository_map.tests_for_module(TARGET)) <= 20
        assert repository_map.tests_for_module(TARGET, limit=0) == ()
        assert repository_map.tests_for_module(TARGET, limit=-1) == ()

    def test_result_is_deterministic(self, repository_map, rebuilt_repository_map):
        first = repository_map.tests_for_module(TARGET)
        assert first == repository_map.tests_for_module(TARGET)
        assert first == rebuilt_repository_map.tests_for_module(TARGET)

    def test_no_fabricated_names(self, repository_map):
        known = {module.path for module in repository_map.modules}
        for path in repository_map.tests_for_module(TARGET, limit=1000):
            assert path in known

    def test_projection_matches_the_existing_reverse_index(self, repository_map):
        dependents = repository_map.dependents_of(TARGET)
        expected = [
            module.path
            for module in repository_map.modules
            if module.module.startswith(TEST_MODULE_PREFIX)
            and module.module in dependents
        ]
        assert set(repository_map.tests_for_module(TARGET, limit=1000)) == set(expected)

    def test_no_is_test_classification_was_introduced(self, repository_map):
        for module in repository_map.modules:
            assert not hasattr(module, "is_test")
            assert not hasattr(module, "covers_component")


# ---------------------------------------------------------------------------
# C/D. Authoring context — contract and test blocks
# ---------------------------------------------------------------------------


class TestAuthoringContextProjection:
    def test_declared_boundary_block_uses_real_architecture_metadata(
        self, repository_map, kernel
    ):
        from atlas.evolution.model_assisted_supplier import _owning_component

        architecture = kernel.architecture_model()
        context = _context(repository_map, architecture)
        assert "declared boundary for" in context
        assert "existing architecture metadata" in context

        component = _owning_component(architecture, TARGET)
        assert component is not None
        assert str(component.name) in context
        if component.responsibility:
            assert "responsibility:" in context
            assert str(component.responsibility)[:60] in context
        for declared in list(component.declared_dependencies)[:MAX_CONTEXT_CONTRACT_ITEMS]:
            assert str(declared) in context
        for provided in list(component.provided_capabilities)[:MAX_CONTEXT_CONTRACT_ITEMS]:
            assert str(provided) in context

    def test_boundary_block_is_bounded(self, repository_map, kernel):
        context = _context(repository_map, kernel.architecture_model())
        line = next(
            line for line in context.splitlines() if "declared boundary for" in line
        )
        assert line.startswith("    ")

    def test_relevant_test_block_is_present_bounded_and_real(
        self, repository_map, kernel
    ):
        architecture = kernel.architecture_model()
        context = _context(repository_map, architecture)
        assert "relevant test modules (import-derived repository evidence" in context
        assert "not a guarantee of behavioural coverage" in context

        listed = [
            line.strip()
            for line in context.splitlines()
            if line.startswith("        tests/")
        ]
        assert listed, "the relevant-test block must list real modules"
        assert len(listed) <= MAX_CONTEXT_TESTS
        assert len(listed) == len(set(listed)), "no duplicates"
        assert listed == sorted(listed), "deterministic ordering"
        known = {module.path for module in repository_map.modules}
        for path in listed:
            assert path in known, f"fabricated test path {path}"
        # The real case is far above the bound, so truncation is stated.
        assert "truncated: first" in context

    def test_existing_context_is_augmented_not_replaced(self, repository_map, kernel):
        context = _context(repository_map, kernel.architecture_model())
        assert "Repository context" in context
        assert "    source" in context
        assert "    symbols:" in context

    def test_absent_model_omits_the_boundary_block_only(self, repository_map):
        context = _context(repository_map, None)
        assert "declared boundary for" not in context
        assert "relevant test modules" in context

    def test_absent_map_omits_the_test_block_only(self, kernel):
        # With no repository map there is no ranking, so there is no context at
        # all — the boundary block must not appear on its own.
        context = _context(None, kernel.architecture_model())
        assert context == ""
        assert "relevant test modules" not in context
        assert "declared boundary for" not in context

    def test_context_is_deterministic(self, repository_map, kernel):
        architecture = kernel.architecture_model()
        assert _context(repository_map, architecture) == _context(
            repository_map, architecture
        )

    def test_unowned_module_omits_the_boundary(self, repository_map, kernel):
        from atlas.evolution.model_assisted_supplier import _owning_component

        assert _owning_component(kernel.architecture_model(), "atlas.zzz.nope") is None


# ---------------------------------------------------------------------------
# E/F. Verification selection
# ---------------------------------------------------------------------------


class TestVerificationSelection:
    def test_derived_candidates_participate(self, repository_map):
        derived = list(repository_map.tests_for_module(TARGET))
        assert derived
        # The measured failure: the name convention alone finds nothing here.
        assert select_relevant_tests([TARGET_PATH], [], max_tests=20) == ()
        merged = select_relevant_tests(
            [TARGET_PATH], [], max_tests=20, derived_tests=derived
        )
        assert merged, "derived candidates must make the result nonzero"
        assert set(merged) == set(derived)

    def test_name_convention_still_works_and_is_unchanged(self):
        assert select_relevant_tests(
            ["atlas/conversation/history.py"], ["tests/test_conversation_history.py"]
        ) == ("tests/test_conversation_history.py",)
        # Passing no derived candidates leaves the name-only result identical.
        assert select_relevant_tests(
            ["atlas/conversation/history.py"],
            ["tests/test_conversation_history.py"],
            derived_tests=(),
        ) == ("tests/test_conversation_history.py",)

    def test_merge_is_deduplicated_bounded_and_sorted(self, repository_map):
        derived = list(repository_map.tests_for_module(TARGET))
        name_hit = ["tests/test_development_gap_capability_adjudication.py"]
        merged = select_relevant_tests(
            [TARGET_PATH], name_hit, max_tests=5, derived_tests=derived
        )
        assert len(merged) <= 5
        assert len(merged) == len(set(merged))
        assert list(merged) == sorted(merged)

    def test_no_fabricated_paths_from_derived_input(self):
        assert select_relevant_tests(["atlas/x.py"], [], derived_tests=["nope"]) == ()
        assert select_relevant_tests(
            ["atlas/x.py"], [], derived_tests=["tests/not_python.txt"]
        ) == ()

    def test_no_registry_or_is_test_was_introduced(self):
        import atlas.evolution.development_test_selection as module

        source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        for forbidden in ("TestRegistry", "TestMap", "is_test", "covers_component"):
            assert forbidden not in source


# ---------------------------------------------------------------------------
# G/H. Provider boundary is unchanged
# ---------------------------------------------------------------------------


class TestProviderBoundaryUnchanged:
    def test_provider_off_is_zero_invocation_and_none(self, repository_map, kernel):
        calls: list[str] = []
        supplier = ModelAssistedChangeSupplier(
            repository_map=repository_map,
            architecture_model=kernel.architecture_model(),
        )
        assert supplier.supply_changes(_need()) is None
        assert calls == []

    def test_enabled_provider_receives_the_new_context(self, repository_map, kernel):
        calls: list[str] = []
        supplier = ModelAssistedChangeSupplier(
            authoring_model=lambda p: calls.append(p) or "{}",
            repository_map=repository_map,
            architecture_model=kernel.architecture_model(),
        )
        assert supplier.supply_changes(_need()) is None  # "{}" is not a valid draft
        assert len(calls) == 1
        assert "declared boundary for" in calls[0]
        assert "relevant test modules" in calls[0]

    def test_malformed_output_still_fails_closed(self, repository_map, kernel):
        for bad in ("not json", "{}", "[]", '{"unexpected": 1}'):
            supplier = ModelAssistedChangeSupplier(
                authoring_model=lambda p, _b=bad: _b,
                repository_map=repository_map,
                architecture_model=kernel.architecture_model(),
            )
            assert supplier.supply_changes(_need()) is None, bad

    def test_raising_provider_still_fails_closed(self, repository_map, kernel):
        def _boom(prompt):
            raise RuntimeError("provider exploded")

        supplier = ModelAssistedChangeSupplier(
            authoring_model=_boom,
            repository_map=repository_map,
            architecture_model=kernel.architecture_model(),
        )
        assert supplier.supply_changes(_need()) is None


# ---------------------------------------------------------------------------
# I. Determinism across a rebuilt map
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_projection_is_stable_across_maps(
        self, repository_map, rebuilt_repository_map
    ):
        assert repository_map.tests_for_module(TARGET) == (
            rebuilt_repository_map.tests_for_module(TARGET)
        )

    def test_selection_is_stable(self, repository_map, rebuilt_repository_map):
        derived_a = list(repository_map.tests_for_module(TARGET))
        derived_b = list(rebuilt_repository_map.tests_for_module(TARGET))
        assert select_relevant_tests(
            [TARGET_PATH], [], derived_tests=derived_a
        ) == select_relevant_tests([TARGET_PATH], [], derived_tests=derived_b)


# ---------------------------------------------------------------------------
# J. The previous milestone's adjudication is unchanged
# ---------------------------------------------------------------------------


class TestPreviousMilestoneUnchanged:
    def test_improvement_request_remains_already_supported(self, kernel):
        result = kernel.run_development_driver("Improve the investigation capability.")
        assert result.terminal.value == "already_supported"
        assert kernel.pending_promotion_reviews() == []
