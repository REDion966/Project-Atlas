"""Fail-closed knowledge routing — bounded-subject regression tests.

Evidence: a turn carrying only a generic "check / look / dig" cue but NO bounded
knowledge subject was routed into validated-knowledge lookup with a stopword
residue ("happen", "should next", "whether still true", "second issue"). The
knowledge path must never query the store with an invented subject — it fails
closed instead, and legitimate knowledge/research/recall turns are unchanged.

Deterministic, model-free, no network, no new architecture.
"""

from __future__ import annotations

from typing import Any

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationReport
from atlas.conversation.task_intake import TaskIntake
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.self_knowledge.architecture_model import build_architecture_model

#: Turns that carry a generic knowledge-ish cue but NO bounded subject.
INVENTED_SUBJECT_PHRASES = (
    "Could you check what is happening here?",
    "What should we look at next?",
    "Can you check whether that's still true?",
    "Can you dig deeper into the second issue?",
)


class _EmptyResult:
    """Validated-knowledge result shape: nothing matched."""

    status = "empty"
    items: tuple[Any, ...] = ()
    message = "No validated (SUPPORTED) knowledge matched the query."


class _RecordingProvider:
    """Records every validated-knowledge query the conversation issues."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def __call__(self, query: str) -> Any:
        self.queries.append(query)
        return _EmptyResult()


class _FailingAI:
    def chat(self, prompt, routing_context=None):
        raise RuntimeError("provider must not be contacted")

    def stream_chat(self, prompt, routing_context=None):
        def _generator():
            raise RuntimeError("provider must not be contacted")
            yield ""  # pragma: no cover

        return _generator()


class _RecordingInvestigation:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def investigate(self, target: str, *, objective: str = "") -> InvestigationReport:
        self.calls.append(target)
        return InvestigationReport(
            target=target,
            objective=objective,
            diagnosis=f"Investigation result for {objective or target}",
            modification_status="NONE",
        )


def _service(provider: _RecordingProvider) -> ConversationService:
    model = build_architecture_model(ComponentRegistry())
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(
            architecture_model_provider=lambda: model,
            validated_knowledge_provider=provider,
        ),
        investigation_service=_RecordingInvestigation(),
    )


# ---------------------------------------------------------------------------
# The four evidenced failures — no invented subject may reach the store
# ---------------------------------------------------------------------------


class TestInventedSubjectFailsClosed:
    def test_no_invented_subject_reaches_the_knowledge_store(self):
        provider = _RecordingProvider()
        service = _service(provider)
        for phrase in INVENTED_SUBJECT_PHRASES:
            service.send(phrase)
        assert provider.queries == []

    def test_no_knowledge_state_is_recorded(self):
        provider = _RecordingProvider()
        service = _service(provider)
        for phrase in INVENTED_SUBJECT_PHRASES:
            service.send(phrase)
            assert service.state_manager.state.last_knowledge is None

    def test_frame_knowledge_fallback_declines_each_phrase(self):
        provider = _RecordingProvider()
        service = _service(provider)
        intake = TaskIntake()
        for phrase in INVENTED_SUBJECT_PHRASES:
            spec = intake.intake(phrase, history_length=0)
            assert service._frame_knowledge_message(phrase, phrase, spec) is None

    def test_answers_do_not_claim_a_knowledge_subject(self):
        provider = _RecordingProvider()
        service = _service(provider)
        for phrase in INVENTED_SUBJECT_PHRASES:
            message = service.send(phrase)
            assert "Validated knowledge for" not in message.content
            assert (message.metadata or {}).get("validated_query") is None


# ---------------------------------------------------------------------------
# Legitimate knowledge / research / recall behaviour is unchanged
# ---------------------------------------------------------------------------


class TestLegitimateKnowledgePreserved:
    def test_bounded_research_request_still_queries_the_store(self):
        provider = _RecordingProvider()
        service = _service(provider)
        service.send("Research the memory service.")
        assert provider.queries == ["memory service"]

    def test_bounded_about_request_still_reaches_the_knowledge_surface(self):
        provider = _RecordingProvider()
        service = _service(provider)
        message = service.send("Tell me about the memory router.")
        assert provider.queries, "the bounded knowledge fallback must still answer"
        assert all("memory router" in query for query in provider.queries)
        assert "memory router" in message.content

    def test_store_recall_is_not_given_an_invented_subject(self):
        """A recall-shaped turn keeps the recall surface and never invents a topic.

        With no store wired the recall surface answers honestly ("no deterministic
        recall available"); the point of the assertion is that NO store query is
        issued with a stopword-derived subject.
        """
        provider = _RecordingProvider()
        service = _service(provider)
        message = service.send("What do you know about the cache layer?")
        # Any store query uses the BOUNDED subject named by the turn — never a
        # stopword-derived residue.
        assert all("cache layer" in query for query in provider.queries)
        assert (message.metadata or {}).get("validated_query") is None
        # The recall surface owns the turn (no invented knowledge answer).
        assert (message.metadata or {}).get("builtin_intent") == "recall"

    def test_conversation_recall_still_works(self):
        provider = _RecordingProvider()
        service = _service(provider)
        service.send("Investigate the conversation architecture.")
        message = service.send("What did we find?")
        assert (message.metadata or {}).get("builtin_intent") == "conversation_recall"
