"""P2/B2.2 — Governed orchestration step execution tests.

Validates the pure, bounded, fail-closed execution layer:
  - valid single/multi-step execution through REAL existing seams
  - dependency ordering and blocked-after-failure
  - unknown capability/tool, malformed step, denied surfaces
  - authority enforcement (owner/user, no escalation, missing session)
  - session attribution preserved through execution
  - tool/capability/workspace/research delegation
  - max-steps bound, deterministic state transitions
  - no arbitrary code execution, no governance bypass
  - plan → steps 1:1 conversion
  - backward compatibility and kernel wiring
"""

from __future__ import annotations

import pytest

from atlas.authority.models import AuthorityLevel
from atlas.authority.service import AuthorityService
from atlas.orchestration.execution_models import (
    ExecutionRequest,
    ExecutionState,
    ExecutionStatus,
    ExecutionStep,
)
from atlas.orchestration.executor import OrchestrationExecutor
from atlas.orchestration.models import NodeKind
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager
from atlas.tools.executor import ToolExecutor
from atlas.tools.models import Tool, ToolResult
from atlas.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Fixtures / builders (real seams; fakes only at genuine external boundaries)
# ---------------------------------------------------------------------------


class _Recorder:
    """Records handler invocations (capability and tool)."""

    def __init__(self):
        self.calls: list[dict] = []


def _make_authority(owner=True, user=None) -> tuple[AuthorityService, SessionContext]:
    authority = AuthorityService("Owner")
    manager = SessionManager(authority)
    if user:
        authority.add_user(user, principal_id=user)
        session = manager.create_session(user)
    else:
        session = manager.create_session("owner")
    return authority, SessionContext.from_session(session)


def _make_capability_executor(recorder: _Recorder, *names: str):
    registry = CapabilityRegistry()
    for name in names:
        def handler(params, _name=name):
            recorder.calls.append({"kind": "capability", "target": _name, "params": params})
            return ExecutionResult(capability=_name, success=True, output={"done": _name})

        registry.register(name, handler)
    return registry, CapabilityDispatcher(registry)


def _make_tool_executor(recorder: _Recorder, *names: str):
    registry = ToolRegistry()
    for name in names:
        def handler(params, _name=name):
            recorder.calls.append({"kind": "tool", "target": _name, "params": params})
            return ToolResult(tool_name=_name, success=True, output={"done": _name})

        registry.register(
            Tool(name=name, description=f"{name} tool", category="utility", handler=handler)
        )
    return ToolExecutor(registry)


def _executor(
    authority=None,
    capability_registry=None,
    capability_dispatcher=None,
    tool_executor=None,
    workspace_service=None,
    research_service=None,
) -> OrchestrationExecutor:
    return OrchestrationExecutor(
        capability_registry=capability_registry,
        capability_dispatcher=capability_dispatcher,
        tool_executor=tool_executor,
        workspace_service=workspace_service,
        research_service=research_service,
        authority_service=authority,
    )


def _step(step_id: str, kind: NodeKind, target: str, inputs=None, depends_on=()):
    return ExecutionStep(
        step_id=step_id,
        kind=kind,
        target=target,
        inputs=inputs or {},
        depends_on=tuple(depends_on),
    )


# ---------------------------------------------------------------------------
# 1. Valid single-step and multi-step execution
# ---------------------------------------------------------------------------


class TestSingleAndMultiStep:
    def test_single_capability_step(self):
        authority, ctx = _make_authority(owner=True)
        rec = _Recorder()
        reg, disp = _make_capability_executor(rec, "conversation")
        ex = _executor(authority, reg, disp)

        result = ex.execute(
            ExecutionRequest(steps=(_step("n1", NodeKind.CAPABILITY, "conversation"),), session_context=ctx)
        )

        assert result.status is ExecutionStatus.COMPLETED
        assert result.completed_count == 1
        assert result.steps[0].state is ExecutionState.COMPLETED
        assert result.steps[0].output == {"done": "conversation"}
        assert len(rec.calls) == 1
        assert rec.calls[0]["target"] == "conversation"

    def test_multi_step_all_completed(self):
        authority, ctx = _make_authority(owner=True)
        rec = _Recorder()
        reg, disp = _make_capability_executor(rec, "a", "b", "c")
        ex = _executor(authority, reg, disp)

        result = ex.execute(
            ExecutionRequest(
                steps=(
                    _step("n1", NodeKind.CAPABILITY, "a"),
                    _step("n2", NodeKind.CAPABILITY, "b"),
                    _step("n3", NodeKind.CAPABILITY, "c"),
                ),
                session_context=ctx,
            )
        )

        assert result.status is ExecutionStatus.COMPLETED
        assert result.completed_count == 3
        assert [r.target for r in result.steps] == ["a", "b", "c"]
        assert [r.state for r in result.steps] == [ExecutionState.COMPLETED] * 3


