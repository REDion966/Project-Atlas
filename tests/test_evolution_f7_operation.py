"""Phase F7 - Autonomous Operation Controller tests.

Focused deterministic coverage of the F7 acceptance criteria:

 1. useful work -> adaptation cycle invoked
 2. no useful work -> NO_WORK
 3. cooldown prevents immediate repeat
 4. maximum cycle limit enforced
 5. consecutive failure limit enforced
 6. repeated failure eventually stops
 7. deterministic result ordering
 8. bounded result size
 9. malformed input fails closed
10. F6 integration
11. F5 evaluation integration
12. governance boundary remains intact
13. no approval / 14. no execution / 15. no sandbox
16. no AI/model imports
17. no EventBus/Scheduler/Memory duplication
18. no Atlas.tick() modification
19. durable-state via existing EvolutionMemory
20. shutdown behavior (kernel bridge)
21. architecture/import scan

Uses real OperationController/OperationPolicy; small deterministic F6-cycle
stubs stand in for the orchestration boundary.
"""

import ast
import inspect
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from atlas.evolution.operation import (
    OperationController,
    OperationDecision,
    OperationPolicy,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]

NOW = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)


class _Cycle:
    def __init__(self, cycle_id="CYC-1", proposals=(), candidates=(),
                 environment_changes=(), status="ok"):
        self.cycle_id = cycle_id
        self.proposals = list(proposals)
        self.candidates = list(candidates)
        self.environment_changes = list(environment_changes)
        self.status = status


class _Proposal:
    def __init__(self, proposal_id):
        self.proposal_id = proposal_id


class _Candidate:
    def __init__(self, candidate_id):
        self.candidate_id = candidate_id


def _ok_cycle(extra=0):
    return _Cycle(
        cycle_id="CYC-OK",
        proposals=[_Proposal(f"P{i}") for i in range(1 + extra)],
        candidates=[_Candidate(f"ADAPT-{i}") for i in range(1 + extra)],
        environment_changes=[object()],
        status="ok",
    )


def _no_work_cycle():
    return _Cycle(cycle_id="CYC-NONE", status="ok")


def _real_proposal(proposal_id="P-REAL"):
    from atlas.evolution.models import (
        EvolutionProposal,
        ImprovementPlan,
        ImprovementPriority,
        ProposalStatus,
    )

    return EvolutionProposal(
        proposal_id=proposal_id,
        title="t",
        summary="s",
        rationale="r",
        expected_benefit="e",
        risks="low",
        impact_analysis="i",
        implementation_approach="a",
        plan=ImprovementPlan(
            plan_id=f"IMP-{proposal_id}", title="t", description="d",
            priority=ImprovementPriority.MEDIUM,
            target_components=["MODEL:openai:gpt-4"],
        ),
        status=ProposalStatus.DRAFT,
    )


class TestBasicOperation(unittest.TestCase):
    """1-2: useful work runs cycles; no useful work -> NO_WORK."""

    def test_useful_work_invokes_cycle(self):
        controller = OperationController(
            cycle_runner=lambda **k: _ok_cycle(),
            now=lambda: NOW,
        )
        result = controller.run_operation(now=NOW)
        self.assertIs(result.decision, OperationDecision.RAN_LIMITED)
        self.assertEqual(result.status, "ok")
        self.assertGreater(result.cycles_ran, 0)
        self.assertTrue(result.useful)

    def test_no_work_returns_no_work(self):
        controller = OperationController(
            cycle_runner=lambda **k: _no_work_cycle(),
            now=lambda: NOW,
        )
        result = controller.run_operation(now=NOW)
        self.assertIs(result.decision, OperationDecision.NO_WORK)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.cycles_ran, 1)  # probe cycle ran
        self.assertFalse(result.useful)

    def test_work_probe_false_skips_cycle(self):
        calls = []
        controller = OperationController(
            cycle_runner=lambda **k: calls.append(1) or _ok_cycle(),
            work_probe=lambda: False,
            now=lambda: NOW,
        )
        result = controller.run_operation(now=NOW)
        self.assertIs(result.decision, OperationDecision.NO_WORK)
        self.assertEqual(result.cycles_ran, 0)
        self.assertEqual(calls, [])


