"""Phase 5.6 — Capability requirements: evidence contract.

Investigation result: capability requirements are already represented and
enforced at the existing boundaries, so no new requirement model was introduced.

* Required inputs — capability handlers validate their inputs and fail closed
  (e.g. ``research.query`` requires a non-empty ``question``).
* Required parameters — ``ToolParameter.required``.
* Required session — ``OrchestrationExecutor`` rejects a run with no session.
* Required authority — per-step authority; escalation is refused.
* Required clarification — ``TaskSpec.needs_clarification`` blocks execution.
"""

from __future__ import annotations

from atlas.authority.models import AuthorityLevel
from atlas.authority.service import AuthorityService
from atlas.conversation.task_intake import TaskIntake
from atlas.orchestration.execution_models import (
    ExecutionRequest,
    ExecutionStatus,
    ExecutionStep,
)
from atlas.orchestration.executor import OrchestrationExecutor
from atlas.orchestration.models import NodeKind
from atlas.orchestration.target_resolution import task_spec_to_execution_steps
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.research.capability_handlers import ResearchCapabilityFactory
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager
from atlas.tools.models import ToolParameter


def _authority_ctx(user=None):
    authority = AuthorityService("Owner")
    manager = SessionManager(authority)
    if user:
        authority.add_user(user, principal_id=user)
        session = manager.create_session(user)
    else:
        session = manager.create_session("owner")
    return authority, SessionContext.from_session(session)


class TestPhase56CapabilityRequirements:
    def test_required_handler_input_is_enforced(self):
        registry = CapabilityRegistry()
        ResearchCapabilityFactory().register(registry)  # research.query/verify/summarize

        # Dispatch with no inputs → the handler must fail closed on its requirement.
        results = CapabilityDispatcher(registry).dispatch(
            [Capability(name="research.query")]
        )
        assert results[0].success is False
        assert "required" in results[0].error

    def test_tool_parameter_required_is_represented(self):
        assert ToolParameter(name="text", required=True).required is True
        assert ToolParameter(name="text").required is False

    def test_missing_session_requirement_fails_closed(self):
        registry = CapabilityRegistry()
        registry.register(
            "conversation",
            lambda params: ExecutionResult(capability="conversation", success=True),
        )
        result = OrchestrationExecutor(
            capability_registry=registry,
            capability_dispatcher=CapabilityDispatcher(registry),
        ).execute(
            ExecutionRequest(
                steps=(
                    ExecutionStep(
                        step_id="s1", kind=NodeKind.CAPABILITY, target="conversation"
                    ),
                ),
                session_context=None,
            )
        )
        assert result.status is ExecutionStatus.REJECTED

    def test_authority_requirement_is_enforced(self):
        authority, ctx = _authority_ctx(user="alice")
        registry = CapabilityRegistry()
        registry.register(
            "conversation",
            lambda params: ExecutionResult(capability="conversation", success=True),
        )
        result = OrchestrationExecutor(
            capability_registry=registry,
            capability_dispatcher=CapabilityDispatcher(registry),
            authority_service=authority,
        ).execute(
            ExecutionRequest(
                steps=(
                    ExecutionStep(
                        step_id="s1", kind=NodeKind.CAPABILITY, target="conversation"
                    ),
                ),
                session_context=ctx,
                required_authority=AuthorityLevel.OWNER,
            )
        )
        assert result.steps[0].allowed is False
        assert result.status is not ExecutionStatus.COMPLETED

    def test_clarification_requirement_blocks_execution(self):
        spec = TaskIntake().intake("improve this module")
        assert spec.needs_clarification is True
        assert task_spec_to_execution_steps(spec) is None
