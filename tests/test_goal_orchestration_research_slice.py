"""Step 2 — research/knowledge-centered goal slice (second vertical slice).

Proves a bounded two-stage KNOWLEDGE goal:

    KNOWLEDGE (EXISTING D3 local-first retrieval, governed acquisition only when
    insufficient) -> bounded carry -> RESEARCH_ANALYSIS (EXISTING deterministic
    technology-analysis conclusion over the carried VALIDATED evidence)
    -> coherent result -> bounded state.

No new engine: the plan comes from the existing SemanticFrame decomposition, the
sequencing from the existing OrchestrationExecutor, and the work from existing
seams. D3/local-first governance is NOT bypassed (the step uses the very seam
the conversational knowledge bridge uses). Raw research text is data, never
authority; missing validated evidence fails the step closed rather than
fabricating a conclusion.
"""

from __future__ import annotations

from atlas.authority.service import AuthorityService
from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationReport, InvestigationService
from atlas.conversation.investigation_synthesis import InvestigationSynthesizer
from atlas.conversation.message import Message
from atlas.conversation.task_intake import TaskIntake
from atlas.orchestration.execution_models import ExecutionRequest, ExecutionStatus
from atlas.orchestration.executor import OrchestrationExecutor
from atlas.orchestration.goal_plan import build_goal_plan
from atlas.orchestration.models import NodeKind
from atlas.research.validated_retrieval import (
    ValidatedKnowledgeItem,
    ValidatedKnowledgeResult,
    ValidatedKnowledgeStatus,
)
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager

RESEARCH_GOAL = "Research the atlas conversation service and then explain how it relates to Atlas."
INVESTIGATION_GOAL = (
    "Investigate the conversation state handling and then explain what we should do next."
)
SOURCE_URI = "code://atlas/conversation/conversation_service.py"


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


class _Cite:
    """Minimal duck-typed citation (the analysis reads ``source_uri`` only)."""

    def __init__(self, source_uri: str) -> None:
        self.source_uri = source_uri


def _validated_items() -> tuple[ValidatedKnowledgeItem, ...]:
    citation = _Cite(SOURCE_URI)
    return (
        ValidatedKnowledgeItem(
            claim_id="claim-1",
            statement="Atlas Conversation Service coordinates conversation turns",
            validation_status="SUPPORTED",
            claim_confidence=0.8,
            verification_score=0.7,
            citations=(citation,),
        ),
        ValidatedKnowledgeItem(
            claim_id="claim-2",
            statement="Atlas Conversation Service owns the routing cascade",
            validation_status="SUPPORTED",
            claim_confidence=0.7,
            verification_score=0.6,
            citations=(citation,),
        ),
    )


class _RecordingKnowledgeDecision:
    """Duck-typed D3 seam (the shape the conversational knowledge path uses)."""

    def __init__(self, *, covered: bool = True, items=None) -> None:
        self.questions: list[str] = []
        self._covered = covered
        self._items = _validated_items() if items is None else tuple(items)

    def retrieve_with_acquisition(self, query, candidate_urls=()):
        self.questions.append(query)
        if not self._covered:
            return None
        return ValidatedKnowledgeResult(
            status=ValidatedKnowledgeStatus.OK, query=query, items=self._items
        )


def _executor(*, decision=None, investigation=None, synthesizer=None):
    return OrchestrationExecutor(
        authority_service=AuthorityService("Owner"),
        knowledge_decision=decision,
        investigation_service=investigation,
        investigation_synthesizer=synthesizer,
    )


def _run(steps, executor):
    return executor.execute(
        ExecutionRequest(steps=tuple(steps), session_context=_owner_session(), max_steps=4)
    )


# ---------------------------------------------------------------------------
# 1/2. Plan creation + ordering
# ---------------------------------------------------------------------------


class TestResearchPlan:
    def test_two_step_knowledge_plan_created(self):
        plan = build_goal_plan(RESEARCH_GOAL)
        assert plan is not None and len(plan) == 2
        knowledge, analysis = plan
        assert knowledge.kind is NodeKind.KNOWLEDGE
        assert knowledge.target == "retrieve"
        assert analysis.kind is NodeKind.RESEARCH_ANALYSIS
        assert analysis.depends_on == (knowledge.step_id,)
        assert analysis.carry_from == (knowledge.step_id,)

    def test_plan_is_deterministic(self):
        assert build_goal_plan(RESEARCH_GOAL) == build_goal_plan(RESEARCH_GOAL)

    def test_single_clause_shapes_are_not_planned(self):
        for text in ("Research the Artemis program.", "Hello Atlas.", "", "..."):
            assert build_goal_plan(text) is None, text

    def test_steps_execute_in_order(self):
        decision = _RecordingKnowledgeDecision()
        result = _run(build_goal_plan(RESEARCH_GOAL), _executor(decision=decision))
        assert result.status is ExecutionStatus.COMPLETED
        assert [s.kind for s in result.steps] == [
            NodeKind.KNOWLEDGE, NodeKind.RESEARCH_ANALYSIS
        ]
        assert all(s.completed for s in result.steps)
        assert decision.questions


