"""L2.2 — shared deterministic surface-whitespace normalization tests."""

from __future__ import annotations

import hashlib
import unittest
from unittest.mock import MagicMock

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_context import (
    MAX_CONTEXT_CHARS,
    MAX_CONTEXT_TURNS,
    build_conversation_context,
)
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.conversation_state import ConversationState
from atlas.conversation.deterministic_fallback import DeterministicFallbackResolver
from atlas.conversation.development_need_dialogue import (
    ConfirmationStatus,
    DevelopmentNeedDialogue,
)
from atlas.conversation.investigation import InvestigationService
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
from atlas.knowledge.knowledge_manager import KnowledgeManager
from atlas.tools.models import Tool
from atlas.tools.registry import ToolRegistry

HISTORY = [Message(role="user", content="hello"), Message(role="assistant", content="hi")]


def _context(current: str):
    return build_conversation_context(HISTORY + [Message(role="user", content=current)])


def _intent(builtin: BuiltinResponseService, text: str):
    classified = builtin._classify(text, TaskIntake().intake(text), _context(text))
    return classified[0] if isinstance(classified, tuple) else classified


def _investigation_service():
    return ConversationService(
        MagicMock(),
        task_intake=TaskIntake(),
        investigation_service=InvestigationService(),
    )


class _UnavailableAI:
    """Deterministic stand-in for an unavailable model provider (no network)."""

    model = "unavailable"
    provider = "none"

    def chat(self, *args, **kwargs):
        raise RuntimeError("provider unavailable")

    def stream(self, *args, **kwargs):
        raise RuntimeError("provider unavailable")


def _knowledge_manager():
    manager = KnowledgeManager()
    manager.remember(
        title="Rollout runbook",
        content="The deployment process uses blue green rollouts.",
        source="runbook",
    )
    manager.remember(
        title="Scheduling",
        content="Deployment scheduling is handled by the release bot.",
        source="ops",
    )
    return manager


def _fallback_service(knowledge_manager=None, tool_registry=None):
    return ConversationService(
        _UnavailableAI(),
        task_intake=TaskIntake(),
        fallback_resolver=DeterministicFallbackResolver(
            knowledge_manager=knowledge_manager, tool_registry=tool_registry
        ),
    )


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