# ---------------------------------------------------------------------------
# 2/3/4. Dependency ordering and blocked-after-failure
# ---------------------------------------------------------------------------


class TestDependencies:
    def test_dependency_order_respected(self):
        authority, ctx = _make_authority(owner=True)
        rec = _Recorder()
        reg, disp = _make_capability_executor(rec, "a", "b")
        ex = _executor(authority, reg, disp)

        result = ex.execute(
            ExecutionRequest(
                steps=(
                    _step("n1", NodeKind.CAPABILITY, "a"),
                    _step("n2", NodeKind.CAPABILITY, "b", depends_on=("n1",)),
                ),
                session_context=ctx,
            )
        )

        assert result.status is ExecutionStatus.COMPLETED
        assert [c["target"] for c in rec.calls] == ["a", "b"]

    def test_dependent_blocked_after_dependency_failure(self):
        authority, ctx = _make_authority(owner=True)
        rec = _Recorder()
        reg, disp = _make_capability_executor(rec, "a", "b")
        # Fail the first capability by removing its handler behavior: replace with failing handler.
        registry = CapabilityRegistry()

        def fail_handler(params):
            return ExecutionResult(capability="a", success=False, error="boom")

        registry.register("a", fail_handler)
        registry.register("b", lambda params: ExecutionResult(capability="b", success=True, output={}))
        disp = CapabilityDispatcher(registry)
        ex = _executor(authority, registry, disp)

        result = ex.execute(
            ExecutionRequest(
                steps=(
                    _step("n1", NodeKind.CAPABILITY, "a"),
                    _step("n2", NodeKind.CAPABILITY, "b", depends_on=("n1",)),
                ),
                session_context=ctx,
            )
        )

        assert result.status is ExecutionStatus.FAILED
        assert result.steps[0].state is ExecutionState.FAILED
        assert result.steps[0].failure_kind == "execution_failed"
        assert result.steps[1].state is ExecutionState.BLOCKED
        assert result.steps[1].failure_kind == "dependency_failed"


# ---------------------------------------------------------------------------
# 5/6. Unknown capability/tool and malformed steps
# ---------------------------------------------------------------------------


class TestUnknownAndMalformed:
    def test_unknown_capability(self):
        authority, ctx = _make_authority(owner=True)
        rec = _Recorder()
        reg, disp = _make_capability_executor(rec, "conversation")
        ex = _executor(authority, reg, disp)

        result = ex.execute(
            ExecutionRequest(steps=(_step("n1", NodeKind.CAPABILITY, "ghost"),), session_context=ctx)
        )

        assert result.status is ExecutionStatus.FAILED
        assert result.steps[0].failure_kind == "missing_target"
        assert result.steps[0].state is ExecutionState.FAILED
        assert rec.calls == []

    def test_unknown_tool(self):
        authority, ctx = _make_authority(owner=True)
        rec = _Recorder()
        tool_ex = _make_tool_executor(rec, "echo")
        ex = _executor(authority, tool_executor=tool_ex)

        result = ex.execute(
            ExecutionRequest(steps=(_step("n1", NodeKind.TOOL, "ghost"),), session_context=ctx)
        )

        assert result.steps[0].failure_kind == "missing_target"
        assert rec.calls == []

    def test_malformed_step_empty_target(self):
        authority, ctx = _make_authority(owner=True)
        rec = _Recorder()
        reg, disp = _make_capability_executor(rec, "a")
        ex = _executor(authority, reg, disp)

        result = ex.execute(
            ExecutionRequest(steps=(_step("n1", NodeKind.CAPABILITY, "  "),), session_context=ctx)
        )

        assert result.steps[0].failure_kind == "invalid_input"
        assert rec.calls == []