class TestPolicyLimits(unittest.TestCase):
    """3-5: cooldown, max cycles, consecutive-failure limits."""

    def test_cooldown_prevents_immediate_repeat(self):
        controller = OperationController(
            cycle_runner=lambda **k: _ok_cycle(),
            policy=OperationPolicy(cooldown_seconds=30),
            now=lambda: NOW,
        )
        controller.run_operation(now=NOW)
        second = controller.run_operation(now=NOW + timedelta(seconds=5))
        self.assertIs(second.decision, OperationDecision.COOLDOWN_ACTIVE)
        self.assertEqual(second.status, "cooldown")
        self.assertGreater(second.cooldown_remaining_seconds, 0)

    def test_max_cycles_limit(self):
        calls = []
        controller = OperationController(
            cycle_runner=lambda **k: calls.append(1) or _ok_cycle(),
            policy=OperationPolicy(max_cycles_per_invocation=10),
            now=lambda: NOW,
        )
        result = controller.run_operation(max_cycles=2, now=NOW)
        self.assertEqual(result.cycles_ran, 2)
        self.assertEqual(len(calls), 2)

    def test_consecutive_failure_limit(self):
        def boom(**kw):
            raise RuntimeError("boom")

        controller = OperationController(
            cycle_runner=boom,
            policy=OperationPolicy(max_consecutive_failures=2),
            now=lambda: NOW,
        )
        result = controller.run_operation(now=NOW)
        self.assertIs(result.decision, OperationDecision.FAILURE_LIMIT)
        self.assertEqual(result.status, "failed")


class TestBoundedDeterministic(unittest.TestCase):
    """6-9: bounded results, deterministic ordering, fail-closed."""

    def test_budget_capped_by_hard_max(self):
        controller = OperationController(
            cycle_runner=lambda **k: _ok_cycle(),
            policy=OperationPolicy(max_cycles_per_invocation=100,
                                   max_budget_cycles=100),
            now=lambda: NOW,
        )
        # With a hard budget of 100 but an explicit run cap of 10, cycles are
        # bounded to the smaller of the two (10).
        result = controller.run_operation(max_cycles=10, now=NOW)
        self.assertLessEqual(result.cycles_ran, 10)

    def test_deterministic_proposal_ordering(self):
        controller = OperationController(
            cycle_runner=lambda **k: _ok_cycle(extra=3),
            policy=OperationPolicy(max_cycles_per_invocation=1),
            now=lambda: NOW,
        )
        r1 = controller.run_operation(now=NOW)
        r2 = controller.run_operation(now=NOW)
        self.assertEqual(r1.proposal_ids, r2.proposal_ids)

    def test_malformed_input_fails_closed(self):
        controller = OperationController(now=lambda: NOW)
        result = controller.run_operation(now=NOW)
        self.assertEqual(result.decision, OperationDecision.NO_WORK)
        self.assertEqual(result.status, "partial")
        self.assertTrue(any(f[0] == "cycle" for f in result.failures))