# ---------------------------------------------------------------------------
# 3/4. Explicit, bounded result carry
# ---------------------------------------------------------------------------


class TestResearchCarry:
    def test_researched_objective_is_carried_into_the_analysis(self):
        result = _run(build_goal_plan(RESEARCH_GOAL), _executor(
            decision=_RecordingKnowledgeDecision()))
        # Step 2 concluded over the objective/evidence step 1 carried.
        assert result.steps[1].output["question"] == "atlas conversation service"

    def test_analysis_consumes_the_carried_validated_evidence(self):
        result = _run(build_goal_plan(RESEARCH_GOAL), _executor(
            decision=_RecordingKnowledgeDecision()))
        output = result.steps[1].output
        assert output["strength"] == "supported"
        assert output["verified_fact_count"] == 2  # the two carried SUPPORTED claims
        assert output["contradictions"] == []
        assert SOURCE_URI in output["supporting_evidence"]

    def test_carry_is_bounded(self):
        result = _run(build_goal_plan(RESEARCH_GOAL), _executor(
            decision=_RecordingKnowledgeDecision()))
        output = result.steps[1].output
        assert set(output) <= {
            "question", "strength", "summary", "verified_fact_count",
            "supporting_evidence", "contradictions", "uncertainties",
            "modification_status",
        }
        assert len(output["supporting_evidence"]) <= 8


# ---------------------------------------------------------------------------
# 5. Failure / insufficient evidence
# ---------------------------------------------------------------------------


class TestResearchFailure:
    def test_no_validated_evidence_fails_the_first_step_closed(self):
        decision = _RecordingKnowledgeDecision(covered=False)
        result = _run(build_goal_plan(RESEARCH_GOAL), _executor(decision=decision))
        assert result.status is not ExecutionStatus.COMPLETED
        assert result.steps[0].failed
        assert result.steps[0].failure_kind == "no_evidence"
        assert not result.steps[1].completed

    def test_empty_validated_items_fail_closed(self):
        class _Empty:
            def retrieve_with_acquisition(self, query, candidate_urls=()):
                return ValidatedKnowledgeResult(
                    status=ValidatedKnowledgeStatus.EMPTY, query=query, items=()
                )

        result = _run(build_goal_plan(RESEARCH_GOAL), _executor(decision=_Empty()))
        assert result.steps[0].failed
        assert not result.steps[1].completed

    def test_analysis_fails_closed_on_a_carry_without_evidence(self):
        # A carried snapshot with no validated claims must not produce a conclusion.
        plan = build_goal_plan(RESEARCH_GOAL)
        knowledge, analysis = plan
        empty_source = type(knowledge)(
            step_id=knowledge.step_id,
            kind=knowledge.kind,
            target=knowledge.target,
            inputs={"question": "atlas conversation service"},
            # A stub that "succeeds" while carrying no claims (adversarial).
            description=knowledge.description,
        )
        executor = _executor(decision=_RecordingKnowledgeDecision(items=()))
        result = _run([empty_source, analysis], executor)
        assert not result.steps[1].completed

    def test_unwired_seam_fails_closed(self):
        result = _run(build_goal_plan(RESEARCH_GOAL), _executor())
        assert all(not s.completed for s in result.steps)


# ---------------------------------------------------------------------------
# 6/7. Governance + investigation-slice regression
# ---------------------------------------------------------------------------


class _Bridge:
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
        goal_orchestration_resolver=_Bridge(executor),
    )


class TestConversationIntegrationAndGovernance:
    def test_knowledge_goal_is_retained_and_governance_neutral(self):
        service = _service(_executor(decision=_RecordingKnowledgeDecision()))
        message = service.send(RESEARCH_GOAL)
        assert "Steps completed: 2/2" in message.content
        plan = service.state_manager.state.current_plan
        assert [s["kind"] for s in plan["steps"]] == ["knowledge", "research_analysis"]
        assert plan["state"] == "completed"
        for key in ("approval", "execution", "promotion", "authorization"):
            assert key not in message.metadata, key
        state = service.state_manager.state
        assert state.pending_approval_id is None
        assert state.evolution_proposal_id is None
        assert message.metadata.get("model_used") is not True
        assert _FailingAI.calls == 0

    def test_investigation_slice_still_composes_and_runs(self):
        class _Investigation:
            def investigate(self, target, *, objective=""):
                return InvestigationReport(
                    target=target,
                    components=("atlas.conversation.conversation_state",),
                    findings=(),
                    diagnosis="d",
                    modification_status="NONE",
                )

        plan = build_goal_plan(INVESTIGATION_GOAL)
        assert [s.kind for s in plan] == [NodeKind.INVESTIGATION, NodeKind.ANALYSIS]
        result = _run(plan, _executor(
            investigation=_Investigation(), synthesizer=InvestigationSynthesizer()))
        assert result.status is ExecutionStatus.COMPLETED

    def test_single_research_request_is_not_claimed(self):
        service = _service(_executor(decision=_RecordingKnowledgeDecision()))
        assert service._maybe_handle_goal_request("Research the Artemis program.") is None
