"""
Phase E3 - DevelopmentPlanner focused tests.

Covers:
1. approved EvolutionProposal to deterministic DevelopmentPlan
2. proposal ordering / dependency preservation
3. affected-file information is preserved when available
4. verification/test intent is represented (TEST_SPEC step)
5. unapproved proposal fails closed
6. invalid/incomplete proposal fails safely
7. planner does not execute code
8. planner does not bypass governance
9. existing E2 sandbox executor remains unchanged
10. deterministic output for the same proposal
"""

import unittest
from datetime import datetime

from atlas.evolution.development_models import (
    DevelopmentPlan,
    DevelopmentStep,
    StepPhase,
    StepStatus,
)
from atlas.evolution.development_planner import (
    DevelopmentPlanner,
    DevelopmentPlannerError,
)
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
    Weakness,
)


def _base_plan(plan_id="IMP-001", title="Fix Runtime", components=None):
    return ImprovementPlan(
        plan_id=plan_id, title=title, description="Improve latency.",
        priority=ImprovementPriority.HIGH,
        weaknesses=[Weakness(area="runtime", description="High error rate", severity=ImprovementPriority.HIGH)],
        expected_benefit="Faster responses with lower error rate.",
        complexity_estimate="medium",
        target_components=components if components is not None else ["runtime", "reasoning"],
    )


def _approved_proposal(proposal_id="PROP-001", title="Fix Runtime Performance", components=None, metadata=None):
    return EvolutionProposal(
        proposal_id=proposal_id, title=title,
        summary="Improve runtime latency.",
        rationale="High error rate detected.",
        expected_benefit="Faster responses with lower error rate.",
        risks="Low additive change.",
        impact_analysis="Affects runtime and reasoning components.",
        implementation_approach=(
            "1. Profile current runtime.\n"
            "2. Identify bottlenecks.\n"
            "3. Implement targeted optimizations.\n"
            "4. Verify through tests."
        ),
        plan=_base_plan(components=components),
        status=ProposalStatus.APPROVED,
        approved_at=datetime.now(),
        metadata=metadata or {},
    )

# 1. Approved proposal -> DevelopmentPlan
class TestApprovedProposalPlan(unittest.TestCase):
    def setUp(self):
        self.planner = DevelopmentPlanner()
        self.proposal = _approved_proposal()

    def test_returns_development_plan_instance(self):
        self.assertIsInstance(self.planner.plan(self.proposal), DevelopmentPlan)

    def test_plan_id_starts_with_devplan(self):
        self.assertTrue(self.planner.plan(self.proposal).plan_id.startswith("DEVPLAN-"))

    def test_proposal_id_copied(self):
        self.assertEqual(self.planner.plan(self.proposal).proposal_id, self.proposal.proposal_id)

    def test_title_copied(self):
        self.assertEqual(self.planner.plan(self.proposal).title, self.proposal.title)

    def test_summary_copied(self):
        self.assertEqual(self.planner.plan(self.proposal).summary, self.proposal.summary)

    def test_plan_has_exactly_seven_steps(self):
        self.assertEqual(len(self.planner.plan(self.proposal).steps), 7)

    def test_all_steps_are_development_step_instances(self):
        for step in self.planner.plan(self.proposal).steps:
            self.assertIsInstance(step, DevelopmentStep)

    def test_all_steps_start_pending(self):
        for step in self.planner.plan(self.proposal).steps:
            self.assertEqual(step.status, StepStatus.PENDING)


# 2. Ordering and dependency preservation
class TestStepOrderingAndDependencies(unittest.TestCase):
    def setUp(self):
        self.plan = DevelopmentPlanner().plan(_approved_proposal())
        self.steps = sorted(self.plan.steps, key=lambda s: s.order)

    def test_step_orders_are_one_through_seven(self):
        self.assertEqual([s.order for s in self.steps], list(range(1, 8)))

    def test_step_ids_are_unique(self):
        ids = [s.step_id for s in self.steps]
        self.assertEqual(len(ids), len(set(ids)))

    def test_step_phases_match_expected_sequence(self):
        expected = [StepPhase.INSPECT, StepPhase.DEFINE, StepPhase.IDENTIFY,
                    StepPhase.TEST_SPEC, StepPhase.IMPLEMENT, StepPhase.VERIFY, StepPhase.ACCEPT]
        self.assertEqual([s.phase for s in self.steps], expected)

    def test_inspect_has_no_dependencies(self):
        self.assertEqual(self.steps[0].depends_on, [])

    def test_define_depends_on_inspect(self):
        self.assertIn("STEP-001", self.steps[1].depends_on)

    def test_identify_depends_on_define(self):
        self.assertIn("STEP-002", self.steps[2].depends_on)

    def test_test_spec_depends_on_identify(self):
        self.assertIn("STEP-003", self.steps[3].depends_on)

    def test_implement_depends_on_test_spec(self):
        self.assertIn("STEP-004", self.steps[4].depends_on)

    def test_verify_depends_on_implement(self):
        self.assertIn("STEP-005", self.steps[5].depends_on)

    def test_accept_depends_on_verify(self):
        self.assertIn("STEP-006", self.steps[6].depends_on)

