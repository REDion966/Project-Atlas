"""Mixed compound/delegation ownership — focused regression tests.

Evidence: one compound user turn whose clauses are owned by DIFFERENT existing
authoritative handlers did not reach those handlers. Three defects, all fixed by
reusing the existing seams:

  * A research clause had no delegated handler, so an "investigate X and
    research Y" compound left the research clause UNATTEMPTED while claiming the
    turn was answered.
  * A research-LEADING compound was claimed whole by the compound route, which
    reported the later clauses as "recognized but not executed" — so
    "research Y and investigate X" swallowed the investigation entirely.
  * "then"-joined and comma-joined compounds ("X, then research Y") were never
    split at all, because ``split_intents`` did not recognise the punctuated
    coordinator form and preferred a later coordinator over an earlier one.

Each clause is now dispatched to the handler a standalone turn would use, so
the EXISTING investigation/knowledge lifecycles record themselves. The
orchestration bridge is never the conversational source of truth.

Deterministic, model-free, no network, no new state/operation/resolver.
"""

from __future__ import annotations

from typing import Any

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationReport
from atlas.conversation.semantic_frame import decompose, split_intents
from atlas.conversation.task_intake import TaskIntake
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.self_knowledge.architecture_model import build_architecture_model

X = "the memory service"
Y = "the knowledge router"
Z = "the cache layer"
TOPIC = "knowledge router"


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------


class _EmptyResult:
    status = "empty"
    items: tuple[Any, ...] = ()
    message = "No validated (SUPPORTED) knowledge matched the query."


class _MatchResult:
    def __init__(self, topic: str) -> None:
        self.status = "matched"
        self.items: tuple[Any, ...] = ()
        self.message = f"Validated knowledge for {topic}: recorded facts about it."


class _RecordingProvider:
    """Records every validated-knowledge query the conversation issues."""

    def __init__(self, topics: tuple[str, ...] = (TOPIC,)) -> None:
        self.queries: list[str] = []
        self.topics = topics

    def __call__(self, query: str) -> Any:
        self.queries.append(query)
        for topic in self.topics:
            if topic.lower() in (query or "").lower():
                return _MatchResult(topic)
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
        self.objectives: list[str] = []

    def investigate(self, target: str, *, objective: str = "") -> InvestigationReport:
        self.calls.append(target)
        self.objectives.append(objective)
        return InvestigationReport(
            target=target,
            objective=objective,
            diagnosis=f"Investigation result for {objective or target}",
            modification_status="NONE",
        )


def _service(provider: _RecordingProvider | None = None):
    investigation = _RecordingInvestigation()
    model = build_architecture_model(ComponentRegistry())
    service = ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(
            architecture_model_provider=lambda: model,
            validated_knowledge_provider=(
                provider if provider is not None else _RecordingProvider()
            ),
        ),
        investigation_service=investigation,
    )
    return service, investigation


def _state(service: ConversationService) -> dict[str, Any]:
    state = service.state_manager.state
    threads = state.thread_state.threads if state.thread_state else ()
    discourse = state.discourse_state
    return {
        "threads": tuple(t.thread_id for t in threads),
        "referent_kinds": tuple(
            r.kind for r in (discourse.referents if discourse else ())
        ),
        "relations": tuple(
            r.relation for r in (discourse.relations if discourse else ())
        ),
        "operation": state.last_operation.kind if state.last_operation else None,
        "result": bool(state.latest_result),
        "knowledge": bool(state.last_knowledge),
        "current_investigation": state.current_investigation,
    }


def _multi(message) -> dict[str, list[str]]:
    return (message.metadata or {}).get("multi_intent") or {}


# ---------------------------------------------------------------------------
# 1. independent compounds, both orders
# ---------------------------------------------------------------------------


class TestIndependentCompounds:
    def test_investigate_then_research_executes_both(self):
        service, investigation = _service()

        message = service.send(f"Investigate {X} and research {Y}.")

        # each clause executed exactly once, through its own handler
        assert investigation.calls == [f"Investigate {X}"]
        assert _multi(message).get("unhandled") == []
        # the investigation lifecycle came from the authoritative handler
        state = _state(service)
        assert state["operation"] == "investigation_request"
        assert state["result"] is True
        assert state["referent_kinds"] == ("operation", "result")
        assert "produced" in state["relations"]
        assert state["threads"]
        # the knowledge lifecycle came from the knowledge path
        assert state["knowledge"] is True

    def test_research_then_investigate_executes_both(self):
        service, investigation = _service()

        message = service.send(f"Research {Y} and investigate {X}.")

        # reversed order is handled the same way — no hard-coded order
        assert investigation.calls == [f"investigate {X}"]
        assert _multi(message).get("unhandled") == []
        state = _state(service)
        assert state["operation"] == "investigation_request"
        assert state["result"] is True
        assert state["knowledge"] is True

    def test_research_does_not_fabricate_an_operation_lifecycle(self):
        service, _ = _service()
        service.send(f"Investigate {X} and research {Y}.")
        state = _state(service)

        # ONE operation + ONE result: the knowledge clause added neither.
        assert state["referent_kinds"].count("operation") == 1
        assert state["referent_kinds"].count("result") == 1

    def test_research_clause_queries_the_knowledge_store(self):
        provider = _RecordingProvider()
        service, _ = _service(provider)

        service.send(f"Investigate {X} and research {Y}.")

        assert any(TOPIC in query for query in provider.queries), provider.queries


