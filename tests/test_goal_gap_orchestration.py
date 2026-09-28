"""Step 2 — INVESTIGATION -> EVIDENCE_GAP_ANALYSIS (the gap slice).

The third legitimate two-stage sequence, composed only from EXISTING production
capabilities:

    InvestigationService.investigate  (D1, read-only)
        -> bounded investigation snapshot (carry)
    EvidenceGapAnalyzer.analyze       (the SAME analyzer the conversational gap
                                       route uses)
        -> concrete, citation-backed gaps over that evidence

Nothing is gathered, mutated, authorized or fabricated; the carry is the same
bounded, data-only projection the ANALYSIS step consumes.
"""

from __future__ import annotations

from collections import Counter

from atlas.authority.service import AuthorityService
from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.evidence_gap_analysis import (
    EvidenceGapAnalyzer,
    GapCategory,
)
from atlas.conversation.investigation import (
    InvestigationFinding,
    InvestigationReport,
    InvestigationService,
)
from atlas.conversation.investigation_synthesis import InvestigationSynthesizer
from atlas.conversation.task_intake import TaskIntake
from atlas.orchestration.execution_models import ExecutionRequest
from atlas.orchestration.executor import OrchestrationExecutor
from atlas.orchestration.goal_plan import build_goal_plan
from atlas.orchestration.models import NodeKind
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager

GAP_GOAL = (
    "Investigate the conversation state handling and then explain the "
    "evidence gaps."
)
PLAIN_GOAL = "Investigate the conversation state handling and then explain what we should do next."
KNOWLEDGE_GOAL = (
    "Research the atlas conversation service and then explain how it relates to Atlas."
)


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


