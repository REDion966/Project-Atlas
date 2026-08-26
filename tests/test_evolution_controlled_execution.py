"""Controlled Self-Improvement Execution Loop — Phase 13.5+.

Closes the gap between an approved EvolutionProposal and a verified
EvolutionResult:

    ExecutionPlan derivation → controlled action execution (injected,
    fail-soft) → validation → honest EvolutionRecord → insight feedback

Guarantees under test:
- every execution attempt produces exactly ONE EvolutionRecord,
- unverified attempts are recorded as failures and never claim IMPLEMENTED,
- the default (no executor) behavior remains purely administrative,
- plan/verification evidence lands in both proposal and record metadata.
"""

from datetime import datetime

import pytest

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.execution_engine import EvolutionExecutionEngine
from atlas.evolution.execution_plan import (
    ExecutionActionResult,
    MAX_PLAN_ACTIONS,
    build_execution_plan,
    verify_execution_results,
)
from atlas.evolution.improvement_planner import ImprovementPlanner
from atlas.evolution.intelligence_engine import EvolutionIntelligenceEngine
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
    Weakness,
)
from atlas.evolution.proposal_generator import ProposalGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_proposal(
    pid: str = "PROP-EXEC",
    targets: list[str] | None = None,
) -> EvolutionProposal:
    """Build a DRAFT proposal with concrete target components."""
    targets = targets if targets is not None else ["memory", "reasoning"]
    weaknesses = [
        Weakness(
            area="testing",
            description="synthetic",
            severity=ImprovementPriority.HIGH,
            supporting_observations=[],
            detected_at=datetime.now(),
        )
    ]
    plan = ImprovementPlanner().create_improvement_plan(weaknesses)
    plan.target_components = list(targets)
    proposal = ProposalGenerator().generate_proposal(plan)
    proposal.proposal_id = pid
    return proposal


def _approved(proposal: EvolutionProposal) -> EvolutionProposal:
    proposal.status = ProposalStatus.APPROVED
    proposal.approved_at = datetime.now()
    return proposal


class _Outcome:
    """Duck-typed executor outcome."""

    def __init__(self, success: bool = True, detail: str = "done"):
        self.success = success
        self.detail = detail


# ---------------------------------------------------------------------------
# ExecutionPlan derivation (pure)
# ---------------------------------------------------------------------------


class TestExecutionPlanDerivation:
    def test_one_action_per_distinct_target(self):
        proposal = _make_proposal(targets=["memory", "reasoning", "memory"])
        plan = build_execution_plan(_approved(proposal))

        assert plan.proposal_id == proposal.proposal_id
        assert [a.target for a in plan.actions] == ["memory", "reasoning"]
        assert all(
            a.action_type == "administrative_record" for a in plan.actions
        )

    def test_bounded_by_max_actions_with_dropped_note(self):
        proposal = _make_proposal(
            targets=[f"component-{i}" for i in range(MAX_PLAN_ACTIONS + 5)]
        )
        plan = build_execution_plan(_approved(proposal))

        assert len(plan.actions) == MAX_PLAN_ACTIONS
        assert plan.metadata["dropped_targets"] == 5
        assert plan.metadata["derived_targets"] == MAX_PLAN_ACTIONS + 5

    def test_to_dict_is_json_safe(self):
        import json

        proposal = _make_proposal()
        data = build_execution_plan(_approved(proposal)).to_dict()
        json.dumps(data)  # must not raise
        assert data["action_count"] == 2

    def test_verify_pure_function(self):
        from atlas.evolution.execution_plan import ExecutionAction

        plan = build_execution_plan(_approved(_make_proposal()))
        ok_results = [
            ExecutionActionResult(action=a, success=True) for a in plan.actions
        ]

        verified, summary = verify_execution_results(plan, ok_results, "IMPLEMENTED")
        assert verified is True
        assert summary == "all actions succeeded and proposal is IMPLEMENTED"

        verified, summary = verify_execution_results(
            plan, ok_results[:-1], "IMPLEMENTED"
        )
        assert verified is False and "expected" in summary

        action = ExecutionAction(action_type="administrative_record", target="x")
        failed = [ExecutionActionResult(action=action, success=False, detail="boom")]
        verified, summary = verify_execution_results(plan, failed, "IMPLEMENTED")
        assert verified is False and "failed" in summary

        verified, summary = verify_execution_results(
            plan, ok_results, "APPROVED"
        )
        assert verified is False and "IMPLEMENTED" in summary


# ---------------------------------------------------------------------------
# Controlled execution loop through the engine
# ---------------------------------------------------------------------------


