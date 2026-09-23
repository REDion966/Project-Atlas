"""Phase 4.5 — Constraint handling: evidence contract.

Investigation result: constraints already affect reasoning/plan/execution rather
than merely existing elsewhere, so no change was required.

* ``atlas/orchestration/target_resolution.py`` — underspecified/ambiguous specs
  and non-routable types produce no steps (no fabricated execution); constraints
  are carried as bounded step *inputs*, never as executable targets.
* ``atlas/orchestration/executor.py`` — denies governed surfaces
  (evolution./autonomy./governance./…), enforces per-step authority
  (fail-closed; escalation refused), and rejects runs with no session.
* ``atlas/reasoning/planning/engine.py::validate`` — structural plan constraints
  (empty actions, unknown/circular dependencies).
"""

from __future__ import annotations

from atlas.authority.models import AuthorityLevel
from atlas.authority.service import AuthorityService
from atlas.conversation.task_intake import TaskIntake
from atlas.orchestration.execution_models import (
    ExecutionRequest,
    ExecutionState,
    ExecutionStatus,
    ExecutionStep,
)
from atlas.orchestration.executor import OrchestrationExecutor
from atlas.orchestration.models import NodeKind
from atlas.orchestration.target_resolution import task_spec_to_execution_steps
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager


def _make_authority(user=None):
    authority = AuthorityService("Owner")
    manager = SessionManager(authority)
    if user:
        authority.add_user(user, principal_id=user)
        session = manager.create_session(user)
    else:
        session = manager.create_session("owner")
    return authority, SessionContext.from_session(session)


def _executor(authority=None, registry=None, dispatcher=None):
    return OrchestrationExecutor(
        capability_registry=registry,
        capability_dispatcher=dispatcher,
        authority_service=authority,
    )


def _step(step_id, kind, target, inputs=None, depends_on=()):
    return ExecutionStep(
        step_id=step_id,
        kind=kind,
        target=target,
        inputs=inputs or {},
        depends_on=tuple(depends_on),
    )


def _cap_executor(*names):
    registry = CapabilityRegistry()
    for name in names:
        registry.register(
            name,
            lambda params, _n=name: ExecutionResult(
                capability=_n, success=True, output={"done": _n}
            ),
        )
    return registry, CapabilityDispatcher(registry)


class TestPhase45ConstraintHandling:
    def test_underspecified_request_produces_no_execution_steps(self):
        spec = TaskIntake().intake("improve this module")
        assert task_spec_to_execution_steps(spec) is None

    def test_governed_surface_target_is_denied(self):
        authority, ctx = _make_authority()
        registry, dispatcher = _cap_executor("conversation")
        result = _executor(authority, registry, dispatcher).execute(
            ExecutionRequest(
                steps=(_step("n1", NodeKind.CAPABILITY, "evolution.gateway"),),
                session_context=ctx,
            )
        )
        assert result.steps[0].state is ExecutionState.FAILED
        assert result.steps[0].failure_kind == "denied_surface"

    def test_missing_session_fails_closed(self):
        registry, dispatcher = _cap_executor("conversation")
        result = _executor(None, registry, dispatcher).execute(
            ExecutionRequest(
                steps=(_step("n1", NodeKind.CAPABILITY, "conversation"),),
                session_context=None,
            )
        )
        assert result.status is ExecutionStatus.REJECTED

    def test_authority_escalation_is_refused(self):
        authority, ctx = _make_authority(user="alice")
        registry, dispatcher = _cap_executor("conversation")
        result = _executor(authority, registry, dispatcher).execute(
            ExecutionRequest(
                steps=(_step("n1", NodeKind.CAPABILITY, "conversation"),),
                session_context=ctx,
                required_authority=AuthorityLevel.OWNER,
            )
        )
        assert result.status is not ExecutionStatus.COMPLETED
        assert result.steps[0].allowed is False