class TestInvestigationTargetWhitespace(unittest.TestCase):
    """N5 — investigation target cleaning is whitespace-equivalent."""

    SUFFIXES = (
        "don't modify anything yet",
        "don't modify anything",
        "do not modify anything yet",
        "do not modify anything",
        "without modifying anything",
    )

    @staticmethod
    def _cleaned(text):
        return InvestigationService._clean_target(text)

    @staticmethod
    def _variants(phrase):
        return (
            phrase.replace(" ", "  "),
            phrase.replace(" ", "\t"),
            phrase.replace(" ", "\n"),
            phrase.replace(" ", "\r\n"),
            phrase.replace(" ", " \t "),
        )

    def test_boundary_suffix_equivalence(self):
        for suffix in self.SUFFIXES:
            canonical = f"Investigate the task intake flow, {suffix}"
            expected = self._cleaned(canonical)
            self.assertEqual(expected, "Investigate the task intake flow", suffix)
            for variant in self._variants(suffix):
                text = f"Investigate the task intake flow, {variant}"
                self.assertEqual(self._cleaned(text), expected, text)
            padded = f"  {canonical}  "
            self.assertEqual(self._cleaned(padded), expected, padded)

    def test_constraints_boundary_equivalence(self):
        for boundary in (
            " | constraints:",
            " |  constraints:",
            "\t|\tconstraints:",
            "\n| constraints:",
        ):
            text = f"Investigate the task intake flow{boundary} keep it read-only"
            self.assertEqual(
                self._cleaned(text), "Investigate the task intake flow", text
            )

    def test_addressing_and_prefix_equivalence(self):
        for text in (
            "Atlas, investigate the task intake flow.",
            "Atlas,  investigate  the task intake flow.",
            "Atlas,\tinvestigate\nthe task intake flow.",
        ):
            self.assertEqual(
                self._cleaned(text), "investigate the task intake flow", text
            )
        for text in (
            "respond: investigate the task intake flow",
            "respond:  investigate  the task intake flow",
        ):
            self.assertEqual(
                self._cleaned(text), "investigate the task intake flow", text
            )

    def test_canonical_targets_unchanged(self):
        for text, expected in (
            ("Investigate the memory architecture", "Investigate the memory architecture"),
            (
                "Investigate the task intake flow, don't modify anything yet",
                "Investigate the task intake flow",
            ),
            (
                "Investigate the task intake flow, don't modify anything",
                "Investigate the task intake flow",
            ),
            (
                "Investigate the task intake flow, without modifying anything",
                "Investigate the task intake flow",
            ),
        ):
            self.assertEqual(self._cleaned(text), expected, text)

    def test_unrelated_trailing_phrases_not_stripped(self):
        for text, tail in (
            ("Investigate the task intake flow, modify everything", "modify everything"),
            ("Investigate the task intake flow, don't  touch anything", "touch anything"),
            ("Investigate the task intake flow, without changing anything", "changing anything"),
            ("Investigate the task intake flow, do not modify anything maybe", "maybe"),
            ("Investigate the task intake flow, unstoppable", "unstoppable"),
        ):
            self.assertTrue(self._cleaned(text).endswith(tail), text)

    def test_report_target_and_concepts_equivalence(self):
        service = InvestigationService()
        canonical = service.investigate(
            "Investigate the task intake flow, don't modify anything yet"
        )
        variant = service.investigate(
            "Investigate the task intake flow, don't  modify anything yet"
        )
        self.assertEqual(variant.target, canonical.target)
        self.assertEqual(variant.target, "Investigate the task intake flow")
        self.assertEqual(
            service._extract_concepts(variant.target),
            service._extract_concepts(canonical.target),
        )

    def test_raw_preservation_state_and_send_stream_parity(self):
        raw = "Investigate the task intake flow, don't  modify anything yet"
        expected_target = "Investigate the task intake flow"

        sent_service = _investigation_service()
        response = sent_service.send(raw)

        streamed_service = _investigation_service()
        chunks = list(streamed_service.stream(raw))

        self.assertEqual(response.metadata["investigation"]["target"], expected_target)
        self.assertTrue(chunks)
        self.assertIn(expected_target, chunks[0])

        for service in (sent_service, streamed_service):
            self.assertEqual(service._conversation.messages[0].content, raw)
            self.assertEqual(
                service._state_manager.state.current_investigation, expected_target
            )

        spec = TaskIntake().intake(raw)
        self.assertEqual(
            spec.input_hash, hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        )
        self.assertEqual(build_turn_meaning(spec, raw).source_text, raw)

    def test_context_bounds_unchanged(self):
        self.assertEqual((MAX_CONTEXT_TURNS, MAX_CONTEXT_CHARS), (10, 500))