class TestF6F5Integration(unittest.TestCase):
    """10-11: F6 adaptation cycle + F5 evaluation integration."""

    def test_f6_cycle_reused(self):
        from atlas.evolution.adaptation.orchestrator import AdaptationOrchestrator
        from atlas.evolution.environment.models import (
            EnvironmentChange, EnvironmentChangeType, EnvironmentDomain,
            EnvironmentEntity, EnvironmentObservationResult,
        )

        class _StubEnv:
            def observe_cycle(self):
                entity = EnvironmentEntity(EnvironmentDomain.TOOL, "tool_a")
                change = EnvironmentChange(
                    entity=entity,
                    change_type=EnvironmentChangeType.CHANGED,
                    current={"available": True},
                )
                return EnvironmentObservationResult(
                    cycle_id="ENV-1", changes=(change,), failures=(),
                    provider_count=1, observed_count=1, success=True,
                )

        runner_returns = []

        def real_f6_runner(**kwargs):
            orch = AdaptationOrchestrator(environment_observer=_StubEnv())
            result = orch.run_cycle(
                lifecycle_targets=kwargs.get("lifecycle_targets", ()),
            )
            runner_returns.append(result)
            return result

        controller = OperationController(
            cycle_runner=real_f6_runner,
            policy=OperationPolicy(max_cycles_per_invocation=1),
            now=lambda: NOW,
        )
        result = controller.run_operation(now=NOW)
        self.assertIn(result.decision,
                      (OperationDecision.RAN_LIMITED, OperationDecision.NO_WORK))
        self.assertEqual(len(runner_returns), 1)
        for env in runner_returns:
            from atlas.evolution.models import ProposalStatus
            for p in env.proposals:
                self.assertIs(p.status, ProposalStatus.DRAFT)

    def test_f5_evaluator_integration(self):
        from atlas.evolution.adaptation.evaluator import AdaptationEvaluator

        controller = OperationController(
            cycle_runner=lambda **k: _Cycle(
                cycle_id="CYC-EVAL",
                proposals=[_real_proposal("P-EVAL-1")],
                candidates=(),
                environment_changes=[object()],
                status="ok",
            ),
            evaluator=AdaptationEvaluator(now=lambda: NOW),
            now=lambda: NOW,
        )
        result = controller.run_operation(now=NOW)
        self.assertGreaterEqual(result.evaluation_count, 1)
        self.assertGreaterEqual(result.feedback_count, 1)


class TestDurableState(unittest.TestCase):
    """19: durable ledger via the EXISTING EvolutionMemory."""

    def test_ledger_via_existing_evolution_memory(self):
        from atlas.evolution.evolution_memory import EvolutionMemory

        memory = EvolutionMemory()
        controller = OperationController(
            cycle_runner=lambda **k: _ok_cycle(),
            evolution_memory=memory,
            now=lambda: NOW,
        )
        controller.run_operation(now=NOW)
        self.assertEqual(memory.record_count, 1)
        record = memory.get_records(1)[0]
        self.assertEqual(record.event_type, "operation_cycle")


class TestGovernanceSafety(unittest.TestCase):
    """Boundaries: imports, no approval/execution, tick untouched, shutdown."""

    def test_no_ai_or_governance_imports(self):
        from atlas.evolution.operation import controller as mod

        src = inspect.getsource(mod)
        for forbidden in ("AIProvider", "AIManager", "ModelRouter", "LLM",
                          "ApprovalManager", "AuthorizationManager",
                          "EvolutionExecutionGateway", "subprocess",
                          "Thread(time", "daemon("):
            self.assertNotIn(forbidden, src)

    def test_architecture_import_scan(self):
        op_dir = _REPO_ROOT / "atlas" / "evolution" / "operation"
        forbidden = (
            "atlas.ai",
            "atlas.evolution.autonomy",
            "atlas.evolution.execution_gateway",
            "atlas.evolution.approval_manager",
            "atlas.evolution.governance",
            "subprocess",
        )
        violations = []
        for path in sorted(op_dir.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if any(alias.name == p or alias.name.startswith(p)
                               for p in forbidden):
                            violations.append((str(path), alias.name))
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if any(node.module == p or node.module.startswith(p)
                           for p in forbidden):
                        violations.append((str(path), node.module))
        self.assertEqual(violations, [])

    def test_no_parallel_infrastructure_mentioned(self):
        import inspect

        from atlas.evolution.operation import controller as mod

        src = inspect.getsource(mod)
        for forbidden in ("EventBus", "Scheduler", "TaskQueue", "ToolRegistry"):
            self.assertNotIn(forbidden, src)

    def test_controller_never_approves_or_executes(self):
        src = inspect.getsource(OperationController.run_operation)
        for forbidden in ("approve(", "execute(", "sandbox", "shell=",
                          "self.run("):
            self.assertNotIn(forbidden, src)

    def test_kernel_bridge_and_tick_untouched(self):
        from atlas.kernel.atlas import Atlas

        import inspect

        tick_src = inspect.getsource(Atlas.tick)
        self.assertNotIn("run_operation_cycle", tick_src)

        atlas = Atlas()
        try:
            atlas.start()
            result = atlas.run_operation_cycle(max_cycles=1)
            self.assertIsNotNone(result)
        finally:
            atlas.shutdown()
        self.assertIsNone(atlas.operation_controller)


if __name__ == "__main__":
    unittest.main()