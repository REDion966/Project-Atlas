"""Agent Workbench — bounded, governed development REPAIR primitive.

Internalized from the bounded repair/retry loops of mini-SWE-agent, OpenHands,
and MiniMax Mini-Agent, adapted to Atlas: a drop-in ``SelfDevelopmentLoop``
change-supplier that returns the baseline workload unchanged unless a bounded
corrective change is authored (via the EXISTING, boundary-validated
``ModelAssistedChangeSupplier``) after a sandbox FAILURE.

Deterministic-first, model-optional, sandbox-only. No authority, no promotion.
"""

from __future__ import annotations

from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
    SandboxWorkload,
)
from atlas.evolution.development_repair import RepairChangeSupplier
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
)
from atlas.evolution.self_development_loop import SelfDevelopmentLoop

OK_CHANGES = [{"path": "mod.py", "content": "VALUE = 1\n"}]
OK_TESTS = {"test_mod.py": "def test_value():\n    assert True\n"}
FAIL_TESTS = {"test_mod.py": "def test_value():\n    assert 1 == 2\n"}
_CORRECTIVE_JSON = (
    '{"code_changes": [{"path": "mod.py", "content": "VALUE = 2\\n"}], '
    '"rationale": "correct the module value"}'
)


def _proposal() -> EvolutionProposal:
    plan = ImprovementPlan(
        plan_id="IMP-REPAIR-001",
        title="Add a value",
        description="Introduce a module value.",
        priority=ImprovementPriority.HIGH,
        expected_benefit="A module value exists.",
        complexity_estimate="low",
        target_components=["mod"],
    )
    return EvolutionProposal(
        proposal_id="PROP-REPAIR-001",
        title="Add a value",
        summary="Introduce a module value.",
        rationale="Modules should export a value.",
        expected_benefit="A module value exists.",
        risks="Low.",
        impact_analysis="Modifies mod.py.",
        implementation_approach="Add a constant and a test.",
        plan=plan,
        status=ProposalStatus.APPROVED,
        metadata={"code_changes": OK_CHANGES, "test_files": OK_TESTS},
    )


def _baseline(proposal, history):
    return SandboxWorkload(
        code_changes=tuple(OK_CHANGES),
        test_files=dict(OK_TESTS),
        verify_target="test_mod.py",
    )


def _failed() -> DevelopmentOutcome:
    return DevelopmentOutcome(
        outcome=DevelopmentOutcomeStatus.FAILED,
        proposal_id="PROP-REPAIR-001",
        plan_id="IMP-REPAIR-001",
        iteration=1,
        message="tests failed",
        changed_files=["mod.py"],
        verification_passed=False,
        rollback_occurred=False,
        test_outcome="failed",
    )


def _succeeded() -> DevelopmentOutcome:
    return DevelopmentOutcome(
        outcome=DevelopmentOutcomeStatus.SUCCESS,
        proposal_id="PROP-REPAIR-001",
        plan_id="IMP-REPAIR-001",
        iteration=1,
    )


def _model(payload):
    return lambda prompt: payload


class TestBaselineFirst:
    def test_disabled_returns_baseline_after_failure(self):
        supplier = RepairChangeSupplier(baseline=_baseline)
        assert supplier.repair_enabled is False
        assert supplier(_proposal(), [_failed()]) == _baseline(_proposal(), [])

    def test_first_attempt_returns_baseline(self):
        supplier = RepairChangeSupplier(baseline=_baseline, repair_model=_model(_CORRECTIVE_JSON))
        assert supplier(_proposal(), []) == _baseline(_proposal(), [])

    def test_success_history_is_not_repaired(self):
        supplier = RepairChangeSupplier(baseline=_baseline, repair_model=_model(_CORRECTIVE_JSON))
        assert supplier(_proposal(), [_succeeded()]) == _baseline(_proposal(), [])

    def test_missing_baseline_is_none(self):
        supplier = RepairChangeSupplier(
            baseline=lambda proposal, history: None, repair_model=_model(_CORRECTIVE_JSON)
        )
        assert supplier(_proposal(), []) is None


