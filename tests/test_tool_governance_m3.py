"""M3 — Tool governance invariant regression tests.

Encodes the M3.2 governance contract (Design A — caller-owned governance):

    A privileged tool handler may execute ONLY after passing through a
    canonical governed boundary (OrchestrationExecutor per-step
    authorization, or P7.6 kernel authorization).

    ToolExecutor and ToolEngine remain low-level/advisory primitives that
    trust their caller; they are NOT governance boundaries and must not be
    used for privileged operations.

These tests prove the invariant holds for the canonical governed path and
document the advisory-only role of ToolEngine.
"""

from __future__ import annotations

import pytest

from atlas.authority.service import AuthorityService
from atlas.orchestration.executor import OrchestrationExecutor
from atlas.orchestration.execution_models import (
    ExecutionRequest,
    ExecutionStatus,
    ExecutionStep,
    NodeKind,
)
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager
from atlas.tools.engine import ToolEngine
from atlas.tools.executor import ToolExecutor
from atlas.tools.models import Tool, ToolRequest, ToolResult
from atlas.tools.registry import ToolRegistry
from atlas.tools.selector import ToolSelector


# ---------------------------------------------------------------------------
# Helpers (local; reuse the project's test doubles)
# ---------------------------------------------------------------------------


class _Recorder:
    def __init__(self):
        self.calls: list[dict] = []


def _make_authority(owner: bool = True, user_id: str = "alice"):
    authority = AuthorityService("Owner")
    manager = SessionManager(authority)
    if owner:
        session = manager.create_session("owner")
    else:
        authority.add_user(user_id, principal_id=user_id)
        session = manager.create_session(user_id)
    return authority, SessionContext.from_session(session)


def _make_tool_executor(rec: _Recorder, *names: str) -> ToolExecutor:
    registry = ToolRegistry()
    for name in names:
        def handler(params, _name=name):
            rec.calls.append({"kind": "tool", "target": _name, "params": params})
            return ToolResult(tool_name=_name, success=True, output={"done": _name})

        registry.register(
            Tool(name=name, description=f"{name} tool", category="utility", handler=handler)
        )
    return ToolExecutor(registry)


def _make_tool_engine(rec: _Recorder, *names: str) -> ToolEngine:
    registry = ToolRegistry()
    for name in names:
        def handler(params, _name=name):
            rec.calls.append({"kind": "tool", "target": _name, "params": params})
            return ToolResult(tool_name=_name, success=True, output={"done": _name})

        registry.register(
            Tool(name=name, description=f"{name} tool", category="utility", handler=handler)
        )
    return ToolEngine(registry, ToolSelector(), ToolExecutor(registry))


def _step(step_id: str, kind: NodeKind, target: str, inputs=None, depends_on=()):
    return ExecutionStep(
        step_id=step_id,
        kind=kind,
        target=target,
        inputs=inputs or {},
        depends_on=tuple(depends_on),
    )


# ---------------------------------------------------------------------------
# Canonical governed path: OrchestrationExecutor authorizes BEFORE tool dispatch
# ---------------------------------------------------------------------------


class TestOrchestrationAuthorizesToolExecution:
    """The canonical governed multi-step path must authorize each step
    (including tool steps) through AuthorityService before dispatching to
    ToolExecutor."""

    def test_owner_can_execute_tool_through_orchestration(self):
        authority, ctx = _make_authority(owner=True)
        rec = _Recorder()
        tool_ex = _make_tool_executor(rec, "echo")
        ex = OrchestrationExecutor(authority_service=authority, tool_executor=tool_ex)

        result = ex.execute(
            ExecutionRequest(
                steps=(_step("n1", NodeKind.TOOL, "echo", inputs={"text": "hi"}),),
                session_context=ctx,
            )
        )

        assert result.status is ExecutionStatus.COMPLETED
        assert result.steps[0].state.name == "COMPLETED"
        # The handler was invoked through the governed boundary.
        assert len(rec.calls) == 1
        assert rec.calls[0]["target"] == "echo"
        assert rec.calls[0]["params"]["text"] == "hi"

    def test_user_denied_tool_execution_through_orchestration(self):
        authority, ctx = _make_authority(owner=False, user_id="alice")
        rec = _Recorder()
        tool_ex = _make_tool_executor(rec, "echo")
        ex = OrchestrationExecutor(authority_service=authority, tool_executor=tool_ex)

        result = ex.execute(
            ExecutionRequest(
                steps=(_step("n1", NodeKind.TOOL, "echo", inputs={"text": "hi"}),),
                session_context=ctx,
                required_authority=__import__(
                    "atlas.authority.models", fromlist=["AuthorityLevel"]
                ).AuthorityLevel.OWNER,
            )
        )

        # Authorization fails closed: the step is FAILED and the handler is
        # never invoked.
        assert result.steps[0].state.name == "FAILED"
        assert result.steps[0].failure_kind == "authorization_failed"
        assert rec.calls == []

    def test_missing_session_context_fails_closed(self):
        authority, _ = _make_authority(owner=True)
        rec = _Recorder()
        tool_ex = _make_tool_executor(rec, "echo")
        ex = OrchestrationExecutor(authority_service=authority, tool_executor=tool_ex)

        result = ex.execute(
            ExecutionRequest(
                steps=(_step("n1", NodeKind.TOOL, "echo"),),
                session_context=None,
            )
        )

        assert result.status is ExecutionStatus.REJECTED
        assert rec.calls == []