# ---------------------------------------------------------------------------
# 7/8/11. Authority enforcement
# ---------------------------------------------------------------------------


class TestAuthority:
    def test_user_cannot_satisfy_owner_required(self):
        authority, ctx = _make_authority(user="alice")
        rec = _Recorder()
        reg, disp = _make_capability_executor(rec, "a")
        ex = _executor(authority, reg, disp)

        result = ex.execute(
            ExecutionRequest(
                steps=(_step("n1", NodeKind.CAPABILITY, "a"),),
                session_context=ctx,
                required_authority=AuthorityLevel.OWNER,
            )
        )

        assert result.status is ExecutionStatus.REJECTED
        assert result.steps[0].failure_kind == "authorization_failed"
        assert result.steps[0].authority == "user"
        assert result.steps[0].allowed is False
        assert rec.calls == []

    def test_owner_satisfies_owner_required(self):
        authority, ctx = _make_authority(owner=True)
        rec = _Recorder()
        reg, disp = _make_capability_executor(rec, "a")
        ex = _executor(authority, reg, disp)

        result = ex.execute(
            ExecutionRequest(
                steps=(_step("n1", NodeKind.CAPABILITY, "a"),),
                session_context=ctx,
                required_authority=AuthorityLevel.OWNER,
            )
        )

        assert result.status is ExecutionStatus.COMPLETED
        assert result.steps[0].allowed is True
        assert result.steps[0].authority == "owner"

    def test_missing_session_context_rejected(self):
        rec = _Recorder()
        reg, disp = _make_capability_executor(rec, "a")
        ex = _executor(None, reg, disp)

        result = ex.execute(
            ExecutionRequest(steps=(_step("n1", NodeKind.CAPABILITY, "a"),), session_context=None)
        )

        assert result.status is ExecutionStatus.REJECTED
        assert "session" in result.error
        assert result.steps == ()
        assert rec.calls == []

    def test_authority_never_derived_from_text(self):
        # A user session targeting a target named "owner" still runs as the
        # user (authority comes from the session, never from target text).
        authority, ctx = _make_authority(user="alice")
        rec = _Recorder()
        reg, disp = _make_capability_executor(rec, "owner")
        ex = _executor(authority, reg, disp)

        result = ex.execute(
            ExecutionRequest(steps=(_step("n1", NodeKind.CAPABILITY, "owner"),), session_context=ctx)
        )

        assert result.status is ExecutionStatus.COMPLETED
        assert result.steps[0].principal_id == "alice"
        assert result.steps[0].authority == "user"

    def test_no_authority_service_fails_closed(self):
        _, ctx = _make_authority(user="alice")
        rec = _Recorder()
        reg, disp = _make_capability_executor(rec, "a")
        ex = _executor(None, reg, disp)

        result = ex.execute(
            ExecutionRequest(steps=(_step("n1", NodeKind.CAPABILITY, "a"),), session_context=ctx)
        )

        assert result.status is ExecutionStatus.REJECTED
        assert result.steps[0].failure_kind == "authorization_failed"


# ---------------------------------------------------------------------------
# 9/10/12. Attribution
# ---------------------------------------------------------------------------


class TestAttribution:
    def test_user_attribution(self):
        authority, ctx = _make_authority(user="alice")
        rec = _Recorder()
        reg, disp = _make_capability_executor(rec, "a")
        ex = _executor(authority, reg, disp)

        result = ex.execute(
            ExecutionRequest(steps=(_step("n1", NodeKind.CAPABILITY, "a"),), session_context=ctx)
        )

        assert result.principal_id == "alice"
        assert result.authority == "user"
        assert result.session_id == ctx.session_id
        assert result.steps[0].principal_id == "alice"
        assert result.steps[0].authority == "user"

    def test_owner_attribution(self):
        authority, ctx = _make_authority(owner=True)
        rec = _Recorder()
        reg, disp = _make_capability_executor(rec, "a")
        ex = _executor(authority, reg, disp)

        result = ex.execute(
            ExecutionRequest(steps=(_step("n1", NodeKind.CAPABILITY, "a"),), session_context=ctx)
        )

        assert result.principal_id == "owner"
        assert result.authority == "owner"

    def test_session_attribution_preserved_in_handler_params(self):
        authority, ctx = _make_authority(user="alice")
        rec = _Recorder()
        reg, disp = _make_capability_executor(rec, "a")
        ex = _executor(authority, reg, disp)

        ex.execute(
            ExecutionRequest(steps=(_step("n1", NodeKind.CAPABILITY, "a"),), session_context=ctx)
        )

        seen = rec.calls[0]["params"].get("session")
        assert seen == {
            "session_id": ctx.session_id,
            "principal_id": "alice",
            "authority": "user",
        }


