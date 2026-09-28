"""Step 2 — plan resumption (smallest real continuation capability).

Closes the gap between "retain a plan and report its status" and genuinely
CONTINUING an unfinished goal across a later turn:

    goal -> plan -> first step completed -> second step not run
         -> later bounded continuation turn -> remaining step resumed
         -> coherent final result

Reuses ONLY existing machinery: ``ConversationState.current_plan`` as the sole
plan state, the existing ``ExecutionStep.carry_from`` carry, the existing
``OrchestrationExecutor``, and the existing bounded continuation semantics
(``TurnRole.CONTINUATION``). Completed steps are SEEDED, never re-executed, so
their bounded result is reused and no work is repeated.
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
from atlas.conversation.task_intake import TaskIntake
from atlas.orchestration.execution_models import (
    ExecutionRequest,
    ExecutionState,
    ExecutionStatus,
)
from atlas.orchestration.executor import OrchestrationExecutor
from atlas.orchestration.goal_plan import build_goal_plan, resume_execution_request
from atlas.orchestration.models import NodeKind
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager

SLICE = "Investigate the conversation state handling and then explain what we should do next."


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


class _RecordingInvestigation:
    """Counts how many times the (read-only) investigation step actually runs."""

    def __init__(self) -> None:
        self.calls = 0

    def investigate(self, target: str, *, objective: str = "") -> InvestigationReport:
        self.calls += 1
        return InvestigationReport(
            target=target,
            objective=objective,
            diagnosis="Identified 1 relevant component(s).",
            components=("atlas.conversation.conversation_state",),
            findings=(
                InvestigationFinding(
                    category="reference",
                    description="Found 3 reference(s) to 'state' in atlas/conversation/",
                    evidence="atlas/conversation/conversation_state.py",
                    location="atlas/conversation/",
                ),
            ),
            modification_status="NONE",
        )


def _executor(investigation) -> OrchestrationExecutor:
    return OrchestrationExecutor(
        authority_service=AuthorityService("Owner"),
        investigation_service=investigation,
        investigation_synthesizer=InvestigationSynthesizer(),
    )


class _Bridge:
    """Mirrors the kernel bridges: the first run is bounded, the resume is full."""

    def __init__(self, executor, *, initial_max_steps: int = 1) -> None:
        self._executor = executor
        self._initial = initial_max_steps

    def request(self, text, steps, session_context=None):
        from atlas.orchestration.reporting import orchestration_result_to_message

        result = self._executor.execute(
            ExecutionRequest(
                steps=tuple(steps), session_context=_owner_session(),
                max_steps=self._initial,
            )
        )
        return orchestration_result_to_message(result, intent=text)

    def resume(self, plan_state, session_context=None):
        from atlas.orchestration.reporting import orchestration_result_to_message

        request = resume_execution_request(plan_state, _owner_session())
        if request is None:
            return None
        result = self._executor.execute(request)
        return orchestration_result_to_message(
            result, intent=str(plan_state.get("objective") or "")
        )


def _service(investigation, *, initial_max_steps: int = 1) -> ConversationService:
    _FailingAI.calls = 0
    bridge = _Bridge(_executor(investigation), initial_max_steps=initial_max_steps)
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        investigation_service=InvestigationService(),
        goal_orchestration_resolver=bridge.request,
        goal_resume_resolver=bridge.resume,
    )


# ---------------------------------------------------------------------------
# 1/2/3. Incomplete plan retention + resume request construction
# ---------------------------------------------------------------------------


class TestPlanRetentionAndRequest:
    def test_partial_plan_is_retained_with_inputs_and_outputs(self):
        investigation = _RecordingInvestigation()
        service = _service(investigation)
        service.send(SLICE)  # bounded to one step -> partial

        plan = service.state_manager.state.current_plan
        assert plan["state"] == "partial"
        assert [s["state"] for s in plan["steps"]] == ["completed", "skipped"]
        # The completed step's bounded INPUT + OUTPUT are retained so the
        # remaining step can be resumed without rebuilding or repeating.
        assert plan["steps"][0]["inputs"]
        assert plan["steps"][0]["output"]
        assert plan["current_step"] == "step-0001"
        assert investigation.calls == 1

    def test_resume_request_rebuilds_only_the_incomplete_steps(self):
        investigation = _RecordingInvestigation()
        service = _service(investigation)
        service.send(SLICE)
        plan = service.state_manager.state.current_plan

        request = resume_execution_request(plan, _owner_session())
        assert request is not None
        assert [s.step_id for s in request.steps] == ["step-0001"]
        assert [s.step_id for s in request.completed_steps] == ["step-0000"]
        assert request.steps[0].carry_from == ("step-0000",)

    def test_resume_request_fails_closed_on_bad_state(self):
        assert resume_execution_request(None) is None
        assert resume_execution_request({}) is None
        assert resume_execution_request({"steps": []}) is None
        # Unknown step kind -> fail closed.
        assert resume_execution_request(
            {"steps": [{"step_id": "s", "kind": "wat", "target": "t", "state": "failed"}]}
        ) is None
        # Everything already completed -> nothing to resume.
        assert resume_execution_request(
            {"steps": [{"step_id": "s", "kind": "analysis", "target": "t",
                        "state": "completed"}]}
        ) is None


# ---------------------------------------------------------------------------
# 4/5/6. Resumption reuses the carry and never repeats completed work
# ---------------------------------------------------------------------------


class TestResumption:
    def test_follow_up_resumes_and_completes_the_goal(self):
        investigation = _RecordingInvestigation()
        service = _service(investigation)
        service.send(SLICE)

        message = service.send("continue")

        plan = service.state_manager.state.current_plan
        assert plan["state"] == "completed"
        assert [s["state"] for s in plan["steps"]] == ["completed", "completed"]
        assert "Steps completed: 2/2" in message.content

    def test_completed_step_is_not_re_executed(self):
        investigation = _RecordingInvestigation()
        service = _service(investigation)
        service.send(SLICE)
        assert investigation.calls == 1

        service.send("continue")

        # The investigation step ran exactly ONCE across both turns.
        assert investigation.calls == 1

    def test_resumed_step_reuses_the_same_bounded_carry(self):
        investigation = _RecordingInvestigation()
        service = _service(investigation)
        first = service.send(SLICE)
        retained_output = service.state_manager.state.current_plan["steps"][0]["output"]

        message = service.send("continue")

        # The analysis concluded over the CARRIED (retained) investigation result.
        assert retained_output.get("target")
        assert retained_output.get("components") == ["atlas.conversation.conversation_state"]
        assert "Steps completed: 2/2" in message.content
        assert first.content  # the earlier turn produced a bounded partial report

    def test_continuation_forms_are_recognized(self):
        for text in ("continue", "continue with that", "finish the remaining step"):
            investigation = _RecordingInvestigation()
            service = _service(investigation)
            service.send(SLICE)
            message = service.send(text)
            assert service.state_manager.state.current_plan["state"] == "completed", text
            assert message.metadata.get("model_used") is not True


# ---------------------------------------------------------------------------
# 7/8. Fail closed + no accidental resumption
# ---------------------------------------------------------------------------


class TestFailClosedAndNoAccidentalResume:
    def test_continuation_without_a_plan_keeps_its_existing_route(self):
        investigation = _RecordingInvestigation()
        service = _service(investigation)
        # No plan yet: "continue" must not fabricate or run anything.
        message = service.send("continue")
        assert message is not None
        assert investigation.calls == 0
        assert service.state_manager.state.current_plan is None

    def test_unrelated_follow_up_does_not_resume(self):
        investigation = _RecordingInvestigation()
        service = _service(investigation)
        service.send(SLICE)
        before = investigation.calls

        for text in ("Hello Atlas.", "what can you do", "Thanks, that helps."):
            message = service.send(text)
            assert message is not None, text
        # No extra investigation ran and the retained plan is untouched.
        assert investigation.calls == before
        assert service.state_manager.state.current_plan["state"] == "partial"

    def test_completed_plan_is_not_resumed_again(self):
        investigation = _RecordingInvestigation()
        service = _service(investigation)
        service.send(SLICE)
        service.send("continue")
        assert investigation.calls == 1

        message = service.send("continue")
        # A completed plan is not re-run; the turn keeps its existing route.
        assert investigation.calls == 1
        assert message is not None

    def test_resume_creates_no_governance_authority(self):
        investigation = _RecordingInvestigation()
        service = _service(investigation)
        service.send(SLICE)
        message = service.send("continue")
        for key in ("approval", "execution", "promotion", "authorization"):
            assert key not in message.metadata, key
        state = service.state_manager.state
        assert state.pending_approval_id is None
        assert state.evolution_proposal_id is None
        assert message.metadata.get("model_used") is not True
        assert _FailingAI.calls == 0


# ---------------------------------------------------------------------------
# 9/10/11. Existing slices unchanged
# ---------------------------------------------------------------------------


class TestExistingSlicesUnchanged:
    def test_investigation_slice_still_composes_full_in_one_turn(self):
        investigation = _RecordingInvestigation()
        service = _service(investigation, initial_max_steps=4)
        message = service.send(SLICE)
        assert "Steps completed: 2/2" in message.content
        assert investigation.calls == 1
        assert service.state_manager.state.current_plan["state"] == "completed"

    def test_knowledge_slice_plan_shape_unchanged(self):
        plan = build_goal_plan(
            "Research the atlas conversation service and then explain how it relates to Atlas."
        )
        assert [s.kind for s in plan] == [NodeKind.KNOWLEDGE, NodeKind.RESEARCH_ANALYSIS]

    def test_unrelated_single_turn_routing_unchanged(self):
        investigation = _RecordingInvestigation()
        service = _service(investigation)
        assert service.send("Hello Atlas.").metadata.get("builtin_intent") == "greeting"
        assert investigation.calls == 0
