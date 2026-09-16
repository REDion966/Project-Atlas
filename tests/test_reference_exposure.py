"""C7 GAP-C31-02 — bounded reference/context exposure tests.

Covers the production ConversationService.send() exposure of the existing
deterministic resolver: bounded multi-word detection, RESOLVED structured
context attachment, AMBIGUOUS clarification (never guesses), UNRESOLVED /
non-reference fail-closed behavior, model independence, and read-only
governance.
"""

from __future__ import annotations

from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import ConversationState
from atlas.conversation.message import Message
from atlas.conversation.reference_resolution import (
    ConversationReferenceResolver,
    ReferenceResolutionStatus,
)
from atlas.conversation.task_intake import TaskIntake


class _CountingFailingAI:
    calls = 0

    def chat(self, prompt, routing_context=None):
        _CountingFailingAI.calls += 1
        raise RuntimeError("No AI available")

    def stream_chat(self, prompt, routing_context=None):
        _CountingFailingAI.calls += 1

        def _g():
            raise RuntimeError("No AI available")
            yield ""  # pragma: no cover

        return _g()


class _SpyResolver:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._inner = ConversationReferenceResolver()

    def resolve(self, query, state):
        self.calls.append(query)
        return self._inner.resolve(query, state)


def _service() -> ConversationService:
    _CountingFailingAI.calls = 0
    return ConversationService(
        ai_service=_CountingFailingAI(),
        task_intake=TaskIntake(),
    )


# ---------------------------------------------------------------------------
# Unit: _apply_reference_resolution
# ---------------------------------------------------------------------------


class TestApplyReferenceResolution:
    def test_no_bounded_reference_returns_spec_unchanged(self):
        service = _service()
        spec = TaskIntake().intake("How is the quality of the output?")
        out_spec, response = service._apply_reference_resolution(spec, spec.goal)
        assert out_spec is spec
        assert response is None

    def test_false_positive_does_not_invoke_resolver(self):
        service = _service()
        spy = _SpyResolver()
        service._reference_resolver = spy
        spec = TaskIntake().intake("What is the priority of the release?")
        service._apply_reference_resolution(spec, "What is the priority of the release?")
        assert spy.calls == []

    def test_resolved_attaches_structured_context(self):
        service = _service()
        service.state_manager.update(
            current_investigation="memory architecture"
        )
        spec = TaskIntake().intake("Based on that investigation, what next?")
        out_spec, response = service._apply_reference_resolution(
            spec, "Based on that investigation, what next?"
        )
        assert response is None
        assert out_spec.context["resolved_reference"] == {
            "field": "current_investigation",
            "value": "memory architecture",
        }
        # original spec is not mutated (frozen)
        assert "resolved_reference" not in spec.context

    def test_ambiguous_returns_existing_clarification(self):
        service = _service()
        service.state_manager.update(
            current_investigation="inv-1", latest_result="result-1"
        )
        spec = TaskIntake().intake("what did you find?")
        out_spec, response = service._apply_reference_resolution(
            spec, "what did you find?"
        )
        assert response is not None
        assert "I need a bit more detail" in response.content
        assert out_spec is spec  # routing spec preserved

    def test_unresolved_returns_spec_unchanged(self):
        service = _service()  # empty state
        spec = TaskIntake().intake("what did you find?")
        out_spec, response = service._apply_reference_resolution(
            spec, "what did you find?"
        )
        assert out_spec is spec
        assert response is None


# ---------------------------------------------------------------------------
# Integration: send()
# ---------------------------------------------------------------------------


class TestSendIntegration:
    def test_non_reference_turn_unchanged(self):
        service = _service()
        response = service.send("How is the quality of the output?")
        assert response.role == "assistant"
        assert "I need a bit more detail" not in response.content
        assert service.state_manager.state.current_task is None

    def test_false_positive_turns_do_not_resolve(self):
        service = _service()
        spy = _SpyResolver()
        service._reference_resolver = spy
        for text in (
            "What is the priority of the release?",
            "Is the architecture documented?",
            "Please summarise the repository structure.",
            "We voted against the rule.",
        ):
            service.send(text)
        assert spy.calls == []

    def test_ambiguous_reference_clarifies_without_guessing(self):
        service = _service()
        service.state_manager.update(
            current_investigation="inv-1", latest_result="result-1"
        )
        response = service.send("what did you find?")
        assert "I need a bit more detail" in response.content
        assert "Multiple plausible" in response.content
        # deterministic clarification, no model call
        assert _CountingFailingAI.calls == 0

    def test_unresolved_reference_preserves_routing(self):
        service = _service()  # empty state
        response = service.send("what did you find?")
        # Not forced into a clarification; routing behaves as before.
        assert "I need a bit more detail" not in response.content

    def test_resolved_reference_reaches_routing_once_with_context(
        self, monkeypatch
    ):
        service = _service()
        service.state_manager.update(current_investigation="memory architecture")
        captured = []

        def fake_investigation(spec, original_text=None):
            captured.append((spec, original_text))
            return Message(role="assistant", content="stub investigation")

        monkeypatch.setattr(
            service, "_maybe_handle_investigation_request", fake_investigation
        )
        text = "Based on that investigation, what should I do next?"
        response = service.send(text)
        assert response.content == "stub investigation"
        assert len(captured) == 1  # single routing pass
        spec, original_text = captured[0]
        assert original_text == text  # original message preserved
        assert spec.context["resolved_reference"]["field"] == "current_investigation"
        assert spec.context["resolved_reference"]["value"] == "memory architecture"

    def test_unsupported_plural_reference_not_resolved(self):
        service = _service()
        service.state_manager.update(current_task="task-1")
        spy = _SpyResolver()
        service._reference_resolver = spy
        service.send("Which of those components depend on it?")
        assert spy.calls == []  # outside first scope; guard blocks invocation

    def test_reference_exposure_is_read_only_and_governed(self):
        service = _service()
        service.state_manager.update(
            current_investigation="inv-1", latest_result="result-1"
        )
        response = service.send("what did you find?")
        meta = dict(getattr(response, "metadata", {}) or {})
        assert "execution" not in meta
        assert "approval" not in meta

    def test_ambiguous_reference_is_deterministic(self):
        service = _service()
        service.state_manager.update(
            current_investigation="inv-1", latest_result="result-1"
        )
        first = service.send("what did you find?").content
        second = service.send("what did you find?").content
        assert first == second
