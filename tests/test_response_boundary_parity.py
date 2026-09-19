"""L8 — response boundary: the user-facing stream path composes the same
deterministic, governed responses as the send path.

Validated limitation: ``ConversationService.stream()`` — the only path the
shipped CLI uses — implemented a SUBSET of the response producers that
``send()`` implements. A bounded repository impact-analysis request and a
development-need confirmation reply were therefore never composed on the
user-facing boundary: the turn fell through the entire governed cascade and
was answered by the provider path (or by the generic unsupported response),
even though Atlas holds a deterministic, read-only, governed response for it.

These tests establish the response-boundary contract behaviourally: the same
turn produces the same composed response on both paths, the structured result
is preserved, the provider is never contacted for a deterministically
answerable turn, and the pending confirmation is actually consumed.

No provider network call is made anywhere in this module.
"""

from __future__ import annotations

import unittest

from atlas.authority.service import AuthorityService
from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.development_need_coordinator import DevelopmentNeedCoordinator
from atlas.conversation.message import Message
from atlas.conversation.task_intake import TaskIntake
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager

IMPACT = "What would be affected if I change atlas/conversation/builtin_response.py?"
IMPACT_ALT = "what depends on atlas/memory/manager.py"
UNRESOLVED_ACTION = "Summarize the tradeoffs of caching."
CONFIRMATION = "yes"
DEGRADED_NOTICE = "External AI inference is currently unavailable"


class _RecordingFailingAI:
    """Any provider contact is recorded and then fails.

    A deterministically answerable turn must never reach this object.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def chat(self, prompt, routing_context=None):
        self.calls.append("chat")
        raise RuntimeError("provider must not be contacted")

    def stream_chat(self, prompt, routing_context=None):
        self.calls.append("stream_chat")

        def _generator():
            raise RuntimeError("provider must not be contacted")
            yield ""  # pragma: no cover

        return _generator()


def _impact_service(ai=None) -> ConversationService:
    return ConversationService(
        ai if ai is not None else _RecordingFailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
    )


def _confirmation_service(bridge, coordinator) -> ConversationService:
    return ConversationService(
        _RecordingFailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        orchestration_resolver=lambda spec, context: None,
        development_need_coordinator=coordinator,
        development_bridge=bridge,
    )


def _governed_bridge(spec) -> Message:
    return Message(
        role="assistant",
        content=f"GOVERNED:{spec.task_type.value}",
    )


def _session_context() -> SessionContext:
    """A real, owner-attributed session (the confirmation path is fail-closed
    without an authoritative session context)."""
    authority = AuthorityService("Owner")
    authority.add_user("Alice", principal_id="alice")
    manager = SessionManager(authority)
    return SessionContext.from_session(manager.create_session("alice"))


class TestRepositoryImpactAtTheUserFacingBoundary(unittest.TestCase):
    """A bounded repository impact request composes its result on stream()."""

    def test_stream_composes_the_impact_result(self):
        ai = _RecordingFailingAI()
        service = _impact_service(ai)

        content = "".join(service.stream(IMPACT))

        self.assertIn("Repository Impact Analysis", content)
        self.assertNotIn(DEGRADED_NOTICE, content)
        self.assertEqual(ai.calls, [], "the provider path must not be used")

    def test_stream_carries_the_structured_result(self):
        service = _impact_service()

        list(service.stream(IMPACT))

        assistant = service.conversation.messages[-1]
        self.assertEqual(assistant.role, "assistant")
        payload = assistant.metadata["repository_impact"]
        self.assertIn("status", payload)
        self.assertIn("resolved_module", payload)
        # The read-only capability records its result like the send path does.
        self.assertIsNotNone(service.state_manager.state.latest_result)

    def test_send_and_stream_compose_the_same_response(self):
        sent = _impact_service().send(IMPACT)

        streamed_service = _impact_service()
        streamed = "".join(streamed_service.stream(IMPACT))

        self.assertEqual(streamed, sent.content)
        self.assertEqual(
            sorted(streamed_service.conversation.messages[-1].metadata),
            sorted(sent.metadata),
        )

    def test_alternate_phrasing_also_composes(self):
        content = "".join(_impact_service().stream(IMPACT_ALT))
        self.assertIn("Repository Impact Analysis", content)

    def test_impact_composition_is_deterministic(self):
        first = "".join(_impact_service().stream(IMPACT))
        second = "".join(_impact_service().stream(IMPACT))
        self.assertEqual(first, second)

    def test_unrelated_turns_are_unaffected(self):
        service = _impact_service()
        content = "".join(service.stream("hello"))
        self.assertIn("model-independent operating framework", content)
        self.assertFalse(
            (service.conversation.messages[-1].metadata or {}).get(
                "repository_impact"
            )
        )


class TestDevelopmentNeedConfirmationAtTheUserFacingBoundary(unittest.TestCase):
    """A confirmation reply is consumed on the user-facing boundary."""

    def test_stream_surfaces_the_need_and_records_the_confirmation(self):
        coordinator = DevelopmentNeedCoordinator()
        service = _confirmation_service(_governed_bridge, coordinator)

        content = "".join(service.stream(UNRESOLVED_ACTION, session_context=_session_context()))

        self.assertIn("could not be resolved", content)
        self.assertTrue(coordinator.has_pending)

    def test_stream_consumes_the_confirmation_reply(self):
        coordinator = DevelopmentNeedCoordinator()
        service = _confirmation_service(_governed_bridge, coordinator)
        session = _session_context()
        list(service.stream(UNRESOLVED_ACTION, session_context=session))
        self.assertTrue(coordinator.has_pending)

        content = "".join(service.stream(CONFIRMATION, session_context=session))

        self.assertFalse(
            coordinator.has_pending,
            "the confirmation reply must be consumed, not dropped",
        )
        self.assertIn("GOVERNED:development_request", content)
        self.assertNotIn("cannot answer", content)

    def test_send_and_stream_resolve_the_same_confirmation(self):
        sent_coordinator = DevelopmentNeedCoordinator()
        sent_service = _confirmation_service(_governed_bridge, sent_coordinator)
        sent_session = _session_context()
        sent_service.send(UNRESOLVED_ACTION, session_context=sent_session)
        sent = sent_service.send(CONFIRMATION, session_context=sent_session).content

        streamed_coordinator = DevelopmentNeedCoordinator()
        streamed_service = _confirmation_service(
            _governed_bridge, streamed_coordinator
        )
        streamed_session = _session_context()
        list(streamed_service.stream(UNRESOLVED_ACTION, session_context=streamed_session))
        streamed = "".join(
            streamed_service.stream(CONFIRMATION, session_context=streamed_session)
        )

        self.assertEqual(streamed, sent)
        self.assertEqual(
            streamed_coordinator.has_pending, sent_coordinator.has_pending
        )

    def test_ordinary_input_without_a_pending_need_is_unchanged(self):
        coordinator = DevelopmentNeedCoordinator()
        service = _confirmation_service(_governed_bridge, coordinator)

        content = "".join(service.stream("hello"))

        self.assertIn("model-independent operating framework", content)
        self.assertFalse(coordinator.has_pending)


if __name__ == "__main__":
    unittest.main()