# ---------------------------------------------------------------------------
# 13/14/15/16. Seam delegation
# ---------------------------------------------------------------------------


class TestSeamDelegation:
    def test_tool_execution_through_real_executor(self):
        authority, ctx = _make_authority(owner=True)
        rec = _Recorder()
        tool_ex = _make_tool_executor(rec, "echo")
        ex = _executor(authority, tool_executor=tool_ex)

        result = ex.execute(
            ExecutionRequest(steps=(_step("n1", NodeKind.TOOL, "echo", inputs={"text": "hi"}),), session_context=ctx)
        )

        assert result.status is ExecutionStatus.COMPLETED
        assert result.steps[0].output == {"done": "echo"}
        assert rec.calls[0]["kind"] == "tool"
        assert rec.calls[0]["params"]["text"] == "hi"

    def test_capability_execution_through_real_dispatcher(self):
        authority, ctx = _make_authority(owner=True)
        rec = _Recorder()
        reg, disp = _make_capability_executor(rec, "conversation")
        ex = _executor(authority, reg, disp)

        result = ex.execute(
            ExecutionRequest(steps=(_step("n1", NodeKind.CAPABILITY, "conversation"),), session_context=ctx)
        )

        assert result.status is ExecutionStatus.COMPLETED
        assert rec.calls[0]["kind"] == "capability"

    def test_workspace_unwired_fails_closed(self):
        authority, ctx = _make_authority(owner=True)
        ex = _executor(authority)

        result = ex.execute(
            ExecutionRequest(
                steps=(_step("n1", NodeKind.WORKSPACE, "list_resources"),),
                session_context=ctx,
            )
        )

        assert result.steps[0].failure_kind == "missing_target"

    def test_workspace_operation_via_real_service(self):
        from atlas.workspace.workspace_service import WorkspaceService

        authority, ctx = _make_authority(owner=True)
        service = WorkspaceService()
        service.create_workspace("w")
        service.create_project("p")
        ex = _executor(authority, workspace_service=service)

        result = ex.execute(
            ExecutionRequest(
                steps=(_step("n1", NodeKind.WORKSPACE, "list_resources"),),
                session_context=ctx,
            )
        )

        assert result.status is ExecutionStatus.COMPLETED
        assert "result" in result.steps[0].output

    def test_research_operation_via_real_service(self):
        from atlas.evolution.models import ResearchResult
        from atlas.research.acquisition import InformationAcquisitionService

        class _StubCoordinator:
            def __init__(self):
                self.planner = None
                self.storage = None

            def run(self, query):
                return ResearchResult(
                    query_id="q1", findings="findings", sources=[], confidence=0.8
                )

        authority, ctx = _make_authority(owner=True)
        service = InformationAcquisitionService(coordinator=_StubCoordinator())
        ex = _executor(authority, research_service=service)

        result = ex.execute(
            ExecutionRequest(
                steps=(_step("n1", NodeKind.RESEARCH, "acquire", inputs={"question": "q"}),),
                session_context=ctx,
            )
        )

        assert result.status is ExecutionStatus.COMPLETED
        assert result.steps[0].output.get("status") in ("ok", "noop", "partial")


# ---------------------------------------------------------------------------
# 17/18/19. Bounds, states, failure reporting
# ---------------------------------------------------------------------------


