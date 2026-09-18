"""L2.2 — shared deterministic surface-whitespace normalization tests."""

from __future__ import annotations

import hashlib
import unittest
from unittest.mock import MagicMock

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_context import build_conversation_context
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import ConversationState
from atlas.conversation.message import Message
from atlas.conversation.normalization import collapse_whitespace
from atlas.conversation.reference_resolution import (
    ConversationReferenceResolver,
    ReferenceResolutionStatus,
    has_bounded_reference,
)
from atlas.conversation.task_intake import TaskIntake
from atlas.conversation.turn_meaning import build_turn_meaning

HISTORY = [Message(role="user", content="hello"), Message(role="assistant", content="hi")]


def _context(current: str):
    return build_conversation_context(HISTORY + [Message(role="user", content=current)])


def _intent(builtin: BuiltinResponseService, text: str):
    classified = builtin._classify(text, TaskIntake().intake(text), _context(text))
    return classified[0] if isinstance(classified, tuple) else classified


class TestSharedWhitespaceRule(unittest.TestCase):
    def test_collapses_runs_and_trims(self):
        self.assertEqual(collapse_whitespace("What  can   you do?"), "What can you do?")
        self.assertEqual(collapse_whitespace("What can you\n do?"), "What can you do?")
        self.assertEqual(collapse_whitespace("What can you\t\tdo?"), "What can you do?")
        self.assertEqual(collapse_whitespace("  What can you do?  "), "What can you do?")

    def test_preserves_case_and_punctuation(self):
        self.assertEqual(collapse_whitespace("What  Can You Do?"), "What Can You Do?")
        self.assertEqual(collapse_whitespace("a ,  b"), "a , b")
        self.assertEqual(collapse_whitespace("don't  stop"), "don't stop")

    def test_non_string_yields_empty_without_coercion(self):
        self.assertEqual(collapse_whitespace(None), "")  # type: ignore[arg-type]
        self.assertEqual(collapse_whitespace(42), "")  # type: ignore[arg-type]

    def test_canonical_single_space_unchanged(self):
        self.assertEqual(collapse_whitespace("What can you do?"), "What can you do?")


class TestBuiltinConvergence(unittest.TestCase):
    def test_capability_help_convergence(self):
        builtin = BuiltinResponseService()
        for text in (
            "What can you do?",
            "What  can you do?",
            "What\tcan you do?",
            "What can\nyou do?",
            "  What can you do?  ",
        ):
            self.assertEqual(_intent(builtin, text), "help", text)

    def test_capability_alias_convergence(self):
        builtin = BuiltinResponseService()
        for text in ("What can you currently do?", "What  can  you  currently  do?"):
            self.assertEqual(_intent(builtin, text), "capabilities", text)

    def test_status_alias_convergence(self):
        builtin = BuiltinResponseService()
        for text in ("How are things looking?", "How  are  things  looking?"):
            self.assertEqual(_intent(builtin, text), "status", text)

    def test_turn_recall_convergence(self):
        builtin = BuiltinResponseService()
        for text in ("What did I ask earlier?", "What  did  I  ask  earlier?"):
            self.assertEqual(_intent(builtin, text), "conversation_recall", text)


class TestReferenceConvergence(unittest.TestCase):
    def setUp(self):
        self.resolver = ConversationReferenceResolver()
        self.state = ConversationState(current_investigation="memory architecture")

    def test_detection_convergence(self):
        for text in (
            "Based on that investigation, what next?",
            "Based on that  investigation, what next?",
            "Based on that\ninvestigation, what next?",
        ):
            self.assertTrue(has_bounded_reference(text), text)

    def test_resolution_convergence(self):
        for text in (
            "Based on that investigation, what next?",
            "Based on that  investigation, what next?",
            "Based on that\ninvestigation, what next?",
        ):
            result = self.resolver.resolve(text, self.state)
            self.assertEqual(result.status, ReferenceResolutionStatus.RESOLVED, text)
            self.assertEqual(result.resolved_field, "current_investigation", text)

    def test_ambiguity_unchanged(self):
        state = ConversationState(current_investigation="inv-1", latest_result="result-1")
        for text in ("what did you find?", "what  did  you  find?"):
            result = self.resolver.resolve(text, state)
            self.assertEqual(result.status, ReferenceResolutionStatus.AMBIGUOUS, text)


class TestNegativesUnchanged(unittest.TestCase):
    def test_punctuation_not_normalized(self):
        builtin = BuiltinResponseService()
        for text in ("What, can you do?", "How, are things looking?"):
            self.assertEqual(_intent(builtin, text), "unsupported", text)

    def test_unsupported_paraphrase_remains_unsupported(self):
        builtin = BuiltinResponseService()
        for text in (
            "Tell me a joke",
            "Tell  me  a  joke",
            "What happened yesterday?",
            "blorptastic quux",
        ):
            self.assertEqual(_intent(builtin, text), "unsupported", text)

    def test_canonical_intents_unchanged(self):
        builtin = BuiltinResponseService()
        for text, expected in (
            ("What capabilities do you currently have?", "capabilities"),
            ("status", "status"),
            ("Who are you?", "identity"),
            ("help", "help"),
        ):
            self.assertEqual(_intent(builtin, text), expected, text)


class TestRawTextPreservationAndParity(unittest.TestCase):
    def test_input_hash_is_raw_based(self):
        raw = "What  can you do?"
        expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        self.assertEqual(TaskIntake().intake(raw).input_hash, expected)

    def test_conversation_history_keeps_raw_input(self):
        service = ConversationService(
            MagicMock(), task_intake=TaskIntake(), builtin_response=BuiltinResponseService()
        )
        raw = "What  can you do?"
        service.send(raw)
        self.assertEqual(service._conversation.messages[0].content, raw)

    def test_turn_meaning_source_text_stays_raw(self):
        raw = "What  can you do?"
        contract = build_turn_meaning(TaskIntake().intake(raw), raw)
        self.assertEqual(contract.source_text, raw)

    def test_send_and_stream_agree_for_whitespace_variant(self):
        sent = ConversationService(
            MagicMock(), task_intake=TaskIntake(), builtin_response=BuiltinResponseService()
        ).send("What  can  you  do?")
        streamed = list(
            ConversationService(
                MagicMock(), task_intake=TaskIntake(), builtin_response=BuiltinResponseService()
            ).stream("What  can  you  do?")
        )
        self.assertEqual(sent.metadata.get("builtin_intent"), "help")
        self.assertTrue(streamed)
        self.assertIn("help", streamed[0])

    def test_normalization_module_is_model_free(self):
        import pathlib

        import atlas.conversation.normalization as module

        source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        for forbidden in ("atlas.ai", "requests", "openai", "ollama", "anthropic"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
