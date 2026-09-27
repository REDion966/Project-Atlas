"""Step 2 — Goal-Centered Orchestration (first vertical slice).

Proves the two-stage conversational goal:
plan -> execute step 1 -> carry its bounded result -> execute step 2 ->
coherent result -> bounded state.

The slice reuses EXISTING machinery only: the bounded SemanticFrame
decomposition composes the plan; the EXISTING OrchestrationExecutor sequences
and attributes it; the EXISTING investigation + synthesis capabilities do the
work. Nothing here grants authority or fabricates downstream evidence.
"""

from __future__ import annotations

from atlas.authority.service import AuthorityService
from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import (
    InvestigationFinding,
    InvestigationReport,
    InvestigationService,
)
from atlas.conversation.investigation_synthesis import InvestigationSynthesizer
from atlas.conversation.message import Message
from atlas.conversation.task_intake import TaskIntake
from atlas.orchestration.execution_models import ExecutionRequest, ExecutionStatus
from atlas.orchestration.executor import OrchestrationExecutor
from atlas.orchestration.goal_plan import build_goal_plan
from atlas.orchestration.models import NodeKind
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager

SLICE = "Investigate the conversation state handling and then explain what we should do next."
TARGET = "investigate conversation state handle"


class _FailingAI:
    calls = 0

    def chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1
        raise RuntimeError("provider must not be contacted")

    def stream_chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1

        def _gen():
            raise RuntimeError("provider must not be contacted")
            yield ""  # pragma: no cover

        return _gen()


def _owner_session() -> SessionContext:
    manager = SessionManager(AuthorityService("Owner"))
    return SessionContext.from_session(manager.create_session("owner"))


def _report(target: str = TARGET, *, empty: bool = False) -> InvestigationReport:
    if empty:
        return InvestigationReport(target=target, modification_status="NONE")
    return InvestigationReport(
        target=target,
        objective="",
        diagnosis="Identified 1 relevant component(s).",
        components=("atlas.conversation.conversation_state",),
        findings=(
            InvestigationFinding(
                category="reference",
                description="Found 3 reference(s) to 'state' in atlas/conversation/",
                evidence="atlas/conversation/conversation_state.py",
                location="atlas/conversation/",
            ),
            InvestigationFinding(
                category="dependency",
                description="'atlas.conversation.conversation_state' depends on: atlas.conversation.entity_capture",
                location="atlas.conversation.conversation_state",
            ),
        ),
        affected_files=("atlas/conversation/conversation_state.py",),
        recommended_next_step="Review the identified components.",
        modification_status="NONE",
    )


class _RecordingInvestigation:
    def __init__(self, report: InvestigationReport) -> None:
        self._report = report
        self.calls: list[tuple[str, str]] = []

    def investigate(self, target: str, *, objective: str = "") -> InvestigationReport:
        self.calls.append((target, objective))
        return self._report


class _RecordingSynthesizer:
    def __init__(self) -> None:
        self.seen: list[InvestigationReport] = []
        self._inner = InvestigationSynthesizer()

    def synthesize(self, report: InvestigationReport):
        self.seen.append(report)
        return self._inner.synthesize(report)


def _executor(*, investigation=None, synthesizer=None) -> OrchestrationExecutor:
    return OrchestrationExecutor(
        authority_service=AuthorityService("Owner"),
        investigation_service=investigation,
        investigation_synthesizer=synthesizer,
    )


def _run(steps, executor):
    return executor.execute(
        ExecutionRequest(steps=tuple(steps), session_context=_owner_session(), max_steps=4)
    )


# ---------------------------------------------------------------------------
# 1. Two-step plan creation (existing decomposition only)
# ---------------------------------------------------------------------------


class TestPlanComposition:
    def test_two_step_plan_created(self):
        plan = build_goal_plan(SLICE)
        assert plan is not None and len(plan) == 2
        investigation, analysis = plan
        assert investigation.kind is NodeKind.INVESTIGATION
        assert analysis.kind is NodeKind.ANALYSIS
        assert analysis.depends_on == (investigation.step_id,)
        assert analysis.carry_from == (investigation.step_id,)

    def test_deterministic(self):
        assert build_goal_plan(SLICE) == build_goal_plan(SLICE)

    def test_non_slice_shapes_are_not_planned(self):
        for text in (
            "Hello Atlas.",
            "Investigate the memory architecture.",
            "Research vector databases and then compare them with Atlas storage.",
            "",
            "...",
        ):
            assert build_goal_plan(text) is None, text


# ---------------------------------------------------------------------------
# 2/3. Ordering + explicit result carry
# ---------------------------------------------------------------------------