# 3. Affected-file information preserved
class TestAffectedFilesPreservation(unittest.TestCase):
    def test_target_components_become_affected_files(self):
        plan = DevelopmentPlanner().plan(_approved_proposal(components=["runtime", "reasoning"]))
        self.assertIn("runtime", plan.affected_files)
        self.assertIn("reasoning", plan.affected_files)

    def test_explicit_metadata_files_take_precedence(self):
        plan = DevelopmentPlanner().plan(_approved_proposal(
            components=["runtime"], metadata={"affected_files": ["atlas/runtime/runtime.py"]}))
        self.assertEqual(plan.affected_files, ["atlas/runtime/runtime.py"])

    def test_inspect_step_carries_affected_files(self):
        plan = DevelopmentPlanner().plan(_approved_proposal(components=["memory"]))
        inspect = next(s for s in plan.steps if s.phase == StepPhase.INSPECT)
        self.assertIn("memory", inspect.affected_files)

    def test_implement_step_carries_affected_files(self):
        plan = DevelopmentPlanner().plan(_approved_proposal(components=["toolchain"]))
        impl = next(s for s in plan.steps if s.phase == StepPhase.IMPLEMENT)
        self.assertIn("toolchain", impl.affected_files)

    def test_no_components_yields_empty_affected_files(self):
        plan = DevelopmentPlanner().plan(_approved_proposal(components=[]))
        self.assertEqual(plan.affected_files, [])


# 4. Verification / test intent represented
class TestVerificationIntentRepresented(unittest.TestCase):
    def setUp(self):
        self.plan = DevelopmentPlanner().plan(_approved_proposal())

    def test_test_spec_intent_references_expected_benefit(self):
        ts = next(s for s in self.plan.steps if s.phase == StepPhase.TEST_SPEC)
        self.assertIn("Faster responses", ts.intent)

    def test_verify_step_intent_mentions_rollback(self):
        verify = next(s for s in self.plan.steps if s.phase == StepPhase.VERIFY)
        self.assertIn("roll back", verify.intent.lower())

    def test_test_spec_objective_not_empty(self):
        ts = next(s for s in self.plan.steps if s.phase == StepPhase.TEST_SPEC)
        self.assertTrue(ts.objective.strip())

    def test_verify_objective_not_empty(self):
        v = next(s for s in self.plan.steps if s.phase == StepPhase.VERIFY)
        self.assertTrue(v.objective.strip())


# 5. Unapproved proposal fails closed
class TestUnapprovedProposalFailsClosed(unittest.TestCase):
    def _with_status(self, status):
        p = _approved_proposal()
        p.status = status
        return p

    def test_draft_raises(self):
        with self.assertRaises(DevelopmentPlannerError) as ctx:
            DevelopmentPlanner().plan(self._with_status(ProposalStatus.DRAFT))
        self.assertIn("APPROVED", str(ctx.exception))

    def test_pending_approval_raises(self):
        with self.assertRaises(DevelopmentPlannerError):
            DevelopmentPlanner().plan(self._with_status(ProposalStatus.PENDING_APPROVAL))

    def test_rejected_raises(self):
        with self.assertRaises(DevelopmentPlannerError):
            DevelopmentPlanner().plan(self._with_status(ProposalStatus.REJECTED))

    def test_deferred_raises(self):
        with self.assertRaises(DevelopmentPlannerError):
            DevelopmentPlanner().plan(self._with_status(ProposalStatus.DEFERRED))

    def test_implemented_raises(self):
        with self.assertRaises(DevelopmentPlannerError):
            DevelopmentPlanner().plan(self._with_status(ProposalStatus.IMPLEMENTED))

    def test_error_message_names_the_actual_status(self):
        p = self._with_status(ProposalStatus.REJECTED)
        with self.assertRaises(DevelopmentPlannerError) as ctx:
            DevelopmentPlanner().plan(p)
        self.assertIn("REJECTED", str(ctx.exception))

