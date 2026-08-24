"""
Phase E5 — SelfDevelopmentLoop focused tests.

Covers:
1. objective/proposal validation
2. approval/governance gate
3. DevelopmentPlanner integration
4. ordered step execution (E3 lifecycle preserved)
5. E2 sandbox execution integration
6. E4 pytest/tool integration
7. successful iteration
8. failed test/verification path
9. rollback/failure handling
10. max_iterations=0
11. max_iterations=1
12. multi-iteration bounded behavior
13. deterministic stopping
14. learning/outcome recording
15. previous outcome influencing the next iteration
16. unavailable capability fail-closed
17. no real-repository mutation
18. no governance bypass
19. no authority escalation
20. no infinite recursion/loop
"""

import unittest

from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
    StepPhase,
    StepStatus,
)
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
)
from atlas.evolution.self_development_loop import (
    DEFAULT_MAX_ITERATIONS,
    SelfDevelopmentLoop,
    build_learning_insight,
    metadata_change_supplier,
)


OK_CHANGES = [{"path": "mod.py", "content": "VALUE = 1\n"}]
OK_TESTS = {"test_mod.py": "def test_value():\n    assert True\n"}
FAIL_TESTS = {"test_mod.py": "def test_value():\n    assert 1 == 2\n"}


def _approved_proposal(metadata=None, title="Add a value") -> EvolutionProposal:
    plan = ImprovementPlan(
        plan_id="IMP-E5-001",
        title=title,
        description="Introduce a module value.",
        priority=ImprovementPriority.HIGH,
        expected_benefit="A module value exists.",
        complexity_estimate="low",
        target_components=["mod"],
    )
    return EvolutionProposal(
        proposal_id="PROP-E5-001",
        title=title,
        summary="Introduce a module value.",
        rationale="Modules should export a value.",
        expected_benefit="A module value exists.",
        risks="Low.",
        impact_analysis="Modifies mod.py.",
        implementation_approach="Add a constant and a test.",
        plan=plan,
        status=ProposalStatus.APPROVED,
        metadata=metadata or {},
    )


def _workload_proposal():
    return _approved_proposal(
        metadata={
            "code_changes": OK_CHANGES,
            "test_files": OK_TESTS,
            "verify_target": "test_mod.py",
        }
    )


def _failing_proposal():
    return _approved_proposal(
        metadata={
            "code_changes": OK_CHANGES,
            "test_files": FAIL_TESTS,
            "verify_target": "test_mod.py",
        }
    )


class TestObjectiveValidation(unittest.TestCase):
    """1 — objective/proposal validation."""

    def test_no_metadata_code_changes_is_invalid_objective(self):
        proposal = _approved_proposal(metadata={})
        result = SelfDevelopmentLoop().run(proposal, max_iterations=2)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.INVALID_OBJECTIVE)

    def test_empty_change_supplier_is_invalid_objective(self):
        loop = SelfDevelopmentLoop(change_supplier=lambda p, h: None)
        result = loop.run(_workload_proposal(), max_iterations=1)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.INVALID_OBJECTIVE)

    def test_none_proposal_fails_closed(self):
        result = SelfDevelopmentLoop().run(None, max_iterations=1)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.GOVERNANCE_DENIED)

    def test_metadata_supplier_returns_none_without_changes(self):
        proposal = _approved_proposal(metadata={})
        self.assertIsNone(metadata_change_supplier(proposal))


class TestApprovalGate(unittest.TestCase):
    """2 — approval/governance gate."""

    def test_draft_proposal_denied(self):
        proposal = _workload_proposal()
        proposal.status = ProposalStatus.DRAFT
        result = SelfDevelopmentLoop().run(proposal, max_iterations=3)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.GOVERNANCE_DENIED)
        self.assertEqual(result.outcomes, [])

    def test_pending_approval_denied(self):
        proposal = _workload_proposal()
        proposal.status = ProposalStatus.PENDING_APPROVAL
        result = SelfDevelopmentLoop().run(proposal)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.GOVERNANCE_DENIED)

    def test_rejected_proposal_denied(self):
        proposal = _workload_proposal()
        proposal.status = ProposalStatus.REJECTED
        result = SelfDevelopmentLoop().run(proposal)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.GOVERNANCE_DENIED)


class TestPlannerIntegration(unittest.TestCase):
    """3 — DevelopmentPlanner integration and ordered E3 lifecycle."""

    def test_plan_produced_and_all_steps_executed(self):
        result = SelfDevelopmentLoop().run(_workload_proposal(), max_iterations=1)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.SUCCESS)
        self.assertIsNotNone(result.plan)
        orders = [s.order for s in result.plan.steps]
        self.assertEqual(orders, sorted(orders))
        for step in result.plan.steps:
            self.assertEqual(step.status, StepStatus.COMPLETED)

    def test_accept_only_completes_after_success(self):
        result = SelfDevelopmentLoop().run(_failing_proposal(), max_iterations=1)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.ITERATIONS_EXHAUSTED)
        accept = next(s for s in result.plan.steps if s.phase == StepPhase.ACCEPT)
        self.assertNotEqual(accept.status, StepStatus.COMPLETED)


