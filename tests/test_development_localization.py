"""Deterministic development localization — file-then-symbol, evidence-producing.

Covers the two previously identified defects first (original-case identifier
surfaces, qualified method matching, no symbol fabrication from prose) and then
the full ladder, bounded ranked context, provenance, ambiguity preservation,
determinism and integration safety.

Everything composes the EXISTING repository map. No model, no provider, no
network, no new parser or dependency, and nothing here authorizes anything.
"""

from __future__ import annotations

import pathlib

import pytest

from atlas.evolution.development_localization import (
    DevelopmentLocalizer,
    LocalizationKind,
    LocalizationStatus,
    identifier_surfaces,
    is_identifier_shaped,
)

TARGET = "atlas.evolution.development_gap"


@pytest.fixture(scope="module")
def repository_map():
    from atlas.research.repository_map import RepositoryMapBuilder

    return RepositoryMapBuilder(pathlib.Path(__file__).resolve().parents[1]).build()


@pytest.fixture(scope="module")
def localizer(repository_map):
    return DevelopmentLocalizer(repository_map)


@pytest.fixture(scope="module")
def kernel():
    import pkgutil
    import tempfile

    import atlas.storage as storage_pkg

    tmp = pathlib.Path(tempfile.mkdtemp())
    db = tmp / "loc.db"
    saved = []
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


# ---------------------------------------------------------------------------
# 1. THE PREVIOUSLY IDENTIFIED DEFECTS (written first)
# ---------------------------------------------------------------------------


class TestIdentifierCasePreservation:
    def test_original_case_identifier_is_a_surface(self):
        surfaces = identifier_surfaces("Update RepositoryMap.")
        assert "RepositoryMap" in surfaces

    def test_prose_words_are_not_identifier_shaped(self):
        for prose in ("change", "update", "replace", "fix", "make", "delete",
                      "helper", "function", "class", "module"):
            assert is_identifier_shaped(prose) is False, prose

    def test_identifiers_are_identifier_shaped(self):
        for good in ("RepositoryMap", "TaskIntake", "some_helper",
                     "a.b.Class.method"):
            assert is_identifier_shaped(good) is True, good

    def test_unique_class_resolves_by_original_case_identifier(self, localizer):
        result = localizer.localize("Update RepositoryMap.")
        assert result.status is LocalizationStatus.RESOLVED
        assert result.symbol is not None
        assert result.symbol.name == "RepositoryMap"
        assert result.symbol.kind == "class"


class TestQualifiedSymbolMatching:
    def test_qualified_method_path_resolves_at_symbol_level(self, localizer):
        result = localizer.localize(
            "Update atlas.research.repository_map.RepositoryMap.tests_for_module."
        )
        assert result.status is LocalizationStatus.RESOLVED
        assert result.target_kind == LocalizationKind.SYMBOL.value
        assert result.symbol is not None
        assert result.symbol.name == "tests_for_module"
        assert result.symbol.kind == "method"
        assert result.target == "atlas.research.repository_map"

    def test_qualified_class_path_resolves_at_symbol_level(self, localizer):
        result = localizer.localize(
            "Change atlas.evolution.failure_classification.classify_failure."
        )
        assert result.symbol is not None
        assert result.symbol.qualified.endswith("classify_failure")

    def test_generic_english_words_do_not_fabricate_symbols(self, localizer):
        # A prose-only request must never resolve through a symbol name.
        for text in ("Change it.", "Update that.", "Fix this.", "Make it better."):
            result = localizer.localize(text)
            assert result.symbol is None, text
            assert result.status is not LocalizationStatus.RESOLVED, text

    def test_prose_word_carried_a_symbol_name_does_not_resolve(self, localizer):
        # "helper"/"update" are prose; they must not select a symbol named so.
        result = localizer.localize("Update the helper that validates empty input.")
        assert result.symbol is None
        assert result.target == ""


# ---------------------------------------------------------------------------
# 2. The localization ladder
# ---------------------------------------------------------------------------


class TestTargetLocalization:
    def test_exact_module_by_name_tokens(self, localizer):
        result = localizer.localize("Improve the development gap module.")
        assert result.status is LocalizationStatus.RESOLVED
        assert result.target == TARGET
        assert result.target_kind == LocalizationKind.MODULE.value

    def test_exact_dotted_module(self, localizer):
        result = localizer.localize(f"Change {TARGET} so it rejects empty input.")
        assert result.resolved and result.target == TARGET

    def test_exact_file_path(self, localizer):
        result = localizer.localize(
            "Change atlas/evolution/development_gap.py to reject empty input."
        )
        assert result.resolved and result.target == TARGET
        assert result.evidence == ("exact file path match",)

    def test_natural_language_component_reference(self, localizer):
        result = localizer.localize("Change the task intake classification.")
        assert result.resolved and result.target == "atlas.conversation.task_intake"

    def test_helper_reference_never_invents_a_target(self, localizer):
        # "the helper that validates empty input" names no identifier: Atlas must
        # not choose one of the many plausible helpers.
        result = localizer.localize("Update the helper that validates empty input.")
        assert not result.resolved
        assert result.target == ""
        assert result.status in (
            LocalizationStatus.AMBIGUOUS, LocalizationStatus.UNRESOLVED,
        )

    def test_nonexistent_target_never_resolves(self, localizer):
        # No evidence-backed candidate exists, so the result must not be a
        # verified target (ranked lexical fallback is allowed but stays unverified).
        result = localizer.localize("Improve the zzz nonexistent widget subsystem.")
        assert not result.resolved
        assert result.target == ""

    def test_ranking_alone_never_resolves(self, localizer):
        result = localizer.localize("Fix the function that resolves typed targets.")
        if result.status is LocalizationStatus.AMBIGUOUS:
            assert result.target == ""
            assert all(c.score == 0.0 for c in result.candidates)

    def test_empty_and_non_text_are_unresolved(self, localizer):
        for bad in ("", "   ", None, 42):
            assert localizer.localize(bad).status is LocalizationStatus.UNRESOLVED

    def test_missing_map_is_inert_and_honest(self):
        result = DevelopmentLocalizer(None).localize("Improve the development gap module.")
        assert result.status is LocalizationStatus.UNRESOLVED and result.target == ""


