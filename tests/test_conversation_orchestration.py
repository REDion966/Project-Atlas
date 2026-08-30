"""P2/B2.3 — Conversation integration tests.

Real integration coverage for the additive ACTION/INFORMATION orchestration
bridge:

- ACTION → real registered capability/tool execution
- INFORMATION → real research execution (supported acquire() contract)
- unresolvable ACTION → clarification/refusal (never success)
- per-request USER SessionContext end-to-end through the kernel bridge
- Owner-required step denied for USER
- DEVELOPMENT_REQUEST isolation
- backward compatibility
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from atlas.ai.ai_manager import AIManager
from atlas.authority.models import AuthorityLevel
from atlas.authority.service import AuthorityService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.development_intake import task_spec_to_development_need
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.orchestration.execution_models import (
    ExecutionRequest,
    ExecutionStatus,
    ExecutionStep,
    OrchestrationResult,
    StepExecutionResult,
    ExecutionState,
)
from atlas.orchestration.executor import OrchestrationExecutor
from atlas.orchestration.models import NodeKind
from atlas.orchestration.reporting import orchestration_result_to_message
from atlas.orchestration.target_resolution import task_spec_to_execution_steps
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager
from atlas.tools.executor import ToolExecutor
from atlas.tools.models import Tool, ToolResult
from atlas.tools.registry import ToolRegistry


def _manager():
    manager = AIManager()
    manager.initialize(provider="Mock Provider", model="atlas-mock-v1", timeout=300)
    return manager


def _authority_and_session(user: str | None = None):
    authority = AuthorityService("Owner")
    manager = SessionManager(authority)
    if user:
        authority.add_user(user, principal_id=user)
        session = manager.create_session(user)
    else:
        session = manager.create_session("owner")
    return authority, SessionContext.from_session(session)


# ---------------------------------------------------------------------------
# Real seams
# ---------------------------------------------------------------------------


def _capability_executor(record: dict):
    registry = CapabilityRegistry()

    def handler(params):
        record["called"] = True
        record["params"] = params
        return ExecutionResult(capability="conversation", success=True, output={"done": True})

    registry.register("conversation", handler)
    return OrchestrationExecutor(
        capability_registry=registry,
        capability_dispatcher=CapabilityDispatcher(registry),
        authority_service=_authority_and_session()[0],
    )


def _tool_executor(record: dict, *names: str):
    registry = ToolRegistry()
    for name in names:
        def handler(params, _name=name):
            record["called"] = True
            record["params"] = params
            return ToolResult(tool_name=_name, success=True, output={"ran": _name})

        registry.register(Tool(name=name, description=f"{name} tool", category="utility", handler=handler))
    return ToolExecutor(registry)


# ---------------------------------------------------------------------------
# 1. Real INFORMATION → research execution
# ---------------------------------------------------------------------------


class TestInformationOrchestration:
    def test_information_request_maps_to_research_step(self):
        intake = TaskIntake()
        spec = intake.intake("Find the latest research on memory consolidation")
        assert spec.task_type is TaskType.INFORMATION_REQUEST
        steps = task_spec_to_execution_steps(spec)
        assert steps is not None
        assert len(steps) == 1
        assert steps[0].kind is NodeKind.RESEARCH
        assert steps[0].target == "acquire"
        # Only the supported question input; no unsupported 'slot' kwarg.
        assert "slot" not in steps[0].inputs
        assert "question" in steps[0].inputs

    def test_information_request_executes_through_real_research(self):
        from atlas.evolution.models import ResearchResult
        from atlas.research.acquisition import InformationAcquisitionService

        authority = AuthorityService("Owner")
        mgr = SessionManager(authority)
        ctx = SessionContext.from_session(mgr.create_session("owner"))

        class _Coordinator:
            def __init__(self):
                self.planner = None
                self.storage = None

            def run(self, query):
                return ResearchResult(query_id="q", findings="found", sources=[], confidence=0.8)

        service = InformationAcquisitionService(coordinator=_Coordinator())
        executor = OrchestrationExecutor(research_service=service, authority_service=authority)

        spec = TaskIntake().intake("Find the latest research on memory consolidation")
        steps = task_spec_to_execution_steps(spec)
        result = executor.execute(ExecutionRequest(steps=tuple(steps), session_context=ctx))

        assert result.status is ExecutionStatus.COMPLETED
        assert result.steps[0].state is ExecutionState.COMPLETED
        # The research result flowed through without the unsupported slot kwarg.
        assert result.steps[0].error == ""

    def test_research_reporting_truthful(self):
        from atlas.evolution.models import ResearchResult
        from atlas.research.acquisition import InformationAcquisitionService

        authority = AuthorityService("Owner")
        ctx = SessionContext.from_session(SessionManager(authority).create_session("owner"))

        class _Coordinator:
            def __init__(self):
                self.planner = None
                self.storage = None

            def run(self, query):
                return ResearchResult(query_id="q", findings="found", sources=[], confidence=0.8)

        executor = OrchestrationExecutor(
            research_service=InformationAcquisitionService(coordinator=_Coordinator()),
            authority_service=authority,
        )
        spec = TaskIntake().intake("Find the latest research on memory consolidation")
        steps = task_spec_to_execution_steps(spec)
        result = executor.execute(ExecutionRequest(steps=tuple(steps), session_context=ctx))
        msg = orchestration_result_to_message(result, intent=spec.intent)
        assert msg.role == "assistant"
        assert msg.metadata["orchestration"]["status"] == "completed"


# ---------------------------------------------------------------------------
# 2. Real ACTION → registered tool execution
# ---------------------------------------------------------------------------


class TestActionOrchestration:
    def test_action_request_maps_to_registered_tool(self):
        intake = TaskIntake()
        spec = intake.intake("Run echo")
        # 'echo' is registered; the bounded goal names it. (Single cue keeps
        # TaskIntake's objective extraction deterministic.)
        steps = task_spec_to_execution_steps(spec, tool_targets={"echo"})
        assert steps is not None
        assert steps[0].kind is NodeKind.TOOL
        assert steps[0].target == "echo"

    def test_action_request_executes_registered_tool(self):
        authority = AuthorityService("Owner")
        ctx = SessionContext.from_session(SessionManager(authority).create_session("owner"))
        record = {}
        executor = OrchestrationExecutor(
            tool_executor=_tool_executor(record, "echo"),
            authority_service=authority,
        )
        spec = TaskIntake().intake("Run echo")
        steps = task_spec_to_execution_steps(spec, tool_targets={"echo"})
        result = executor.execute(ExecutionRequest(steps=tuple(steps), session_context=ctx))
        assert result.status is ExecutionStatus.COMPLETED
        assert record.get("called") is True

    def test_unresolvable_action_refuses_not_success(self):
        intake = TaskIntake()
        spec = intake.intake("Create a report so that I can review progress, using local data")
        assert spec.task_type is TaskType.ACTION_REQUEST
        # No registered tool named in the bounded intent → refuse (None).
        steps = task_spec_to_execution_steps(spec, tool_targets={"echo"})
        assert steps is None

    def test_action_not_fabricated_as_conversation_placeholder(self):
        # A generic action with no matching tool must NOT fall back to the
        # 'conversation' placeholder capability.
        spec = TaskIntake().intake("Create a report so that I can review progress, using local data")
        steps = task_spec_to_execution_steps(spec, tool_targets={"echo"})
        assert steps is None


# ---------------------------------------------------------------------------
# 3. Session / authority end-to-end
# ---------------------------------------------------------------------------


class TestSessionAuthorityEndToEnd:
    def test_user_session_remains_user_through_kernel_bridge(self):
        # Exercise the real kernel bridge with a per-request USER session.
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            authority = atlas.authority_service
            authority.add_user("Alice", principal_id="alice")
            ctx = atlas.start_user_session("alice")

            spec = TaskIntake().intake("Run the echo tool")
            msg = atlas._orchestration_bridge(spec, session_context=ctx)

            # The message carries the deterministic result with the USER
            # principal preserved (never escalated to owner).
            assert msg.metadata["orchestration"]["principal_id"] == "alice"
            assert msg.metadata["orchestration"]["authority"] == "user"
        finally:
            atlas.shutdown()

    def test_owner_required_step_denied_for_user(self):
        authority = AuthorityService("Owner")
        mgr = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        ctx = SessionContext.from_session(mgr.create_session("alice"))

        record = {}
        executor = OrchestrationExecutor(
            tool_executor=_tool_executor(record, "echo"),
            authority_service=authority,
        )
        step = ExecutionStep(step_id="n1", kind=NodeKind.TOOL, target="echo", inputs={})
        result = executor.execute(
            ExecutionRequest(
                steps=(step,),
                session_context=ctx,
                required_authority=AuthorityLevel.OWNER,
            )
        )
        assert result.status is ExecutionStatus.REJECTED
        assert result.steps[0].failure_kind == "authorization_failed"
        assert record.get("called") is not True

    def test_missing_session_fails_closed(self):
        authority = AuthorityService("Owner")
        record = {}
        executor = OrchestrationExecutor(
            tool_executor=_tool_executor(record, "echo"),
            authority_service=authority,
        )
        step = ExecutionStep(step_id="n1", kind=NodeKind.TOOL, target="echo", inputs={})
        result = executor.execute(ExecutionRequest(steps=(step,), session_context=None))
        assert result.status is ExecutionStatus.REJECTED
        assert record.get("called") is not True


# ---------------------------------------------------------------------------
# 4. DEVELOPMENT isolation
# ---------------------------------------------------------------------------


class TestDevelopmentIsolation:
    def test_development_not_routed_to_orchestration(self):
        manager = _manager()
        authority = AuthorityService("Owner")
        ctx = SessionContext.from_session(SessionManager(authority).create_session("owner"))

        hit = {}

        def resolver(spec, session_context):
            hit["type"] = spec.task_type.value
            return "wrong"

        service = ConversationService(
            manager.service,
            task_intake=TaskIntake(),
            development_bridge=lambda spec: "DEVELOPMENT_BRIDGE",
            orchestration_resolver=resolver,
            session_context=ctx,
        )
        resp = service.send("add a new capability to Atlas for scheduling")
        assert resp.content == "DEVELOPMENT_BRIDGE"
        assert "type" not in hit

    def test_development_intake_preserved(self):
        spec = TaskIntake().intake("add a new capability to Atlas for scheduling")
        need = task_spec_to_development_need(spec)
        assert need is not None
        assert need.title


# ---------------------------------------------------------------------------
# 5. Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_conversation_service_without_orchestration(self):
        manager = _manager()
        authority = AuthorityService("Owner")
        ctx = SessionContext.from_session(SessionManager(authority).create_session("owner"))
        service = ConversationService(manager.service, task_intake=TaskIntake(), session_context=ctx)
        resp = service.send("Hello Atlas")
        assert resp.role == "assistant"
        assert resp.content

    def test_task_spec_to_execution_steps_refuses_non_routable(self):
        assert task_spec_to_execution_steps(TaskIntake().intake("Hello Atlas")) is None
        assert task_spec_to_execution_steps(TaskIntake().intake("add a new capability to Atlas")) is None
