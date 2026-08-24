"""Phase E6 — Final Core Integration & End-to-End Acceptance tests.

These tests prove the real, governed self-development path is reachable through
the ACTUAL E2/E3/E4/E5 implementations:

    APPROVED PROPOSAL
        -> DevelopmentPlanner.plan()
        -> DevelopmentPlan
        -> SelfDevelopmentLoop.run()
        -> CodeSandbox
        -> SandboxImplementer (E2 CodeApplier) writes code inside the sandbox
        -> real pytest (E4) runs against that sandbox
        -> verification
        -> DevelopmentOutcome recorded
        -> LearningMemory / history
        -> bounded next iteration

Deliberately NOT mocked: SelfDevelopmentLoop, DevelopmentPlanner, CodeSandbox,
SandboxImplementer, SandboxCodeExecutor, pytest execution, or verification.
The development objective is the smallest built-in capability that exercises
the same path as "a built-in greet tool that returns 'hello'" - a module whose
function returns 'hello' and a real pytest that asserts it.

No commit / no push. All changes stay in the working tree.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from atlas.evolution.autonomy.code_sandbox import CodeSandbox, SandboxPathError
from atlas.evolution.autonomy.sandbox_tools import (
    pytest_tool,
    register_sandbox_tools,
)
from atlas.evolution.development_models import (
    DevelopmentOutcomeStatus,
    SandboxWorkload,
    StepPhase,
    StepStatus,
)
from atlas.evolution.development_planner import DevelopmentPlanner
from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
)
from atlas.evolution.self_development_loop import (
    SandboxImplementer,
    SelfDevelopmentLoop,
    metadata_change_supplier,
)
from atlas.learning_engine.learning_memory import LearningMemory
from atlas.tools.registry import ToolRegistry

_REPO_ROOT = Path(__file__).resolve().parents[1]

GREET_CODE_CHANGES = [
    {"path": "greet.py", "content": "def greet():\n    return 'hello'\n"}
]
GREET_TESTS = {
    "test_greet.py": (
        "def test_greet_returns_hello():\n"
        "    from greet import greet\n"
        "    assert greet() == 'hello'\n"
    ),
}
FAIL_TESTS = {
    "test_greet.py": (
        "def test_greet_returns_hello():\n"
        "    from greet import greet\n"
        "    assert greet() == 'not-hello'\n"
    ),
}


def _improvement_plan() -> ImprovementPlan:
    return ImprovementPlan(
        plan_id="IMP-E6-001",
        title="Add a built-in greet tool that returns 'hello'",
        description="A greet function returning 'hello'.",
        priority=ImprovementPriority.HIGH,
        expected_benefit="greet() returns 'hello' and the tool registers.",
        complexity_estimate="low",
        target_components=["greet"],
    )


def _proposal(metadata, status=ProposalStatus.APPROVED) -> EvolutionProposal:
    return EvolutionProposal(
        proposal_id="PROP-E6-001",
        title="Add a built-in greet tool that returns 'hello'",
        summary="A built-in greet tool that returns 'hello' and registers cleanly.",
        rationale="greet is a deterministic built-in capability.",
        expected_benefit="greet() returns 'hello' and a test passes.",
        risks="Low.",
        impact_analysis="Adds a greet module inside the sandbox.",
        implementation_approach="Write greet.py and a passing pytest.",
        plan=_improvement_plan(),
        status=status,
        metadata=metadata,
    )


def _greet_proposal(status=ProposalStatus.APPROVED) -> EvolutionProposal:
    return _proposal(
        {
            "code_changes": GREET_CODE_CHANGES,
            "test_files": GREET_TESTS,
            "verify_target": "test_greet.py",
        },
        status=status,
    )


def _failing_proposal(status=ProposalStatus.APPROVED) -> EvolutionProposal:
    return _proposal(
        {
            "code_changes": GREET_CODE_CHANGES,
            "test_files": FAIL_TESTS,
            "verify_target": "test_greet.py",
        },
        status=status,
    )


def _repo_git_status() -> str:
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return proc.stdout


class TestEndToEndGreet(unittest.TestCase):
    """The approved objective reaches a verified SUCCESS in one run."""

    def test_full_governed_path_reaches_success(self):
        memory = LearningMemory()
        planner = DevelopmentPlanner()
        loop = SelfDevelopmentLoop(planner=planner, learning_store=memory)
        result = loop.run(_greet_proposal(), max_iterations=3)

        # 1. Approved proposal exists and the run reached SUCCESS.
        self.assertEqual(result.status, DevelopmentOutcomeStatus.SUCCESS)

        # 2. DevelopmentPlanner created a DevelopmentPlan.
        self.assertIsNotNone(result.plan)
        self.assertEqual(result.plan.proposal_id, "PROP-E6-001")
        self.assertGreaterEqual(len(result.plan.steps), 7)

        # 3. SelfDevelopmentLoop executed it (stopped at the first SUCCESS).
        self.assertEqual(result.iterations_used, 1)
        self.assertEqual(len(result.outcomes), 1)

        # 4-6. Verification + outcome assertions.
        outcome = result.outcomes[0]
        self.assertEqual(outcome.outcome, DevelopmentOutcomeStatus.SUCCESS)
        self.assertIn("greet.py", outcome.changed_files)
        self.assertTrue(outcome.verification_passed)
        self.assertEqual(outcome.test_outcome, "passed")
        self.assertEqual(outcome.effectiveness_proxy, 1.0)

        # 7. Every E3 step completed (acceptance proceeded).
        for step in result.plan.steps:
            self.assertEqual(step.status, StepStatus.COMPLETED)

        # 8. Learning/history was recorded in the existing LearningMemory.
        self.assertGreaterEqual(memory.insight_count, 1)

        # 9. The real repository was not modified.
        self.assertFalse((_REPO_ROOT / "greet.py").exists())

    def test_code_changed_inside_sandbox_only(self):
        """The real E2 SandboxImplementer writes inside the sandbox root only."""
        with tempfile.TemporaryDirectory() as td:
            with CodeSandbox(base_dir=td) as sandbox:
                impl = SandboxImplementer()
                ok, files, message = impl.apply(
                    sandbox,
                    _greet_proposal(),
                    SandboxWorkload(
                        code_changes=tuple(GREET_CODE_CHANGES),
                        test_files=GREET_TESTS,
                        verify_target="test_greet.py",
                    ),
                    1,
                )
                self.assertTrue(ok, message)
                self.assertEqual(files, ["greet.py"])
                # The change lands inside the sandbox, never in the repo.
                self.assertTrue(sandbox.exists("greet.py"))
                self.assertEqual(
                    sandbox.read_text("greet.py"), "def greet():\n    return 'hello'\n"
                )
                self.assertNotIn(_REPO_ROOT, sandbox.resolve("greet.py").parents)
            # Sandbox disposed; the real repository is untouched.
            self.assertFalse((_REPO_ROOT / "greet.py").exists())


class TestFailureRollback(unittest.TestCase):
    """The failure path: implementation then test failure -> rollback -> FAILED."""

    def test_failing_test_no_acceptance_no_promotion_no_repo_change(self):
        promotions: list = []

        def gate(proposal, outcome):
            promotions.append(outcome)
            return True

        base = tempfile.mkdtemp(prefix="e6_base_")
        before = _repo_git_status()
        try:
            loop = SelfDevelopmentLoop(promotion_gate=gate, base_dir=base)
            result = loop.run(_failing_proposal(), max_iterations=1)
        finally:
            shutil.rmtree(base, ignore_errors=True)

        # The failure path is real: pytest ran and failed inside the sandbox.
        outcome = result.outcomes[0]
        self.assertEqual(outcome.outcome, DevelopmentOutcomeStatus.FAILED)
        self.assertEqual(outcome.test_outcome, "failed")
        self.assertFalse(outcome.verification_passed)
        self.assertEqual(outcome.effectiveness_proxy, 0.0)

        # No acceptance: the ACCEPT step never completed.
        accept = next(s for s in result.plan.steps if s.phase == StepPhase.ACCEPT)
        self.assertNotEqual(accept.status, StepStatus.COMPLETED)

        # No promotion: the promotion gate was never consulted.
        self.assertEqual(promotions, [])

        # Rollback: the disposable sandbox is disposed (bad change discarded).
        if result.sandbox_path:
            self.assertFalse(os.path.isdir(result.sandbox_path))

        # The real repository is unchanged.
        after = _repo_git_status()
        self.assertEqual(before, after)
        self.assertFalse((_REPO_ROOT / "greet.py").exists())

    def test_real_e2_sandbox_rollback_restores_prior_state(self):
        """The real E2 CodeSandbox snapshot/restore primitive rolls back state.

        Exercises the actual E2 rollback machinery (CodeSandbox.snapshot +
        CodeSandbox.restore) used by SandboxImplementer when a change fails, so
        the test asserts the real mechanism, not a boolean.
        """
        with tempfile.TemporaryDirectory() as td:
            with CodeSandbox(base_dir=td) as sandbox:
                sandbox.write_text("greet.py", "def greet():\n    return 'old'\n")
                snapshot = sandbox.snapshot(["greet.py"])
                sandbox.write_text("greet.py", "def greet():\n    return 'bad'\n")
                self.assertNotEqual(
                    sandbox.read_text("greet.py"), snapshot["greet.py"]
                )
                sandbox.restore(snapshot)
                self.assertEqual(
                    sandbox.read_text("greet.py"), "def greet():\n    return 'old'\n"
                )


class TestMultiIterationLearning(unittest.TestCase):
    """Iteration 1 fails; history biases iteration 2; both are recorded."""

    def test_iter1_fail_iter2_success_uses_supplied_history(self):
        memory = LearningMemory()
        calls: list[int] = []

        def supplier(proposal, history):
            calls.append(len(history))
            if history:
                return metadata_change_supplier(_greet_proposal())
            return metadata_change_supplier(_failing_proposal())

        loop = SelfDevelopmentLoop(change_supplier=supplier, learning_store=memory)
        result = loop.run(_proposal({}), max_iterations=2)

        # Iteration 1 failed, iteration 2 succeeded.
        self.assertEqual(result.status, DevelopmentOutcomeStatus.SUCCESS)
        self.assertEqual(result.iterations_used, 2)
        self.assertEqual(len(result.outcomes), 2)
        self.assertEqual(result.outcomes[0].outcome, DevelopmentOutcomeStatus.FAILED)
        self.assertEqual(result.outcomes[1].outcome, DevelopmentOutcomeStatus.SUCCESS)

        # History was actually supplied to the supplier on the 2nd call.
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(calls[1], 1)

        # Both outcomes were recorded in the shared LearningMemory.
        self.assertGreaterEqual(memory.insight_count, 2)

        # The final outcome is SUCCESS and iteration count stayed bounded.
        self.assertEqual(result.outcomes[-1].outcome, DevelopmentOutcomeStatus.SUCCESS)
        self.assertLessEqual(result.iterations_used, 2)

    def test_max_iterations_bounded_no_infinite_loop(self):
        result = SelfDevelopmentLoop().run(_failing_proposal(), max_iterations=3)
        self.assertEqual(
            result.status, DevelopmentOutcomeStatus.ITERATIONS_EXHAUSTED
        )
        self.assertEqual(result.iterations_used, 3)
        self.assertEqual(len(result.outcomes), 3)


class TestGovernanceAndSafety(unittest.TestCase):
    """Governance / safety acceptance for the E6 integrated path."""

    def test_unapproved_proposal_cannot_execute(self):
        for status in (
            ProposalStatus.DRAFT,
            ProposalStatus.PENDING_APPROVAL,
            ProposalStatus.REJECTED,
        ):
            result = SelfDevelopmentLoop().run(_greet_proposal(status=status))
            self.assertEqual(
                result.status, DevelopmentOutcomeStatus.GOVERNANCE_DENIED
            )
            self.assertEqual(result.outcomes, [])
            self.assertIsNone(result.plan)
        # None proposal also fails closed.
        result = SelfDevelopmentLoop().run(None, max_iterations=2)
        self.assertEqual(result.status, DevelopmentOutcomeStatus.GOVERNANCE_DENIED)
        self.assertEqual(result.outcomes, [])

    def test_code_remains_constitutionally_protected(self):
        from atlas.evolution.autonomy.scope_classifier import STATE_SCOPES
        from atlas.evolution.governance.models import ScopeType

        self.assertNotIn(ScopeType.CODE, STATE_SCOPES)

    def test_sandbox_cannot_escape_its_root(self):
        with tempfile.TemporaryDirectory() as td:
            with CodeSandbox(base_dir=td) as sandbox:
                for bad in ("../escape.txt", "a/../../escape.txt", "/abs.py"):
                    with self.assertRaises(SandboxPathError):
                        sandbox.write_text(bad, "x")
                with self.assertRaises(SandboxPathError):
                    sandbox.read_text("../../etc/passwd")

    def test_e4_tools_require_a_valid_sandbox_workspace(self):
        # The real repo root is not a minted sandbox workspace -> fail closed.
        result = pytest_tool().handler(
            {"workspace": str(_REPO_ROOT), "timeout_seconds": 5}
        )
        self.assertFalse(result.success)
        # A plain temp dir is not a minted workspace either.
        with tempfile.TemporaryDirectory() as td:
            result = pytest_tool().handler({"workspace": td, "timeout_seconds": 5})
            self.assertFalse(result.success)

    def test_real_repository_not_modified_by_full_path(self):
        before = _repo_git_status()
        SelfDevelopmentLoop().run(_greet_proposal(), max_iterations=1)
        after = _repo_git_status()
        self.assertEqual(before, after)

    def test_promotion_remains_behind_the_boundary(self):
        registry = ToolRegistry()
        registered = register_sandbox_tools(registry)
        self.assertEqual(len(registered), 3)
        names_before = {t.name for t in registry.list()}
        SelfDevelopmentLoop().run(_greet_proposal(), max_iterations=1)
        names_after = {t.name for t in registry.list()}
        # The run must not promote any new tool into the real registry.
        self.assertEqual(names_before, names_after)
        # Nor create the greet module in the real repository.
        self.assertFalse((_REPO_ROOT / "greet.py").exists())

    def test_iteration_count_remains_bounded(self):
        result = SelfDevelopmentLoop().run(_failing_proposal(), max_iterations=2)
        self.assertLessEqual(result.iterations_used, 2)
        self.assertEqual(len(result.outcomes), result.iterations_used)


class TestKernelReachable(unittest.TestCase):
    """The integrated path is reachable from the real Atlas kernel graph."""

    def test_kernel_wires_tools_and_reaches_success(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()

            # E4 sandbox tools registered through the existing ToolRegistry.
            names = {t.name for t in atlas._tool_registry.list()}
            for tool_name in (
                "sandbox_pytest",
                "sandbox_git_status",
                "sandbox_git_diff",
            ):
                self.assertIn(tool_name, names)

            # Kernel-owned self-development loop + planner exist and are wired.
            self.assertIsNotNone(atlas.self_development_loop)
            self.assertIsNotNone(atlas.development_planner)

            # An approved greet proposal reaches SUCCESS through the kernel.
            result = atlas.run_self_development(_greet_proposal(), max_iterations=3)
            self.assertEqual(result.status, DevelopmentOutcomeStatus.SUCCESS)
            self.assertEqual(result.outcomes[0].test_outcome, "passed")
        finally:
            atlas.shutdown()


if __name__ == "__main__":
    unittest.main()