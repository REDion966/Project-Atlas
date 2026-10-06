"""STEP 2 — development/coding capability architecture (focused tests).

Covers the bounded structural editor, the change planner, the ChangeAuthorRouter,
failure classification, the reverse-dependency authoring evidence, and the kernel
integration. Everything is deterministic; no provider is contacted, nothing is
written to the repository, and no governance boundary is reachable.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from atlas.evolution.change_author_router import (
    AuthorRoute,
    ChangeAuthorRouter,
    ChangePlan,
    ROUTE_PRIORITY,
    plan_change,
    stated_constraints,
)
from atlas.evolution.development_cycle import DevelopmentNeed
from atlas.evolution.failure_classification import (
    REPAIRABLE_KINDS,
    FailureKind,
    classify_failure,
    classify_outcomes,
)
from atlas.evolution.structural_editor import (
    STRUCTURAL_ORIGIN,
    EditKind,
    StructuralChangeSupplier,
    StructuralEdit,
    apply_structural_edits,
    structural_spec,
)

SOURCE = '''"""module."""
import os


def alpha(a, b):
    """old."""
    return a + b


class Beta:
    def one(self):
        return 1
'''

TARGET_PATH = "atlas/evolution/failure_classification.py"


def _need(**kwargs):
    base = {"title": "Change the existing implementation.", "summary": ""}
    base.update(kwargs)
    return DevelopmentNeed(**base)


# ---------------------------------------------------------------------------
# 1. Structural editor — bounded, anchored, syntax-preserving
# ---------------------------------------------------------------------------


class TestStructuralEditor:
    def test_replace_top_level_function(self):
        result = apply_structural_edits(
            SOURCE, [StructuralEdit("m.py", "alpha", EditKind.REPLACE,
                                    'def alpha(a, b):\n    """new."""\n    return a - b')]
        )
        assert result.ok is True
        assert '"""new."""' in result.content
        assert "return a - b" in result.content
        ast.parse(result.content)

    def test_replace_method_preserves_class_indentation(self):
        result = apply_structural_edits(
            SOURCE, [StructuralEdit("m.py", "Beta.one", EditKind.REPLACE,
                                    "def one(self):\n    return 2")]
        )
        assert result.ok is True
        assert "    def one(self):" in result.content
        assert "        return 2" in result.content
        ast.parse(result.content)

    def test_insert_after_adds_a_new_definition(self):
        result = apply_structural_edits(
            SOURCE, [StructuralEdit("m.py", "alpha", EditKind.INSERT_AFTER,
                                    "def gamma():\n    return 3")]
        )
        assert result.ok is True and "def gamma()" in result.content
        ast.parse(result.content)

    def test_delete_removes_only_the_anchor(self):
        result = apply_structural_edits(
            SOURCE, [StructuralEdit("m.py", "alpha", EditKind.DELETE)]
        )
        assert result.ok is True
        assert "def alpha" not in result.content
        assert "class Beta" in result.content

    def test_only_the_anchored_span_changes(self):
        result = apply_structural_edits(
            SOURCE, [StructuralEdit("m.py", "alpha", EditKind.REPLACE,
                                    "def alpha(a, b):\n    return a")]
        )
        assert result.ok is True
        assert '"""module."""' in result.content
        assert "import os" in result.content
        assert "class Beta:" in result.content

    def test_unknown_symbol_is_refused(self):
        result = apply_structural_edits(
            SOURCE, [StructuralEdit("m.py", "nope", EditKind.REPLACE, "x = 1")]
        )
        assert result.ok is False and "not found" in result.reason

    def test_a_breaking_edit_is_refused(self):
        result = apply_structural_edits(
            SOURCE, [StructuralEdit("m.py", "alpha", EditKind.REPLACE, "def alpha(:")]
        )
        assert result.ok is False and "invalid syntax" in result.reason

    def test_unparseable_source_is_refused(self):
        result = apply_structural_edits(
            "def (", [StructuralEdit("m.py", "a", EditKind.REPLACE, "x = 1")]
        )
        assert result.ok is False

    def test_empty_and_non_text_inputs_are_refused(self):
        assert apply_structural_edits("", []).ok is False
        assert apply_structural_edits(None, []).ok is False
        assert apply_structural_edits(SOURCE, None).ok is False
        assert apply_structural_edits(SOURCE, [object()]).ok is False

    def test_delete_needs_no_replacement_but_replace_does(self):
        assert apply_structural_edits(
            SOURCE, [StructuralEdit("m.py", "alpha", EditKind.DELETE)]
        ).ok is True
        assert apply_structural_edits(
            SOURCE, [StructuralEdit("m.py", "alpha", EditKind.REPLACE, "")]
        ).ok is False

    def test_edits_are_bounded(self):
        many = [StructuralEdit("m.py", "alpha", EditKind.REPLACE, "x = 1")] * 20
        assert apply_structural_edits(SOURCE, many).ok is False
        huge = StructuralEdit("m.py", "alpha", EditKind.REPLACE, "x = 1\n" * 30_000)
        assert apply_structural_edits(SOURCE, [huge]).ok is False

    def test_editing_is_deterministic(self):
        edit = StructuralEdit("m.py", "alpha", EditKind.REPLACE, "def alpha(a, b):\n    return a")
        assert apply_structural_edits(SOURCE, [edit]).content == (
            apply_structural_edits(SOURCE, [edit]).content
        )

    def test_multiple_edits_do_not_interfere(self):
        result = apply_structural_edits(SOURCE, [
            StructuralEdit("m.py", "alpha", EditKind.REPLACE, "def alpha(a, b):\n    return a"),
            StructuralEdit("m.py", "Beta.one", EditKind.REPLACE, "def one(self):\n    return 9"),
        ])
        assert result.ok is True
        assert "return a" in result.content and "return 9" in result.content
        ast.parse(result.content)


class TestStructuralChangeSupplier:
    def test_authors_a_real_module_change(self):
        supplier = StructuralChangeSupplier()
        author = supplier.supply_changes(_need(metadata={"structural": [structural_spec(
            TARGET_PATH, "classify_outcomes",
            'def classify_outcomes(outcomes: Any) -> tuple:\n    """edited."""\n    return ()',
        )]}))
        assert author is not None
        assert author.origin == STRUCTURAL_ORIGIN
        path, content = author.code_changes[0]
        assert path == TARGET_PATH
        assert "edited." in content
        ast.parse(content)

    def test_no_spec_returns_none(self):
        assert StructuralChangeSupplier().supply_changes(_need()) is None

    def test_missing_path_or_symbol_is_refused(self):
        for spec in ({"path": TARGET_PATH}, {"symbol": "x"}, {"path": "", "symbol": "x"}):
            with pytest.raises(ValueError):
                StructuralChangeSupplier().supply_changes(_need(metadata={"structural": [spec]}))

    def test_unsafe_path_is_refused(self):
        with pytest.raises(ValueError):
            StructuralChangeSupplier().supply_changes(_need(metadata={"structural": [
                structural_spec("../../etc/passwd", "x", "y = 1")]}))

    def test_architecture_sensitive_and_unknown_paths_fail_closed(self):
        for path in ("atlas/kernel/atlas.py", "atlas/zzz/nope.py"):
            with pytest.raises(ValueError):
                StructuralChangeSupplier().supply_changes(_need(metadata={"structural": [
                    structural_spec(path, "x", "y = 1")]}))

    def test_unsupported_kind_is_refused(self):
        with pytest.raises(ValueError):
            StructuralChangeSupplier().supply_changes(_need(metadata={"structural": [
                structural_spec(TARGET_PATH, "classify_outcomes", "x = 1", kind="rewrite")]}))

    def test_origin_is_not_model_assisted(self):
        assert StructuralChangeSupplier().origin == "deterministic-structural"


# ---------------------------------------------------------------------------
# 2. Change planning (STEP 2I)
# ---------------------------------------------------------------------------


class TestChangePlanning:
    def test_constraints_are_read_from_the_needs_own_words(self):
        need = _need(title="Improve the module while preserving its existing interface.")
        assert "preserving" in stated_constraints(need)
        assert "existing interface" in stated_constraints(need)

    def test_no_constraint_is_invented(self):
        assert stated_constraints(_need(title="Add a new capability.")) == ()

    def test_unavailable_when_no_evidence(self):
        plan = plan_change(_need(title="Improve the development gap module."))
        assert isinstance(plan, ChangePlan)
        assert plan.route is AuthorRoute.UNAVAILABLE
        assert plan.actionable is False

    @pytest.mark.parametrize("key,route", [
        ("code_changes", AuthorRoute.EXPLICIT_PATCH),
        ("structural", AuthorRoute.STRUCTURAL),
        ("scaffold", AuthorRoute.SCAFFOLD),
        ("evidence_change", AuthorRoute.EVIDENCE),
    ])
    def test_each_existing_convention_routes_deterministically(self, key, route):
        plan = plan_change(_need(metadata={key: [{"a": 1}]}))
        assert plan.route is route
        assert plan.deterministic is True

    def test_priority_is_deterministic_and_explicit_first(self):
        assert ROUTE_PRIORITY[0] is AuthorRoute.EXPLICIT_PATCH
        plan = plan_change(_need(metadata={"code_changes": [{}], "scaffold": {}}))
        assert plan.route is AuthorRoute.EXPLICIT_PATCH

    def test_specialist_is_last_and_only_when_available(self):
        need = _need()
        assert plan_change(need, specialist_available=False).route is AuthorRoute.UNAVAILABLE
        specialist = plan_change(need, specialist_available=True)
        assert specialist.route is AuthorRoute.SPECIALIST_MODEL
        assert specialist.deterministic is False

    def test_a_deterministic_route_always_beats_the_specialist(self):
        plan = plan_change(_need(metadata={"scaffold": {}}), specialist_available=True)
        assert plan.route is AuthorRoute.SCAFFOLD

    def test_plan_is_serializable_and_deterministic(self):
        need = _need(title="preserve the interface", metadata={"structural": [{}]})
        assert plan_change(need).to_dict() == plan_change(need).to_dict()

    def test_non_need_is_unavailable(self):
        assert plan_change("nonsense").route is AuthorRoute.UNAVAILABLE


# ---------------------------------------------------------------------------
# 3. ChangeAuthorRouter (STEP 2E)
# ---------------------------------------------------------------------------


class TestChangeAuthorRouter:
    def test_deterministic_routes_without_a_specialist(self):
        router = ChangeAuthorRouter()
        assert router.specialist_enabled is False
        assert AuthorRoute.SPECIALIST_MODEL not in router.routes()
        assert set(router.routes()) == {
            AuthorRoute.EXPLICIT_PATCH, AuthorRoute.STRUCTURAL,
            AuthorRoute.SCAFFOLD, AuthorRoute.EVIDENCE,
        }

    def test_author_returns_none_without_evidence(self):
        assert ChangeAuthorRouter().author(_need(title="Improve something.")) is None

    def test_author_dispatches_to_the_matching_existing_supplier(self):
        router = ChangeAuthorRouter()
        need = _need(metadata={"code_changes": [{"path": "atlas/x.py", "content": "x = 1"}]})
        supplied = router.author(need)
        assert supplied is not None and supplied.origin == "deterministic"

    def test_author_for_is_route_isolated(self):
        router = ChangeAuthorRouter()
        need = _need(metadata={"code_changes": [{"path": "atlas/x.py", "content": "x = 1"}]})
        assert router.author_for(need, AuthorRoute.EXPLICIT_PATCH) is not None
        assert router.author_for(need, AuthorRoute.SCAFFOLD) is None
        assert router.author_for(need, AuthorRoute.SPECIALIST_MODEL) is None

    def test_specialist_is_used_only_when_no_deterministic_route_serves(self):
        class _Specialist:
            calls = 0

            def supply_changes(self, need):
                _Specialist.calls += 1
                return "specialist-draft"

        router = ChangeAuthorRouter(specialist=_Specialist())
        router.author(_need(metadata={"code_changes": [{"path": "atlas/x.py", "content": "x = 1"}]}))
        assert _Specialist.calls == 0  # deterministic route won
        assert router.author(_need(title="Improve something.")) == "specialist-draft"
        assert _Specialist.calls == 1

    def test_non_need_is_ignored(self):
        assert ChangeAuthorRouter().author("nonsense") is None

    def test_a_supplier_refusal_propagates_for_fail_closed_handling(self):
        router = ChangeAuthorRouter()
        need = _need(metadata={"structural": [{"path": "atlas/kernel/atlas.py", "symbol": "x",
                                              "kind": "replace", "source": "y = 1"}]})
        with pytest.raises(ValueError):
            router.author(need)

    def test_no_authority_surface(self):
        router = ChangeAuthorRouter()
        for forbidden in ("approve", "promote", "authorize", "execute"):
            assert not hasattr(router, forbidden)


# ---------------------------------------------------------------------------
# 4. Failure classification (STEP 2K)
# ---------------------------------------------------------------------------


class TestFailureClassification:
    @pytest.mark.parametrize("reason,expected", [
        ("invalid syntax (<unknown>, line 3)", FailureKind.SYNTAX),
        ("AssertionError: 1 != 2", FailureKind.TEST),
        ("No module named 'widget'", FailureKind.IMPORT),
        ("not authorized: OWNER approval required", FailureKind.GOVERNANCE),
        ("the provider returned malformed json", FailureKind.PROVIDER),
        ("symbol 'alpha' was not found", FailureKind.WRONG_TARGET),
        ("path escapes the repository", FailureKind.UNRELATED),
        ("supplier produced no changes", FailureKind.INCOMPLETE),
        ("a behavioral regression was detected", FailureKind.REGRESSION),
        ("pytest: No such file or directory", FailureKind.ENVIRONMENT),
    ])
    def test_each_kind_is_classified(self, reason, expected):
        assert classify_failure(reason).kind is expected

    def test_governance_and_target_failures_are_not_repairable(self):
        assert classify_failure("not authorized").repairable is False
        assert classify_failure("symbol 'x' was not found").repairable is False
        assert classify_failure("invalid syntax").repairable is True

    def test_repairable_set_is_the_bounded_one(self):
        assert REPAIRABLE_KINDS == frozenset({
            FailureKind.SYNTAX, FailureKind.IMPORT, FailureKind.TEST,
            FailureKind.REGRESSION, FailureKind.INCOMPLETE,
        })

    def test_empty_evidence_is_unknown_not_a_guess(self):
        assert classify_failure("").kind is FailureKind.UNKNOWN
        assert classify_failure(None).repairable is False

    def test_classification_is_deterministic_and_serializable(self):
        first = classify_failure("AssertionError", stage="verify")
        assert first.to_dict() == classify_failure("AssertionError", stage="verify").to_dict()

    def test_stage_and_status_participate(self):
        assert classify_failure("", stage="approval").kind is FailureKind.GOVERNANCE

    def test_classify_outcomes_skips_success(self):
        class _Outcome:
            def __init__(self, status, reason=""):
                self.status = status
                self.reason = reason

        class _Status:
            def __init__(self, value):
                self.value = value

        outcomes = [_Outcome(_Status("success")), _Outcome(_Status("failed"), "invalid syntax")]
        classified = classify_outcomes(outcomes)
        assert len(classified) == 1 and classified[0].kind is FailureKind.SYNTAX
        assert classify_outcomes([]) == ()


# ---------------------------------------------------------------------------
# 5. Repository intelligence + kernel integration
# ---------------------------------------------------------------------------


class TestKernelIntegration:
    def test_router_is_deterministic_only_by_default(self, kernel):
        router = kernel.change_author_router()
        assert router.specialist_enabled is False
        assert AuthorRoute.SPECIALIST_MODEL not in router.routes()

    def test_router_is_cache_only(self, kernel):
        assert kernel.change_author_router() is kernel.change_author_router()

    def test_authoring_context_carries_reverse_dependency_evidence(self, kernel):
        from atlas.evolution.model_assisted_supplier import ModelAssistedChangeSupplier

        supplier = ModelAssistedChangeSupplier(
            authoring_model=lambda p: "{}",
            repository_map=kernel.repository_map,
            architecture_model=kernel.architecture_model(),
        )
        need = DevelopmentNeed(
            title="Improve the development gap adjudication",
            summary="Preserve the interface.",
            target_components=("atlas.evolution.development_gap",),
        )
        context = supplier._build_authoring_context(need)
        assert "imported by (change impact):" in context
        # Anchored to the DECLARED target, and bounded.
        assert context.splitlines()[1].startswith("- 1. atlas.evolution.development_gap")
        line = next(
            l for l in context.splitlines() if "imported by (change impact):" in l
        )
        assert "tests." not in line

    def test_understanding_and_planning_authorize_nothing(self, kernel):
        before = kernel.pending_promotion_reviews()
        router = kernel.change_author_router()
        router.plan(_need(title="Improve the development gap module."))
        assert kernel.pending_promotion_reviews() == before


@pytest.fixture(scope="module")
def kernel():
    import pkgutil
    import tempfile

    import atlas.storage as storage_pkg

    tmp = pathlib.Path(tempfile.mkdtemp())
    db = tmp / "step2.db"
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
# 6. Architectural quality — leaf boundaries and no framework adoption
# ---------------------------------------------------------------------------


class TestArchitecturalBoundary:
    def test_new_modules_import_no_framework(self):
        root = pathlib.Path(__file__).resolve().parents[1] / "atlas" / "evolution"
        imported: set[str] = set()
        for name in (
            "structural_editor.py", "change_author_router.py", "failure_classification.py",
        ):
            tree = ast.parse((root / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
        for forbidden in ("libcst", "tree_sitter", "ast_grep", "spacy", "openai",
                          "anthropic", "requests", "torch", "transformers"):
            assert forbidden not in imported

    def test_no_unrestricted_rewriting_surface_exists(self):
        from atlas.evolution import structural_editor as module

        source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        # The editor is anchored on the syntax tree; it never rewrites by text.
        assert "re.sub" not in source and "str.replace(" not in source
        assert set(k.value for k in EditKind) == {"replace", "insert_after", "delete"}