# 6. Invalid / incomplete proposal fails safely
class TestInvalidProposalFailsSafely(unittest.TestCase):
    def test_empty_title_raises(self):
        proposal = _approved_proposal()
        proposal.title = "   "
        with self.assertRaises(DevelopmentPlannerError) as ctx:
            DevelopmentPlanner().plan(proposal)
        self.assertIn("title is empty", str(ctx.exception))

    def test_empty_proposal_id_raises(self):
        proposal = _approved_proposal()
        proposal.proposal_id = "  "
        with self.assertRaises(DevelopmentPlannerError):
            DevelopmentPlanner().plan(proposal)


# 7. Planner does not execute code
class TestPlannerDoesNotExecuteCode(unittest.TestCase):
    def test_plan_returns_plan_not_execution_result(self):
        plan = DevelopmentPlanner().plan(_approved_proposal())
        self.assertIsInstance(plan, DevelopmentPlan)

    def test_plan_does_not_import_sandbox_executor(self):
        import atlas.evolution.development_planner as mod
        import inspect
        self.assertNotIn("SandboxCodeExecutor", inspect.getsource(mod))

    def test_implement_step_is_pending_not_complete(self):
        plan = DevelopmentPlanner().plan(_approved_proposal())
        impl = next(s for s in plan.steps if s.phase == StepPhase.IMPLEMENT)
        self.assertEqual(impl.status, StepStatus.PENDING)


# 8. Planner does not bypass governance
class TestPlannerDoesNotBypassGovernance(unittest.TestCase):
    def test_plan_requires_approved_status(self):
        proposal = _approved_proposal()
        proposal.status = ProposalStatus.DRAFT
        with self.assertRaises(DevelopmentPlannerError):
            DevelopmentPlanner().plan(proposal)

    def test_planner_source_has_no_authorization_manager(self):
        import atlas.evolution.development_planner as mod; import inspect
        self.assertNotIn("AuthorizationManager", inspect.getsource(mod))

    def test_planner_source_has_no_rule_engine(self):
        import atlas.evolution.development_planner as mod; import inspect
        self.assertNotIn("RuleEngine", inspect.getsource(mod))

    def test_planner_source_has_no_constraint_registry(self):
        import atlas.evolution.development_planner as mod; import inspect
        self.assertNotIn("ConstraintRegistry", inspect.getsource(mod))


# 9. E2 sandbox executor remains unchanged
class TestE2SandboxExecutorUnchanged(unittest.TestCase):
    def test_sandbox_code_executor_still_importable(self):
        from atlas.evolution.autonomy.code_execution import SandboxCodeExecutor
        self.assertTrue(callable(getattr(SandboxCodeExecutor, "execute", None)))

    def test_code_sandbox_still_importable(self):
        from atlas.evolution.autonomy.code_sandbox import CodeSandbox, CodeChangeSet
        self.assertTrue(callable(getattr(CodeSandbox, "write_text", None)))
        self.assertTrue(callable(getattr(CodeChangeSet, "validate_path", None)))

    def test_importing_development_planner_does_not_break_sandbox(self):
        from atlas.evolution.autonomy.code_execution import SandboxCodeExecutor
        from atlas.evolution.development_planner import DevelopmentPlanner  # noqa
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            executor = SandboxCodeExecutor(base_dir=td)
            self.assertTrue(hasattr(executor, "execute"))


# 10. Deterministic output for the same proposal
class TestDeterministicOutput(unittest.TestCase):
    def _make_proposal(self):
        return _approved_proposal(proposal_id="PROP-DETERM", title="Determinism Check", components=["memory"])

    def test_same_proposal_produces_same_step_structure(self):
        planner = DevelopmentPlanner()
        proposal = self._make_proposal()
        plan_a = planner.plan(proposal)
        plan_b = planner.plan(proposal)
        for sa, sb in zip(sorted(plan_a.steps, key=lambda s: s.order), sorted(plan_b.steps, key=lambda s: s.order)):
            self.assertEqual(sa.phase, sb.phase)
            self.assertEqual(sa.order, sb.order)
            self.assertEqual(sa.objective, sb.objective)
            self.assertEqual(sa.intent, sb.intent)
            self.assertEqual(sa.affected_files, sb.affected_files)
            self.assertEqual(sa.depends_on, sb.depends_on)

    def test_affected_files_identical_across_two_plans(self):
        planner = DevelopmentPlanner()
        proposal = self._make_proposal()
        self.assertEqual(planner.plan(proposal).affected_files, planner.plan(proposal).affected_files)

    def test_plan_ids_differ_per_call(self):
        planner = DevelopmentPlanner()
        proposal = self._make_proposal()
        self.assertNotEqual(planner.plan(proposal).plan_id, planner.plan(proposal).plan_id)


if __name__ == "__main__":
    unittest.main()
