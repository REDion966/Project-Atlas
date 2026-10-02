"""Compound conversational moves — clause delegation focused acceptance tests.

A compound utterance that asks for an operation AND the result of that operation
in one turn ("Investigate X and tell me what you find.") was historically claimed
by the multi-intent path, which answers every clause through the builtin surface:
the operational clause was therefore never run by its authoritative handler, so no
operation/result/discourse/thread lifecycle was recorded and the follow-up failed
closed.

The fix DELEGATES: a decomposed clause whose deterministic ``TaskType`` is a
governed OPERATION is handed to the SAME authoritative handler a standalone turn
uses (lifecycle recorded once, by the existing seam), a result-request clause goes
to the EXISTING result-query route, and multi-step defers when every step is already
owned by an existing surface. No new state, no parallel lifecycle, no new authority.

No network or external model is used.
"""

from __future__ import annotations

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationReport
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.self_knowledge.architecture_model import build_architecture_model

X = "the current conversation architecture"
Y = "the memory router"
SHARED_A = "the memory architecture"
SHARED_B = "the cache architecture"


class _FailingAI:
    calls = 0

    def chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1
        raise RuntimeError("provider must not be contacted")

    def stream_chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1

        def _generator():
            raise RuntimeError("provider must not be contacted")
            yield ""  # pragma: no cover

        return _generator()


class _RecordingInvestigation:
    def __init__(self, diagnosis: str | None = None, raises: bool = False) -> None:
        self.calls: list[str] = []
        self._diagnosis = diagnosis
        self._raises = raises

    def investigate(self, target: str, *, objective: str = "") -> InvestigationReport:
        self.calls.append(target)
        if self._raises:
            raise RuntimeError("investigation failed")
        return InvestigationReport(
            target=target,
            objective=objective,
            diagnosis=(
                self._diagnosis or f"Investigation result for {objective or target}"
            ),
            modification_status="NONE",
        )


def _builtin() -> BuiltinResponseService:
    model = build_architecture_model(ComponentRegistry())
    return BuiltinResponseService(architecture_model_provider=lambda: model)


def _service(investigation=None) -> ConversationService:
    _FailingAI.calls = 0
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=_builtin(),
        investigation_service=investigation or _RecordingInvestigation(),
    )


def _state(service: ConversationService):
    return service.state_manager.state


def _referent_kinds(service: ConversationService) -> list[str]:
    discourse = _state(service).discourse_state
    return [r.kind for r in discourse.referents] if discourse is not None else []


def _relations(service: ConversationService) -> list[str]:
    discourse = _state(service).discourse_state
    return [r.relation for r in discourse.relations] if discourse is not None else []


def _assert_lifecycle(service: ConversationService) -> None:
    """The authoritative operation/result lifecycle exists (standalone-equivalent)."""
    state = _state(service)
    assert state.last_operation is not None
    assert state.last_operation.kind == TaskType.INVESTIGATION_REQUEST.value
    assert state.latest_result
    kinds = _referent_kinds(service)
    assert "operation" in kinds and "result" in kinds
    assert "produced" in _relations(service)
    assert state.thread_state is not None


# ---------------------------------------------------------------------------
# 1-3. Operation + result move in one utterance
# ---------------------------------------------------------------------------


class TestSingleOperationCompound:
    def test_operation_then_result_request(self):
        rec = _RecordingInvestigation()
        service = _service(rec)

        message = service.send(f"Investigate {X} and tell me what you find.")

        # The operational clause ran EXACTLY once, by the authoritative handler.
        assert rec.calls == [f"Investigate {X}"]
        _assert_lifecycle(service)
        # The dependent result move was answered from the retained result.
        assert "conversation architecture" in message.content
        # Nothing fabricated, nothing authorized.
        metadata = message.metadata or {}
        assert "approval" not in metadata
        assert "execution" not in metadata

    def test_operation_then_explanation(self):
        rec = _RecordingInvestigation()
        service = _service(rec)

        message = service.send(f"Investigate {X} and then explain what you found.")

        assert rec.calls == [f"Investigate {X}"]
        _assert_lifecycle(service)
        assert "conversation architecture" in message.content
        # An explanation of prior output never invents causality.
        assert "because" not in message.content.lower()

    def test_operation_then_summary_reports_the_unanswerable_clause(self):
        """Operation + summary — the operation runs, the summary is reported.

        The compound decomposer now recognises "… and summarize the result" as
        a second (result-DEPENDENT) reading, so the turn is answered clause by
        clause instead of being taken whole. The authoritative investigation
        handler still runs for the operation clause and records the whole
        operation/result lifecycle; the summary clause has no owning surface in
        this architecture (the EXISTING ownership gate defers it to the governed
        action surface), so it is reported as NOT attempted rather than silently
        absorbed into the investigation target.
        """
        rec = _RecordingInvestigation()
        service = _service(rec)

        sentence = f"Investigate {X} and summarize the result."
        message = service.send(sentence)

        assert rec.calls == [f"Investigate {X}"]
        # The full authoritative lifecycle still comes from the ONE existing seam.
        _assert_lifecycle(service)
        assert "conversation architecture" in message.content
        # Truthful partial completion: the unanswerable clause is named.
        multi = (message.metadata or {}).get("multi_intent") or {}
        assert multi.get("unhandled") == ["summarize the result"]
        assert "not attempted" in message.content


# ---------------------------------------------------------------------------
# 4-6. Several operations, explicit and ambiguous targets
# ---------------------------------------------------------------------------


