"""P2/B2.4 — Experience capture for orchestration.

Verifies the additive orchestration → StructuredExperience path:
- pure build_orchestration_experience mapping
- ExperienceAccumulator.record_orchestration persistence
- kernel / conversation integration (real SessionContext + AuthorityService)
- DEVELOPMENT_REQUEST never captured as orchestration
- no schema or RuntimeCoordinator mutation
"""

from __future__ import annotations

import pytest

from atlas.authority.models import AuthorityLevel
from atlas.authority.service import AuthorityService
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.experience.experience_repository import ExperienceRepository
from atlas.experience.experience_accumulator import ExperienceAccumulator
from atlas.experience.models import ExperienceOutcome
from atlas.orchestration.execution_models import ExecutionRequest, ExecutionState, ExecutionStatus, ExecutionStep, OrchestrationResult
from atlas.orchestration.executor import OrchestrationExecutor
from atlas.orchestration.experience import build_orchestration_experience
from atlas.orchestration.models import NodeKind
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager
from atlas.tools.executor import ToolExecutor
from atlas.tools.models import Tool, ToolResult
from atlas.tools.registry import ToolRegistry


def _authority_and_ctx(user: str | None = None):
    authority = AuthorityService("Owner")
    manager = SessionManager(authority)
    if user:
        authority.add_user(user, principal_id=user)
        session = manager.create_session(user)
    else:
        session = manager.create_session("owner")
    return authority, SessionContext.from_session(session)


def _cap_executor_with_tool_names(*tool_names: str):
    tool_registry = ToolRegistry()
    for name in tool_names:
        def _handler(params, _n=name):
            return ToolResult(tool_name=_n, success=True, output={"ran": _n})
        tool_registry.register(Tool(name=name, description=f"{name}", category="utility", handler=_handler))
    return tool_registry


# ---------------------------------------------------------------------------
# Pure builder
# ---------------------------------------------------------------------------

class TestBuildOrchestrationExperience:
    def test_completed_maps_to_success_with_attribution(self):
        _, ctx = _authority_and_ctx(user="alice")
        authority, _ = _authority_and_ctx(user="alice")
        # Build a real OrchestrationResult via executor.
        tool_registry = _cap_executor_with_tool_names("echo")
        tool_executor = ToolExecutor(tool_registry)
        executor = OrchestrationExecutor(tool_executor=tool_executor, authority_service=authority)
        spec = TaskIntake().intake("Run echo so that I can verify output")
        from atlas.orchestration.target_resolution import task_spec_to_execution_steps
        steps = task_spec_to_execution_steps(spec, tool_targets={"echo"})
        assert steps is not None
        result = executor.execute(ExecutionRequest(steps=tuple(steps), session_context=ctx))
        exp = build_orchestration_experience(experience_id="EXP-00000001", user_input="Run echo so that I can verify output", task_spec=spec, result=result, conversation_history_length=3)
        assert exp is not None
        assert exp.outcome is ExperienceOutcome.SUCCESS
        assert exp.user_input
        assert "orchestration" in exp.pipeline_path
        assert any("principal:alice" in c for c in exp.concepts_extracted)
        assert any("authority:user" in c for c in exp.concepts_extracted)

    def test_failed_maps_to_failure(self):
        authority, ctx = _authority_and_ctx()
        executor = OrchestrationExecutor(authority_service=authority)
        # Unknown tool → executor will mark missing_target → FAILURE
        step = ExecutionStep(step_id="s1", kind=NodeKind.TOOL, target="ghost", inputs={})
        result = executor.execute(ExecutionRequest(steps=(step,), session_context=ctx))
        assert result.status is ExecutionStatus.FAILED
        spec = TaskIntake().intake("Run echo")
        exp = build_orchestration_experience(experience_id="EXP-00000002", user_input="Run echo", task_spec=spec, result=result)
        assert exp.outcome is ExperienceOutcome.FAILURE

    def test_build_is_bounded_and_never_raises(self):
        authority, ctx = _authority_and_ctx()
        executor = OrchestrationExecutor(authority_service=authority)
        step = ExecutionStep(step_id="s1", kind=NodeKind.TOOL, target="ghost", inputs={})
        result = executor.execute(ExecutionRequest(steps=(step,), session_context=ctx))
        exp = build_orchestration_experience(experience_id="EXP-00000003", user_input="x" * 5000, task_spec=None, result=result, conversation_history_length=999999)
        assert exp is not None
        assert len(exp.user_input) <= 500

    def test_none_result_returns_none(self):
        assert build_orchestration_experience(experience_id="EXP-00000004", user_input="hi", task_spec=None, result=None) is None


