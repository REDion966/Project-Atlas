"""M6.4 — Execution Ownership Contract Architectural Tests.

Pins the canonical execution-ownership contract established by M6.3:

  * Three top-level execution owners (one per execution kind):
      - OrchestrationExecutor   (multi-step orchestration)
      - GoalExecutionEngine      (user-authorized goal execution)
      - SelfDevelopmentLoop      (sandboxed code development)
  * Non-owner boundaries remain intact:
      - ToolExecutor / ToolEngine            (primitives)
      - CapabilityDispatcher                  (dispatcher)
      - ToolChainExecutor                     (sub-primitive)
      - RuntimeCoordinator / EvolutionScheduler (coordinators)
      - EvolutionExecutionGateway             (governance gate)
      - TaskManager/Scheduler/Worker          (legacy)
  * M2/M3/M4/M5/P7 governance boundaries are unchanged.

No production behavior is changed; these tests verify architectural
invariants only.

Test design:
  * Source/AST inspection where structural verification is necessary.
  * Behavioral tests where behavior is the actual invariant.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

import pytest

from atlas.goals.goal_execution_engine import GoalExecutionEngine
from atlas.orchestration.executor import OrchestrationExecutor
from atlas.task.task import Task
from atlas.task.task_status import TaskStatus
from atlas.tools.engine import ToolEngine
from atlas.tools.executor import ToolExecutor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
ATLAS_ROOT = REPO_ROOT / "atlas"


def _source(module_path: str) -> str:
    """Return the source text of a repository module by dotted path."""
    relative = module_path.replace(".", "/") + ".py"
    target = REPO_ROOT / relative
    if not target.exists():
        # Try package __init__ resolution.
        target = REPO_ROOT / module_path.replace(".", "/") / "__init__.py"
    return target.read_text(encoding="utf-8")


def _tree(source_text: str) -> ast.AST:
    return ast.parse(source_text)


def _imported_names(tree: ast.AST) -> set[str]:
    """All top-level module names imported anywhere in the tree."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


# ---------------------------------------------------------------------------
# T1 — ToolExecutor primitive boundary
# ---------------------------------------------------------------------------


class TestToolExecutorPrimitiveBoundary:
    """ToolExecutor must remain a low-level primitive.

    It must NOT acquire AuthorityService/governance ownership.
    """

    def test_no_governance_imports(self):
        """ToolExecutor source must not import any authority/governance module."""
        src = _source("atlas.tools.executor")
        tree = _tree(src)
        imports = _imported_names(tree)
        for name in imports:
            assert "authority" not in name.lower(), (
                f"ToolExecutor imports authority module: {name}"
            )
            assert "governance" not in name.lower(), (
                f"ToolExecutor imports governance module: {name}"
            )

    def test_constructor_accepts_only_registry(self):
        """ToolExecutor.__init__ takes only a registry — no governance surface."""
        sig = inspect.signature(ToolExecutor.__init__)
        params = list(sig.parameters.keys())
        assert params == ["self", "registry"], (
            f"ToolExecutor.__init__ params changed: {params}"
        )

    def test_no_authority_or_gateway_attributes(self):
        """ToolExecutor instance must not expose governance attributes."""
        for attr in ("authority_service", "gateway", "rule_engine",
                     "approval_manager", "promotion_gate"):
            assert not hasattr(ToolExecutor, attr), (
                f"ToolExecutor exposes governance attribute: {attr}"
            )


# ---------------------------------------------------------------------------
# T2 — ToolEngine primitive boundary
# ---------------------------------------------------------------------------