class TestAdministrativeDefaultPath:
    def _engine_and_memory(self):
        from atlas.evolution.evolution_memory import EvolutionMemory

        memory = EvolutionMemory()
        engine = EvolutionExecutionEngine(
            approval_manager=ApprovalManager(),
            evolution_memory=memory,
        )
        return memory, engine

    def test_default_execution_is_verified_and_administrative(self):
        memory, engine = self._engine_and_memory()
        proposal = _approved(_make_proposal("PROP-ADMIN"))
        memory.store_proposal(proposal)

        result = engine.execute(proposal)

        assert result.success is True
        assert result.error == ""
        assert proposal.status == ProposalStatus.IMPLEMENTED
        assert proposal.metadata["verification"]["verified"] is True
        assert proposal.metadata["execution_plan_id"]

        records = memory.get_records(10)
        assert len(records) == 1  # exactly one record per attempt
        record = records[0]
        assert record.metadata["success"] is True
        assert record.metadata["execution_plan"]["proposal_id"] == "PROP-ADMIN"
        assert record.metadata["verification"]["verified"] is True
        assert len(record.metadata["action_results"]) == 2

    def test_default_path_survives_restart(self, tmp_path):
        from atlas.evolution.evolution_memory import EvolutionMemory
        from atlas.storage.evolution_storage import SQLiteEvolutionStorage

        storage = SQLiteEvolutionStorage(db_path=tmp_path / "exec.db")
        storage.initialize()
        try:
            memory = EvolutionMemory(storage=storage)
            engine = EvolutionExecutionEngine(
                approval_manager=ApprovalManager(),
                evolution_memory=memory,
            )
            proposal = _approved(_make_proposal("PROP-DURABLE"))
            memory.store_proposal(proposal)
            engine.execute(proposal)

            fresh = EvolutionMemory(storage=storage)
            fresh.restore()
            restored = fresh.get_proposal("PROP-DURABLE")
            assert restored.status == ProposalStatus.IMPLEMENTED
            assert restored.metadata["verification"]["verified"] is True
            assert fresh.record_count == 1
        finally:
            storage.close()


class TestControlledExecutorSeam:
    def _engine(self, memory, **kwargs):
        return EvolutionExecutionEngine(
            approval_manager=ApprovalManager(),
            evolution_memory=memory,
            **kwargs,
        )

    def test_executor_receives_every_action(self):
        from atlas.evolution.evolution_memory import EvolutionMemory

        seen: list[str] = []

        def executor(action):
            seen.append(action.target)
            return _Outcome(success=True)

        memory = EvolutionMemory()
        engine = self._engine(memory, action_executor=executor)
        proposal = _approved(
            _make_proposal("PROP-CTRL", targets=["memory", "tools"])
        )

        result = engine.execute(proposal)

        assert result.success is True
        assert sorted(seen) == ["memory", "tools"]
        record = memory.get_records(1)[0]
        assert all(r["success"] for r in record.metadata["action_results"])

    def test_failing_action_blocks_implementation_and_is_recorded(self):
        from atlas.evolution.evolution_memory import EvolutionMemory

        calls: list[str] = []

        def executor(action):
            calls.append(action.target)
            if action.target == "tools":
                return _Outcome(success=False, detail="tool unavailable")
            return _Outcome(success=True)

        memory = EvolutionMemory()
        engine = self._engine(memory, action_executor=executor)
        proposal = _approved(
            _make_proposal("PROP-FAIL", targets=["memory", "tools"])
        )

        result = engine.execute(proposal)

        # Both actions attempted (fail-soft; no abort on first failure).
        assert calls == ["memory", "tools"]
        assert result.success is False
        assert "tool unavailable" in result.error
        # A failed attempt must not claim IMPLEMENTED.
        assert proposal.status == ProposalStatus.APPROVED
        assert proposal.metadata["verification"]["verified"] is False

        records = memory.get_records(10)
        assert len(records) == 1  # exactly one record for the attempt
        assert records[0].metadata["success"] is False
        failed = [
            r for r in records[0].metadata["action_results"] if not r["success"]
        ]
        assert failed and failed[0]["target"] == "tools"

    def test_raising_executor_becomes_failed_result_not_exception(self):
        from atlas.evolution.evolution_memory import EvolutionMemory

        def executor(action):
            raise RuntimeError(f"cannot execute {action.target}")

        memory = EvolutionMemory()
        engine = self._engine(memory, action_executor=executor)
        proposal = _approved(_make_proposal("PROP-RAISE"))

        result = engine.execute(proposal)  # must not raise

        assert result.success is False
        assert proposal.status == ProposalStatus.APPROVED
        records = memory.get_records(10)
        assert len(records) == 1
        assert records[0].metadata["success"] is False
        detail = records[0].metadata["action_results"][0]["detail"]
        assert "cannot execute" in detail

    def test_custom_validator_can_reject(self):
        from atlas.evolution.evolution_memory import EvolutionMemory

        memory = EvolutionMemory()

        def strict_validator(plan, results, final_status):
            return False, "validation harness unavailable"

        engine = self._engine(memory, result_validator=strict_validator)
        proposal = _approved(_make_proposal("PROP-VALIDATE"))

        result = engine.execute(proposal)

        assert result.success is False
        assert result.error == "validation harness unavailable"
        assert proposal.status == ProposalStatus.APPROVED
        assert memory.get_records(1)[0].metadata["success"] is False

    def test_failed_execution_feeds_failure_insight(self):
        from atlas.evolution.evolution_memory import EvolutionMemory

        memory = EvolutionMemory()
        engine = self._engine(
            memory,
            action_executor=lambda action: _Outcome(
                success=False, detail="nope"
            ),
        )
        proposal = _approved(_make_proposal("PROP-LEARN"))
        engine.execute(proposal)

        intelligence = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            insight_scorer=None,
        )
        insights = intelligence.analyze_all()
        assert len(insights) >= 1
        assert insights[0].outcome == "failure"
        assert insights[0].proposal_id == "PROP-LEARN"