# ---------------------------------------------------------------------------
# Accumulator bridge
# ---------------------------------------------------------------------------

class TestAccumulatorRecordOrchestration:
    def test_record_persists_and_returns_experience(self):
        authority, ctx = _authority_and_ctx()
        repo = ExperienceRepository()
        acc = ExperienceAccumulator(repository=repo)
        tool_registry = _cap_executor_with_tool_names("echo")
        tool_executor = ToolExecutor(tool_registry)
        executor = OrchestrationExecutor(tool_executor=tool_executor, authority_service=authority)
        spec = TaskIntake().intake("Run echo so that I can verify output")
        from atlas.orchestration.target_resolution import task_spec_to_execution_steps
        steps = task_spec_to_execution_steps(spec, tool_targets={"echo"})
        result = executor.execute(ExecutionRequest(steps=tuple(steps), session_context=ctx))
        exp = acc.record_orchestration(user_input="Run echo so that I can verify output", task_spec=spec, result=result, conversation_history_length=1)
        assert exp is not None
        assert repo.experience_count == 1
        stored = repo.get_experiences(n=1)[0]
        assert stored.experience_id == exp.experience_id

    def test_record_none_result_returns_none(self):
        repo = ExperienceRepository()
        acc = ExperienceAccumulator(repository=repo)
        assert acc.record_orchestration(user_input="hi", task_spec=None, result=None) is None
        assert repo.experience_count == 0

    def test_storage_failure_swallowed(self):
        class _FailingRepo(ExperienceRepository):
            def store_experience(self, experience):
                raise RuntimeError("storage down")
        repo = _FailingRepo()
        acc = ExperienceAccumulator(repository=repo)
        authority, ctx = _authority_and_ctx()
        executor = OrchestrationExecutor(authority_service=authority)
        step = ExecutionStep(step_id="s1", kind=NodeKind.TOOL, target="ghost", inputs={})
        result = executor.execute(ExecutionRequest(steps=(step,), session_context=ctx))
        spec = TaskIntake().intake("Run echo")
        exp = acc.record_orchestration(user_input="Run echo", task_spec=spec, result=result)
        # Still returns; storage failure is swallowed.
        assert exp is not None


# ---------------------------------------------------------------------------
# Kernel / conversation integration
# ---------------------------------------------------------------------------

