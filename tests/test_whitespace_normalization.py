"""L2.2 — shared deterministic surface-whitespace normalization tests."""

from __future__ import annotations

import hashlib
import unittest
from unittest.mock import MagicMock

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_context import build_conversation_context
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import ConversationState
from atlas.conversation.deterministic_fallback import DeterministicFallbackResolver
from atlas.conversation.development_need_dialogue import (
    ConfirmationStatus,
    DevelopmentNeedDialogue,
)
from atlas.conversation.message import Message
from atlas.conversation.normalization import collapse_whitespace
from atlas.conversation.reference_resolution import (
    ConversationReferenceResolver,
    ReferenceResolutionStatus,
    has_bounded_reference,
)
from atlas.conversation.repository_impact import looks_like_repository_impact_request
from atlas.conversation.task_intake import TaskIntake
from atlas.conversation.turn_meaning import build_turn_meaning
from atlas.tools.models import Tool
from atlas.tools.registry import ToolRegistry

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


class TestConfirmationDialogueWhitespace(unittest.TestCase):
    """F1 — confirmation replies match whitespace-equivalently."""

    def setUp(self):
        self.dialogue = DevelopmentNeedDialogue()
        self.pending = object()  # only inspected for None

    def _status(self, reply):
        return self.dialogue.interpret_confirmation(reply, self.pending)

    def test_affirmative_phrases_equivalent(self):
        for canonical, variants in (
            ("go ahead", ("go  ahead", "go\t ahead", "go\n ahead", "  go ahead  ")),
            ("sounds good", ("sounds  good",)),
            ("please do", ("please  do",)),
        ):
            expected = self._status(canonical)
            self.assertEqual(expected, ConfirmationStatus.CONFIRMED, canonical)
            for variant in variants:
                self.assertEqual(self._status(variant), expected, variant)

    def test_negative_phrase_equivalent(self):
        expected = self._status("maybe later")
        self.assertEqual(expected, ConfirmationStatus.DENIED)
        for variant in ("maybe  later", "maybe\tlater"):
            self.assertEqual(self._status(variant), expected, variant)

    def test_unsupported_reply_remains_ambiguous(self):
        for reply in ("banana", "banana  split"):
            self.assertEqual(self._status(reply), ConfirmationStatus.AMBIGUOUS, reply)


class TestFallbackKeywordWhitespace(unittest.TestCase):
    """F2 — fallback tool/capability keyword matching is whitespace-equivalent."""

    def setUp(self):
        registry = ToolRegistry()
        registry.register(
            Tool(name="code_inspector", description="Inspect code files.", category="code")
        )
        self.resolver = DeterministicFallbackResolver(tool_registry=registry)

    def test_multi_word_keyword_equivalence(self):
        expected = self.resolver.resolve("what can you do").content
        self.assertIn("code_inspector", expected)
        for variant in (
            "what  can  you  do",
            "what\tcan\tyou\tdo",
            "what\ncan\nyou\ndo",
            "  what can you do  ",
        ):
            self.assertEqual(self.resolver.resolve(variant).content, expected, variant)


class TestRepositoryImpactCueWhitespace(unittest.TestCase):
    """F3 — repository impact cue matching is whitespace-equivalent."""

    def test_multi_word_cue_equivalence(self):
        for cue in ("impact analysis", "impact  analysis", "impact\tanalysis", "impact\nanalysis"):
            text = f"Please give me an {cue} for atlas.conversation.conversation_state"
            self.assertTrue(looks_like_repository_impact_request(text), cue)

    def test_would_be_affected_equivalence(self):
        for cue in (
            "What would be affected if atlas.conversation.conversation_state changes?",
            "What would be  affected if atlas.conversation.conversation_state changes?",
            "What would be\taffected if atlas.conversation.conversation_state changes?",
        ):
            self.assertTrue(looks_like_repository_impact_request(cue), cue)

    def test_non_impact_text_unchanged(self):
        self.assertFalse(looks_like_repository_impact_request("Hello there, how are you?"))


class TestContextualCandidateWhitespace(unittest.TestCase):
    """F4 — stored candidates with irregular whitespace resolve equivalently."""

    def _resolve(self, content):
        context = build_conversation_context(
            [Message(role="user", content=content), Message(role="assistant", content="ok")]
        )
        return ConversationReferenceResolver().resolve_contextual(
            "What about the conversation system?", context, ConversationState()
        )

    def test_irregular_candidate_resolves_equivalently(self):
        canonical = self._resolve("Investigate the conversation system.")
        self.assertEqual(canonical.status, ReferenceResolutionStatus.RESOLVED)
        for content in (
            "Investigate the conversation  system.",
            "Investigate the conversation\nsystem.",
            "Investigate the conversation\t system.",
        ):
            variant = self._resolve(content)
            self.assertEqual(variant.status, canonical.status, content)
            self.assertEqual(variant.resolved_field, canonical.resolved_field, content)
            # Raw candidate text is preserved (normalization is matching-only).
            self.assertEqual(variant.resolved_value, content)

    def test_contextual_ambiguity_unchanged(self):
        context = build_conversation_context([
            Message(role="user", content="Investigate the conversation system."),
            Message(role="assistant", content="a"),
            Message(role="user", content="Investigate the capability handler."),
            Message(role="assistant", content="b"),
        ])
        result = ConversationReferenceResolver().resolve_contextual(
            "Look into that.", context, ConversationState()
        )
        self.assertEqual(result.status, ReferenceResolutionStatus.AMBIGUOUS)

    def test_contextual_unresolved_unchanged(self):
        context = build_conversation_context([])
        result = ConversationReferenceResolver().resolve_contextual(
            "Look into that.", context, ConversationState()
        )
        self.assertEqual(result.status, ReferenceResolutionStatus.UNRESOLVED)


if __name__ == "__main__":
    unittest.main()