# ---------------------------------------------------------------------------
# 2. explicit ordering
# ---------------------------------------------------------------------------


class TestOrderedCompounds:
    def test_then_joined_investigate_then_research(self):
        service, investigation = _service()

        message = service.send(f"Investigate {X}, then research {Y}.")

        assert investigation.calls == [f"Investigate {X}"]
        assert _multi(message).get("unhandled") == []
        assert _state(service)["knowledge"] is True

    def test_then_joined_research_then_investigate(self):
        service, investigation = _service()

        message = service.send(f"Research {Y}, then investigate {X}.")

        assert investigation.calls == [f"investigate {X}"]
        assert _multi(message).get("unhandled") == []
        assert _state(service)["knowledge"] is True

    def test_clause_text_carries_no_coordinator(self):
        subjects = tuple(
            sub.subject for sub in split_intents(f"Investigate {X}, then research {Y}.")
        )
        assert subjects == (f"Investigate {X}", f"research {Y}")


# ---------------------------------------------------------------------------
# 3. two investigations stay two operations
# ---------------------------------------------------------------------------


class TestTwoInvestigations:
    def test_both_operations_record_their_own_lifecycle(self):
        service, investigation = _service()

        service.send(f"Investigate {X} and investigate {Z}.")

        assert investigation.calls == [f"Investigate {X}", f"investigate {Z}"]
        state = _state(service)
        assert state["referent_kinds"].count("operation") == 2
        assert state["referent_kinds"].count("result") == 2
        assert state["relations"].count("produced") == 2
        assert "supersedes" in state["relations"]

    def test_follow_ups_resolve_each_occurrence(self):
        service, _ = _service()
        service.send(f"Investigate {X} and investigate {Z}.")

        latest = service.send("What did you find?")
        first = service.send("What about the first issue?")
        second = service.send("What about the second issue?")

        assert "cache layer" in latest.content
        assert "memory service" in first.content
        assert "cache layer" in second.content

    def test_no_duplicate_execution(self):
        service, investigation = _service()
        service.send(f"Investigate {X} and investigate {Z}.")
        assert len(investigation.calls) == 2


# ---------------------------------------------------------------------------
# 4. result-dependent clause
# ---------------------------------------------------------------------------


class TestResultDependentClause:
    def test_a_retrospective_result_clause_is_answered_from_the_record(self):
        service, investigation = _service()
        message = service.send(f"Investigate {X} and tell me what you find.")

        # the result clause resolved the retained investigation result and did
        # NOT start a second investigation
        assert len(investigation.calls) == 1
        assert _multi(message).get("unhandled") == []
        assert "Investigation result" in message.content

    def test_a_result_request_clause_is_handled_not_dropped(self):
        service, _ = _service()
        message = service.send(f"Investigate {X}, research {Y}, then tell me what you found.")

        assert _multi(message).get("unhandled") == []
        assert "Investigation result" in message.content

    def test_a_summary_clause_is_reported_honestly(self):
        service, investigation = _service()

        message = service.send(
            f"Investigate {X}, research {Y}, and summarize the results."
        )

        # the two owned clauses ran; the summary has no owning surface and is
        # reported as NOT attempted — never silently absorbed or fabricated
        assert investigation.calls == [f"Investigate {X}"]
        assert _state(service)["knowledge"] is True
        assert _multi(message).get("unhandled") == ["summarize the results"]
        assert "not attempted" in message.content


# ---------------------------------------------------------------------------
# 5. partial failure
# ---------------------------------------------------------------------------


class TestPartialFailure:
    def test_an_unowned_clause_does_not_erase_a_completed_one(self):
        service, investigation = _service()

        message = service.send(f"Investigate {X} and approve the change.")

        # the governed clause was neither executed nor claimed
        assert investigation.calls == [f"Investigate {X}"]
        assert _multi(message).get("unhandled") == ["approve the change"]
        # the completed clause's authoritative lifecycle is intact
        assert _state(service)["result"] is True
        assert _state(service)["operation"] == "investigation_request"

    def test_a_failed_clause_is_never_claimed_as_completed(self):
        service, investigation = _service()

        message = service.send(f"Investigate {X} and approve the change.")

        body = message.content
        assert "approve the change" in body
        assert "Nothing was executed or authorized." in body