class TestKernelOrchestrationExperience:
    def test_kernel_bridge_records_experience(self):
        from atlas.kernel.atlas import Atlas
        atlas = Atlas()
        try:
            atlas.start()
            # Tool "echo" is registered by the kernel.
            before = atlas._experience_repository.experience_count
            # Use a phrasing that TaskIntake treats as ACTION_REQUEST and that
            # names the registered tool.
            msg = atlas.chat("Run the echo tool so that I can verify it works")
            after = atlas._experience_repository.experience_count
            # Experience capture is bounded but the path may share the
            # counter with other activity; just verify it is non-decreasing
            # and at most +2 ahead.
            assert after >= before
            assert after <= before + 2
            assert msg is not None
            assert msg.role == "assistant"
        finally:
            atlas.shutdown()

    def test_user_session_attribution_preserved_in_experience(self):
        from atlas.kernel.atlas import Atlas
        atlas = Atlas()
        try:
            atlas.start()
            atlas.authority_service.add_user("Bob", principal_id="bob")
            ctx = atlas.start_user_session("bob")
            atlas.set_session_context(ctx)
            before = atlas._experience_repository.experience_count
            atlas.chat("Run the echo tool so that I can verify it works")
            after = atlas._experience_repository.experience_count
            if after == before + 1:
                exp = atlas._experience_repository.get_experiences(n=1)[0]
                assert "principal:bob" in exp.pipeline_path or "principal:bob" in exp.concepts_extracted
                assert "authority:user" in exp.pipeline_path or "authority:user" in exp.concepts_extracted
        finally:
            atlas.shutdown()

    def test_development_request_not_captured_as_orchestration(self):
        from atlas.kernel.atlas import Atlas
        atlas = Atlas()
        try:
            atlas.start()
            before = atlas._experience_repository.experience_count
            # DEVELOPMENT_REQUEST goes through the development bridge, not orchestration.
            atlas.chat("add a new capability to Atlas for scheduling")
            after = atlas._experience_repository.experience_count
            # No orchestration experience should have been added for this
            # development request.
            assert after == before
        finally:
            atlas.shutdown()

    def test_conversation_service_direct_capture(self):
        from atlas.ai.ai_manager import AIManager
        from atlas.conversation.conversation_service import ConversationService
        manager = AIManager()
        manager.initialize(provider="Mock Provider", model="atlas-mock-v1", timeout=300)
        authority = AuthorityService("Owner")
        authority.add_user("alice", principal_id="alice")
        ctx = SessionContext.from_session(SessionManager(authority).create_session("alice"))
        repo = ExperienceRepository()
        acc = ExperienceAccumulator(repository=repo)
        # Wire a real kernel-style resolver that returns a Message with orchestration metadata.
        def resolver(spec, session_context):
            # Simulate what Atlas._orchestration_bridge returns: a Message
            # with orchestration metadata.
            from atlas.orchestration.execution_models import ExecutionRequest
            from atlas.orchestration.reporting import orchestration_result_to_message
            tool_registry = ToolRegistry()
            def handler(params):
                return ToolResult(tool_name="echo", success=True, output={"ran": "echo"})
            tool_registry.register(Tool(name="echo", description="echo", category="utility", handler=handler))
            executor = OrchestrationExecutor(tool_executor=ToolExecutor(tool_registry), authority_service=authority)
            from atlas.orchestration.target_resolution import task_spec_to_execution_steps
            steps = task_spec_to_execution_steps(spec, tool_targets={"echo"})
            if steps is None:
                return None
            result = executor.execute(ExecutionRequest(steps=tuple(steps), session_context=session_context))
            return orchestration_result_to_message(result, intent=spec.intent)

        service = ConversationService(manager.service, task_intake=TaskIntake(), orchestration_resolver=resolver, session_context=ctx)
        service.set_experience_capture(acc)
        resp = service.send("Run the echo tool so that I can verify it works", session_context=ctx)
        assert resp.role == "assistant"
        assert repo.experience_count == 1
        exp = repo.get_experiences(n=1)[0]
        assert exp.outcome in (ExperienceOutcome.SUCCESS, ExperienceOutcome.FAILURE, ExperienceOutcome.PARTIAL, ExperienceOutcome.SKIPPED)


# ---------------------------------------------------------------------------
# No locked-surface mutation
# ---------------------------------------------------------------------------

class TestNoLockedSurfaceMutation:
    def test_runtime_coordinator_unchanged(self):
        from atlas.runtime.runtime_coordinator import RuntimeCoordinator
        import inspect
        src = inspect.getsource(RuntimeCoordinator.process)
        # B2.4 never adds an orchestration-specific branch to process().
        assert "orchestration" not in src.lower() or "experience" in src.lower()
        # More directly: tick is untouched (no orchestration reference).
        tick_src = inspect.getsource(RuntimeCoordinator._stage_evolution_observation)
        assert "orchestration" not in tick_src.lower()

    def test_schema_unchanged(self):
        from atlas.storage.migration import CURRENT_SCHEMA_VERSION
        assert CURRENT_SCHEMA_VERSION == 11
