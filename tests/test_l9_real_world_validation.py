"""L9 — end-to-end real-world language validation (regression net).

This suite is the durable artifact of the L9 validation phase. Every
expectation in :data:`EXPECTED` was captured from the LIVE production path
(``Atlas.start()`` -> ``Atlas.chat()`` / ``Atlas.stream()``) over the bounded
real-world corpus in :data:`CORPUS` (categories A-M of the L9 command), and is
pinned here so the composed L0-L8 behaviour cannot drift silently.

What is pinned:

* the deterministic intake contract per corpus turn: ``task_type``,
  ``needs_clarification``, ambiguity reasons, and the L3 structured utterance
  meaning (illocution + leading operation);
* the L6 fail-closed gate for reference-bearing governed requests;
* Phase 3-5 ownership and the L7 eligibility boundary: cognition is entered
  ONLY for casual/question residual turns, never for a governed one;
* L4/L5 reference retention (``development_intent`` / ``latest_result`` /
  ``current_investigation``) across realistic multi-turn variation;
* L8 response precedence on a delegated turn (a Mock/local-tier answer is never
  surfaced; a trustworthy non-local answer becomes the single response; the
  redundant conversation-level AI call does not run);
* provider-free behaviour, streaming parity, and corpus determinism.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from atlas.cognition.api import CognitionAPI
from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.development_need_coordinator import DevelopmentNeedCoordinator
from atlas.conversation.investigation import InvestigationService
from atlas.conversation.message import Message
from atlas.conversation.task_intake import (
    TaskIntake,
    reconcile_resolved_reference_ambiguity,
)
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.planning import PlanningEngine
from atlas.runtime.runtime_coordinator import RuntimeCoordinator
from atlas.services.cognition_service import CognitionService

# ---------------------------------------------------------------------------
# Corpus (categories A-M). Texts are the single source of truth; expectations
# are keyed by (scenario id, turn index) so no text is duplicated.
# ---------------------------------------------------------------------------

CORPUS: dict[str, tuple[str, ...]] = {
    # A. simple direct requests
    "A1": ("Create a task for backing up the database.",),
    "A2": ("Build a module that tracks long-running tasks.",),
    "A3": ("Research how Atlas currently handles references.",),
    "A4": ("Explain what Atlas does.",),
    "A5": ("What should I work on next?",),
    # B. natural conversational variants
    "B1": ("Can you tell me what Atlas does?",),
    "B2": ("I'd like Atlas to support email notifications.",),
    "B3": ("Could you look into how references work?",),
    "B4": ("I want you to investigate why this is failing.",),
    "B5": ("Please create something that can monitor long-running jobs.",),
    # C. paraphrases of one intent
    "C1": ("Add a capability that sends email notifications.",),
    "C2": ("Build me a capability to send email notifications.",),
    "C3": ("We need a way to send email notifications.",),
    "C4": ("Set up a module that can send email notifications.",),
    "C5": ("Make Atlas able to send email notifications.",),
    "C6": ("Introduce a capability for sending email notifications.",),
    # D. multi-turn references
    "D1": (
        "Create an email notification capability.",
        "Make it send reminders too.",
        "Now explain how that works.",
    ),
    "D2": (
        "Build a capability for scheduled follow-ups.",
        "Develop that capability.",
        "Can you improve it?",
        "What did you change?",
    ),
    # E. demonstratives / references
    "E1": ("Build it.",),
    "E2": ("Use this.",),
    "E3": ("Develop that capability.",),
    "E4": ("Run this.",),
    "E5": ("Summarize them.",),
    "E6": ("Summarize the reference resolution behaviour.", "Summarize them."),
    # F. ambiguous / underspecified
    "F1": ("Fix the thing that's broken.",),
    "F2": ("Make it better.",),
    "F3": ("Improve the module that tracks this.",),
    "F4": ("Deploy this service.",),
    "F5": ("Change it.",),
    # G. questions vs requests vs statements
    "G1": ("What does Atlas do?",),
    "G2": ("Can you explain what Atlas does?",),
    "G3": ("Atlas handles references deterministically.",),
    "G4": ("How does Atlas handle references?",),
    "G5": ("Please investigate the reference resolution flow.",),
    "G6": ("The references are handled by the resolver.",),
    # H. governed domains
    "H1": ("Add a capability for scheduled follow-ups.",),
    "H2": ("Investigate why Atlas cannot answer this question.",),
    "H3": ("Research how Atlas currently handles references.",),
    "H4": ("approve this proposal",),
    "H5": ("reject this proposal",),
    "H6": ("verify the result",),
    "H7": ("give me the final report",),
    "H8": ("execute the approved proposal",),
    "H9": ("prepare a development proposal",),
    # I. casual
    "I1": ("Hello Atlas.",),
    "I2": ("Hi there!",),
    "I3": ("What can you do?",),
    "I4": ("How are you?",),
    "I5": ("Thanks, that helps.",),
    # J. negative / correction / clarification
    "J1": ("No, I meant the other capability.",),
    "J2": ("That's not what I asked.",),
    "J3": ("Use the previous result.",),
    "J4": ("I meant the email service, not the scheduler.",),
    "J5": ("Don't modify anything yet.",),
    # K. longer multi-clause sentences
    "K1": (
        "I want Atlas to investigate why the scheduled task failed and tell me "
        "what part of the system is responsible.",
    ),
    "K2": (
        "Can you create a capability that sends a reminder after a task has "
        "been waiting for more than an hour?",
    ),
    "K3": (
        "Before changing anything, research how Atlas currently handles this "
        "and explain what you find.",
    ),
    "K4": (
        "Please look into why the last development cycle failed, then tell me "
        "what to do next.",
    ),
    # L. noise / linguistic variation
    "L1": ("create a module that tracks long running tasks",),
    "L2": ("BUILD A MODULE THAT TRACKS LONG-RUNNING TASKS.",),
    "L3": (
        "Could you please build a module that tracks long-running tasks? Thanks!",
    ),
    "L4": ("um, so, can you like research how atlas handles references?",),
    "L5": ("Research  how   Atlas handles references.",),
    "L6": ("Pls research how Atlas handles refs",),
    "L7": ("hey atlas!! quick one — what can you do??",),
    "L8": ("What   should I   work on next?",),
    # M. cross-turn context
    "M1": ("Build a capability for scheduled follow-ups.", "Can you improve it?"),
    "M2": (
        "Research how Atlas handles references.",
        "What did you change?",
        "Use the previous result.",
    ),
    "M3": (
        "Investigate the reference resolution flow.",
        "Now explain how that works.",
    ),
    "M4": (
        "Add a capability for email notifications.",
        "That's not what I asked.",
        "I meant the email service, not the scheduler.",
    ),
    # streaming parity
    "S1": ("What should I work on next?",),
    "S2": ("Hello Atlas.",),
    "S3": ("Investigate why Atlas cannot answer this question.",),
}

#: Live-captured contract: task_type, needs_clarification, ambiguity reasons,
#: L3 illocution, L3 operation.
EXPECTED: dict[tuple[str, int], tuple[str, bool, tuple[str, ...], str, str | None]] = {
    ("A1", 0): ("action_request", False, ("success",), "request", "act"),
    ("A2", 0): ("development_request", False, ("success",), "request", "develop"),
    ("A3", 0): ("information_request", False, (), "request", "research"),
    ("A4", 0): ("question", False, (), "request", "explain"),
    ("A5", 0): ("question", False, (), "question", None),
    ("B1", 0): ("question", False, (), "question", None),
    ("B2", 0): ("conversation", False, (), "request", None),
    ("B3", 0): ("question", False, (), "question", None),
    ("B4", 0): ("investigation_request", False, ("reference",), "request", "investigate"),
    ("B5", 0): ("action_request", True, ("reference", "success"), "request", "act"),
    ("C1", 0): ("development_request", False, ("success",), "request", "develop"),
    ("C2", 0): ("development_request", False, ("success",), "request", "develop"),
    ("C3", 0): ("conversation", False, (), "request", None),
    ("C4", 0): ("conversation", False, (), "statement", None),
    ("C5", 0): ("action_request", False, ("success",), "request", "act"),
    ("C6", 0): ("conversation", False, (), "statement", None),
    ("D1", 0): ("action_request", False, ("success",), "request", "act"),
    ("D1", 1): ("action_request", True, ("reference", "success"), "request", "act"),
    ("D1", 2): ("question", False, ("reference",), "statement", "explain"),
    ("D2", 0): ("development_request", False, ("success",), "request", "develop"),
    ("D2", 1): ("development_request", True, ("reference", "success"), "request", "develop"),
    ("D2", 2): ("question", False, ("reference",), "question", "develop"),
    ("D2", 3): ("question", False, (), "question", None),
    ("E1", 0): ("action_request", True, ("reference", "success"), "request", "develop"),
    ("E2", 0): ("conversation", False, ("reference",), "statement", None),
    ("E3", 0): ("development_request", True, ("reference", "success"), "request", "develop"),
    ("E4", 0): ("action_request", True, ("reference", "success"), "request", "act"),
    ("E5", 0): ("action_request", True, ("reference", "success"), "request", "act"),
    ("E6", 0): ("action_request", False, ("success",), "request", "act"),
    ("E6", 1): ("action_request", True, ("reference", "success"), "request", "act"),
    ("F1", 0): ("conversation", False, (), "request", "develop"),
    ("F2", 0): ("action_request", True, ("reference", "success"), "request", "act"),
    ("F3", 0): ("development_request", True, ("reference", "success"), "request", "develop"),
    ("F4", 0): ("action_request", True, ("reference", "success"), "request", "act"),
    ("F5", 0): ("conversation", False, ("reference",), "statement", None),
    ("G1", 0): ("question", False, (), "question", None),
    ("G2", 0): ("question", False, (), "question", "explain"),
    ("G3", 0): ("conversation", False, (), "statement", None),
    ("G4", 0): ("question", False, (), "question", None),
    ("G5", 0): ("investigation_request", False, (), "request", "investigate"),
    ("G6", 0): ("conversation", False, (), "statement", None),
    ("H1", 0): ("development_request", False, ("success",), "request", "develop"),
    ("H2", 0): ("investigation_request", False, ("reference",), "request", "investigate"),
    ("H3", 0): ("information_request", False, (), "request", "research"),
    ("H4", 0): ("approval", False, ("reference",), "statement", None),
    ("H5", 0): ("rejection_request", False, ("reference",), "statement", None),
    ("H6", 0): ("verification_request", False, (), "statement", None),
    ("H7", 0): ("report_request", False, (), "statement", None),
    ("H8", 0): ("execution_request", False, (), "statement", None),
    ("H9", 0): ("planning_request", False, (), "statement", None),
    ("I1", 0): ("conversation", False, (), "statement", None),
    ("I2", 0): ("conversation", False, (), "statement", None),
    ("I3", 0): ("question", False, (), "question", None),
    ("I4", 0): ("conversation", False, (), "question", None),
    ("I5", 0): ("conversation", False, ("reference",), "statement", None),
    ("J1", 0): ("conversation", False, (), "statement", None),
    ("J2", 0): ("question", False, ("reference",), "statement", None),
    ("J3", 0): ("conversation", False, (), "statement", None),
    ("J4", 0): ("conversation", False, (), "statement", None),
    ("J5", 0): ("conversation", False, (), "statement", "develop"),
    ("K1", 0): ("investigation_request", False, (), "request", "investigate"),
    ("K2", 0): ("development_request", False, ("success",), "question", "develop"),
    ("K3", 0): ("information_request", False, ("reference",), "statement", "research"),
    ("K4", 0): ("question", False, (), "request", None),
    ("L1", 0): ("development_request", False, ("success",), "request", "develop"),
    ("L2", 0): ("development_request", False, ("success",), "request", "develop"),
    ("L3", 0): ("development_request", False, ("success",), "question", "develop"),
    ("L4", 0): ("information_request", False, (), "question", "research"),
    ("L5", 0): ("information_request", False, (), "request", "research"),
    ("L6", 0): ("information_request", False, (), "statement", "research"),
    ("L7", 0): ("conversation", False, (), "question", None),
    ("L8", 0): ("question", False, (), "question", None),
    ("M1", 0): ("development_request", False, ("success",), "request", "develop"),
    ("M1", 1): ("question", False, ("reference",), "question", "develop"),
    ("M2", 0): ("information_request", False, (), "request", "research"),
    ("M2", 1): ("question", False, (), "question", None),
    ("M2", 2): ("conversation", False, (), "statement", None),
    ("M3", 0): ("investigation_request", False, (), "request", "investigate"),
    ("M3", 1): ("question", False, ("reference",), "statement", "explain"),
    ("M4", 0): ("development_request", False, ("success",), "request", "develop"),
    ("M4", 1): ("question", False, ("reference",), "statement", None),
    ("M4", 2): ("conversation", False, (), "statement", None),
    ("S1", 0): ("question", False, (), "question", None),
    ("S2", 0): ("conversation", False, (), "statement", None),
    ("S3", 0): ("investigation_request", False, ("reference",), "request", "investigate"),
}

#: Fingerprint of the whole corpus contract (see :func:`corpus_rows`).
CORPUS_DIGEST = "adee784e450d570b"

#: Task types whose handlers own the turn outright: cognition must never
#: receive one of these (Phase 3-5 / governed lifecycle isolation).
GOVERNED_TASK_TYPES = frozenset({
    "action_request",
    "development_request",
    "investigation_request",
    "information_request",
    "approval",
    "rejection_request",
    "verification_request",
    "report_request",
    "execution_request",
    "planning_request",
    "recovery_request",
    "repository_impact_request",
    "autonomy_request",
    "l2_autonomy_request",
    "l3_autonomy_request",
    "l4_autonomy_request",
    "l5_autonomy_request",
})

CASUAL_TASK_TYPES = frozenset({"conversation", "unknown", "question"})

#: Turns the live run showed to be genuinely ambiguous: the deterministic gate
#: must clarify rather than act.
FAIL_CLOSED = ("B5", "E1", "E3", "E4", "E5", "F2", "F3", "F4")

CASES = [(sid, i) for sid, turns in CORPUS.items() for i in range(len(turns))]


def corpus_rows() -> list[list]:
    """The corpus contract as rows (the digest is computed over this)."""
    intake = TaskIntake()
    rows = []
    for sid, index in CASES:
        spec = intake.intake(CORPUS[sid][index])
        meaning = spec.context["utterance_meaning"]
        rows.append([
            sid, index, spec.task_type.value, spec.needs_clarification,
            sorted(spec.ambiguity.ambiguities), meaning["illocution"],
            meaning["operation"],
        ])
    return rows


class TestCorpusContract:
    def test_corpus_is_intact(self):
        assert len(CORPUS) == 73
        assert len(CASES) == 85
        assert set(EXPECTED) == set(CASES)

    @pytest.mark.parametrize(("sid", "index"), CASES, ids=[f"{s}-{i}" for s, i in CASES])
    def test_intake_contract(self, sid, index):
        expected = EXPECTED[(sid, index)]
        intake = TaskIntake()
        spec = intake.intake(CORPUS[sid][index])
        meaning = spec.context["utterance_meaning"]
        actual = (
            spec.task_type.value,
            spec.needs_clarification,
            tuple(spec.ambiguity.ambiguities),
            meaning["illocution"],
            meaning["operation"],
        )
        assert actual == expected

    def test_corpus_digest_is_stable(self):
        digest = hashlib.sha256(
            json.dumps(corpus_rows(), sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        assert digest == CORPUS_DIGEST

    def test_corpus_determinism_across_repeated_evaluation(self):
        assert corpus_rows() == corpus_rows()


class TestAmbiguityGate:
    def test_only_action_and_development_requests_may_need_clarification(self):
        for sid, index in CASES:
            spec = TaskIntake().intake(CORPUS[sid][index])
            if spec.needs_clarification:
                assert spec.task_type.value in ("action_request", "development_request"), sid

    def test_clarification_requires_the_global_threshold(self):
        for sid, index in CASES:
            spec = TaskIntake().intake(CORPUS[sid][index])
            if spec.needs_clarification:
                assert spec.ambiguity.ambiguity_score >= 0.5, sid
            elif spec.task_type.value in ("action_request", "development_request"):
                assert spec.ambiguity.ambiguity_score < 0.5, sid

    @pytest.mark.parametrize("sid", FAIL_CLOSED)
    def test_ambiguous_reference_turns_stay_fail_closed(self, sid):
        spec = TaskIntake().intake(CORPUS[sid][0])
        assert spec.needs_clarification is True
        assert "reference" in spec.ambiguity.ambiguities
        assert spec.ambiguity.clarification_questions

    def test_negated_development_cue_is_not_a_development_request(self):
        # "Don't modify anything yet." is a boundary statement, not a request.
        spec = TaskIntake().intake(CORPUS["J5"][0])
        assert spec.task_type.value == "conversation"
        assert spec.needs_clarification is False

    def test_relative_complementizer_does_not_raise_reference(self):
        # "Build a module that tracks long-running tasks." -> no reference reason.
        spec = TaskIntake().intake(CORPUS["A2"][0])
        assert "reference" not in spec.ambiguity.ambiguities
        # A genuine demonstrative in the same shape still does (mixed case).
        mixed = TaskIntake().intake(CORPUS["F3"][0])
        assert "reference" in mixed.ambiguity.ambiguities


class TestL3MeaningContract:
    def test_questions_and_requests_are_distinguished_for_the_same_intent(self):
        intake = TaskIntake()
        question = intake.intake(CORPUS["G4"][0]).context["utterance_meaning"]
        request = intake.intake(CORPUS["A3"][0]).context["utterance_meaning"]
        assert question["illocution"] == "question"
        assert request["illocution"] == "request"
        assert question["operation"] is None and request["operation"] == "research"

    def test_leading_operation_wins_over_a_later_cue(self):
        # "Research how Atlas could improve X" leads with research.
        meaning = TaskIntake().intake(
            "Research how Atlas could improve the reference resolver."
        )
        assert meaning.task_type.value == "information_request"
        assert meaning.context["utterance_meaning"]["operation"] == "research"

    def test_meaning_is_json_safe_and_carried_on_the_spec(self):
        spec = TaskIntake().intake(CORPUS["K2"][0])
        json.dumps(spec.context["utterance_meaning"])
        assert spec.context["utterance_meaning"]["operation"] == "develop"


# ---------------------------------------------------------------------------
# End-to-end routing / ownership / isolation, on a kernel-shaped service.
# ---------------------------------------------------------------------------

NON_LOCAL = ("Stub Provider", "stub-1")
LOCAL_TIER = ("Mock Provider", "atlas-mock-v1")


class _Response:
    def __init__(self, text, provider=None, model=None) -> None:
        self.text = text
        if provider is not None:
            self.provider = provider
        if model is not None:
            self.model = model


class _AI:
    def __init__(self, text="CHAT ANSWER", identity=None) -> None:
        self._text = text
        self._identity = identity
        self.calls = 0

    def chat(self, messages, routing_context=None):
        self.calls += 1
        provider, model = self._identity or (None, None)
        return _Response(self._text, provider, model)

    def stream_chat(self, messages, routing_context=None):
        self.calls += 1
        yield self._text


class _RecordingAPI:
    def __init__(self, inner) -> None:
        self._inner = inner
        self.calls: list[str] = []

    def process(self, user_input, memory=None, metadata=None, goal=None,
                turn_meaning=None):
        self.calls.append(user_input)
        return self._inner.process(
            user_input=user_input, memory=memory, metadata=metadata,
            goal=goal, turn_meaning=turn_meaning,
        )


def _pipeline(ai_service):
    registry = CapabilityRegistry()
    registry.register("conversation", lambda p: ExecutionResult(
        capability="conversation", success=True, output={}))
    coordinator = RuntimeCoordinator(
        reasoning_controller=ReasoningController(),
        capability_analyzer=CapabilityAnalyzer(),
        capability_registry=registry,
        capability_router=CapabilityRouter(registry),
        capability_dispatcher=CapabilityDispatcher(registry),
        planning_engine=PlanningEngine(),
        ai_service=ai_service,
    )
    service = CognitionService(runtime_coordinator=coordinator)
    service.start()
    return CognitionAPI(cognition_service=service)


def _service(pipeline_ai=None, chat_ai=None, cognition=True,
             orchestration_result=None, bridge_specs=None):
    """A service wired like the kernel (same collaborators, bounded stubs)."""
    pipeline = _pipeline(pipeline_ai or _AI("PIPELINE ANSWER", LOCAL_TIER))
    recording = _RecordingAPI(pipeline) if cognition else None

    def _bridge(spec):
        if bridge_specs is not None:
            bridge_specs.append(spec)
        return Message(role="assistant", content="DEVELOPMENT", metadata={})

    def _resolver(spec, session_context):
        return orchestration_result

    service = ConversationService(
        chat_ai or _AI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        cognition_api=recording,
        orchestration_resolver=_resolver,
        development_bridge=_bridge,
        investigation_service=InvestigationService(),
        development_need_coordinator=DevelopmentNeedCoordinator(),
    )
    return service, recording


class TestGovernedOwnership:
    @pytest.mark.parametrize(("sid", "index"), [
        ("H1", 0), ("H2", 0), ("H3", 0), ("H4", 0), ("H5", 0), ("H6", 0),
        ("H7", 0), ("H8", 0), ("H9", 0), ("A2", 0), ("A3", 0), ("B4", 0),
        ("G5", 0), ("K1", 0), ("K2", 0), ("M4", 0),
    ], ids=lambda v: str(v))
    def test_governed_turns_never_reach_cognition(self, sid, index):
        service, recording = _service()
        message = service.send(CORPUS[sid][index])
        assert recording.calls == []
        assert message.content.strip()

    def test_development_request_keeps_the_development_bridge(self):
        service, _recording = _service()
        assert service.send(CORPUS["H1"][0]).content == "DEVELOPMENT"

    def test_investigation_request_keeps_the_investigation_handler(self):
        service, _recording = _service()
        message = service.send(CORPUS["H2"][0])
        assert message.metadata.get("investigation") is not None

    def test_l6_clarification_precedes_cognition(self):
        for sid in ("E1", "E3", "E4", "E5", "F4"):
            service, recording = _service()
            message = service.send(CORPUS[sid][0])
            assert recording.calls == [], sid
            assert "more detail" in message.content, sid


class TestCasualFloorAndDelegation:
    def test_greeting_stays_on_the_deterministic_floor(self):
        service, recording = _service()
        message = service.send(CORPUS["I1"][0])
        assert recording.calls == []
        assert message.metadata.get("builtin_intent") == "greeting"

    def test_help_question_is_answered_deterministically(self):
        service, recording = _service()
        message = service.send(CORPUS["I3"][0])
        assert recording.calls == []
        assert message.metadata.get("builtin_intent") == "help"

    def test_eligible_open_question_is_delegated(self):
        service, recording = _service(
            pipeline_ai=_AI("PIPELINE ANSWER", NON_LOCAL)
        )
        message = service.send(CORPUS["A5"][0])
        assert recording.calls == [CORPUS["A5"][0]]
        assert message.content == "PIPELINE ANSWER"

    def test_local_mock_answer_is_never_surfaced_for_a_corpus_turn(self):
        chat_ai = _AI()
        service, recording = _service(
            pipeline_ai=_AI("Hello! I am Atlas's first AI provider.", LOCAL_TIER),
            chat_ai=chat_ai,
        )
        message = service.send(CORPUS["B1"][0])
        assert recording.calls == [CORPUS["B1"][0]]
        assert "first AI provider" not in message.content
        assert chat_ai.calls == 0
        assert message.metadata.get("builtin_intent") == "unsupported"

    def test_provider_free_operation_stays_deterministic(self):
        pipeline = _pipeline(None)
        service = ConversationService(
            _AI(),
            task_intake=TaskIntake(),
            builtin_response=BuiltinResponseService(),
            cognition_api=_RecordingAPI(pipeline),
        )
        message = service.send(CORPUS["A5"][0])
        assert message.content.strip()
        assert message.metadata.get("builtin_intent") == "unsupported"

    def test_streaming_parity_for_corpus_turns(self):
        for sid in ("S1", "S2"):
            sent = _service()[0].send(CORPUS[sid][0]).content
            streamed = "".join(_service()[0].stream(CORPUS[sid][0]))
            assert streamed == sent, sid

    def test_streaming_reaches_the_same_governed_handler(self):
        service, recording = _service()
        streamed = "".join(service.stream(CORPUS["S3"][0]))
        assert recording.calls == []
        assert streamed.startswith("## Investigation")


class TestReferenceReconciliationBoundary:
    def test_bound_reference_clears_only_the_reference_reason(self):
        raw = TaskIntake().intake(CORPUS["D2"][1])
        assert raw.needs_clarification is True
        reconciled = reconcile_resolved_reference_ambiguity(raw)
        assert reconciled.ambiguity.ambiguities == ("success",)
        assert reconciled.needs_clarification is False

    def test_unbound_spec_is_returned_unchanged(self):
        raw = TaskIntake().intake(CORPUS["A1"][0])
        same = reconcile_resolved_reference_ambiguity(raw)
        assert same is raw
        assert same.to_dict() == raw.to_dict()


class TestContextRetention:
    def test_development_antecedent_survives_a_reference_only_follow_up(self):
        bridge_specs: list = []
        service, recording = _service(bridge_specs=bridge_specs)
        service.send(CORPUS["D2"][0])
        message = service.send(CORPUS["D2"][1])
        assert recording.calls == []
        assert message.content == "DEVELOPMENT"
        resolved = bridge_specs[-1].context.get("resolved_reference")
        assert resolved is not None
        assert resolved["field"] == "development_intent"
        assert "scheduled follow-ups" in resolved["value"]

    def test_research_result_is_recallable_across_turns(self):
        result = Message(
            role="assistant",
            content="Done: Research how Atlas handles references.",
            metadata={"orchestration": {"status": "completed"}},
        )
        service, recording = _service(orchestration_result=result)
        service.send(CORPUS["M2"][0])
        message = service.send("Use the previous result.")
        assert recording.calls == []
        assert message.metadata.get("builtin_intent") == "reference"
        assert "Research how Atlas handles references" in message.content

    def test_investigation_subject_is_recallable_across_turns(self):
        service, recording = _service()
        service.send(CORPUS["M3"][0])
        message = service.send(CORPUS["M3"][1])
        assert recording.calls == []
        assert message.metadata.get("builtin_intent") == "reference"

    def test_context_never_leaks_a_raw_state_object(self):
        service, _recording = _service()
        service.send(CORPUS["M2"][0])
        message = service.send("Use the previous result.")
        json.dumps(message.metadata)
        assert "latest_result" not in message.content