class TestCorrectiveRepair:
    def test_corrective_workload_after_failure(self):
        supplier = RepairChangeSupplier(baseline=_baseline, repair_model=_model(_CORRECTIVE_JSON))
        workload = supplier(_proposal(), [_failed()])
        assert workload is not None
        assert workload.code_changes == (
            {"path": "mod.py", "content": "VALUE = 2\n"},
        )
        # The baseline verification requirement is preserved.
        assert workload.test_files == dict(OK_TESTS)
        assert workload.verify_target == "test_mod.py"

    def test_invalid_model_output_falls_back_to_baseline(self):
        supplier = RepairChangeSupplier(
            baseline=_baseline, repair_model=_model("not json at all")
        )
        assert supplier(_proposal(), [_failed()]) == _baseline(_proposal(), [])

    def test_model_exception_falls_back_to_baseline(self):
        def boom(prompt):
            raise RuntimeError("model down")

        supplier = RepairChangeSupplier(baseline=_baseline, repair_model=boom)
        assert supplier(_proposal(), [_failed()]) == _baseline(_proposal(), [])

    def test_architecture_sensitive_path_is_refused(self):
        payload = (
            '{"code_changes": [{"path": "atlas/kernel/atlas.py", '
            '"content": "X = 1\\n"}]}'
        )
        supplier = RepairChangeSupplier(
            baseline=_baseline, repair_model=_model(payload)
        )
        # The existing supplier refuses the sensitive path -> fail-closed baseline.
        assert supplier(_proposal(), [_failed()]) == _baseline(_proposal(), [])

    def test_empty_model_change_falls_back(self):
        supplier = RepairChangeSupplier(
            baseline=_baseline, repair_model=_model('{"code_changes": []}')
        )
        assert supplier(_proposal(), [_failed()]) == _baseline(_proposal(), [])

    def test_repair_is_deterministic(self):
        supplier = RepairChangeSupplier(baseline=_baseline, repair_model=_model(_CORRECTIVE_JSON))
        first = supplier(_proposal(), [_failed()])
        second = supplier(_proposal(), [_failed()])
        assert first == second


class TestNoAuthorityOrSideEffects:
    def test_repair_supplier_has_no_authority_surface(self):
        supplier = RepairChangeSupplier(baseline=_baseline, repair_model=_model(_CORRECTIVE_JSON))
        for banned in ("approve", "promote", "authorize", "activate", "execute"):
            assert not hasattr(supplier, banned)

    def test_inputs_are_not_mutated(self):
        proposal = _proposal()
        history = [_failed()]
        before_metadata = dict(proposal.metadata)
        supplier = RepairChangeSupplier(baseline=_baseline, repair_model=_model(_CORRECTIVE_JSON))
        supplier(proposal, history)
        assert proposal.metadata == before_metadata
        assert len(history) == 1

    def test_corrective_workload_is_sandbox_data_only(self):
        supplier = RepairChangeSupplier(baseline=_baseline, repair_model=_model(_CORRECTIVE_JSON))
        workload = supplier(_proposal(), [_failed()])
        assert isinstance(workload, SandboxWorkload)


class TestLoopSeam:
    def test_loop_hands_accumulated_history_to_the_supplier(self):
        seen: list[int] = []

        def supplier(proposal, history):
            seen.append(len(history))
            return SandboxWorkload(
                code_changes=tuple(OK_CHANGES),
                test_files=dict(FAIL_TESTS),
                verify_target="test_mod.py",
            )

        result = SelfDevelopmentLoop(change_supplier=supplier).run(
            _proposal(), max_iterations=2
        )
        assert result.status in (
            DevelopmentOutcomeStatus.FAILED,
            DevelopmentOutcomeStatus.ITERATIONS_EXHAUSTED,
        )
        # The loop passes accumulated history, so a corrective supplier can bias
        # the bounded retry (the seam the repair primitive rides).
        assert seen == [0, 1]


# ---------------------------------------------------------------------------
# Kernel wiring — off by default
# ---------------------------------------------------------------------------


def _started_atlas(monkeypatch, tmp_path):
    import atlas.kernel.atlas as kernel_mod
    from atlas.storage.research_storage import ResearchSQLiteStorage
    from tests.test_durable_guided_improvement import _storage_class

    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage", _storage_class(tmp_path)
    )

    class _TmpResearch(ResearchSQLiteStorage):
        def __init__(self, db_path=None):  # noqa: D107
            super().__init__(db_path=tmp_path / "research.db")

    monkeypatch.setattr("atlas.kernel.atlas.ResearchSQLiteStorage", _TmpResearch)
    atlas = kernel_mod.Atlas()
    atlas.start()
    return atlas


class TestKernelWiring:
    def test_repair_is_off_by_default(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            assert atlas._development_repair_supplier() is None  # noqa: SLF001
            # The loop keeps its built-in supplier when repair is disabled.
            from atlas.evolution.self_development_loop import metadata_change_supplier

            assert atlas._self_development_loop._change_supplier is (  # noqa: SLF001
                metadata_change_supplier
            )
        finally:
            atlas.shutdown()