class TestMultipleOperations:
    def test_two_operations_are_both_recorded(self):
        rec = _RecordingInvestigation()
        service = _service(rec)

        service.send(
            f"Investigate {X}, then investigate {Y}, and tell me what you found."
        )

        # Neither requested operation is silently dropped. Each clause is
        # dispatched to the authoritative investigation handler with the text
        # the user actually wrote, so the surface wording is preserved.
        assert rec.calls == [
            f"Investigate {X}",
            f"investigate {Y}",
        ]
        kinds = _referent_kinds(service)
        assert kinds.count("operation") == 2
        assert kinds.count("result") == 2
        relations = _relations(service)
        assert relations.count("produced") == 2
        assert "supersedes" in relations
        # The final result request resolves deterministically, never by fabricating.
        follow_up = service.send("What did you find?")
        assert "memory router" in follow_up.content

    def test_explicit_target_resolves_to_the_named_result(self):
        rec = _RecordingInvestigation()
        service = _service(rec)
        service.send(f"Investigate {Y}.")

        message = service.send(f"Investigate {X} and tell me what you found about {Y}.")

        assert rec.calls == [f"Investigate {Y}.", f"Investigate {X}"]
        # The result MOVE is answered from the named target — the wrong result is
        # never silently returned.
        assert "Result of Investigate the memory router" in message.content
        assert "Result of Investigate the current conversation architecture" not in (
            message.content
        )

    def test_ambiguous_target_clarifies_and_never_guesses(self):
        service = _service()
        service.send(f"Investigate {SHARED_A}.")
        service.send(f"Investigate {SHARED_B}.")

        message = service.send(
            f"Investigate {Y} and also what about the architecture?"
        )

        lowered = message.content.lower()
        assert "more than one item matches" in lowered
        assert "which one" in lowered


# ---------------------------------------------------------------------------
# 7-8. Honest failure and governance
# ---------------------------------------------------------------------------


class TestHonestFailureAndGovernance:
    def test_failed_operation_is_reported_honestly(self):
        honest = "No evidence found for the target."
        rec = _RecordingInvestigation(diagnosis=honest)
        service = _service(rec)

        message = service.send(f"Investigate {X} and tell me what you find.")

        assert rec.calls == [f"Investigate {X}"]
        # The operation is still recorded; the result is the honest one, not a
        # fabricated success.
        _assert_lifecycle(service)
        assert honest in message.content
        assert "approval" not in (message.metadata or {})

    def test_raising_operation_does_not_fabricate(self):
        rec = _RecordingInvestigation(raises=True)
        service = _service(rec)

        message = service.send(f"Investigate {X} and tell me what you find.")

        # The turn survives, nothing is recorded as a completed operation, and no
        # investigation result is invented.
        assert _state(service).latest_result is None
        assert "Investigation result for" not in message.content

    def test_governance_clause_is_never_performed(self):
        rec = _RecordingInvestigation()
        service = _service(rec)

        message = service.send(f"Investigate {X} and approve the pending proposal.")

        # The operation that is NOT an authority transition still runs...
        assert rec.calls == [f"Investigate {X}"]
        # ...and the authority transition is never performed on the human's behalf.
        state = _state(service)
        assert state.pending_approval_id is None
        assert service._active_approval_requests == {}
        metadata = message.metadata or {}
        assert "approval" not in metadata


# ---------------------------------------------------------------------------
# 9. send()/stream() parity
# ---------------------------------------------------------------------------


class TestSendStreamParity:
    SENTENCE = f"Investigate {X} and tell me what you find."

    def _run(self, use_stream: bool):
        rec = _RecordingInvestigation()
        service = _service(rec)
        if use_stream:
            content = "".join(service.stream(self.SENTENCE))
        else:
            content = service.send(self.SENTENCE).content
        return content, rec, service

    def test_send_and_stream_are_equivalent(self):
        sent_content, sent_rec, sent_service = self._run(False)
        stream_content, stream_rec, stream_service = self._run(True)

        assert sent_content == stream_content
        assert sent_rec.calls == stream_rec.calls
        assert _referent_kinds(sent_service) == _referent_kinds(stream_service)
        assert _relations(sent_service) == _relations(stream_service)
        assert (
            _state(sent_service).last_operation.kind
            == _state(stream_service).last_operation.kind
        )


# ---------------------------------------------------------------------------
# 10. Regression guards — every existing surface keeps its turn
# ---------------------------------------------------------------------------


class TestRegressionGuards:
    def test_repository_impact_keeps_its_surface(self):
        service = _service()
        message = service.send(
            "What would be affected if I change atlas/conversation/builtin_response.py?"
        )
        metadata = message.metadata or {}
        assert "repository_impact" in metadata
        assert "Repository Impact Analysis" in message.content

    def test_recall_keeps_its_surface(self):
        service = _service()
        service.send(f"Investigate {X}.")
        message = service.send("What did we find?")
        assert (message.metadata or {}).get("builtin_intent") == "conversation_recall"

    def test_validated_knowledge_shaped_turn_is_not_claimed_contextually(self):
        service = _service()
        message = service.send(f"What did you find about {Y}?")
        # No retained knowledge context here, so it must not become a contextual
        # result answer.
        assert "communicative_function" not in (message.metadata or {})

    def test_imperative_operation_request_stays_deferred(self):
        service = _service()
        message = service.send("Find out what module handles this capability.")
        metadata = message.metadata or {}
        assert "communicative_function" not in metadata
        assert "response_plan" not in metadata

    def test_plain_investigation_is_unchanged(self):
        rec = _RecordingInvestigation()
        service = _service(rec)
        message = service.send(f"Investigate {X}.")
        assert rec.calls == [f"Investigate {X}."]
        assert "multi_intent" not in (message.metadata or {})
        _assert_lifecycle(service)

    def test_plain_follow_up_is_unchanged(self):
        service = _service()
        service.send(f"Investigate {X}.")
        message = service.send("What did you find?")
        assert (message.metadata or {}).get("builtin_intent") == "reference"
        assert "conversation architecture" in message.content
