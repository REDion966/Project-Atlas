"""P15.2 — Conversation Continuity Verification.

Proves the CURRENT Atlas conversation runtime preserves context across
multiple turns through the canonical entry point (ConversationService.send)
and correctly resolves references to previously established context.

Continuity mechanisms exercised:
  1. conversation.messages accumulates across turns (same service instance)
  2. ConversationState persists across turns (investigation records state)
  3. ConversationReferenceResolver resolves Turn-2 references against Turn-1 state
  4. Cross-session isolation: independent services do not share context
"""

from __future__ import annotations

import unittest

from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationService
from atlas.conversation.message import Message
from atlas.conversation.reference_resolution import ReferenceResolutionStatus
from atlas.conversation.task_intake import TaskIntake


class _FailingAIService:
    """Mock AI service that always fails, forcing deterministic fallback."""

    def chat(self, prompt, routing_context=None):
        raise RuntimeError("No active AI provider selected.")

    def stream_chat(self, prompt, routing_context=None):
        def _generator():
            raise ConnectionError("No active AI provider selected.")
            yield ""  # pragma: no cover

        return _generator()


class TestConversationContinuity(unittest.TestCase):
    """Multi-turn continuity through the canonical ConversationService.send path."""

    def _make_service(self) -> ConversationService:
        return ConversationService(
            ai_service=_FailingAIService(),
            task_intake=TaskIntake(),
            investigation_service=InvestigationService(),
        )

    # ------------------------------------------------------------------
    # Same-session continuity
    # ------------------------------------------------------------------

    def test_turn1_investigation_establishes_state(self):
        """Turn 1 investigation records context into ConversationState."""
        service = self._make_service()

        turn1 = "investigate the memory subsystem"
        response1 = service.send(turn1)

        self.assertIsInstance(response1, Message)
        self.assertEqual(response1.role, "assistant")

        # State must record the investigation established in Turn 1.
        state = service.state_manager.state
        self.assertIsNotNone(state.current_investigation)
        self.assertIn("memory", state.current_investigation.lower())

        # Conversation history must contain the Turn-1 exchange.
        roles = [m.role for m in service.conversation.messages]
        self.assertIn("user", roles)
        self.assertIn("assistant", roles)
        self.assertEqual(service.conversation.messages[0].content, turn1)

    def test_turn2_reference_resolves_to_turn1_context(self):
        """Turn 2 reference uses Turn 1 state (continuity).

        After Turn 1, both ``current_investigation`` and ``latest_result``
        are set by the investigation handler. The reference "what did you
        find?" maps to both fields, so the resolver correctly reports
        AMBIGUITY (its contract: never guess). The key continuity property
        is that BOTH candidates come from Turn 1's established context.
        """
        service = self._make_service()

        # Turn 1: establish investigation context.
        turn1 = "investigate the memory subsystem"
        service.send(turn1)

        state_after_turn1 = service.state_manager.state
        self.assertIsNotNone(state_after_turn1.current_investigation)
        investigation_target = state_after_turn1.current_investigation
        latest = state_after_turn1.latest_result
        self.assertIsNotNone(latest)

        # Turn 2: reference requiring Turn-1 context.
        result = service.resolve_reference("what did you find?")

        # Both fields are set by Turn 1, so the resolver correctly flags
        # ambiguity rather than guessing. Continuity is proven because the
        # candidates are exactly the Turn-1-established values.
        self.assertEqual(result.status, ReferenceResolutionStatus.AMBIGUOUS)
        self.assertIn("current_investigation", result.candidates)
        self.assertIn("latest_result", result.candidates)

        # A more specific reference resolves uniquely to the investigation.
        specific = service.resolve_reference("that investigation")
        self.assertEqual(specific.status, ReferenceResolutionStatus.RESOLVED)
        self.assertEqual(specific.resolved_field, "current_investigation")
        self.assertEqual(specific.resolved_value, investigation_target)

    def test_conversation_history_accumulates_across_turns(self):
        """Both turns are preserved in conversation.messages."""
        service = self._make_service()

        service.send("investigate the memory subsystem")
        service.send("what did you find?")

        contents = [m.content for m in service.conversation.messages]
        self.assertIn("investigate the memory subsystem", contents)
        self.assertIn("what did you find?", contents)
        # 2 user + 2 assistant = 4 messages
        self.assertEqual(len(service.conversation.messages), 4)

    def test_state_persists_across_turns(self):
        """ConversationState established in Turn 1 survives into Turn 2."""
        service = self._make_service()

        service.send("investigate the memory subsystem")
        investigation_after_t1 = service.state_manager.state.current_investigation

        service.send("what did you find?")
        investigation_after_t2 = service.state_manager.state.current_investigation

        self.assertEqual(investigation_after_t1, investigation_after_t2)

    # ------------------------------------------------------------------
    # Cross-session isolation
    # ------------------------------------------------------------------

    def test_separate_sessions_do_not_share_context(self):
        """Session B must NOT inherit Session A's investigation context."""
        session_a = self._make_service()
        session_b = self._make_service()

        # Session A establishes an investigation.
        session_a.send("investigate the memory subsystem")
        self.assertIsNotNone(
            session_a.state_manager.state.current_investigation
        )

        # Session B has no knowledge of Session A's investigation.
        result_b = session_b.resolve_reference("what did you find?")
        self.assertEqual(result_b.status, ReferenceResolutionStatus.UNRESOLVED)
        self.assertIsNone(session_b.state_manager.state.current_investigation)

    def test_separate_sessions_independent_topics(self):
        """Two sessions tracking different topics resolve independently."""
        session_a = self._make_service()
        session_b = self._make_service()

        session_a.send("investigate the memory subsystem")
        session_b.send("investigate the authentication module")

        topic_a = session_a.state_manager.state.current_investigation
        topic_b = session_b.state_manager.state.current_investigation

        self.assertIsNotNone(topic_a)
        self.assertIsNotNone(topic_b)
        self.assertNotEqual(topic_a, topic_b)
        self.assertIn("memory", topic_a.lower())
        self.assertIn("authentication", topic_b.lower())

        # Each session's reference resolves to its own context.
        ref_a = session_a.resolve_reference("that investigation")
        ref_b = session_b.resolve_reference("that investigation")
        self.assertEqual(ref_a.resolved_value, topic_a)
        self.assertEqual(ref_b.resolved_value, topic_b)


if __name__ == "__main__":
    unittest.main()