# ---------------------------------------------------------------------------
# Advisory-only role of ToolEngine
# ---------------------------------------------------------------------------


class TestToolEngineAdvisoryOnly:
    """ToolEngine is a low-level/advisory composer. It performs no authority
    check and must not be treated as a privileged execution path. These tests
    document that contract without inventing a privilege model."""

    def test_tool_engine_executes_without_authority_check(self):
        """ToolEngine has no authority surface; it executes directly. This is
        the documented advisory-only behavior — it is NOT a privileged path."""
        rec = _Recorder()
        engine = _make_tool_engine(rec, "echo")

        result = engine.fulfill(ToolRequest(goal="echo", context={"text": "hi"}))

        assert result.success is True
        assert rec.calls[0]["target"] == "echo"

    def test_tool_engine_does_not_import_or_use_authority_service(self):
        """ToolEngine's source must not reference AuthorityService — it is a
        pure advisory primitive, not a governance boundary."""
        import inspect

        src = inspect.getsource(ToolEngine)
        assert "AuthorityService" not in src
        assert "authority_service" not in src
        assert "assert_owner" not in src
        assert "require_owner" not in src

    def test_tool_executor_does_not_import_or_use_authority_service(self):
        """ToolExecutor's source must not reference AuthorityService — it is a
        low-level execution primitive that trusts its caller."""
        import inspect

        src = inspect.getsource(ToolExecutor)
        assert "AuthorityService" not in src
        assert "authority_service" not in src
        assert "assert_owner" not in src
        assert "require_owner" not in src


# ---------------------------------------------------------------------------
# Architecture invariant: privileged work enters through governed boundaries
# ---------------------------------------------------------------------------


class TestGovernanceInvariant:
    """Privileged development operations must enter through a governed
    boundary, not directly through ToolEngine/ToolExecutor."""

    def test_orchestration_is_the_canonical_governed_tool_path(self):
        """The only production path that combines multi-step execution with
        tool dispatch is OrchestrationExecutor, which authorizes per-step."""
        authority, ctx = _make_authority(owner=True)
        rec = _Recorder()
        tool_ex = _make_tool_executor(rec, "echo")
        ex = OrchestrationExecutor(authority_service=authority, tool_executor=tool_ex)

        result = ex.execute(
            ExecutionRequest(
                steps=(_step("n1", NodeKind.TOOL, "echo", inputs={"text": "hi"}),),
                session_context=ctx,
            )
        )

        # Governed path: authorized, then dispatched.
        assert result.status is ExecutionStatus.COMPLETED
        assert len(rec.calls) == 1

    def test_kernel_privileged_methods_require_session_context_authority(self):
        """P7.6 kernel development methods already validate SessionContext
        authority through _require_development_authority. This regression test
        confirms that boundary is intact and unaffected by M3."""
        from atlas.kernel.atlas import Atlas

        # A minimal kernel surface: the authority method requires a valid
        # session context and resolves identity through SessionManager.
        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        owner_session = manager.create_session("owner")
        owner_ctx = SessionContext.from_session(owner_session)

        # Build a minimal kernel with only authority/session wiring.
        kernel = Atlas.__new__(Atlas)
        kernel._authority_service = authority
        kernel._session_manager = manager

        # Owner passes the authority check (no exception).
        kernel._require_development_authority(owner_ctx, action="approval")

        # A USER session is denied.
        authority.add_user("Alice", principal_id="alice")
        user_session = manager.create_session("alice")
        user_ctx = SessionContext.from_session(user_session)
        with pytest.raises(RuntimeError, match="denied"):
            kernel._require_development_authority(user_ctx, action="approval")