class TestE2Integration(unittest.TestCase):
    """4,5 — E2 sandbox execution integration."""

    def test_implementation_applied_inside_sandbox(self):
        result = SelfDevelopmentLoop().run(_workload_proposal(), max_iterations=1)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.SUCCESS)
        self.assertTrue(result.outcomes[0].verification_passed)
        self.assertIn("mod.py", result.outcomes[0].changed_files)

    def test_failed_apply_records_failed_and_rollback(self):
        def failing_implementer(sandbox, proposal, workload, iteration):
            return False, ["mod.py"], "apply exploded"

        loop = SelfDevelopmentLoop(implementer=failing_implementer)
        result = loop.run(_workload_proposal(), max_iterations=1)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.ITERATIONS_EXHAUSTED)
        self.assertEqual(result.outcomes[0].outcome, DevelopmentOutcomeStatus.FAILED)
        self.assertTrue(result.outcomes[0].rollback_occurred)


class TestE4Integration(unittest.TestCase):
    """6 — E4 pytest/tool integration (real pytest child process)."""

    def test_pytest_pass_via_sandbox_verifier(self):
        result = SelfDevelopmentLoop().run(_workload_proposal(), max_iterations=1)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.SUCCESS)
        self.assertEqual(result.outcomes[0].test_outcome, "passed")

    def test_pytest_failure_via_sandbox_verifier(self):
        result = SelfDevelopmentLoop().run(_failing_proposal(), max_iterations=1)
        self.assertEqual(result.outcomes[0].test_outcome, "failed")
        self.assertFalse(result.outcomes[0].verification_passed)


class TestLimitsAndStopping(unittest.TestCase):
    """10,11,12,13 — bounded iterations and deterministic stopping."""

    def test_max_iterations_zero_runs_nothing(self):
        result = SelfDevelopmentLoop().run(_workload_proposal(), max_iterations=0)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.ITERATIONS_EXHAUSTED)
        self.assertEqual(result.iterations_used, 0)
        self.assertEqual(result.outcomes, [])

    def test_max_iterations_one_stops_after_success(self):
        result = SelfDevelopmentLoop().run(_workload_proposal(), max_iterations=1)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.SUCCESS)
        self.assertEqual(result.iterations_used, 1)

    def test_persistent_failure_consumes_budget(self):
        result = SelfDevelopmentLoop().run(_failing_proposal(), max_iterations=3)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.ITERATIONS_EXHAUSTED)
        self.assertEqual(result.iterations_used, 3)
        self.assertEqual(len(result.outcomes), 3)

    def test_no_iteration_exceeds_budget(self):
        result = SelfDevelopmentLoop().run(_failing_proposal(), max_iterations=5)
        self.assertLessEqual(result.iterations_used, 5)
        self.assertEqual(len(result.outcomes), result.iterations_used)

    def test_default_budget_used_when_none(self):
        result = SelfDevelopmentLoop().run(_failing_proposal())
        self.assertEqual(result.iterations_used, DEFAULT_MAX_ITERATIONS)

    def test_success_stops_immediately(self):
        result = SelfDevelopmentLoop().run(_workload_proposal(), max_iterations=10)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.SUCCESS)
        self.assertEqual(result.iterations_used, 1)
        self.assertEqual(len(result.outcomes), 1)


class TestLearningAndHistory(unittest.TestCase):
    """14,15 — learning/outcome recording + history biases next iteration."""

    def test_outcomes_recorded_as_instances(self):
        result = SelfDevelopmentLoop().run(_failing_proposal(), max_iterations=2)
        for outcome in result.outcomes:
            self.assertIsInstance(outcome, DevelopmentOutcome)
            self.assertGreater(outcome.iteration, 0)

    def test_learning_memory_receives_insights(self):
        from atlas.learning_engine.learning_memory import LearningMemory

        memory = LearningMemory()
        loop = SelfDevelopmentLoop(learning_store=memory)
        loop.run(_workload_proposal(), max_iterations=1)
        self.assertGreaterEqual(memory.insight_count, 1)

    def test_build_learning_insight_maps_failure(self):
        outcome = DevelopmentOutcome(
            outcome=DevelopmentOutcomeStatus.FAILED, proposal_id="P",
            plan_id="PLAN", iteration=1, test_outcome="failed",
        )
        insight = build_learning_insight(outcome)
        self.assertEqual(insight.category.name, "FAILURE_AVOIDANCE")
        self.assertIn("failed", insight.description.lower())

    def test_history_biases_next_iteration(self):
        from atlas.evolution.self_development_loop import metadata_change_supplier

        supplier_calls = []

        def supplier(proposal, history):
            supplier_calls.append(len(history))
            if history:
                return metadata_change_supplier(_workload_proposal())
            return metadata_change_supplier(_failing_proposal())

        loop = SelfDevelopmentLoop(change_supplier=supplier)
        result = loop.run(_approved_proposal(), max_iterations=2)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.SUCCESS)
        self.assertEqual(len(result.outcomes), 2)
        self.assertEqual(result.outcomes[0].outcome, DevelopmentOutcomeStatus.FAILED)
        self.assertEqual(result.outcomes[1].outcome, DevelopmentOutcomeStatus.SUCCESS)
        self.assertGreater(len(supplier_calls), 1)