def _report(target: str, *, with_test_evidence: bool = True, findings: int = 3) -> InvestigationReport:
    items = [
        InvestigationFinding(
            category="reference",
            description="Found 3 reference(s) to 'state' in atlas/conversation/",
            evidence="atlas/conversation/conversation_state.py",
            location="atlas/conversation/",
        ),
        InvestigationFinding(
            category="dependency",
            description="Imported by conversation_service",
            evidence="atlas/conversation/conversation_service.py",
            location="atlas.conversation.conversation_service",
        ),
    ]
    if with_test_evidence:
        items.insert(
            0,
            InvestigationFinding(
                category="test",
                description="Found 1 test file referencing 'conversation_state'",
                evidence="tests/test_conversation_state.py",
                location="tests/",
            ),
        )
    items = (items * (findings // len(items) + 1))[:findings]
    return InvestigationReport(
        target=target,
        objective=target,
        diagnosis="Identified 2 relevant component(s).",
        components=(
            "atlas.conversation.conversation_state",
            "atlas.conversation.conversation_service",
        ),
        findings=tuple(items),
        modification_status="NONE",
    )


class _RecordingInvestigation:
    def __init__(self, *, with_test_evidence: bool = True, findings: int = 3) -> None:
        self.calls = 0
        self._with_test = with_test_evidence
        self._findings = findings

    def investigate(self, target: str, *, objective: str = "") -> InvestigationReport:
        self.calls += 1
        return _report(target, with_test_evidence=self._with_test, findings=self._findings)


def _executor(investigation) -> OrchestrationExecutor:
    return OrchestrationExecutor(
        authority_service=AuthorityService("Owner"),
        investigation_service=investigation,
        investigation_synthesizer=InvestigationSynthesizer(),
        evidence_gap_analyzer=EvidenceGapAnalyzer(),
    )


class _Bridge:
    def __init__(self, executor, *, initial_max_steps: int = 4) -> None:
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
        from atlas.orchestration.goal_plan import resume_execution_request
        from atlas.orchestration.reporting import orchestration_result_to_message

        request = resume_execution_request(plan_state, _owner_session())
        if request is None:
            return None
        result = self._executor.execute(request)
        return orchestration_result_to_message(
            result, intent=str(plan_state.get("objective") or "")
        )


def _service(investigation, *, initial_max_steps: int = 4) -> ConversationService:
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
# 1/2. Composition and ordering
# ---------------------------------------------------------------------------


class TestComposition:
    def test_gap_goal_composes_investigation_then_gap_analysis(self):
        steps = build_goal_plan(GAP_GOAL)
        assert steps is not None
        assert [s.kind for s in steps] == [
            NodeKind.INVESTIGATION,
            NodeKind.EVIDENCE_GAP_ANALYSIS,
        ]

    def test_exact_step_ordering_and_wiring(self):
        first, second = build_goal_plan(GAP_GOAL)
        assert first.step_id == "step-0000"
        assert second.step_id == "step-0001"
        assert second.depends_on == ("step-0000",)
        assert second.carry_from == ("step-0000",)
        assert second.kind is NodeKind.EVIDENCE_GAP_ANALYSIS

    def test_plain_explanation_clause_keeps_the_analysis_slice(self):
        steps = build_goal_plan(PLAIN_GOAL)
        assert [s.kind for s in steps] == [NodeKind.INVESTIGATION, NodeKind.ANALYSIS]

    def test_knowledge_clause_is_unaffected_by_the_gap_vocabulary(self):
        steps = build_goal_plan(KNOWLEDGE_GOAL)
        assert [s.kind for s in steps] == [NodeKind.KNOWLEDGE, NodeKind.RESEARCH_ANALYSIS]


# ---------------------------------------------------------------------------
# 3/4. Stage 1 -> stage 2 carry, and its bounds
# ---------------------------------------------------------------------------


class TestCarry:
    def test_gap_step_consumes_the_carried_investigation_result(self):
        investigation = _RecordingInvestigation()
        service = _service(investigation)
        message = service.send(GAP_GOAL)

        plan = service.state_manager.state.current_plan
        assert plan["state"] == "completed"
        assert [s["state"] for s in plan["steps"]] == ["completed", "completed"]
        assert investigation.calls == 1
        assert "Steps completed: 2/2" in message.content

        # Stage 2 derived its gaps from stage 1's carried evidence.
        gaps = plan["steps"][1]["output"]["gaps"]
        assert [g["component"] for g in gaps] == [
            "atlas.conversation.conversation_service"
        ]
        assert gaps[0]["category"] == GapCategory.UNTESTED_COMPONENT.value
        assert gaps[0]["evidence"], "each gap must cite the report findings"
        assert plan["steps"][1]["output"]["finding_count"] > 0

    def test_carry_is_bounded_at_the_boundary(self):
        investigation = _RecordingInvestigation(findings=30)
        service = _service(investigation)
        service.send(GAP_GOAL)

        plan = service.state_manager.state.current_plan
        stage_one = plan["steps"][0]["output"]
        # The investigation snapshot handed to stage 2 is strictly bounded...
        assert len(stage_one["findings"]) <= 24
        assert len(stage_one["components"]) <= 8
        # ...and bounded PER CATEGORY, so no evidence category is starved (a
        # global cap would drop every 'test' finding and force stage 2 to fail
        # closed on evidence the investigation actually gathered).
        by_category = Counter(f["category"] for f in stage_one["findings"])
        assert set(by_category) == {"reference", "dependency", "test"}
        assert all(count <= 8 for count in by_category.values())
        # ...and stage 2 could only analyse the bounded view it received.
        assert plan["steps"][1]["output"]["finding_count"] <= 24
        for gap in plan["steps"][1]["output"]["gaps"]:
            assert len(gap["observation"]) <= 240
            assert len(gap["interpretation"]) <= 240


# ---------------------------------------------------------------------------
# 5. Insufficient evidence -> fail closed (never a fabricated gap)
# ---------------------------------------------------------------------------


class TestFailClosed:
    def test_no_test_evidence_fails_closed(self):
        investigation = _RecordingInvestigation(with_test_evidence=False)
        service = _service(investigation)
        message = service.send(GAP_GOAL)

        plan = service.state_manager.state.current_plan
        assert plan["state"] == "partial"  # stage 1 completed, stage 2 failed
        assert plan["steps"][1]["state"] == "failed"
        assert "insufficient evidence" in plan["steps"][1]["error"]
        assert "Completed with issues" in message.content
        assert "insufficient evidence" in message.content

    def test_no_carry_fails_closed(self):
        # A gap step run with no carried result must never invent an analysis.
        executor = _executor(_RecordingInvestigation())
        from atlas.orchestration.execution_models import ExecutionStep

        result = executor.execute(
            ExecutionRequest(
                steps=(
                    ExecutionStep(
                        step_id="step-0000",
                        kind=NodeKind.EVIDENCE_GAP_ANALYSIS,
                        target="analyze_gaps",
                        inputs={},
                    ),
                ),
                session_context=_owner_session(),
            )
        )
        assert result.steps[0].state.value == "failed"
        assert "exactly one carried result" in result.steps[0].error

    def test_unwired_analyzer_fails_closed(self):
        executor = OrchestrationExecutor(
            authority_service=AuthorityService("Owner"),
            investigation_service=_RecordingInvestigation(),
        )
        from atlas.orchestration.execution_models import ExecutionStep

        result = executor.execute(
            ExecutionRequest(
                steps=(
                    ExecutionStep(
                        step_id="step-0000",
                        kind=NodeKind.EVIDENCE_GAP_ANALYSIS,
                        target="analyze_gaps",
                    ),
                ),
                session_context=_owner_session(),
            )
        )
        assert result.steps[0].state.value == "failed"
        assert result.steps[0].failure_kind == "missing_target"


# ---------------------------------------------------------------------------
# 6. Governance preservation
# ---------------------------------------------------------------------------


class TestGovernance:
    def test_no_authority_is_created_or_bypassed(self):
        investigation = _RecordingInvestigation()
        service = _service(investigation)
        message = service.send(GAP_GOAL)

        for key in ("approval", "execution", "promotion", "authorization"):
            assert key not in message.metadata, key
        state = service.state_manager.state
        assert state.pending_approval_id is None
        assert state.evolution_proposal_id is None
        assert message.metadata.get("model_used") is not True
        assert _FailingAI.calls == 0
        assert service.state_manager.state.current_plan["steps"][1]["output"][
            "modification_status"
        ] == "NONE"


# ---------------------------------------------------------------------------
# 7. Plan resumption for the new sequence
# ---------------------------------------------------------------------------


class TestResumption:
    def test_partial_gap_plan_resumes_without_rerunning_stage_one(self):
        investigation = _RecordingInvestigation()
        service = _service(investigation, initial_max_steps=1)
        service.send(GAP_GOAL)

        plan = service.state_manager.state.current_plan
        assert plan["state"] == "partial"
        assert [s["state"] for s in plan["steps"]] == ["completed", "skipped"]
        assert investigation.calls == 1

        service.send("continue")

        plan = service.state_manager.state.current_plan
        assert plan["state"] == "completed"
        assert [s["state"] for s in plan["steps"]] == ["completed", "completed"]
        assert investigation.calls == 1  # stage 1 never repeated
        assert plan["steps"][1]["output"]["gaps"]

    def test_unrelated_turn_does_not_resume_the_gap_plan(self):
        investigation = _RecordingInvestigation()
        service = _service(investigation, initial_max_steps=1)
        service.send(GAP_GOAL)
        before = investigation.calls

        service.send("Hello Atlas.")
        assert investigation.calls == before
        assert service.state_manager.state.current_plan["state"] == "partial"