class TestFallbackKnowledgeQueryWhitespace(unittest.TestCase):
    """N6 — fallback knowledge-query matching is whitespace-equivalent."""

    CANONICAL = "The deployment process uses blue green rollouts"

    @staticmethod
    def _variants(phrase):
        return (
            ("double_space", phrase.replace(" ", "  ")),
            ("tab", phrase.replace(" ", "\t")),
            ("newline", phrase.replace(" ", "\n")),
            ("crlf", phrase.replace(" ", "\r\n")),
            ("mixed", phrase.replace(" ", " \t\n ")),
            ("nbsp", phrase.replace(" ", "\u00a0")),
            ("em_space", phrase.replace(" ", "\u2003")),
        )

    def setUp(self):
        self.resolver = DeterministicFallbackResolver(
            knowledge_manager=_knowledge_manager()
        )

    def _resolve(self, text):
        message = self.resolver.resolve(text)
        return message.metadata["fallback_type"], message.content

    def test_whitespace_variants_match_canonical_result(self):
        expected = self._resolve(self.CANONICAL)
        self.assertEqual(expected[0], "knowledge")
        self.assertIn("blue green rollouts", expected[1])
        for name, variant in self._variants(self.CANONICAL):
            with self.subTest(variant=name):
                self.assertEqual(self._resolve(variant), expected)

    def test_leading_and_trailing_whitespace_do_not_change_result(self):
        expected = self._resolve(self.CANONICAL)
        for variant in (
            f"  {self.CANONICAL}",
            f"{self.CANONICAL}  ",
            f"\t {self.CANONICAL}\n ",
        ):
            with self.subTest(variant=repr(variant)):
                self.assertEqual(self._resolve(variant), expected)

    def test_irregular_variants_return_the_single_canonical_entry(self):
        # Before N6 the irregular form missed the whole-text strategy and fell
        # through to the token strategies, returning an extra entry.
        expected_content = self._resolve(self.CANONICAL)[1]
        for name, variant in self._variants(self.CANONICAL):
            with self.subTest(variant=name):
                self.assertEqual(self._resolve(variant)[1], expected_content)

    def test_returned_entry_content_is_unchanged(self):
        _, content = self._resolve(self.CANONICAL)
        self.assertIn("### Rollout runbook", content)
        self.assertIn("The deployment process uses blue green rollouts.", content)
        self.assertIn("- Source: runbook", content)

    def test_tool_keyword_fallback_unchanged(self):
        registry = ToolRegistry()
        registry.register(
            Tool(name="code_inspector", description="Inspect code files.", category="code")
        )
        resolver = DeterministicFallbackResolver(
            knowledge_manager=_knowledge_manager(), tool_registry=registry
        )
        for text in ("what can you do", "what  can  you  do", "what\tcan\tyou\tdo"):
            message = resolver.resolve(text)
            self.assertEqual(message.metadata["fallback_type"], "tool_guidance", text)
            self.assertIn("code_inspector", message.content, text)

    def test_degraded_notice_unchanged(self):
        for text in ("hello there comptroller", "hello  there  comptroller"):
            message = self.resolver.resolve(text)
            self.assertEqual(message.metadata["fallback_type"], "degraded_notice", text)
            self.assertIn("deterministic-first degraded mode", message.content, text)

    def test_unsupported_paraphrase_still_degrades(self):
        for text in ("What happened yesterday?", "blorptastic quux"):
            self.assertEqual(
                self.resolver.resolve(text).metadata["fallback_type"],
                "degraded_notice",
                text,
            )

    def test_shared_rule_is_load_bearing(self):
        """The normalization itself is what makes the two forms converge."""
        variant = self._variants(self.CANONICAL)[0][1]
        spec = TaskIntake().intake(variant)
        canonical = self.resolver._search_knowledge(self.CANONICAL, spec)
        normalized = self.resolver._search_knowledge(collapse_whitespace(variant), spec)
        unnormalized = self.resolver._search_knowledge(variant, spec)

        def titles(entries):
            return [entry.title for entry in entries]

        self.assertEqual(titles(canonical), ["Rollout runbook"])
        self.assertEqual(titles(normalized), titles(canonical))
        self.assertNotEqual(titles(unnormalized), titles(normalized))

    def test_send_and_stream_converge_through_conversation_service(self):
        variant = self._variants(self.CANONICAL)[0][1]

        canonical_response = _fallback_service(_knowledge_manager()).send(self.CANONICAL)
        variant_response = _fallback_service(_knowledge_manager()).send(variant)

        self.assertEqual(canonical_response.metadata["fallback_type"], "knowledge")
        self.assertEqual(
            canonical_response.metadata["fallback_type"],
            variant_response.metadata["fallback_type"],
        )
        self.assertEqual(canonical_response.content, variant_response.content)

        chunks = list(_fallback_service(_knowledge_manager()).stream(variant))
        self.assertEqual("".join(chunks), variant_response.content)


if __name__ == "__main__":
    unittest.main()