class TestToolEnginePrimitiveBoundary:
    """ToolEngine must remain a low-level/advisory primitive.

    It must NOT acquire AuthorityService/governance ownership.
    """

    def test_no_governance_imports(self):
        """ToolEngine source must not import any authority/governance module."""
        src = _source("atlas.tools.engine")
        tree = _tree(src)
        imports = _imported_names(tree)
        for name in imports:
            assert "authority" not in name.lower(), (
                f"ToolEngine imports authority module: {name}"
            )
            assert "governance" not in name.lower(), (
                f"ToolEngine imports governance module: {name}"
            )

    def test_constructor_accepts_registry_selector_executor(self):
        """ToolEngine.__init__ takes only registry/selector/executor."""
        sig = inspect.signature(ToolEngine.__init__)
        params = list(sig.parameters.keys())
        assert params == ["self", "registry", "selector", "executor"], (
            f"ToolEngine.__init__ params changed: {params}"
        )

    def test_no_authority_or_gateway_attributes(self):
        """ToolEngine instance must not expose governance attributes."""
        for attr in ("authority_service", "gateway", "rule_engine",
                     "approval_manager", "promotion_gate"):
            assert not hasattr(ToolEngine, attr), (
                f"ToolEngine exposes governance attribute: {attr}"
            )


# ---------------------------------------------------------------------------
# T3 — RuntimeCoordinator coordinator boundary
# ---------------------------------------------------------------------------


class TestRuntimeCoordinatorCoordinatorBoundary:
    """RuntimeCoordinator must remain a coordinator/delegator.

    It must NOT become a privileged execution owner. Its role is to
    orchestrate the cognitive pipeline and delegate execution to
    ToolEngine / CapabilityDispatcher.
    """

    def test_delegates_tool_execution_to_tool_engine(self):
        """RuntimeCoordinator must invoke ToolEngine.fulfill, not ToolExecutor.execute."""
        src = _source("atlas.runtime.runtime_coordinator")
        # Must delegate to the tool engine surface (selection + execution).
        assert "tool_engine.fulfill" in src, (
            "RuntimeCoordinator no longer delegates to ToolEngine.fulfill"
        )

    def test_delegates_capability_execution_to_dispatcher(self):
        """RuntimeCoordinator must invoke CapabilityDispatcher.dispatch."""
        src = _source("atlas.runtime.runtime_coordinator")
        assert "capability_dispatcher.dispatch" in src, (
            "RuntimeCoordinator no longer delegates to CapabilityDispatcher.dispatch"
        )

    def test_does_not_import_goal_execution_engine(self):
        """RuntimeCoordinator must not own goal execution."""
        src = _source("atlas.runtime.runtime_coordinator")
        tree = _tree(src)
        imports = _imported_names(tree)
        assert not any("goal_execution_engine" in name for name in imports), (
            "RuntimeCoordinator imports GoalExecutionEngine — ownership violation"
        )

    def test_does_not_import_self_development_loop(self):
        """RuntimeCoordinator must not own self-development execution."""
        src = _source("atlas.runtime.runtime_coordinator")
        tree = _tree(src)
        imports = _imported_names(tree)
        assert not any("self_development_loop" in name for name in imports), (
            "RuntimeCoordinator imports SelfDevelopmentLoop — ownership violation"
        )


# ---------------------------------------------------------------------------
# T4 — SelfDevelopmentLoop safety boundary
# ---------------------------------------------------------------------------


class TestSelfDevelopmentLoopSafetyBoundary:
    """SelfDevelopmentLoop must refuse proposals not in APPROVED state.

    This is the P7 safety pre-flight invariant.
    """

    def test_refuses_non_approved_proposal(self):
        """A proposal with status != APPROVED is refused with GOVERNANCE_DENIED."""
        from atlas.evolution.development_models import DevelopmentOutcomeStatus
        from atlas.evolution.models import EvolutionProposal, ProposalStatus
        from atlas.evolution.self_development_loop import SelfDevelopmentLoop

        proposal = EvolutionProposal(
            proposal_id="PROP-TEST-1",
            title="test",
            summary="test",
            rationale="test",
            expected_benefit="test",
            risks="test",
            impact_analysis="test",
            implementation_approach="test",
            plan=None,
            status=ProposalStatus.PENDING_APPROVAL,  # NOT approved
            metadata={},
        )
        loop = SelfDevelopmentLoop()
        result = loop.run(proposal)
        assert result.status == DevelopmentOutcomeStatus.GOVERNANCE_DENIED
        assert "not APPROVED" in result.message

    def test_refuses_none_proposal(self):
        """A None proposal is refused."""
        from atlas.evolution.development_models import DevelopmentOutcomeStatus
        from atlas.evolution.self_development_loop import SelfDevelopmentLoop

        loop = SelfDevelopmentLoop()
        result = loop.run(None)
        assert result.status == DevelopmentOutcomeStatus.GOVERNANCE_DENIED


