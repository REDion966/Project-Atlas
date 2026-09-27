"""Step 1 — Open-Ended Conversation.

Closes the two evidenced gaps that prevented useful open-ended, multi-turn
conversation, reusing the EXISTING (already bounded) cognition/model seam:

  * a natural conversational imperative that names no Atlas operation
    ("Tell me a short story about a lighthouse.") was L3-classified as a
    *statement* and refused with the canned deterministic notice — it never
    reached the wired model seam. It is now a REQUEST.
  * the model prompt carried no conversation history (only a count), so a
    model-backed answer had no multi-turn context. The bounded recent-turn
    window is now rendered into the prompt.

Safety boundaries asserted here: Atlas stays the authority (the model produces
text only — no execution/approval/promotion/authorization metadata and no state
mutation), the deterministic floor keeps first opportunity, an unavailable/local
provider falls back deterministically, and the whole path stays model-optional.
"""

from __future__ import annotations

from atlas.cognition.api import CognitionAPI
from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.task_intake import TaskIntake, build_utterance_meaning
from atlas.conversation.utterance_meaning import Illocution
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.planning import PlanningEngine
from atlas.runtime.runtime_coordinator import RuntimeCoordinator
from atlas.services.cognition_service import CognitionService

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
    """Duck-typed ai_service that records the messages it was given."""

    def __init__(self, text="<<MODEL ANSWER>>", identity=NON_LOCAL) -> None:
        self._text = text
        self._identity = identity
        self.calls = 0
        self.seen: list[list[dict[str, str]]] = []

    def chat(self, messages, routing_context=None):
        self.calls += 1
        self.seen.append(list(messages))
        prov, model = self._identity or (None, None)
        return _Response(self._text, prov, model)

    def stream_chat(self, messages, routing_context=None):
        self.calls += 1
        yield self._text


class _RaisingAI(_AI):
    def chat(self, messages, routing_context=None):
        self.calls += 1
        raise RuntimeError("provider unavailable")


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


def _service(identity=NON_LOCAL, model_ai=None, wire_conversation=True):
    registry = CapabilityRegistry()
    registry.register("conversation", lambda p: ExecutionResult(
        capability="conversation", success=True, output={}))
    model_ai = model_ai or _AI(identity=identity)
    coordinator = RuntimeCoordinator(
        reasoning_controller=ReasoningController(),
        capability_analyzer=CapabilityAnalyzer(),
        capability_registry=registry,
        capability_router=CapabilityRouter(registry),
        capability_dispatcher=CapabilityDispatcher(registry),
        planning_engine=PlanningEngine(),
        ai_service=model_ai,
    )
    cognition = CognitionService(runtime_coordinator=coordinator)
    cognition.start()
    recording = _RecordingAPI(CognitionAPI(cognition_service=cognition))
    service = ConversationService(
        _AI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        cognition_api=recording,
    )
    if wire_conversation:
        # Mirrors the kernel composition root (Atlas wires the conversation
        # service onto the runtime coordinator).
        coordinator._conversation_service = service  # noqa: SLF001
    return service, recording, model_ai


# ---------------------------------------------------------------------------
# 1. L3 — natural conversational imperatives are requests (not statements)
# ---------------------------------------------------------------------------


class TestConversationalRequestIllocution:
    def test_conversational_imperatives_are_requests(self):
        for text in (
            "Tell me a short story about a lighthouse.",
            "Give me a fun fact about octopuses.",
            "Show me how to make bread.",
            "Describe how tides work.",
            "Walk me through a typical day.",
            "Summarize the plot of the film.",
        ):
            assert build_utterance_meaning(text).illocution is Illocution.REQUEST, text

    def test_questions_and_plain_statements_are_unchanged(self):
        assert build_utterance_meaning("How does photosynthesis work?").illocution is Illocution.QUESTION
        for text in ("I've been thinking about switching careers.", "...", "Hello."):
            assert build_utterance_meaning(text).illocution is Illocution.STATEMENT, text


# ---------------------------------------------------------------------------
# 2. Conversational integration — the request now reaches the model
# ---------------------------------------------------------------------------


