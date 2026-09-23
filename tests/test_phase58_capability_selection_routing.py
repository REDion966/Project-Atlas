"""Phase 5.8 — Capability selection/routing: evidence contract.

Investigation result: Atlas already has ONE coherent selection/routing chain, so
no new router/planner was introduced.

    reasoning (CapabilityAnalyzer) → CapabilityRouter → CapabilityDispatcher
      → OrchestrationExecutor (governed action boundary)

Unavailable capabilities are excluded; dependencies and governance are enforced.
"""

from __future__ import annotations

from atlas.authority.service import AuthorityService
from atlas.orchestration.execution_models import (
    ExecutionRequest,
    ExecutionState,
    ExecutionStatus,
    ExecutionStep,
)
from atlas.orchestration.executor import OrchestrationExecutor
from atlas.orchestration.models import NodeKind
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.models import ReasoningPlan, ReasoningStep
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager


def _authority_ctx():
    authority = AuthorityService("Owner")
    manager = SessionManager(authority)
    return authority, SessionContext.from_session(manager.create_session("owner"))


def _registry(*names):
    registry = CapabilityRegistry()
    for name in names:
        registry.register(
            name,
            lambda params, _n=name: ExecutionResult(
                capability=_n, success=True, output={"done": _n}
            ),
        )
    return registry


def _step(step_id, target, depends_on=()):
    return ExecutionStep(
        step_id=step_id, kind=NodeKind.CAPABILITY, target=target, depends_on=tuple(depends_on)
    )


class TestPhase58CapabilitySelectionRouting:
    def test_reasoning_to_governed_execution_chain(self):
        registry = _registry("conversation")
        capabilities = CapabilityAnalyzer().analyze(
            ReasoningPlan(goal="respond", steps=[ReasoningStep(action="respond")])
        )
        routes = CapabilityRouter(registry).route(capabilities)
        assert [r.capability for r in routes] == ["conversation"]

        authority, ctx = _authority_ctx()
        result = OrchestrationExecutor(
            capability_registry=registry,
            capability_dispatcher=CapabilityDispatcher(registry),
            authority_service=authority,
        ).execute(
            ExecutionRequest(
                steps=(_step("s1", "conversation"),), session_context=ctx
            )
        )
        assert result.status is ExecutionStatus.COMPLETED
        assert result.steps[0].state is ExecutionState.COMPLETED

    def test_unavailable_capability_is_refused(self):
        capabilities = [Capability(name="knowledge_retrieval")]
        assert CapabilityRouter(_registry("conversation")).route(capabilities) == []
        assert (
            CapabilityDispatcher(CapabilityRegistry()).dispatch(capabilities)[0].success
            is False
        )

    def test_unsupported_request_selects_nothing_routable(self):
        capabilities = CapabilityAnalyzer().analyze(
            ReasoningPlan(goal="g", steps=[ReasoningStep(action="unknown_action")])
        )
        assert [c.name for c in capabilities] == ["general"]
        assert CapabilityRouter(_registry("conversation")).route(capabilities) == []

    def test_governance_restriction_is_preserved(self):
        registry = _registry("conversation")
        authority, ctx = _authority_ctx()
        result = OrchestrationExecutor(
            capability_registry=registry,
            capability_dispatcher=CapabilityDispatcher(registry),
            authority_service=authority,
        ).execute(
            ExecutionRequest(
                steps=(_step("s1", "evolution.gateway"),), session_context=ctx
            )
        )
        assert result.steps[0].state is ExecutionState.FAILED
        assert result.steps[0].failure_kind == "denied_surface"