# ---------------------------------------------------------------------------
# T5 — GoalExecutionEngine authorization boundary
# ---------------------------------------------------------------------------


class TestGoalExecutionEngineAuthorizationBoundary:
    """GoalExecutionEngine must require authorized_by == 'user:cli'.

    This is the user-authorization invariant.
    """

    def test_refuses_non_user_cli_authorization(self):
        """A goal with authorized_by != 'user:cli' is refused."""
        from unittest.mock import MagicMock

        from atlas.goals.execution_models import GoalAuthorization
        from atlas.goals.models import (
            GoalCategory,
            GoalPriority,
            GoalStatus,
            ImprovementGoal,
        )

        goal = ImprovementGoal(
            goal_id="GOAL-AUTH-1",
            title="auth test",
            description="auth test",
            category=GoalCategory.TOOLING,
            priority=GoalPriority.HIGH,
            status=GoalStatus.APPROVED,
            evidence_count=1,
            confidence=0.5,
        )
        auth = GoalAuthorization(
            goal_id="GOAL-AUTH-1",
            authorized_by="system:auto",  # NOT user:cli
            comment="",
            strategy_key="test",
            strategy_name="test",
            planning_context_version="2026-01-01T00:00:00",
        )

        repo = MagicMock()
        repo.get_goals_by_status.return_value = [goal]
        repo.get_authorization.return_value = auth

        engine = GoalExecutionEngine(repository=repo)
        result = engine.settle()

        # Must be refused — not success.
        assert result is not None
        assert result.success is False
        assert "user:cli" in (result.error or "") or "not 'user:cli'" in (result.error or "")


# ---------------------------------------------------------------------------
# T6 — Task.run legacy boundary (M2 contract)
# ---------------------------------------------------------------------------


class TestTaskRunLegacyBoundary:
    """Task.run() must preserve the M2 no-op/failure contract.

    This test verifies the contract without altering Task.run().
    """

    def test_non_terminal_task_fails_with_reason(self):
        """Non-terminal task transitions RUNNING -> FAILED with deterministic reason."""
        task = Task(name="m2-pending")
        assert task.status is TaskStatus.PENDING

        result = task.run()

        assert result is None
        assert task.status is TaskStatus.FAILED
        assert task.started_at is not None
        assert task.finished_at is not None
        assert task.error == "Task has no executable payload"

    def test_terminal_task_is_no_op(self):
        """Terminal tasks (COMPLETED/FAILED/CANCELLED) are left untouched."""
        for terminal_status in (TaskStatus.COMPLETED, TaskStatus.FAILED,
                                TaskStatus.CANCELLED):
            task = Task(name=f"m2-terminal-{terminal_status.name}")
            # Move to terminal state.
            if terminal_status is TaskStatus.COMPLETED:
                task.start()
                task.complete()
            elif terminal_status is TaskStatus.FAILED:
                task.start()
                task.fail("pre-existing")
            else:
                task.cancel()

            original_error = task.error
            original_finished = task.finished_at

            result = task.run()

            assert result is None
            assert task.status is terminal_status
            assert task.error == original_error
            assert task.finished_at == original_finished


# ---------------------------------------------------------------------------
# T7 — OrchestrationExecutor evolution/governance denial boundary
# ---------------------------------------------------------------------------


