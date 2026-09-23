"""Phase 4.9 — Reasoning → action integration: evidence contract.

Investigation result: Atlas already bridges a structured reasoning/plan result to
a governed action sequence through the existing orchestration layer, so no new
execution system was introduced.

* ``atlas/reasoning/capabilities/analyzer.py`` → required capabilities.
* ``atlas/orchestration/target_resolution.py`` → bounded ``ExecutionStep``s.
* ``atlas/orchestration/executor.py::OrchestrationExecutor`` — governed execution
  through existing capability/tool/research seams with SessionContext
  attribution, per-step authority, dependency ordering, and fail-closed guards.

The path is: capabilities → ExecutionStep → governance/authority → execution →
structured results with attribution.
"""

from __future__ import annotations

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
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.models import ReasoningPlan, ReasoningStep
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


class TestPhase49ReasoningAction:
    def test_reasoning_capabilities_become_governed_action_steps(self):
        registry, dispatcher = _cap_executor("conversation")
        capabilities = CapabilityAnalyzer().analyze(
            ReasoningPlan(goal="respond", steps=[ReasoningStep(action="respond")])
        )
        steps = tuple(
            ExecutionStep(
                step_id=f"step-{i:04d}", kind=NodeKind.CAPABILITY, target=c.name
            )
            for i, c in enumerate(capabilities)
        )

        authority, ctx = _make_authority()
        result = OrchestrationExecutor(
            capability_registry=registry,
            capability_dispatcher=dispatcher,
            authority_service=authority,
        ).execute(ExecutionRequest(steps=steps, session_context=ctx))

        assert result.status is ExecutionStatus.COMPLETED
        assert result.steps[0].state is ExecutionState.COMPLETED
        assert result.steps[0].allowed is True
        assert result.steps[0].principal_id  # attributed to the session principal
        assert result.completed_count == 1

    def test_research_shaped_information_request_maps_to_governed_research_step(self):
        spec = TaskIntake().intake("research the latest approaches to vector databases")
        steps = task_spec_to_execution_steps(spec)
        assert steps is not None
        assert steps[0].kind is NodeKind.RESEARCH
        assert steps[0].target == "acquire"
        assert "question" in steps[0].inputs

    def test_dependency_ordering_is_respected(self):
        registry, dispatcher = _cap_executor("a", "b")
        steps = (
            ExecutionStep(step_id="s1", kind=NodeKind.CAPABILITY, target="a"),
            ExecutionStep(
                step_id="s2", kind=NodeKind.CAPABILITY, target="b", depends_on=("s1",)
            ),
        )
        authority, ctx = _make_authority()
        result = OrchestrationExecutor(
            capability_registry=registry,
            capability_dispatcher=dispatcher,
            authority_service=authority,
        ).execute(ExecutionRequest(steps=steps, session_context=ctx))

        assert result.completed_count == 2
        assert [s.target for s in result.steps] == ["a", "b"]

    def test_non_actionable_request_produces_no_action(self):
        # A non-routable / underspecified request must not fabricate execution.
        assert task_spec_to_execution_steps(TaskIntake().intake("what does this module do?")) is None
