"""B4 — Model-assisted authoring activation tests.

Proves the kernel-level OPT-IN activation policy for
``ModelAssistedChangeSupplier``:

  * OFF BY DEFAULT: ``[development] model_assisted_authoring = false`` keeps
    the existing deterministic-first composition — the authoritative
    ``CompositeChangeSupplier`` composes ``DeterministicChangeSupplier`` then
    ``ScaffoldChangeSupplier`` and NO model member; no model is required and no
    model-assisted authoring occurs.
  * EXPLICIT OPT-IN: when the flag is ``true``, the kernel composes the
    existing ``ModelAssistedChangeSupplier`` as the LAST member of that same
    authoritative composition; a fake authoring model configured on that member
    can produce a bounded ``SuppliedChanges`` with
    ``origin="model-assisted-draft"``.
  * SHARED COMPOSITION (Task 2): the F9 ``DevelopmentCycleController`` and the
    conversational P17 authoring seam receive the SAME authoritative
    ``CompositeChangeSupplier`` instance — there is exactly one composition,
    with the fixed order Deterministic -> Scaffold -> Model.
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


# ---------------------------------------------------------------------------
# Phase 5.2 composition helpers (Task 2 reconciliation).
#
# The authoritative supplier is a CompositeChangeSupplier with a fixed
# deterministic-first order: Deterministic -> Scaffold -> Model (the model
# member exists only when [development].model_assisted_authoring is opted in).
# Both the F9 DevelopmentCycleController and the conversational P17 seam
# receive that SAME instance, so configuration must be applied to the model
# MEMBER, never to the composite itself.
# ---------------------------------------------------------------------------


def _authoritative_supplier(atlas):
    """The shared Phase 5.2 composition used by both consumers."""
    from atlas.evolution.development_scaffold_supplier import (
        CompositeChangeSupplier,
    )

    supplier = atlas.development_controller._change_supplier  # noqa: SLF001
    assert isinstance(supplier, CompositeChangeSupplier)
    return supplier


def _model_member(supplier):
    """The ModelAssistedChangeSupplier member of the composition, or None."""
    from atlas.evolution.model_assisted_supplier import (
        ModelAssistedChangeSupplier,
    )

    return next(
        (
            member
            for member in supplier.suppliers
            if isinstance(member, ModelAssistedChangeSupplier)
        ),
        None,
    )


def _configure_authoring_model(supplier, authoring_model):
    """Install a deterministic authoring double on the MODEL member."""
    from atlas.evolution.model_assisted_supplier import (
        ModelAssistedChangeSupplier,
    )

    member = _model_member(supplier)
    assert isinstance(member, ModelAssistedChangeSupplier), (
        "model-assisted authoring is opted in but the composition carries no "
        "ModelAssistedChangeSupplier member"
    )
    member._authoring_model = authoring_model  # noqa: SLF001
    return member


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
        from atlas.evolution.development_scaffold_supplier import (
            ScaffoldChangeSupplier,
        )

        _config_flag(False)
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            # Phase 5.2 — the controller receives the authoritative
            # deterministic-first composition: Deterministic then Scaffold, and
            # NO model member when the flag is off.
            supplier = _authoritative_supplier(atlas)
            assert isinstance(supplier.suppliers[0], DeterministicChangeSupplier)
            assert isinstance(supplier.suppliers[1], ScaffoldChangeSupplier)
            assert _model_member(supplier) is None
            assert len(supplier.suppliers) == 2
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
        from atlas.evolution.development_cycle import DeterministicChangeSupplier
        from atlas.evolution.development_scaffold_supplier import (
            ScaffoldChangeSupplier,
        )
        from atlas.evolution.model_assisted_supplier import (
            ModelAssistedChangeSupplier,
        )

        _config_flag(True)
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            # Phase 5.2 — the model supplier is composed as the LAST member of
            # the authoritative deterministic-first composition.
            supplier = _authoritative_supplier(atlas)
            assert isinstance(supplier.suppliers[0], DeterministicChangeSupplier)
            assert isinstance(supplier.suppliers[1], ScaffoldChangeSupplier)
            member = _model_member(supplier)
            assert isinstance(member, ModelAssistedChangeSupplier)
            assert supplier.suppliers[-1] is member
            assert len(supplier.suppliers) == 3
        finally:
            atlas.shutdown()

    def test_config_true_fake_model_reaches_pending_approval(
        self, monkeypatch, tmp_path, _config_flag
    ):
        _config_flag(True)
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _stub_research(atlas)
            # Configure the fake authoring model on the MODEL member of the
            # authoritative composition (the composite itself carries no
            # authoring model); no provider is contacted.
            _configure_authoring_model(
                _authoritative_supplier(atlas),
                lambda prompt: _valid_model_payload(),
            )

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

            supplier = _authoritative_supplier(atlas)
            _configure_authoring_model(
                supplier, lambda prompt: _valid_model_payload()
            )

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
            supplier = _authoritative_supplier(atlas)
            _configure_authoring_model(
                supplier, lambda prompt: _valid_model_payload()
            )

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
            _configure_authoring_model(
                _authoritative_supplier(atlas),
                lambda prompt: (_ for _ in ()).throw(  # noqa: SLF001
                    RuntimeError("provider unavailable")
                ),
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
            _configure_authoring_model(
                _authoritative_supplier(atlas),
                lambda prompt: "{not json",
            )
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


class TestConversationalSeamWiring:
    """Evolution #6 — the conversational P17 authoring seam receives the
    already-constructed ModelAssistedChangeSupplier exactly when
    [development].model_assisted_authoring is opted in, and receives None
    (deterministic/evidence-only) otherwise. No provider is contacted: the
    authoring callable is replaced with a deterministic test double."""

    def test_flag_off_conversational_seam_has_no_model_supplier(
        self, monkeypatch, tmp_path, _config_flag
    ):
        _config_flag(False)
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            # Phase 5.2 (Task 2) — the seam receives the SAME authoritative
            # composition as the controller; with the flag off it composes no
            # model member, so no model-assisted authoring can occur.
            seam_supplier = (
                atlas._conversation._proposal_converter._change_supplier  # noqa: SLF001
            )
            assert seam_supplier is _authoritative_supplier(atlas)
            assert _model_member(seam_supplier) is None

            # Deterministic/evidence-only behavior is unchanged: planning
            # still reaches the governed PENDING_APPROVAL stop with no
            # authored workload.
            list(atlas.stream("Investigate the memory architecture"))
            list(atlas.stream("Plan this improvement"))
            planned = atlas._conversation.conversation.messages[-1]  # noqa: SLF001
            assert planned.metadata["planning"]["status"] == "prepared"
            assert "authored_workload" not in planned.metadata["planning"]
            state = atlas._conversation.state_manager.state  # noqa: SLF001
            assert state.evolution_proposal_id is not None
            assert state.pending_approval_id is not None
        finally:
            atlas.shutdown()

    def test_flag_on_conversational_seam_receives_authoritative_composition(
        self, monkeypatch, tmp_path, _config_flag
    ):
        from atlas.evolution.development_scaffold_supplier import (
            CompositeChangeSupplier,
        )
        from atlas.evolution.model_assisted_supplier import (
            ModelAssistedChangeSupplier,
        )

        _config_flag(True)
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            seam_supplier = (
                atlas._conversation._proposal_converter._change_supplier  # noqa: SLF001
            )
            # Phase 5.2 (Task 2) — the SAME already-constructed authoritative
            # composition backs both the F9 controller and the conversational
            # seam: no second supplier, deterministic-first order preserved.
            assert isinstance(seam_supplier, CompositeChangeSupplier)
            assert (
                seam_supplier
                is atlas.development_controller._change_supplier  # noqa: SLF001
            )
            # ... and with the flag on it composes the model-assisted member.
            assert isinstance(
                _model_member(seam_supplier), ModelAssistedChangeSupplier
            )
        finally:
            atlas.shutdown()

    def test_flag_on_conversational_authored_draft_reaches_pending_approval(
        self, monkeypatch, tmp_path, _config_flag
    ):
        """With the flag on, the conversational path authors an unverified
        draft through the injected supplier, stops at PENDING_APPROVAL, and
        never auto-approves, executes, or promotes."""
        _config_flag(True)
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            supplier = (
                atlas._conversation._proposal_converter._change_supplier  # noqa: SLF001
            )
            # Deterministic test double replaces the kernel's AI-backed
            # callable on the MODEL member of the shared composition; no
            # provider is contacted.
            _configure_authoring_model(
                supplier, lambda prompt: _valid_model_payload()
            )

            approval_manager = atlas._approval_manager  # noqa: SLF001
            original_approve = approval_manager.approve
            approval_manager.approve = MagicMock(wraps=original_approve)  # noqa: SLF001

            list(atlas.stream("Investigate the memory architecture"))
            list(atlas.stream("Plan this improvement"))

            state = atlas._conversation.state_manager.state  # noqa: SLF001
            assert state.evolution_proposal_id is not None
            assert state.pending_approval_id is not None

            planned = atlas._conversation.conversation.messages[-1]  # noqa: SLF001
            planning = planned.metadata["planning"]
            assert planning["status"] == "prepared"
            assert planning["authored_workload"] == {
                "code_changes": 1,
                "test_files": 1,
                "change_origin": "model-assisted-draft",
                "content_status": "unverified-draft",
            }

            ev_proposal = (
                atlas._conversation._resolve_evolution_proposal(  # noqa: SLF001
                    state.evolution_proposal_id
                )
            )
            cycle = ev_proposal.metadata["development_cycle"]
            assert cycle["change_origin"] == "model-assisted-draft"
            assert cycle["content_status"] == "unverified-draft"
            assert ev_proposal.status.name == "PENDING_APPROVAL"

            # Governance: the path stopped at the approval boundary; the
            # model's draft was never approved, executed, or promoted.
            approval_manager.approve.assert_not_called()
        finally:
            atlas.shutdown()