class TestOrchestrationExecutorDenialBoundary:
    """OrchestrationExecutor must deny evolution/governance prefixes.

    Defense in depth: denied prefixes must fail closed.
    """

    def test_denied_prefixes_blocked(self):
        """Targets under evolution/autonomy/governance prefixes are denied."""
        from atlas.orchestration.executor import _DENIED_PREFIXES

        required = {"evolution.", "autonomy.", "governance.", "approval.",
                    "promotion.", "gateway.", "application.", "schedule."}
        denied = set(_DENIED_PREFIXES)
        assert required.issubset(denied), (
            f"Missing denied prefixes: {required - denied}"
        )

    def test_denied_target_fails_closed(self):
        """A denied target produces a denied_surface failure."""
        from unittest.mock import MagicMock

        from atlas.authority.models import AuthorityLevel, Principal
        from atlas.authority.service import AuthorityService
        from atlas.orchestration.execution_models import ExecutionRequest, ExecutionStep
        from atlas.orchestration.executor import OrchestrationExecutor
        from atlas.orchestration.models import NodeKind
        from atlas.session.context import SessionContext
        from atlas.session.models import Session

        principal = Principal(
            principal_id="p1",
            name="test-principal",
            authority=AuthorityLevel.OWNER,
        )
        session = Session(session_id="s1", principal=principal)
        ctx = SessionContext(session=session)

        authority = MagicMock(spec=AuthorityService)
        authority.check.return_value = MagicMock(allowed=True, reason="")

        step = ExecutionStep(
            step_id="s1",
            kind=NodeKind.CAPABILITY,
            target="evolution.execute",
            depends_on=(),
        )
        request = ExecutionRequest(steps=[step], session_context=ctx)

        executor = OrchestrationExecutor(authority_service=authority)
        result = executor.execute(request)

        assert result.steps[0].failure_kind == "denied_surface"


# ---------------------------------------------------------------------------
# T8 — ToolChainExecutor ownership boundary
# ---------------------------------------------------------------------------


class TestToolChainExecutorOwnershipBoundary:
    """ToolChainExecutor must remain a sub-primitive, not a top-level owner.

    It must NOT have a direct production ownership/wiring path that
    promotes it into a top-level execution owner. Legitimate internal
    construction/use through CapabilityDispatcher is allowed.
    """

    def test_toolchain_executor_not_imported_by_kernel(self):
        """The kernel must not directly instantiate ToolChainExecutor as an owner."""
        kernel_src = _source("atlas.kernel.atlas")
        # ToolChainExecutor is allowed as a type reference in toolchain module
        # wiring, but the kernel must not import it directly as an owner.
        tree = _tree(kernel_src)
        imports = _imported_names(tree)
        assert not any("toolchain.executor" in name for name in imports), (
            "Kernel directly imports ToolChainExecutor — ownership violation"
        )

    def test_toolchain_executor_wired_through_capability_dispatcher(self):
        """ToolChainExecutor is wired through ToolchainCapabilityFactory (CapabilityDispatcher path)."""
        factory_src = _source("atlas.toolchain.capability_handlers")
        # The factory registers capabilities — ToolChainExecutor is used
        # internally, not exposed as a top-level owner.
        assert "ToolChainExecutor" in factory_src
        assert "CapabilityRegistry" in factory_src, (
            "ToolchainCapabilityFactory must register through CapabilityRegistry"
        )

    def test_toolchain_executor_does_not_import_goal_or_self_development(self):
        """ToolChainExecutor must not reach into other owners' domains."""
        src = _source("atlas.toolchain.executor")
        tree = _tree(src)
        imports = _imported_names(tree)
        for name in imports:
            assert "goal_execution_engine" not in name, (
                "ToolChainExecutor imports GoalExecutionEngine — ownership violation"
            )
            assert "self_development_loop" not in name, (
                "ToolChainExecutor imports SelfDevelopmentLoop — ownership violation"
            )
            assert "orchestration.executor" not in name, (
                "ToolChainExecutor imports OrchestrationExecutor — ownership violation"
            )