class TestBoundsAndStates:
    def test_max_steps_bound(self):
        authority, ctx = _make_authority(owner=True)
        rec = _Recorder()
        reg, disp = _make_capability_executor(rec, "a", "b", "c", "d", "e")
        ex = _executor(authority, reg, disp)

        result = ex.execute(
            ExecutionRequest(
                steps=tuple(_step(f"n{i}", NodeKind.CAPABILITY, name) for i, name in enumerate(["a", "b", "c", "d", "e"])),
                session_context=ctx,
                max_steps=3,
            )
        )

        assert result.status is ExecutionStatus.PARTIAL
        assert result.completed_count == 3
        assert result.skipped_count == 2
        assert all(
            r.failure_kind == "bound_exceeded"
            for r in result.steps[3:]
        )

    def test_deterministic_state_transitions(self):
        authority, ctx = _make_authority(owner=True)
        rec = _Recorder()
        reg, disp = _make_capability_executor(rec, "a", "b")
        ex = _executor(authority, reg, disp)

        result = ex.execute(
            ExecutionRequest(
                steps=(
                    _step("n1", NodeKind.CAPABILITY, "a"),
                    _step("n2", NodeKind.CAPABILITY, "b"),
                ),
                session_context=ctx,
            )
        )

        # Each step appears exactly once, in declared order, terminal states.
        assert [r.step_id for r in result.steps] == ["n1", "n2"]
        assert [r.state for r in result.steps] == [ExecutionState.COMPLETED] * 2

    def test_execution_failure_reporting(self):
        authority, ctx = _make_authority(owner=True)
        registry = CapabilityRegistry()

        def failing(params):
            return ExecutionResult(capability="x", success=False, error="handler exploded")

        registry.register("x", failing)
        ex = _executor(authority, registry, CapabilityDispatcher(registry))

        result = ex.execute(
            ExecutionRequest(steps=(_step("n1", NodeKind.CAPABILITY, "x"),), session_context=ctx)
        )

        assert result.status is ExecutionStatus.FAILED
        assert result.steps[0].failure_kind == "execution_failed"
        assert "handler exploded" in result.steps[0].error


# ---------------------------------------------------------------------------
# 20/21. No arbitrary code / no governance bypass
# ---------------------------------------------------------------------------


class TestNoArbitraryCode:
    def test_eval_import_os_targets_missing(self):
        authority, ctx = _make_authority(owner=True)
        rec = _Recorder()
        reg, disp = _make_capability_executor(rec, "a")
        ex = _executor(authority, reg, disp)

        for bad in ("__import__", "eval", "os.system", "exec"):
            result = ex.execute(
                ExecutionRequest(steps=(_step("n1", NodeKind.CAPABILITY, bad),), session_context=ctx)
            )
            assert result.steps[0].failure_kind == "missing_target"

    def test_denied_surfaces_never_invoked(self):
        authority, ctx = _make_authority(owner=True)
        rec = _Recorder()
        reg, disp = _make_capability_executor(rec, "evolution.execute", "autonomy.apply", "a")
        ex = _executor(authority, reg, disp)

        for denied in ("evolution.execute", "autonomy.apply"):
            result = ex.execute(
                ExecutionRequest(steps=(_step("n1", NodeKind.CAPABILITY, denied),), session_context=ctx)
            )
            assert result.steps[0].failure_kind == "denied_surface"

        # The registered handler for the denied name was never invoked.
        assert all(c["target"] != "evolution.execute" for c in rec.calls)

    def test_executor_has_no_governance_references(self):
        ex = OrchestrationExecutor()
        for attr in ("execution_gateway", "application_engine", "approval_manager", "rule_engine"):
            assert not hasattr(ex, attr)


# ---------------------------------------------------------------------------
# 22/23/24. Plan→steps, continue_on_failure, backward compat
# ---------------------------------------------------------------------------