class TestGovernanceAndSafety(unittest.TestCase):
    """16,17,18,19,20 — fail-closed boundaries for the loop."""

    def test_unavailable_capability_fails_closed(self):
        loop = SelfDevelopmentLoop(implementer=None, verifier=object())
        result = loop.run(_workload_proposal(), max_iterations=2)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.UNAVAILABLE_CAPABILITY)
        self.assertEqual(result.outcomes, [])

    def test_no_governance_modules_imported(self):
        import inspect

        import atlas.evolution.self_development_loop as mod
        src = inspect.getsource(mod)
        for forbidden in ("AuthorizationManager", "RuleEngine",
                          "ConstraintRegistry", "ApprovalManager"):
            self.assertNotIn(forbidden, src)

    def test_code_boundary_remains_constitutional(self):
        from atlas.evolution.autonomy.scope_classifier import STATE_SCOPES
        from atlas.evolution.governance.models import ScopeType

        self.assertNotIn(ScopeType.CODE, STATE_SCOPES)

    def test_promotion_gate_refusal_records_governance_denied(self):
        def refusing_gate(proposal, outcome):
            return False

        loop = SelfDevelopmentLoop(promotion_gate=refusing_gate)
        result = loop.run(_workload_proposal(), max_iterations=1)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.GOVERNANCE_DENIED)
        self.assertEqual(result.outcomes[-1].outcome,
                         DevelopmentOutcomeStatus.GOVERNANCE_DENIED)

    def test_promotion_gate_approval_allows_success(self):
        def approving_gate(proposal, outcome):
            return True

        loop = SelfDevelopmentLoop(promotion_gate=approving_gate)
        result = loop.run(_workload_proposal(), max_iterations=1)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.SUCCESS)

    def test_loop_never_mutates_real_repository(self):
        import os
        import subprocess
        import tempfile

        repo = tempfile.TemporaryDirectory()
        try:
            subprocess.run(["git", "init", "-b", "main"], cwd=repo.name,
                           check=True, capture_output=True, text=True)
            with open(os.path.join(repo.name, "keep.txt"), "w") as fh:
                fh.write("keep\n")
            subprocess.run(["git", "add", "."], cwd=repo.name, check=True,
                           capture_output=True, text=True)
            subprocess.run(
                ["git", "-c", "user.name=a", "-c", "user.email=a@b",
                 "commit", "-m", "seed"], cwd=repo.name, check=True,
                capture_output=True, text=True)
            before = subprocess.run(["git", "rev-parse", "HEAD"],
                                    cwd=repo.name, capture_output=True, text=True)
            # Run the loop with its sandbox rooted UNDER the repo's parent, so
            # the sandbox root can never be inside the repository itself.
            loop = SelfDevelopmentLoop(base_dir=os.path.dirname(repo.name))
            result = loop.run(_workload_proposal(), max_iterations=1)
            self.assertEqual(result.status, DevelopmentOutcomeStatus.SUCCESS)
            after = subprocess.run(["git", "rev-parse", "HEAD"],
                                   cwd=repo.name, capture_output=True, text=True)
            self.assertEqual(before.stdout, after.stdout)
            # The sandbox root must NOT live in the repo itself.
            if result.sandbox_path:
                self.assertNotIn(repo.name, os.path.realpath(result.sandbox_path))
        finally:
            repo.cleanup()

    def test_no_recursion_no_self_invocation(self):
        # The loop is a bounded for-loop; running it never spawns a new
        # SelfDevelopmentLoop.run() and cannot recurse.
        import inspect

        import atlas.evolution.self_development_loop as mod
        src = inspect.getsource(mod.SelfDevelopmentLoop.run)
        self.assertIn("for iteration in range", src)
        self.assertNotIn(".run(", src.replace(".run_iteration(", ""))


if __name__ == "__main__":
    unittest.main()
