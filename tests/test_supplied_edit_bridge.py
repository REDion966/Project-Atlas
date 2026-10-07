"""The plan -> authoring bridge for EXPLICITLY SUPPLIED edits.

Covers the deliberately narrow supported class (a request that supplies its own
replacement code for a named symbol) and, above all, the fail-closed boundary
around it. Ends with a REAL end-to-end bounded development exercise on an
isolated fixture repository: request -> intent -> localization -> plan ->
verification expectations -> supplied edit -> CodeChangeSet -> changed source ->
executed verification.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
import pathlib
import shutil
import sys

import pytest

from atlas.evolution.development_cycle import DevelopmentNeed
from atlas.evolution.development_localization import DevelopmentLocalizer
from atlas.evolution.structural_editor import (
    StructuralChangeSupplier,
    StructuralEdit,
    apply_structural_edits,
)
from atlas.evolution.supplied_edit_intake import supplied_structural_edit
from atlas.research.repository_map import RepositoryMapBuilder

ROOT = pathlib.Path(__file__).resolve().parents[1]

REQUEST = (
    "Update the explicitly named helper `add` in widget.py while preserving its "
    "public interface:\n\n"
    "```python\ndef add(a, b):\n    return a + b\n```\n"
)

ORIGINAL_WIDGET = "def add(a, b):\n    return a - b\n\n\ndef label():\n    return 'widget'\n"


@pytest.fixture(scope="module")
def kernel():
    import pkgutil
    import tempfile

    import atlas.storage as storage_pkg

    tmp = pathlib.Path(tempfile.mkdtemp())
    db = tmp / "bridge.db"
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


@pytest.fixture(scope="module")
def fixture_repo(tmp_path_factory):
    """A tiny isolated repository — never Atlas's own production source."""
    root = tmp_path_factory.mktemp("widget_repo")
    (root / "widget.py").write_text(ORIGINAL_WIDGET, encoding="utf-8")
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "test_widget.py").write_text(
        "from widget import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture(scope="module")
def fixture_localization(fixture_repo):
    repository_map = RepositoryMapBuilder(fixture_repo).build()
    return DevelopmentLocalizer(repository_map).localize(REQUEST)


@pytest.fixture(scope="module")
def real_localizer():
    return DevelopmentLocalizer(RepositoryMapBuilder(ROOT).build())


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _entry(localization, **overrides):
    edit = supplied_structural_edit(REQUEST, localization)
    assert edit.entry is not None, edit.reason
    return dict(edit.entry, **overrides)


# ---------------------------------------------------------------------------
# A/B. The supported class: explicit replacement -> change -> verification
# ---------------------------------------------------------------------------


class TestSupportedSuppliedEdit:
    def test_explicit_replacement_produces_a_structural_spec(self, fixture_localization):
        edit = supplied_structural_edit(REQUEST, fixture_localization)
        assert edit.ok is True, edit.reason
        assert edit.symbol == "add"
        assert edit.kind == "replace"
        assert edit.entry == {
            "path": "widget.py",
            "symbol": "add",
            "kind": "replace",
            "source": "def add(a, b):\n    return a + b\n",
        }

    def test_spec_is_a_proposal_not_permission(self, fixture_localization):
        payload = supplied_structural_edit(REQUEST, fixture_localization).to_dict()
        assert payload["authorized"] is False
        assert payload["executed"] is False

    def test_existing_supplier_turns_the_spec_into_a_change_set(
        self, fixture_repo, fixture_localization
    ):
        need = DevelopmentNeed(
            title=REQUEST, summary=REQUEST, metadata={"structural": [_entry(fixture_localization)]}
        )
        changes = StructuralChangeSupplier(root=fixture_repo).supply_changes(need)
        assert changes is not None
        assert changes.origin == "deterministic-structural"
        path, content = changes.code_changes[0]
        assert path == "widget.py"
        assert "return a + b" in content
        assert "def label():\n    return 'widget'" in content

    def test_authoring_preserves_the_declared_interface(
        self, fixture_repo, fixture_localization
    ):
        need = DevelopmentNeed(
            title=REQUEST, summary=REQUEST, metadata={"structural": [_entry(fixture_localization)]}
        )
        _, content = StructuralChangeSupplier(
            root=fixture_repo
        ).supply_changes(need).code_changes[0]
        updated = fixture_repo / "widget_updated.py"
        updated.write_text(content, encoding="utf-8")
        assert list(inspect.signature(_load(updated, "widget_i1").add).parameters) == [
            "a",
            "b",
        ]

    def test_delete_and_insert_after_kinds_are_recognised(self, fixture_localization):
        delete = supplied_structural_edit(
            "Delete the helper `label` in widget.py:\n\n```python\n```\n",
            fixture_localization,
        )
        assert delete.ok and delete.kind == "delete"
        insert = supplied_structural_edit(
            "Insert after `add` in widget.py:\n\n```python\ndef extra():\n    return 1\n```\n",
            fixture_localization,
        )
        assert insert.ok and insert.kind == "insert_after"


# ---------------------------------------------------------------------------
# C–I. Fail-closed boundary
# ---------------------------------------------------------------------------


class TestFailClosed:
    def test_ambiguous_target_yields_no_authoring(self, real_localizer):
        request = (
            "Update the helper that validates empty input:\n\n"
            "```python\ndef helper():\n    return 1\n```\n"
        )
        localization = real_localizer.localize(request)
        assert localization.resolved is False
        edit = supplied_structural_edit(request, localization)
        assert edit.ok is False and edit.entry is None
        assert "not be localized" in edit.reason

    def test_unresolved_target_yields_no_authoring(self, real_localizer):
        request = (
            "Improve the zzz nonexistent widget subsystem:\n\n"
            "```python\ndef thing():\n    return 1\n```\n"
        )
        edit = supplied_structural_edit(request, real_localizer.localize(request))
        assert edit.ok is False and edit.entry is None

    def test_missing_replacement_yields_no_authoring(self, fixture_localization):
        edit = supplied_structural_edit(
            "Update the helper `add` in widget.py.", fixture_localization
        )
        assert edit.ok is False
        assert "no code block" in edit.reason

    def test_missing_symbol_yields_no_authoring(self, fixture_localization):
        edit = supplied_structural_edit(
            "Update widget.py:\n\n```python\ndef add(a, b):\n    return a + b\n```\n",
            fixture_localization,
        )
        assert edit.ok is False
        assert "names no target symbol" in edit.reason

    def test_target_mismatch_yields_no_authoring(self, fixture_localization):
        edit = supplied_structural_edit(
            "Update the helper `subtract` in widget.py:\n\n"
            "```python\ndef subtract(a, b):\n    return a - b\n```\n",
            fixture_localization,
        )
        assert edit.ok is False
        assert "is not part of the localized target" in edit.reason

    def test_multiple_symbols_yield_no_authoring(self, fixture_localization):
        edit = supplied_structural_edit(
            "Update the helpers `add` and `label` in widget.py:\n\n"
            "```python\ndef add(a, b):\n    return a + b\n```\n",
            fixture_localization,
        )
        assert edit.ok is False

    def test_multiple_code_blocks_yield_no_authoring(self, fixture_localization):
        edit = supplied_structural_edit(
            REQUEST + "\n```python\ndef other():\n    return 2\n```\n",
            fixture_localization,
        )
        assert edit.ok is False
        assert "more than one code block" in edit.reason

    def test_missing_localization_yields_no_authoring(self):
        assert supplied_structural_edit(REQUEST, None).ok is False

    def test_empty_request_yields_no_authoring(self, fixture_localization):
        assert supplied_structural_edit("", fixture_localization).ok is False

    def test_unsupported_edit_kind_is_refused_by_the_supplier(
        self, fixture_repo, fixture_localization
    ):
        bad = _entry(fixture_localization, kind="rewrite")
        need = DevelopmentNeed(title="x", summary="x", metadata={"structural": [bad]})
        with pytest.raises(ValueError, match="unsupported structural kind"):
            StructuralChangeSupplier(root=fixture_repo).supply_changes(need)

    def test_malformed_replacement_is_refused(self):
        result = apply_structural_edits(
            "def add(a, b):\n    return a - b\n",
            [
                StructuralEdit(
                    path="widget.py",
                    symbol="add",
                    source="def add(a, b)\n    return a + b",
                )
            ],
        )
        assert result.ok is False
        assert "invalid syntax" in result.reason

    def test_unrelated_or_escaping_path_is_rejected(
        self, fixture_repo, fixture_localization
    ):
        escaping = _entry(fixture_localization, path="../outside.py")
        need = DevelopmentNeed(title="x", summary="x", metadata={"structural": [escaping]})
        with pytest.raises(ValueError):
            StructuralChangeSupplier(root=fixture_repo).supply_changes(need)

    def test_unknown_symbol_is_refused_by_the_supplier(
        self, fixture_repo, fixture_localization
    ):
        bad = _entry(fixture_localization, symbol="not_a_real_symbol")
        need = DevelopmentNeed(title="x", summary="x", metadata={"structural": [bad]})
        with pytest.raises(ValueError, match="was not found"):
            StructuralChangeSupplier(root=fixture_repo).supply_changes(need)


# ---------------------------------------------------------------------------
# J–T. Integration, governance and determinism
# ---------------------------------------------------------------------------


class TestIntegrationAndGovernance:
    def test_explicit_edits_need_no_model_and_no_provider(self, kernel):
        request = (
            "Update the explicitly named helper `RepositoryMapBuilder` in "
            "atlas/research/repository_map.py:\n\n"
            "```python\nclass RepositoryMapBuilder:\n    pass\n```\n"
        )
        assert kernel.development_supplied_edit(request)["ok"] is True
        source = (
            ROOT / "atlas/evolution/supplied_edit_intake.py"
        ).read_text(encoding="utf-8")
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not (
            {"openai", "anthropic", "requests", "torch", "transformers", "spacy"}
            & imported
        )

    def test_the_bridge_authorizes_and_promotes_nothing(self, kernel):
        before = len(kernel.pending_promotion_reviews())
        payload = kernel.development_supplied_edit(REQUEST)
        assert payload["authorized"] is False and payload["executed"] is False
        assert len(kernel.pending_promotion_reviews()) == before

    def test_non_development_requests_are_unchanged(self, kernel):
        for request in (
            "Investigate the development gap helper.",
            "What would be affected if I change atlas/memory/manager.py?",
            "Change it.",
            "Hello there.",
        ):
            assert kernel.development_supplied_edit(request) == {}, request

    def test_repository_impact_and_investigation_stay_themselves(self, kernel):
        assert kernel._conversation._intake(
            "What would be affected if I change atlas/memory/manager.py?"
        ).task_type.value == "repository_impact_request"
        assert kernel._conversation._intake(
            "Investigate the development gap helper."
        ).task_type.value == "investigation_request"

    def test_repeated_parsing_is_byte_identical(self, fixture_localization):
        first = supplied_structural_edit(REQUEST, fixture_localization).to_dict()
        second = supplied_structural_edit(REQUEST, fixture_localization).to_dict()
        assert first == second

    def test_plan_verification_expectations_survive_into_authoring(
        self, fixture_localization
    ):
        from atlas.evolution.change_author_router import plan_development_change

        need = DevelopmentNeed(title=REQUEST, summary=REQUEST)
        plan = plan_development_change(need, fixture_localization)
        assert plan.verification is not None
        assert plan.verification.verification_target == "widget"
        assert plan.constraints
        assert plan.provenance
        assert plan.actionable is False, "planning is not authorization"


# ---------------------------------------------------------------------------
# The REAL end-to-end bounded development exercise
# ---------------------------------------------------------------------------


class TestRealBoundedDevelopmentExercise:
    def test_full_loop_on_an_isolated_fixture(self, fixture_repo, tmp_path):
        # 0. honest baseline: the fixture's own test does NOT pass before the fix
        assert (fixture_repo / "widget.py").read_text(encoding="utf-8") == ORIGINAL_WIDGET
        baseline = _load(fixture_repo / "widget.py", "widget_baseline")
        assert baseline.add(1, 2) == -1, "the bug the request asks to fix"

        # 1. localization
        repository_map = RepositoryMapBuilder(fixture_repo).build()
        localization = DevelopmentLocalizer(repository_map).localize(REQUEST)
        assert localization.status.value == "resolved"
        assert localization.target == "widget"

        # 2. bounded plan + verification expectations
        from atlas.evolution.change_author_router import plan_development_change

        need = DevelopmentNeed(title=REQUEST, summary=REQUEST)
        plan = plan_development_change(need, localization)
        assert plan.localized is True
        assert plan.verification is not None
        assert plan.verification.verification_target == "widget"
        assert plan.actionable is False, "planning is not authorization"

        # 3. the explicit supplied edit -> structural spec (fail-closed parser)
        edit = supplied_structural_edit(REQUEST, localization)
        assert edit.ok is True and edit.entry["symbol"] == "add"

        # 4. authoring through the EXISTING supplier -> CodeChangeSet content
        need = DevelopmentNeed(
            title=REQUEST, summary=REQUEST, metadata={"structural": [edit.entry]}
        )
        changes = StructuralChangeSupplier(root=fixture_repo).supply_changes(need)
        assert changes is not None and changes.origin == "deterministic-structural"
        path, content = changes.code_changes[0]
        assert path == "widget.py"

        # 5. apply into an ISOLATED copy (the repository is never modified)
        work = tmp_path / "applied"
        shutil.copytree(fixture_repo, work)
        (work / "widget.py").write_text(content, encoding="utf-8")

        # 6. verification — the fixture's OWN test is executed against the change
        sys.path.insert(0, str(work))
        try:
            importlib.invalidate_caches()
            sys.modules.pop("widget", None)
            widget = importlib.import_module("widget")
            assert widget.add(1, 2) == 3, "the reported behaviour is now correct"
            assert list(inspect.signature(widget.add).parameters) == ["a", "b"]
            assert widget.label() == "widget", "the sibling is untouched"
            fixture_test = _load(work / "tests" / "test_widget.py", "widget_e2e_test")
            fixture_test.test_add()  # the fixture's verification passes
        finally:
            sys.path.remove(str(work))
            sys.modules.pop("widget", None)

        # 7. the original source was NEVER modified
        assert (fixture_repo / "widget.py").read_text(encoding="utf-8") == ORIGINAL_WIDGET

    def test_a_tampered_replacement_is_rejected_before_any_change(self, fixture_repo):
        # Atlas must reject an unsafe proposal safely.
        broken = StructuralEdit(
            path="widget.py", symbol="add", source="def add(a, b)\n    return a * b"
        )
        result = apply_structural_edits(
            (fixture_repo / "widget.py").read_text(encoding="utf-8"), [broken]
        )
        assert result.ok is False and result.content == ""
        assert (fixture_repo / "widget.py").read_text(encoding="utf-8") == ORIGINAL_WIDGET
