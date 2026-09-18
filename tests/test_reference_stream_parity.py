"""Phase 6 — send/stream parity for bounded reference resolution (no provider)."""

from __future__ import annotations

import unittest

from atlas.conversation.builtin_response import (
    BuiltinResponseService,
    _MAX_CONVERSATION_RECALL_CHARS,
)
from atlas.conversation.conversation_context import (
    MAX_CONTEXT_CHARS,
    MAX_CONTEXT_TURNS,
)
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationService
from atlas.conversation.task_intake import TaskIntake

CONTINUATION_STATE = {"current_task": "task-1", "current_investigation": "inv-1"}
RESOLVED_STATE = {"current_investigation": "memory architecture"}

NON_REFERENCE = "How is the quality of the output?"
RESOLVED_TEXT = "Based on that investigation, what next?"
AMBIGUOUS_TEXT = "continue with that"
UNRESOLVED_TEXT = "what did you find?"
CLARIFICATION = "I need a bit more detail"


class _FailingAI:
    def chat(self, prompt, routing_context=None):
        raise RuntimeError("No AI available")

    def stream_chat(self, prompt, routing_context=None):
        def _g():
            raise RuntimeError("No AI available")
            yield ""  # pragma: no cover

        return _g()


def _service(investigation: bool = False) -> ConversationService:
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        investigation_service=InvestigationService() if investigation else None,
    )


def _spy(service: ConversationService) -> list:
    calls: list = []
    original = service._apply_reference_resolution

    def wrapper(spec, text):
        out_spec, response = original(spec, text)
        calls.append((dict(out_spec.context or {}), response))
        return out_spec, response

    service._apply_reference_resolution = wrapper
    return calls


def _send(state_seed, text, investigation=False):
    service = _service(investigation)
    service.state_manager.update(**state_seed)
    return service.send(text)


def _stream(state_seed, text, investigation=False, spy=False):
    service = _service(investigation)
    service.state_manager.update(**state_seed)
    calls = _spy(service) if spy else None
    chunks = list(service.stream(text))
    return chunks, calls, service


class TestSendStreamParity(unittest.TestCase):
    def test_non_reference_parity(self):
        sent = _send({}, NON_REFERENCE).content
        chunks, calls, _ = _stream({}, NON_REFERENCE, spy=True)
        self.assertEqual("".join(chunks), sent)
        self.assertNotIn(CLARIFICATION, sent)
        self.assertIsNone(calls[0][1])

    def test_lexicon_resolved_parity(self):
        sent = _send(RESOLVED_STATE, RESOLVED_TEXT).content
        chunks, calls, _ = _stream(RESOLVED_STATE, RESOLVED_TEXT, spy=True)
        self.assertTrue(calls, "stream must invoke reference resolution")
        self.assertEqual(
            calls[0][0].get("resolved_reference"),
            {"field": "current_investigation", "value": "memory architecture"},
        )
        self.assertIsNone(calls[0][1], "RESOLVED must not produce a clarification")
        self.assertTrue(chunks)
        self.assertNotIn(CLARIFICATION, chunks[0])
        self.assertEqual("".join(chunks), sent)

    def test_lexicon_ambiguous_parity(self):
        sent = _send(CONTINUATION_STATE, AMBIGUOUS_TEXT)
        self.assertIn(CLARIFICATION, sent.content)
        chunks, calls, _ = _stream(CONTINUATION_STATE, AMBIGUOUS_TEXT, spy=True)
        self.assertIsNotNone(calls[0][1], "AMBIGUOUS must produce the clarification")
        self.assertEqual(len(chunks), 1, "AMBIGUOUS must stop routing after one chunk")
        self.assertEqual(chunks[0], sent.content)

    def test_lexicon_unresolved_parity(self):
        sent = _send({}, UNRESOLVED_TEXT).content
        chunks, calls, _ = _stream({}, UNRESOLVED_TEXT, spy=True)
        self.assertIsNone(calls[0][1])
        self.assertEqual("".join(chunks), sent)
        self.assertNotIn(CLARIFICATION, "".join(chunks))


class TestStreamReferenceBehaviour(unittest.TestCase):
    def test_ambiguous_stops_routing_without_governed_handler(self):
        service = _service()
        service.state_manager.update(**CONTINUATION_STATE)
        invoked: list = []
        service._maybe_handle_investigation_request = lambda *a, **k: invoked.append("inv")
        service._maybe_handle_development_request = lambda *a, **k: invoked.append("dev")
        chunks = list(service.stream(AMBIGUOUS_TEXT))
        self.assertEqual(len(chunks), 1)
        self.assertIn(CLARIFICATION, chunks[0])
        self.assertEqual(invoked, [])

    def test_resolution_message_carries_no_authority(self):
        service = _service()
        service.state_manager.update(**CONTINUATION_STATE)
        list(service.stream(AMBIGUOUS_TEXT))
        message = service._conversation.messages[-1]
        self.assertNotIn("execution", message.metadata or {})
        self.assertNotIn("approval", message.metadata or {})

    def test_phase5_recall_still_works_on_stream(self):
        service = _service()
        service.send("hello")
        chunks = list(service.stream("What did I ask earlier?"))
        self.assertTrue(chunks)
        self.assertIn("hello", chunks[0])

    def test_investigation_stream_still_governed(self):
        service = _service(investigation=True)
        chunks = list(service.stream("Investigate the conversation system."))
        self.assertTrue(chunks)
        self.assertIn("Investigation", chunks[0])

    def test_capability_response_unchanged_on_stream(self):
        chunks, _, service = _stream({}, "What can you currently do?")
        self.assertTrue(chunks)
        self.assertNotIn(CLARIFICATION, chunks[0])
        self.assertEqual(
            service._conversation.messages[-1].metadata.get("builtin_intent"),
            "capabilities",
        )

    def test_blocks_are_unchanged(self):
        self.assertEqual(MAX_CONTEXT_TURNS, 10)
        self.assertEqual(MAX_CONTEXT_CHARS, 500)
        self.assertEqual(_MAX_CONVERSATION_RECALL_CHARS, 400)


if __name__ == "__main__":
    unittest.main()
