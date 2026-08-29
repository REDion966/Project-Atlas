"""B4 — Model-assisted change supplier tests.

Covers the fail-closed, bounded authoring adapter against the existing
``ChangeSupplier`` seam, reusing the real ``SuppliedChanges`` /
``DevelopmentCyclePolicy`` / ``CodeChangeSet`` / ``PromotionGate`` definitions.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from atlas.evolution.development_cycle import (
    DevelopmentCycleController,
    DevelopmentNeed,
    DeterministicChangeSupplier,
)
from atlas.evolution.model_assisted_supplier import (
    ModelAssistedChangeSupplier,
    ORIGIN_MODEL_ASSISTED_DRAFT,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _need(**overrides) -> DevelopmentNeed:
    base = dict(
        title="Add scheduling capability",
        summary="Add a scheduling capability to Atlas.",
        candidate_id="CAND-B4-1",
    )
    base.update(overrides)
    return DevelopmentNeed(**base)


def _json_string(**payload) -> str:
    import json

    return json.dumps(payload)


def _supplier(response=None, *, exc=None) -> ModelAssistedChangeSupplier:
    def fake_model(prompt):
        if exc is not None:
            raise exc
        return response

    return ModelAssistedChangeSupplier(fake_model)


_VALID_CODE_CHANGES = [
    {"path": "atlas/example/feature.py", "content": "# feature\n"},
]


class TestValidAuthoring:
    def test_valid_single_code_change(self):
        response = _json_string(code_changes=_VALID_CODE_CHANGES)
        result = _supplier(response).supply_changes(_need())
        assert result is not None
        assert result.code_changes == (("atlas/example/feature.py", "# feature\n"),)
        assert result.test_files == ()

    def test_valid_multiple_changes_and_tests(self):
        response = _json_string(
            code_changes=[
                {"path": "atlas/example/a.py", "content": "# a\n"},
                {"path": "atlas/example/b.py", "content": "# b\n"},
            ],
            test_files={"tests/test_a.py": "def test_a():\n    pass\n"},
        )
        result = _supplier(response).supply_changes(_need())
        assert result is not None
        assert len(result.code_changes) == 2
        assert result.test_files == (("tests/test_a.py", "def test_a():\n    pass\n"),)

    def test_correct_origin(self):
        response = _json_string(code_changes=_VALID_CODE_CHANGES)
        result = _supplier(response).supply_changes(_need())
        assert result is not None
        assert result.origin == "model-assisted-draft"
        assert result.origin == ORIGIN_MODEL_ASSISTED_DRAFT

    def test_confidence_bounded(self):
        for value in (0.0, 0.5, 1.0, -0.5, 1.7, None):
            response = _json_string(
                code_changes=_VALID_CODE_CHANGES, confidence=value
            )
            result = _supplier(response).supply_changes(_need())
            assert result is not None
            assert 0.0 <= result.confidence <= 1.0

    def test_confidence_non_numeric_clamped_to_zero(self):
        response = _json_string(
            code_changes=_VALID_CODE_CHANGES, confidence="high"
        )
        result = _supplier(response).supply_changes(_need())
        assert result is not None
        assert result.confidence == 0.0

    def test_rationale_bounded(self):
        response = _json_string(
            code_changes=_VALID_CODE_CHANGES,
            rationale="x" * 10_000,
        )
        result = _supplier(response).supply_changes(_need())
        assert result is not None
        assert len(result.notes) <= 500


class TestMissingModel:
    def test_missing_model_returns_none(self):
        supplier = ModelAssistedChangeSupplier()
        assert supplier.supply_changes(_need()) is None

    def test_model_exception_returns_none(self):
        supplier = _supplier(exc=RuntimeError("provider unavailable"))
        assert supplier.supply_changes(_need()) is None

    def test_model_returns_none_returns_none(self):
        supplier = _supplier(response=None)
        assert supplier.supply_changes(_need()) is None


class TestParsingFailures:
    def test_malformed_json(self):
        assert _supplier("{not json").supply_changes(_need()) is None

    def test_non_dict_json(self):
        assert _supplier("[1, 2, 3]").supply_changes(_need()) is None
        assert _supplier('"a string"').supply_changes(_need()) is None
        assert _supplier("42").supply_changes(_need()) is None

    def test_trailing_garbage(self):
        assert (
            _supplier('{"code_changes": []} extra').supply_changes(_need()) is None
        )

    def test_empty_response(self):
        assert _supplier("").supply_changes(_need()) is None
        assert _supplier("   ").supply_changes(_need()) is None


class TestStructuralValidation:
    def test_missing_code_changes(self):
        assert _supplier(_json_string()).supply_changes(_need()) is None

    def test_code_changes_not_list(self):
        assert (
            _supplier(_json_string(code_changes="x")).supply_changes(_need()) is None
        )

    def test_empty_code_changes(self):
        assert (
            _supplier(_json_string(code_changes=[])).supply_changes(_need()) is None
        )

    def test_code_change_missing_content(self):
        response = _json_string(code_changes=[{"path": "a.py"}])
        assert _supplier(response).supply_changes(_need()) is None

    def test_code_change_non_string_path(self):
        response = _json_string(code_changes=[{"path": 123, "content": "x"}])
        assert _supplier(response).supply_changes(_need()) is None

    def test_code_change_non_string_content(self):
        response = _json_string(code_changes=[{"path": "a.py", "content": 123}])
        assert _supplier(response).supply_changes(_need()) is None

    def test_test_files_not_dict(self):
        response = _json_string(
            code_changes=_VALID_CODE_CHANGES, test_files=["tests/x.py"]
        )
        assert _supplier(response).supply_changes(_need()) is None

    def test_test_files_non_string_value(self):
        response = _json_string(
            code_changes=_VALID_CODE_CHANGES, test_files={"tests/x.py": 5}
        )
        assert _supplier(response).supply_changes(_need()) is None

    def test_unsupported_field_rejected(self):
        response = _json_string(
            code_changes=_VALID_CODE_CHANGES, operation="delete"
        )
        assert _supplier(response).supply_changes(_need()) is None

    def test_rationale_non_string_rejected(self):
        response = _json_string(
            code_changes=_VALID_CODE_CHANGES, rationale=123
        )
        assert _supplier(response).supply_changes(_need()) is None


class TestBounds:
    def test_too_many_code_changes(self):
        changes = [{"path": f"f{i}.py", "content": "# c"} for i in range(10)]
        assert (
            _supplier(_json_string(code_changes=changes)).supply_changes(_need())
            is None
        )

    def test_too_many_test_files(self):
        tests = {f"tests/t{i}.py": "def test():\n    pass\n" for i in range(10)}
        response = _json_string(
            code_changes=_VALID_CODE_CHANGES, test_files=tests
        )
        assert _supplier(response).supply_changes(_need()) is None

    def test_oversized_path(self):
        response = _json_string(
            code_changes=[{"path": "a" * 300 + ".py", "content": "# c"}]
        )
        assert _supplier(response).supply_changes(_need()) is None

    def test_oversized_content(self):
        response = _json_string(
            code_changes=[{"path": "a.py", "content": "x" * 40_000}]
        )
        assert _supplier(response).supply_changes(_need()) is None


class TestPathSafety:
    def test_absolute_path(self):
        response = _json_string(
            code_changes=[{"path": "/etc/passwd", "content": "x"}]
        )
        assert _supplier(response).supply_changes(_need()) is None

    def test_traversal_path(self):
        response = _json_string(
            code_changes=[{"path": "../outside.py", "content": "x"}]
        )
        assert _supplier(response).supply_changes(_need()) is None

    def test_drive_prefixed_path(self):
        response = _json_string(
            code_changes=[{"path": "C:/windows/system32/x.py", "content": "x"}]
        )
        assert _supplier(response).supply_changes(_need()) is None

    def test_empty_path_segment(self):
        response = _json_string(
            code_changes=[{"path": "a//b.py", "content": "x"}]
        )
        assert _supplier(response).supply_changes(_need()) is None

    def test_dot_segment(self):
        response = _json_string(
            code_changes=[{"path": "./a.py", "content": "x"}]
        )
        assert _supplier(response).supply_changes(_need()) is None

    @pytest.mark.parametrize(
        "path",
        [
            "atlas/kernel/atlas.py",
            "atlas/kernel/service_container.py",
            "atlas/runtime/runtime_coordinator.py",
            "atlas/storage/migration.py",
            "atlas/storage/evolution_storage.py",
            "atlas/evolution/governance/rule_engine.py",
            "atlas/evolution/governance/authorization_manager.py",
        ],
    )
    def test_architecture_sensitive_paths_rejected(self, path):
        response = _json_string(code_changes=[{"path": path, "content": "# c"}])
        assert _supplier(response).supply_changes(_need()) is None


class TestAtomicRejection:
    def test_one_invalid_entry_rejects_all(self):
        response = _json_string(
            code_changes=[
                {"path": "atlas/example/ok.py", "content": "# ok\n"},
                {"path": "../evil.py", "content": "# evil\n"},
            ]
        )
        assert _supplier(response).supply_changes(_need()) is None

    def test_one_invalid_test_rejects_all(self):
        response = _json_string(
            code_changes=_VALID_CODE_CHANGES,
            test_files={
                "tests/test_ok.py": "def test():\n    pass\n",
                "../evil.py": "def test():\n    pass\n",
            },
        )
        assert _supplier(response).supply_changes(_need()) is None


class TestGovernanceAndDefaults:
    def test_off_by_default(self):
        controller = DevelopmentCycleController(approval_manager=object())
        # The controller must default to the deterministic supplier when no
        # model-assisted supplier is injected.
        assert isinstance(controller._change_supplier, DeterministicChangeSupplier)

    def test_model_assisted_supplier_satisfies_protocol(self):
        # Duck-typed protocol conformance: it exposes supply_changes(need).
        supplier = ModelAssistedChangeSupplier()
        assert callable(supplier.supply_changes)
        assert supplier.supply_changes(_need()) is None


class TestImportBoundary:
    # Forbidden = execution/authority surfaces. The supplier MAY import the
    # pure reusable definitions it is explicitly required to reuse:
    #   * CodeChangeSet       (atlas.evolution.autonomy.code_sandbox)
    #   * DevelopmentCyclePolicy / SuppliedChanges / DevelopmentNeed
    #                         (atlas.evolution.development_cycle)
    #   * ARCHITECTURE_SENSITIVE_PREFIXES (atlas.evolution.promotion_gate)
    _FORBIDDEN = (
        "atlas.ai",
        "atlas.runtime",
        "atlas.kernel",
        "atlas.events",
        "atlas.storage",
        "atlas.evolution.execution_gateway",
        "atlas.evolution.autonomy.dispatcher",
        "atlas.evolution.autonomy.code_execution",
        "atlas.evolution.autonomy.applier_registry",
        "atlas.evolution.autonomy.verification_service",
        "atlas.evolution.autonomy.rollback_manager",
        "atlas.evolution.self_development_loop",
        "atlas.evolution.approval_manager",
    )

    def test_no_forbidden_imports(self):
        source = (
            _REPO_ROOT / "atlas/evolution/model_assisted_supplier.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(
                        alias.name == p or alias.name.startswith(p + ".")
                        for p in self._FORBIDDEN
                    ), f"imports {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not any(
                    node.module == p or node.module.startswith(p + ".")
                    for p in self._FORBIDDEN
                ), f"imports {node.module}"

    def test_no_governance_or_execution_calls(self):
        source = (
            _REPO_ROOT / "atlas/evolution/model_assisted_supplier.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden_calls = {
            "approve",
            "reject",
            "authorize",
            "execute_request",
            "apply",
            "promote",
            "tick",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", getattr(node.func, "id", ""))
                assert name not in forbidden_calls, f"calls {name}()"