# ---------------------------------------------------------------------------
# 6. ambiguity / fail-closed
# ---------------------------------------------------------------------------


class TestAmbiguityFailsClosed:
    def test_an_unwired_knowledge_path_leaves_the_clause_unattempted(self):
        # no validated-knowledge provider: the knowledge path does not own the
        # clause, so the compound must not claim it was answered
        service, _ = _service(provider=None)
        object.__setattr__(
            service._builtin_response, "_validated_knowledge_provider", None
        )

        message = service.send(f"Investigate {X} and research {Y}.")

        assert _multi(message).get("handled") == [f"Investigate {X}"]


# ---------------------------------------------------------------------------
# 7. governance is never bypassed by a compound
# ---------------------------------------------------------------------------


class TestGovernance:
    def test_approval_clause_is_not_executed(self):
        service, investigation = _service()
        service.send(f"Investigate {X} and approve the change.")
        # no approval state was created by the compound
        assert _state(service)["operation"] == "investigation_request"

    def test_execution_clause_is_not_executed(self):
        service, investigation = _service()
        message = service.send(f"Research {Y} and execute the change.")
        assert investigation.calls == []
        # the execution clause is reported as NOT executed, never performed
        assert "it was not executed" in message.content
        assert "Recognized additional subrequests" in message.content

    def test_governance_verbs_stay_out_of_the_delegated_handlers(self):
        service, _ = _service()
        handlers = service._DELEGATED_CLAUSE_HANDLERS
        joined = " ".join(name for name, _ in handlers.values())
        for verb in ("approve", "reject", "execute", "autonomy"):
            assert verb not in joined


# ---------------------------------------------------------------------------
# 8. follow-up conversation after a mixed compound
# ---------------------------------------------------------------------------


class TestFollowUps:
    def test_investigation_result_is_still_recallable(self):
        service, _ = _service()
        service.send(f"Investigate {X} and research {Y}.")

        found = service.send("What did you find?")

        assert (found.metadata or {}).get("builtin_intent") == "reference"
        assert "memory service" in found.content

    def test_knowledge_result_is_still_recallable(self):
        service, _ = _service()
        service.send(f"Investigate {X} and research {Y}.")

        follow = service.send("Tell me more about the memory service.")

        assert "## Investigation" not in follow.content

    def test_the_two_lifecycles_are_distinguishable(self):
        service, _ = _service()
        service.send(f"Research {Y} and investigate {X}.")

        state = _state(service)
        assert state["result"] is True        # the investigation result
        assert state["knowledge"] is True     # the knowledge result
        assert state["referent_kinds"].count("operation") == 1


# ---------------------------------------------------------------------------
# 9. decomposition invariants (one decomposition, one ownership per clause)
# ---------------------------------------------------------------------------


class TestDecompositionInvariants:
    def test_a_single_multi_clause_intent_is_never_over_split(self):
        # the anti-over-split guard still protects an enumerative subject
        assert split_intents("Investigate the component that handles references and memory.") == ()
        assert decompose("Investigate the component that handles references and memory.") == ()

    def test_a_comma_separated_subject_is_not_split(self):
        assert split_intents(f"Investigate the memory service, the cache layer") == ()

    def test_the_coordinator_never_fires_inside_a_word(self):
        assert split_intents("Investigate the android thenar handler") == ()

    def test_mixed_operators_split_into_three_clauses(self):
        subjects = tuple(
            sub.subject
            for sub in split_intents(
                f"Investigate {X} and research {Y}, then tell me what you found"
            )
        )
        assert subjects == (f"Investigate {X}", f"research {Y}", "tell me what you found")


# ---------------------------------------------------------------------------
# 10. send()/stream() parity
# ---------------------------------------------------------------------------


class TestSendStreamParity:
    def _run(self, use_stream: bool, text: str):
        provider = _RecordingProvider()
        service, investigation = _service(provider)
        if use_stream:
            content = "".join(service.stream(text))
        else:
            content = service.send(text).content
        return (
            content,
            tuple(investigation.calls),
            _state(service),
            tuple(provider.queries),
        )

    def test_mixed_compound_is_equivalent(self):
        text = f"Investigate {X} and research {Y}."
        assert self._run(False, text) == self._run(True, text)

    def test_reversed_order_is_equivalent(self):
        text = f"Research {Y} and investigate {X}."
        assert self._run(False, text) == self._run(True, text)

    def test_partial_failure_is_equivalent(self):
        text = f"Investigate {X} and approve the change."
        assert self._run(False, text) == self._run(True, text)

    def test_result_dependent_is_equivalent(self):
        text = f"Investigate {X}, research {Y}, and summarize the results."
        assert self._run(False, text) == self._run(True, text)