class TestOpenEndedRouting:
    def test_open_ended_request_is_answered_by_the_model(self):
        service, recording, model = _service()
        message = service.send("Tell me a short story about a lighthouse.")
        assert recording.calls == ["Tell me a short story about a lighthouse."]
        assert message.content == "<<MODEL ANSWER>>"
        assert message.metadata.get("model_used") is True

    def test_greeting_and_plain_statement_stay_deterministic(self):
        for text, intent in (("Hello Atlas.", "greeting"),
                             ("...", "unsupported"),
                             ("I've been thinking about switching careers.", "unsupported")):
            service, recording, _model = _service()
            message = service.send(text)
            assert recording.calls == [], text
            assert message.metadata.get("builtin_intent") == intent, text
            assert message.metadata.get("model_used") is not True, text


# ---------------------------------------------------------------------------
# 3. Multi-turn context reaches the model (bounded)
# ---------------------------------------------------------------------------


def _conversation_section(system_content: str) -> str:
    """The '## Conversation Context' section of the model prompt, or ''."""
    marker = "## Conversation Context"
    start = system_content.find(marker)
    if start == -1:
        return ""
    rest = system_content[start + len(marker):]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


class TestMultiTurnContext:
    def test_model_prompt_carries_prior_turns(self):
        service, _recording, model = _service()
        service.send("Tell me about the Eiffel Tower.")
        service.send("Why was it built?")

        assert model.calls == 2
        system = model.seen[-1][0]
        assert system["role"] == "system"
        history = _conversation_section(system["content"])
        assert "Tell me about the Eiffel Tower." in history
        assert "<<MODEL ANSWER>>" in history  # the prior assistant turn
        # The current turn is the user message, never duplicated into history.
        assert "Why was it built?" not in history
        assert model.seen[-1][1] == {"role": "user", "content": "Why was it built?"}

    def test_first_turn_has_no_prior_turns(self):
        service, _recording, model = _service()
        service.send("Tell me a short story.")
        # No prior turns -> no conversation-context section at all.
        assert _conversation_section(model.seen[0][0]["content"]) == ""


# ---------------------------------------------------------------------------
# 4. Safety / authority boundaries
# ---------------------------------------------------------------------------


class TestAuthorityBoundaries:
    def test_model_answer_carries_no_governance_authority(self):
        service, _recording, _model = _service()
        before = service.state_manager.state
        message = service.send("Tell me a short story about a lighthouse.")
        for key in ("approval", "execution", "promotion", "authorization", "planning"):
            assert key not in message.metadata, key
        after = service.state_manager.state
        assert after.pending_approval_id is None
        assert after.last_operation == before.last_operation

    def test_local_tier_is_never_surfaced_and_falls_back_deterministically(self):
        service, recording, _model = _service(identity=LOCAL_TIER)
        message = service.send("Tell me a short story about a lighthouse.")
        assert recording.calls  # delegated ...
        assert message.metadata.get("model_used") is not True
        assert message.metadata.get("builtin_intent") == "unsupported"
        assert "external AI model" in message.content  # the deterministic notice

    def test_provider_failure_falls_back_deterministically(self):
        service, _recording, _model = _service(model_ai=_RaisingAI())
        message = service.send("Tell me a short story about a lighthouse.")
        assert message.metadata.get("model_used") is not True
        assert message.metadata.get("builtin_intent") == "unsupported"
        assert message.content.strip()

    def test_governed_requests_are_not_eligible_for_the_model_seam(self):
        # The bounded eligibility gate (unchanged) excludes every governed
        # task type, so a development/investigation request can never be
        # delegated to the model by this path.
        from atlas.conversation.conversation_service import reasoning_eligibility

        intake = TaskIntake()
        for text in (
            "Add a capability for scheduled follow-ups.",
            "Investigate the conversation state handling.",
        ):
            spec = intake.intake(text)
            assert not spec.task_type.value in ("conversation", "question", "unknown"), text
            assert reasoning_eligibility(spec, "unsupported") is None, text

    def test_deterministic_across_runs(self):
        a, _ra, _ma = _service()
        b, _rb, _mb = _service()
        assert a.send("Tell me a short story.").content == b.send("Tell me a short story.").content