# ---------------------------------------------------------------------------
# 3. Bounded ranked context + provenance
# ---------------------------------------------------------------------------


class TestRankedContext:
    def test_resolved_target_carries_bounded_context(self, localizer):
        context = localizer.localize("Improve the development gap module.").context
        assert context.modules == (TARGET,)
        assert context.symbols and context.tests and context.dependents

    def test_context_respects_its_budget(self, localizer):
        from atlas.evolution.development_localization import MAX_SYMBOLS, MAX_TESTS

        context = localizer.localize("Change the task intake classification.").context
        assert len(context.symbols) <= MAX_SYMBOLS
        assert len(context.tests) <= MAX_TESTS

    def test_every_selection_explains_itself(self, localizer):
        result = localizer.localize("Improve the development gap module.")
        assert result.evidence
        assert result.candidates[0].reasons

    def test_context_facts_come_from_the_map(self, localizer, repository_map):
        result = localizer.localize("Improve the development gap module.")
        known_modules = {module.module for module in repository_map.modules}
        known_paths = {module.path for module in repository_map.modules}
        assert result.target in known_modules
        assert set(result.context.tests) <= known_paths

    def test_no_fabricated_symbols(self, localizer, repository_map):
        known = {info.qualified for info in repository_map.symbols}
        for symbol in localizer.localize("Improve the development gap module.").context.symbols:
            assert symbol.qualified in known

    def test_symbol_localization_carries_its_symbol(self, localizer):
        result = localizer.localize(
            "Update atlas.research.repository_map.RepositoryMap.tests_for_module."
        )
        assert result.symbol is not None
        assert result.symbol in result.context.symbols


# ---------------------------------------------------------------------------
# 4. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    @pytest.mark.parametrize("text", [
        "Improve the development gap module.",
        "Update RepositoryMap.",
        "Update atlas.research.repository_map.RepositoryMap.tests_for_module.",
        "Update the helper that validates empty input.",
        "Change it.",
        "Fix the function that resolves typed targets.",
        "Change the task intake classification.",
    ])
    def test_repeated_localization_is_identical(self, localizer, text):
        first = localizer.localize(text)
        second = localizer.localize(text)
        assert first.to_dict() == second.to_dict()
        assert [c.identifier for c in first.candidates] == [
            c.identifier for c in second.candidates
        ]

    def test_fresh_map_produces_identical_result(self, repository_map):
        from atlas.research.repository_map import RepositoryMapBuilder

        other = RepositoryMapBuilder(pathlib.Path(__file__).resolve().parents[1]).build()
        text = "Improve the development gap module."
        assert DevelopmentLocalizer(repository_map).localize(text).to_dict() == (
            DevelopmentLocalizer(other).localize(text).to_dict()
        )

    def test_surfaces_are_bounded_and_ordered(self):
        from atlas.evolution.development_localization import MAX_SURFACES

        surfaces = identifier_surfaces(
            " ".join(f"someThing_{index}" for index in range(80))
        )
        assert len(surfaces) <= MAX_SURFACES
        assert list(surfaces) == sorted(surfaces, key=lambda s: (-len(s), s))


# ---------------------------------------------------------------------------
# 5. Integration, safety and unchanged classification
# ---------------------------------------------------------------------------


class TestIntegrationAndSafety:
    def test_kernel_localization_is_reachable(self, kernel):
        payload = kernel.development_localization("Improve the development gap module.")
        assert payload["status"] == "resolved" and payload["target"] == TARGET

    def test_kernel_localization_is_fail_soft(self, kernel):
        assert kernel.development_localization("")["status"] == "unresolved"

    def test_localization_authorizes_nothing(self, kernel):
        before = len(kernel.pending_promotion_reviews())
        kernel.development_localization("Improve the development gap module.")
        assert len(kernel.pending_promotion_reviews()) == before

    def test_no_authority_surface(self):
        localizer = DevelopmentLocalizer(None)
        for forbidden in ("approve", "promote", "authorize", "execute", "apply"):
            assert not hasattr(localizer, forbidden)

    def test_module_has_no_framework_or_model_dependency(self):
        import ast

        path = pathlib.Path(__file__).resolve().parents[1] / (
            "atlas/evolution/development_localization.py"
        )
        imported: set[str] = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for forbidden in ("openai", "anthropic", "requests", "spacy", "tree_sitter",
                          "libcst", "torch", "transformers", "numpy"):
            assert forbidden not in imported

    @pytest.mark.parametrize("text,expected", [
        ("Improve the development gap module.", "development_request"),
        ("Investigate the development gap helper.", "investigation_request"),
        ("What would be affected if I change atlas/memory/manager.py?",
         "repository_impact_request"),
        ("Change it.", "conversation"),
        ("Hello there.", "conversation"),
        ("Reject the proposal.", "rejection_request"),
    ])
    def test_classification_is_unchanged_by_localization(self, kernel, text, expected):
        assert kernel._conversation._intake(text).task_type.value == expected

    def test_repository_impact_keeps_its_payload(self, kernel):
        message = kernel.chat("What would be affected if I change atlas/memory/manager.py?")
        payload = (message.metadata or {}).get("repository_impact")
        assert payload and payload.get("status") == "resolved"
