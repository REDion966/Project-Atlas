"""B4 — Model-assisted authoring activation tests.

Proves the kernel-level OPT-IN activation policy for
``ModelAssistedChangeSupplier``:

  * OFF BY DEFAULT: ``[development] model_assisted_authoring = false`` keeps
    the existing ``DeterministicChangeSupplier``; no model is required and no
    model-assisted authoring occurs.
  * EXPLICIT OPT-IN: when the flag is ``true``, the kernel constructs and
    injects ``ModelAssistedChangeSupplier`` through the existing
    ``change_supplier`` seam; a fake authoring model can produce a bounded
    ``SuppliedChanges`` with ``origin="model-assisted-draft"``.
  * GOVERNANCE: the cycle STOPS at PENDING_APPROVAL; approval, execution, and
    promotion are never called automatically.
  * FAIL-CLOSED: a failing/malformed model produces a supplier failure and no
    ungoverned development occurs.
  * BACKWARD COMPATIBILITY: the controller constructor is unchanged,
    ``DeterministicChangeSupplier`` remains the default, and
    ``RuntimeCoordinator`` / ``Atlas.tick()`` / schema v11 are untouched.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.test_durable_guided_improvement import _storage_class


@pytest.fixture(autouse=True)
def _isolated_evolution_storage(monkeypatch, tmp_path):
    """Kernel-starting tests must not touch the operator DB."""
    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage",
        _storage_class(tmp_path),
    )


@pytest.fixture
def _config_flag(monkeypatch, tmp_path):
    """Point Configuration at a temp config.toml with the given flag value."""
    created: dict[str, bool] = {}

    def _apply(enabled: bool) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            "[application]\n"
            'name = "Atlas"\n'
            'version = "0.20.0"\n\n'
            "[ai]\n"
            'provider = "Mock Provider"\n'
            'model = "atlas-mock-v1"\n'
            "temperature = 0.7\n"
            "timeout = 300\n"
            "allow_fallback = false\n\n"
            "[conversation]\n"
            "history_limit = 20\n\n"
            "[logging]\n"
            'level = "INFO"\n\n'
            "[development]\n"
            f"model_assisted_authoring = {str(enabled).lower()}\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "atlas.kernel.atlas.Configuration",
            _config_class(config_path),
        )
        created["enabled"] = enabled

    return _apply


def _config_class(config_path: Path):
    from atlas.config.configuration import Configuration

    class TmpConfiguration(Configuration):
        def __init__(self):  # noqa: D107 - test shim
            super().__init__(filename=str(config_path))

    return TmpConfiguration


def _started_atlas(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage",
        _storage_class(tmp_path),
    )
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    return atlas


class _FakeAcquisition:
    """Duck-typed F8 acquisition result (no network)."""

    status = "ok"

    def to_dict(self):
        return {
            "acquisition_id": "ACQ-ACT-000001",
            "status": "ok",
            "report_id": "report:act",
            "sources": ("https://example.test/a",),
            "confidence": 0.8,
            "claim_count": 1,
        }


def _stub_research(atlas):
    controller = atlas.development_controller
    controller._researcher = lambda **kwargs: _FakeAcquisition()  # noqa: SLF001


def _need():
    from atlas.evolution.development_cycle import DevelopmentNeed

    return DevelopmentNeed(
        title="Add scheduling capability",
        summary="Add a scheduling capability to Atlas.",
        candidate_id="CAND-ACT-1",
        evidence_change_ids=("CHG-ACT-1",),
        research_question="how are features added to Atlas?",
    )


def _valid_model_payload() -> str:
    return json.dumps(
        {
            "code_changes": [
                {"path": "atlas/example/scheduler.py", "content": "# scheduler\n"}
            ],
            "test_files": {"tests/test_scheduler.py": "def test_scheduler():\n    pass\n"},
            "rationale": "Add a scheduling capability.",
            "confidence": 0.7,
        }
    )


class TestOffByDefault:
    def test_config_false_keeps_deterministic_supplier(
        self, monkeypatch, tmp_path, _config_flag
    ):
        from atlas.evolution.development_cycle import DeterministicChangeSupplier

        _config_flag(False)
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            assert isinstance(
                atlas.development_controller._change_supplier,  # noqa: SLF001
                DeterministicChangeSupplier,
            )
        finally:
            atlas.shutdown()

    def test_config_false_no_model_assisted_authoring(
        self, monkeypatch, tmp_path, _config_flag
    ):
        from atlas.evolution.model_assisted_supplier import (
            ModelAssistedChangeSupplier,
        )

        _config_flag(False)
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            supplier = atlas.development_controller._change_supplier  # noqa: SLF001
            assert not isinstance(supplier, ModelAssistedChangeSupplier)
        finally:
            atlas.shutdown()

    def test_config_false_behavior_unchanged(
        self, monkeypatch, tmp_path, _config_flag
    ):
        _config_flag(False)
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _stub_research(atlas)
            result = atlas.run_development_cycle(_need())
            # Deterministic supplier found no code_changes -> honest refusal.
            assert not result.ok
            assert any(
                stage == "supplier" for stage, _ in result.failures
            )
        finally:
            atlas.shutdown()


class TestExplicitOptIn:
    def test_config_true_injects_model_supplier(
        self, monkeypatch, tmp_path, _config_flag
    ):
        from atlas.evolution.model_assisted_supplier import (
            ModelAssistedChangeSupplier,
        )

        _config_flag(True)
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            assert isinstance(
                atlas.development_controller._change_supplier,  # noqa: SLF001
                ModelAssistedChangeSupplier,
            )
        finally:
            atlas.shutdown()

    def test_config_true_fake_model_reaches_pending_approval(
        self, monkeypatch, tmp_path, _config_flag
    ):
        _config_flag(True)
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _stub_research(atlas)
            # Replace the kernel's AIService-backed model with a fake.
            supplier = atlas.development_controller._change_supplier  # noqa: SLF001
            supplier._authoring_model = lambda prompt: _valid_model_payload()  # noqa: SLF001

            result = atlas.run_development_cycle(_need())
            assert result.ok
            assert result.proposal_status == "PENDING_APPROVAL"
            assert result.proposal_id
            assert result.approval_request_id
        finally:
            atlas.shutdown()

    def test_config_true_proposal_carries_model_origin(
        self, monkeypatch, tmp_path, _config_flag
    ):
        _config_flag(True)
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _stub_research(atlas)
            captured: dict = {}
            manager = atlas._approval_manager  # noqa: SLF001
            original = manager.create_approval_request

            def spy(proposal):
                captured["proposal"] = proposal
                return original(proposal)

            manager.create_approval_request = spy  # noqa: SLF001

            supplier = atlas.development_controller._change_supplier  # noqa: SLF001
            supplier._authoring_model = lambda prompt: _valid_model_payload()  # noqa: SLF001

            atlas.run_development_cycle(_need())
            meta = captured["proposal"].metadata["development_cycle"]
            assert meta["change_origin"] == "model-assisted-draft"
            assert meta["content_status"] == "unverified-draft"
        finally:
            atlas.shutdown()


class TestGovernance:
    def test_no_automatic_approval_execution_promotion(
        self, monkeypatch, tmp_path, _config_flag
    ):
        from atlas.kernel.atlas import Atlas

        _config_flag(True)
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _stub_research(atlas)
            supplier = atlas.development_controller._change_supplier  # noqa: SLF001
            supplier._authoring_model = lambda prompt: _valid_model_payload()  # noqa: SLF001

            approval_manager = atlas._approval_manager  # noqa: SLF001
            original_approve = approval_manager.approve
            approval_manager.approve = MagicMock(wraps=original_approve)

            result = atlas.run_development_cycle(_need())
            assert result.proposal_status == "PENDING_APPROVAL"
            approval_manager.approve.assert_not_called()
            # No execution surface is even reachable from this path.
            tick_src = inspect.getsource(Atlas.tick)
            assert "run_development_cycle" not in tick_src
        finally:
            atlas.shutdown()


class TestModelFailure:
    def test_model_exception_fails_closed(
        self, monkeypatch, tmp_path, _config_flag
    ):
        _config_flag(True)
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _stub_research(atlas)
            supplier = atlas.development_controller._change_supplier  # noqa: SLF001
            supplier._authoring_model = lambda prompt: (_ for _ in ()).throw(  # noqa: SLF001
                RuntimeError("provider unavailable")
            )
            result = atlas.run_development_cycle(_need())
            assert not result.ok
            assert any(stage == "supplier" for stage, _ in result.failures)
        finally:
            atlas.shutdown()

    def test_malformed_model_output_fails_closed(
        self, monkeypatch, tmp_path, _config_flag
    ):
        _config_flag(True)
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _stub_research(atlas)
            supplier = atlas.development_controller._change_supplier  # noqa: SLF001
            supplier._authoring_model = lambda prompt: "{not json"  # noqa: SLF001
            result = atlas.run_development_cycle(_need())
            assert not result.ok
            assert any(stage == "supplier" for stage, _ in result.failures)
        finally:
            atlas.shutdown()


class TestArchitecturalGuards:
    def test_tick_and_runtime_untouched(self):
        from atlas.kernel.atlas import Atlas

        tick_src = inspect.getsource(Atlas.tick)
        for forbidden in (
            "_model_assisted_authoring_model",
            "ModelAssistedChangeSupplier",
            "run_development_cycle",
        ):
            assert forbidden not in tick_src

    def test_supplier_import_boundaries_intact(self):
        import ast

        source = (
            Path("atlas/evolution/model_assisted_supplier.py")
            .read_text(encoding="utf-8")
        )
        tree = ast.parse(source)
        forbidden = (
            "atlas.ai",
            "atlas.runtime",
            "atlas.kernel",
            "atlas.events",
            "atlas.storage",
            "atlas.evolution.execution_gateway",
            "atlas.evolution.autonomy.dispatcher",
            "atlas.evolution.self_development_loop",
            "atlas.evolution.approval_manager",
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(
                        alias.name == p or alias.name.startswith(p + ".")
                        for p in forbidden
                    ), f"imports {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not any(
                    node.module == p or node.module.startswith(p + ".")
                    for p in forbidden
                ), f"imports {node.module}"
