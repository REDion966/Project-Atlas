"""NLU-2 — research targeting, evidence relevance, missing-information tests.

Deterministic and model-free: no provider, no kernel, no network.
"""

from __future__ import annotations

from atlas.authority.service import AuthorityService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.research_objective import (
    looks_like_research_request,
    research_subject_gap,
)
from atlas.conversation.task_intake import TaskIntake
from atlas.orchestration.execution_models import (
    ExecutionRequest,
    ExecutionState,
    ExecutionStatus,
    ExecutionStep,
)
from atlas.orchestration.executor import OrchestrationExecutor
from atlas.orchestration.models import NodeKind
from atlas.research.relevance import (
    Relevance,
    classify_relevance,
    objective_subject_tokens,
)
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager


class _FakeAI:
    def chat(self, *args, **kwargs):
        raise RuntimeError("no provider")

    def stream_chat(self, *args, **kwargs):
        def _gen():
            raise RuntimeError("no provider")
            yield ""  # pragma: no cover

        return _gen()


# ---------------------------------------------------------------------------
# Evidence relevance gate
# ---------------------------------------------------------------------------


class TestRelevanceGate:
    def test_phone_subject_against_code_source_is_irrelevant(self):
        assert (
            classify_relevance(
                "Research the camera specifications of the Samsung Galaxy S26 Ultra "
                "for a detailed review.",
                ["code://tests/test_promotion_review_visibility.py"],
            )
            is Relevance.IRRELEVANT
        )

    def test_purpose_words_do_not_count_as_subject(self):
        # "review" / "capabilities" are purpose/abstraction words: a source
        # matching only on them is NOT relevant to a phone-camera objective.
        assert (
            classify_relevance(
                "Research video capabilities for a detailed review.",
                ["code://atlas/reasoning/capabilities/analyzer.py"],
            )
            is Relevance.IRRELEVANT
        )

    def test_shared_subject_token_is_relevant(self):
        assert (
            classify_relevance(
                "Research the memory architecture.",
                ["code://atlas/memory/memory_service.py"],
            )
            is Relevance.RELEVANT
        )

    def test_no_sources_is_no_evidence(self):
        assert (
            classify_relevance("Research smartphone cameras.", [])
            is Relevance.NO_EVIDENCE
        )

    def test_subject_tokens_exclude_purpose_vocabulary(self):
        tokens = objective_subject_tokens(
            "Research the camera specifications for a detailed review."
        )
        assert "camera" in tokens
        assert "specifications" in tokens
        assert "review" not in tokens
        assert "research" not in tokens

    def test_no_subject_tokens_never_blocks(self):
        # A degenerate objective with no subject cannot judge relevance.
        assert (
            classify_relevance("research for a review", ["code://x/y.py"])
            is Relevance.RELEVANT
        )


# ---------------------------------------------------------------------------
# Executor research relevance wiring
# ---------------------------------------------------------------------------


def _ctx():
    authority = AuthorityService("Owner")
    return SessionContext.from_session(SessionManager(authority).create_session("owner"))


class _AcquisitionResult:
    def __init__(self, status, sources, claim_count):
        self.status = status
        self.sources = list(sources)
        self.claim_count = claim_count
        self.findings = ""

    def to_dict(self):
        return {
            "status": self.status,
            "sources": list(self.sources),
            "claim_count": self.claim_count,
        }


class _ResearchService:
    """Minimal research service double (returns a fixed AcquisitionResult-like)."""

    def __init__(self, status, sources, claims=0):
        self._result = _AcquisitionResult(status, sources, claims)

    def acquire(self, **kwargs):
        return self._result


def _run_research(question, research_service):
    executor = OrchestrationExecutor(
        research_service=research_service, authority_service=AuthorityService("Owner")
    )
    step = ExecutionStep(
        step_id="s1", kind=NodeKind.RESEARCH, target="acquire", inputs={"question": question}
    )
    return executor.execute(
        ExecutionRequest(steps=(step,), session_context=_ctx())
    )


class TestExecutorResearchRelevance:
    def test_irrelevant_evidence_is_not_success(self):
        result = _run_research(
            "Research the camera specifications of the Samsung Galaxy S26 Ultra.",
            _ResearchService("ok", ["code://tests/test_promotion_review_visibility.py"], 25),
        )
        assert result.status is ExecutionStatus.FAILED
        step = result.steps[0]
        assert step.state is ExecutionState.FAILED
        assert step.failure_kind == "no_relevant_evidence"
        assert "does not address" in step.error

    def test_relevant_evidence_is_success(self):
        result = _run_research(
            "Research the memory architecture.",
            _ResearchService("ok", ["code://atlas/memory/memory_service.py"], 5),
        )
        assert result.status is ExecutionStatus.COMPLETED
        assert result.steps[0].state is ExecutionState.COMPLETED

    def test_no_sources_is_no_evidence(self):
        result = _run_research("Research smartphone cameras.", _ResearchService("noop", [], 0))
        assert result.status is ExecutionStatus.FAILED
        assert result.steps[0].failure_kind == "no_evidence"


# ---------------------------------------------------------------------------
# Missing-information / clarification
# ---------------------------------------------------------------------------


class TestResearchSubjectGap:
    def test_indefinite_generic_subject_asks(self):
        assert research_subject_gap("I want to research a phone for a review.") is not None
        assert research_subject_gap("research a product for a review.") is not None

    def test_demonstrative_subject_asks(self):
        assert research_subject_gap("Research this product for me.") is not None

    def test_unresolved_possessive_subject_asks(self):
        assert research_subject_gap("Research its camera system.") is not None
        # A genuinely resolved reference must not be blocked.
        assert (
            research_subject_gap("Research its camera system.", reference_resolved=True)
            is None
        )

    def test_unspecified_comparison_set_asks(self):
        assert (
            research_subject_gap(
                "Research the differences between the cameras of three flagship "
                "smartphones."
            )
            is not None
        )

    def test_named_subject_does_not_ask(self):
        assert (
            research_subject_gap(
                "Research the camera specifications of the Samsung Galaxy S26 Ultra "
                "for a detailed review."
            )
            is None
        )

    def test_broad_domain_does_not_ask(self):
        assert research_subject_gap("Research smartphone cameras.") is None
        assert (
            research_subject_gap(
                "Research what matters when reviewing a smartphone camera, including "
                "sensor size, aperture, stabilization, autofocus, video capabilities, "
                "and low-light performance."
            )
            is None
        )

    def test_non_research_request_does_not_ask(self):
        assert research_subject_gap("Compare the camera systems of three phones.") is None
        assert looks_like_research_request("Compare the camera systems of three phones.") is False


class TestConversationResearchClarification:
    def _service(self):
        return ConversationService(
            _FakeAI(),
            task_intake=TaskIntake(),
            orchestration_resolver=lambda spec, ctx: None,
        )

    def test_missing_subject_asks_clarification_not_research(self):
        message = self._service().send("I want to research a phone for a review.")
        assert "which specific" in message.content.lower()
        assert message.metadata.get("research_clarification", {}).get("reason") == "missing_subject"
        assert "Done" not in message.content

    def test_specified_subject_reaches_the_resolver(self):
        calls = []

        def resolver(spec, ctx):
            calls.append(spec)
            return None

        service = ConversationService(
            _FakeAI(), task_intake=TaskIntake(), orchestration_resolver=resolver
        )
        service.send(
            "Research the camera specifications of the Samsung Galaxy S26 Ultra."
        )
        assert calls, "a specified research request must reach the resolver"
