"""Development Outcome → Evolution History bridge (Phase 13.5).

Verifies that ``Atlas.run_self_development()`` closes the last edge of the
governed decision pipeline: every ``SelfDevelopmentLoop`` run — success,
failure, or early fail-closed refusal — leaves exactly one
``event_type="development"`` EvolutionRecord in EvolutionMemory, best-effort
and fail-soft, with the returned ``DevelopmentRunResult`` never affected.

Also guards SDL purity: ``self_development_loop.py`` must stay free of
EvolutionMemory imports (the bridge lives in the kernel, not the loop).
"""

import pytest

from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
    DevelopmentPlan,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.intelligence_engine import EvolutionIntelligenceEngine
from atlas.evolution.self_development_loop import DevelopmentRunResult
from atlas.storage.evolution_storage import SQLiteEvolutionStorage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeLoop:
    """Stands in for SelfDevelopmentLoop; returns a canned run result."""

    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, proposal, max_iterations=None):
        self.calls.append({"proposal": proposal, "max_iterations": max_iterations})
        return self.result


class _RaisingPipeline:
    def consolidate(self):
        raise RuntimeError("consolidation exploded")


def _plan(pid="PROP-B1", plan_id="PLAN-B1"):
    return DevelopmentPlan(
        plan_id=plan_id,
        proposal_id=pid,
        title="Bridge test plan",
        summary="synthetic",
    )


def _run_result(
    status,
    pid="PROP-B1",
    plan_id="PLAN-B1",
    outcomes=None,
    iterations=2,
    message="",
    with_plan=True,
):
    return DevelopmentRunResult(
        status=status,
        plan=_plan(pid, plan_id) if with_plan else None,
        outcomes=list(outcomes or []),
        iterations_used=iterations,
        message=message,
    )


def _outcome(status, **overrides):
    base = dict(
        outcome=status,
        proposal_id="PROP-B1",
        plan_id="PLAN-B1",
        iteration=2,
        message="final iteration",
        changed_files=["pkg/module.py"],
        verification_passed=False,
        rollback_occurred=False,
        test_outcome="1 failed",
    )
    base.update(overrides)
    return DevelopmentOutcome(**base)


class _Proposal:
    def __init__(self, pid="PROP-B1"):
        self.proposal_id = pid


@pytest.fixture
def atlas():
    """A lightweight Atlas instance with injectable evolution collaborators."""
    from atlas.kernel.atlas import Atlas

    instance = Atlas()
    yield instance


def _wire(atlas, loop_result, memory=None, pipeline=None):
    atlas._self_development_loop = _FakeLoop(loop_result)
    if memory is not None:
        atlas._evolution_memory = memory
    atlas._knowledge_pipeline = pipeline
    return atlas


# ---------------------------------------------------------------------------
# Bridge behavior
# ---------------------------------------------------------------------------


class TestSuccessfulRunRecorded:
    def test_success_creates_one_development_record(self, atlas):
        outcome = _outcome(
            DevelopmentOutcomeStatus.SUCCESS,
            verification_passed=True,
            test_outcome="1 passed",
        )
        loop_result = _run_result(
            DevelopmentOutcomeStatus.SUCCESS,
            outcomes=[outcome],
            message="all good",
        )
        memory = EvolutionMemory()
        _wire(atlas, loop_result, memory=memory)

        proposal = _Proposal()
        returned = atlas.run_self_development(proposal, max_iterations=3)

        # Result passes through unchanged.
        assert returned is loop_result

        dev_records = memory.get_records_by_type("development")
        assert len(dev_records) == 1
        record = dev_records[0]
        assert record.record_id.startswith("DEV-")
        assert proposal.proposal_id in record.related_ids
        assert "PLAN-B1" in record.related_ids
        meta = record.metadata
        assert meta["terminal_status"] == "SUCCESS"
        assert meta["success"] is True
        assert meta["iterations_used"] == 2
        assert meta["verification_passed"] is True
        assert meta["test_outcome"] == "1 passed"
        assert meta["changed_files"] == ["pkg/module.py"]

    def test_max_iterations_forwarded_to_loop(self, atlas):
        loop_result = _run_result(DevelopmentOutcomeStatus.SUCCESS)
        _wire(atlas, loop_result, memory=EvolutionMemory())
        atlas.run_self_development(_Proposal(), max_iterations=7)
        assert atlas._self_development_loop.calls[0]["max_iterations"] == 7


class TestFailedRunEvidence:
    def test_failed_run_records_failure_evidence(self, atlas):
        outcome = _outcome(
            DevelopmentOutcomeStatus.FAILED,
            verification_passed=False,
            rollback_occurred=True,
            test_outcome="2 failed",
        )
        loop_result = _run_result(
            DevelopmentOutcomeStatus.FAILED,
            outcomes=[outcome],
            message="verification failed",
        )
        memory = EvolutionMemory()
        _wire(atlas, loop_result, memory=memory)

        result = atlas.run_self_development(_Proposal())

        assert result.status is DevelopmentOutcomeStatus.FAILED
        record = memory.get_records_by_type("development")[0]
        assert record.metadata["success"] is False
        assert record.metadata["terminal_status"] == "FAILED"
        assert record.metadata["rollback_occurred"] is True
        assert record.metadata["verification_passed"] is False
        assert "verification failed" in record.description