class TestExecutionOrderingAndCarry:
    def test_two_steps_execute_in_order(self):
        investigation = _RecordingInvestigation(_report())
        synthesizer = _RecordingSynthesizer()
        result = _run(build_goal_plan(SLICE), _executor(
            investigation=investigation, synthesizer=synthesizer))

        assert result.status is ExecutionStatus.COMPLETED
        assert [s.kind for s in result.steps] == [NodeKind.INVESTIGATION, NodeKind.ANALYSIS]
        assert all(s.completed for s in result.steps)
        assert investigation.calls and synthesizer.seen

    def test_step_one_result_is_carried_into_step_two(self):
        investigation = _RecordingInvestigation(_report())
        synthesizer = _RecordingSynthesizer()
        _run(build_goal_plan(SLICE), _executor(
            investigation=investigation, synthesizer=synthesizer))

        # Step 2 consumed the ACTUAL step-1 report (carried, bounded, data-only).
        carried = synthesizer.seen[0]
        assert carried.target == TARGET
        assert carried.components == ("atlas.conversation.conversation_state",)
        assert len(carried.findings) == 2

    def test_step_two_output_is_synthesised_from_carried_evidence(self):
        synt = _RecordingSynthesizer()
        result = _run(build_goal_plan(SLICE), _executor(
            investigation=_RecordingInvestigation(_report()), synthesizer=synt))
        analysis = result.steps[1]
        assert analysis.output.get("target") == TARGET
        assert analysis.output.get("recommended_focus")


# ---------------------------------------------------------------------------
# 4. Failure / partial behavior (no fabricated downstream evidence)
# ---------------------------------------------------------------------------


class TestFailureIsolation:
    def test_failed_step_one_blocks_step_two(self):
        investigation = _RecordingInvestigation(_report(empty=True))
        synthesizer = _RecordingSynthesizer()
        result = _run(build_goal_plan(SLICE), _executor(
            investigation=investigation, synthesizer=synthesizer))

        assert result.status is not ExecutionStatus.COMPLETED
        assert result.steps[0].failed
        assert not result.steps[1].completed
        # Step 2 never ran, so no downstream evidence was fabricated.
        assert synthesizer.seen == []

    def test_unwired_capability_fails_closed(self):
        result = _run(build_goal_plan(SLICE), _executor())  # nothing wired
        assert result.status is not ExecutionStatus.COMPLETED
        assert all(not s.completed for s in result.steps)

    def test_carry_of_a_non_completed_step_is_refused(self):
        # Bypass depends_on so the carry (not the dependency gate) is exercised.
        plan = build_goal_plan(SLICE)
        investigation, analysis = plan
        orphan = type(analysis)(
            step_id=analysis.step_id,
            kind=analysis.kind,
            target=analysis.target,
            inputs={},
            depends_on=(),
            carry_from=(investigation.step_id,),
            description=analysis.description,
        )
        synthesizer = _RecordingSynthesizer()
        result = _run([investigation, orphan], _executor(
            investigation=_RecordingInvestigation(_report(empty=True)),
            synthesizer=synthesizer))
        assert synthesizer.seen == []


# ---------------------------------------------------------------------------
# 5/6. Bounded state + governance preservation
# ---------------------------------------------------------------------------


class _GoalBridge:
    """Duck-typed bridge (mirrors the kernel's) that runs the real executor."""

    def __init__(self, executor) -> None:
        self._executor = executor

    def __call__(self, text, steps, session_context=None):
        from atlas.orchestration.reporting import orchestration_result_to_message

        result = self._executor.execute(
            ExecutionRequest(steps=tuple(steps), session_context=_owner_session(), max_steps=4)
        )
        return orchestration_result_to_message(result, intent=text)


def _service(executor) -> ConversationService:
    _FailingAI.calls = 0
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        investigation_service=InvestigationService(),
        goal_orchestration_resolver=_GoalBridge(executor),
    )


class TestConversationStateAndGovernance:
    def _service_with_slice(self, *, empty: bool = False) -> ConversationService:
        return _service(_executor(
            investigation=_RecordingInvestigation(_report(empty=empty)),
            synthesizer=_RecordingSynthesizer(),
        ))

    def test_plan_is_retained_in_bounded_state(self):
        service = self._service_with_slice()
        message = service.send(SLICE)

        assert "Steps completed: 2/2" in message.content
        plan = service.state_manager.state.current_plan
        assert isinstance(plan, dict)
        assert plan["state"] == "completed"
        assert [s["kind"] for s in plan["steps"]] == ["investigation", "analysis"]
        assert plan["steps"][1]["carry_from"] == ["step-0000"]
        # Bounded + JSON-safe (round-trips through the state contract).
        import json

        json.dumps(service.state_manager.state.to_dict())

    def test_status_followup_reads_the_retained_plan(self):
        service = self._service_with_slice()
        service.send(SLICE)
        followup = service.send("plan status")
        assert "Active goal" in followup.content
        assert "step-0000" in followup.content
        assert (followup.metadata or {}).get("goal_plan")

    def test_no_governance_authority_is_created(self):
        service = self._service_with_slice()
        before = service.state_manager.state
        message = service.send(SLICE)
        for key in ("approval", "execution", "promotion", "authorization"):
            assert key not in message.metadata, key
        after = service.state_manager.state
        assert after.pending_approval_id is None
        assert after.evolution_proposal_id is None
        assert after.last_operation == before.last_operation
        assert message.metadata.get("model_used") is not True
        assert _FailingAI.calls == 0

    def test_governed_clause_is_never_planned(self):
        # A governance-sensitive clause stays on its OWNER route (not planned).
        plan = build_goal_plan(
            "Investigate the memory architecture and then approve this proposal."
        )
        assert plan is None

    def test_single_step_behavior_is_intact(self):
        service = self._service_with_slice()
        # A single-clause investigation is NOT claimed by the goal route.
        assert service._maybe_handle_goal_request("Investigate the memory architecture.") is None
        # No active plan -> the status form keeps its existing route.
        assert service._maybe_handle_goal_followup("plan status") is None