class TestPlanAndCompatibility:
    def _plan(self, names):
        from atlas.conversation.task_intake import TaskIntake
        from atlas.orchestration.orchestrator import Orchestrator
        from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
        from atlas.reasoning.planning.engine import PlanningEngine

        registry = CapabilityRegistry()
        for name in names:
            registry.register(
                name,
                lambda params, _n=name: ExecutionResult(capability=_n, success=True, output={"done": _n}),
            )
        orchestrator = Orchestrator(
            task_intake=TaskIntake(),
            planning_engine=PlanningEngine(),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=registry,
        )
        return orchestrator.plan("Create a report using local data"), registry

    def test_plan_steps_converted_one_to_one(self):
        authority, ctx = _make_authority(owner=True)
        plan, registry = self._plan(("general",))
        ex = _executor(authority, registry, CapabilityDispatcher(registry))

        result = ex.execute(
            ExecutionRequest(plan=plan, session_context=ctx)
        )

        # Executes exactly the plan's single node.
        assert result.status is ExecutionStatus.COMPLETED
        assert result.completed_count == 1
        assert result.steps[0].target == plan.graph.nodes[0].capability_name

    def test_continue_on_failure_false_stops_run(self):
        authority, ctx = _make_authority(owner=True)
        registry = CapabilityRegistry()

        def failing(params):
            return ExecutionResult(capability="x", success=False, error="no")

        registry.register("x", failing)
        registry.register("y", lambda params: ExecutionResult(capability="y", success=True, output={}))
        ex = _executor(authority, registry, CapabilityDispatcher(registry))

        result = ex.execute(
            ExecutionRequest(
                steps=(
                    _step("n1", NodeKind.CAPABILITY, "x"),
                    _step("n2", NodeKind.CAPABILITY, "y"),
                ),
                session_context=ctx,
                continue_on_failure=False,
            )
        )

        assert result.status is ExecutionStatus.FAILED
        assert result.steps[1].state is ExecutionState.SKIPPED

    def test_continue_on_failure_true_continues_independent(self):
        authority, ctx = _make_authority(owner=True)
        registry = CapabilityRegistry()

        def failing(params):
            return ExecutionResult(capability="x", success=False, error="no")

        registry.register("x", failing)
        registry.register("y", lambda params: ExecutionResult(capability="y", success=True, output={}))
        ex = _executor(authority, registry, CapabilityDispatcher(registry))

        result = ex.execute(
            ExecutionRequest(
                steps=(
                    _step("n1", NodeKind.CAPABILITY, "x"),
                    _step("n2", NodeKind.CAPABILITY, "y"),
                ),
                session_context=ctx,
                continue_on_failure=True,
            )
        )

        assert result.status is ExecutionStatus.PARTIAL
        assert result.steps[0].failed
        assert result.steps[1].completed

    def test_no_collaborators_safe(self):
        _, ctx = _make_authority(user="alice")
        ex = OrchestrationExecutor()

        result = ex.execute(
            ExecutionRequest(steps=(_step("n1", NodeKind.CAPABILITY, "a"),), session_context=ctx)
        )

        # Validation runs before dispatch: no registry/seam → MISSING_TARGET,
        # never raises, deterministic.
        assert result.status is ExecutionStatus.FAILED
        assert result.steps[0].failure_kind == "missing_target"


# ---------------------------------------------------------------------------
# 25. Kernel wiring
# ---------------------------------------------------------------------------


class TestKernelWiring:
    def test_kernel_wires_orchestration_executor(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            ex = atlas.orchestration_executor
            assert ex is not None
            # Shares the kernel's existing seams.
            assert ex._capability_registry is atlas._capability_registry
            assert ex._capability_dispatcher is atlas._capability_dispatcher
            assert ex._tool_executor is atlas._tool_executor
            assert ex._authority_service is atlas._authority_service
            # Not registered in the container (key-set is exact-set-tested).
            assert "orchestration_executor" not in atlas.container.names()
        finally:
            atlas.shutdown()
        assert atlas.orchestration_executor is None

    def test_kernel_executor_end_to_end_owner_session(self):
        from atlas.kernel.atlas import Atlas
        from atlas.orchestration.execution_models import ExecutionRequest, ExecutionStep
        from atlas.orchestration.models import NodeKind

        atlas = Atlas()
        try:
            atlas.start()
            ctx = atlas.session_context
            step = ExecutionStep(step_id="n1", kind=NodeKind.TOOL, target="echo", inputs={"text": "hi"})
            result = atlas.orchestration_executor.execute(
                ExecutionRequest(steps=(step,), session_context=ctx)
            )
            assert result.status.value in ("completed", "failed", "partial")
            # Owner session attribution.
            assert result.principal_id == "owner"
        finally:
            atlas.shutdown()