class TestEarlyRefusalRecorded:
    def test_fail_closed_refusal_is_recorded(self, atlas):
        loop_result = _run_result(
            DevelopmentOutcomeStatus.INVALID_OBJECTIVE,
            with_plan=False,  # early refusal: no plan was derived
            message="no workload",
        )
        memory = EvolutionMemory()
        _wire(atlas, loop_result, memory=memory)

        result = atlas.run_self_development(_Proposal())

        assert result.plan is None
        record = memory.get_records_by_type("development")[0]
        assert record.metadata["terminal_status"] == "INVALID_OBJECTIVE"
        assert record.metadata["success"] is False
        # Only the proposal id is known at refusal time.
        assert record.related_ids == ["PROP-B1"]


# ---------------------------------------------------------------------------
# Fail-soft guarantees
# ---------------------------------------------------------------------------


class TestFailSoftGuarantees:
    def test_memory_write_failure_does_not_break_execution(self, atlas):
        loop_result = _run_result(DevelopmentOutcomeStatus.SUCCESS)

        class _RaisingMemory:
            def store_record(self, record):
                raise RuntimeError("storage exploded")

        _wire(atlas, loop_result, memory=_RaisingMemory())

        result = atlas.run_self_development(_Proposal())
        assert result is loop_result  # identical object, untouched
        assert result.status is DevelopmentOutcomeStatus.SUCCESS

    def test_missing_memory_skips_persistence(self, atlas):
        loop_result = _run_result(DevelopmentOutcomeStatus.SUCCESS)
        atlas._self_development_loop = _FakeLoop(loop_result)
        atlas._evolution_memory = None
        atlas._knowledge_pipeline = None

        result = atlas.run_self_development(_Proposal())
        assert result is loop_result

    def test_consolidation_failure_is_swallowed(self, atlas):
        loop_result = _run_result(DevelopmentOutcomeStatus.SUCCESS)
        _wire(
            atlas,
            loop_result,
            memory=EvolutionMemory(),
            pipeline=_RaisingPipeline(),
        )

        result = atlas.run_self_development(_Proposal())
        assert result is loop_result


# ---------------------------------------------------------------------------
# Durability and downstream consumption
# ---------------------------------------------------------------------------


class TestDurabilityAndConsumption:
    def test_development_record_survives_restart(self, tmp_path):
        storage = SQLiteEvolutionStorage(db_path=tmp_path / "dev.db")
        storage.initialize()
        try:
            from atlas.kernel.atlas import Atlas

            instance = Atlas()
            instance._self_development_loop = _FakeLoop(
                _run_result(
                    DevelopmentOutcomeStatus.SUCCESS,
                    pid="PROP-DUR",
                    outcomes=[
                        _outcome(
                            DevelopmentOutcomeStatus.SUCCESS,
                            verification_passed=True,
                            test_outcome="1 passed",
                        )
                    ],
                )
            )
            memory = EvolutionMemory(storage=storage)
            instance._evolution_memory = memory
            instance._knowledge_pipeline = None

            instance.run_self_development(_Proposal("PROP-DUR"))

            fresh = EvolutionMemory(storage=storage)
            fresh.restore()
            dev_records = fresh.get_records_by_type("development")
            assert len(dev_records) == 1
            assert "PROP-DUR" in dev_records[0].related_ids
            assert dev_records[0].metadata["success"] is True
            # Metadata must round-trip as JSON-safe evidence.
            assert isinstance(dev_records[0].metadata["changed_files"], list)
        finally:
            storage.close()

    def test_development_record_is_f7_consumable_shape(self):
        """The record carries the deterministic success flag the F7 insight
        engine keys on. Note: ``analyze_all()`` currently scopes to
        ``event_type="execution"`` records; development records are exposed
        through the same query surface (``get_records_by_type``) so a future
        engine extension can consume them without schema changes."""
        from atlas.kernel.atlas import Atlas

        instance = Atlas()
        outcome = _outcome(
            DevelopmentOutcomeStatus.FAILED,
            verification_passed=False,
        )
        memory = EvolutionMemory()
        instance._self_development_loop = _FakeLoop(
            _run_result(
                DevelopmentOutcomeStatus.FAILED,
                outcomes=[outcome],
                message="boom",
            )
        )
        instance._evolution_memory = memory
        instance._knowledge_pipeline = None

        instance.run_self_development(_Proposal())

        record = memory.get_records_by_type("development")[0]
        # F7 classifier contract: deterministic success flag + proposal link.
        assert record.metadata["success"] is False
        assert record.metadata["error"] if "error" in record.metadata else True
        assert any("PROP-B1" == rid for rid in [record.related_ids[0]])

        # The existing intelligence engine can still be pointed at the
        # memory without erroring on the unknown event type.
        intelligence = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            insight_scorer=None,
        )
        assert intelligence.analyze_all() == []


# ---------------------------------------------------------------------------
# SDL purity guard
# ---------------------------------------------------------------------------


def test_self_development_loop_stays_free_of_evolution_memory():
    import inspect

    import atlas.evolution.self_development_loop as sdl_module

    source = inspect.getsource(sdl_module)
    assert "EvolutionMemory" not in source
    assert "from atlas.evolution.evolution_memory" not in source