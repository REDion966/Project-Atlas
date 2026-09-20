"""Phase 2.2 — bounded deterministic lexical canonicalization tests.

Covers the pure canonicalizer (bounds, equivalences, frames, no overmatch,
determinism, model independence), real `ConversationService.send`/`stream`
behavior for ordinary variations, negative/boundary cases, governed precedence,
reference/repeat conservation, and contract stability of `TaskSpec`/`TurnMeaning`.
No provider is contacted anywhere in this module.
"""

from __future__ import annotations

import ast
import dataclasses
import unittest
from pathlib import Path

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.investigation import InvestigationService
from atlas.conversation.normalization import (
    MAX_EQUIVALENCE_ENTRIES,
    MAX_EQUIVALENCE_PHRASE_CHARS,
    MAX_SURFACE_INPUT_CHARS,
    _SURFACE_EQUIVALENCES,
    canonicalize_surface,
    collapse_whitespace,
)
from atlas.conversation.reference_resolution import is_repeat_request
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.conversation.turn_meaning import TurnMeaning

_REPO_ROOT = Path(__file__).resolve().parents[1]


class _FailingAI:
    calls = 0

    def chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1
        raise RuntimeError("No AI available")

    def stream_chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1

        def _g():
            raise RuntimeError("No AI available")
            yield ""  # pragma: no cover

        return _g()


def _service(investigation: bool = False) -> ConversationService:
    _FailingAI.calls = 0
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(),
        investigation_service=InvestigationService() if investigation else None,
    )


def _intent(message) -> object:
    return (message.metadata or {}).get("builtin_intent")


# ---------------------------------------------------------------------------
# 1. Pure canonicalizer
# ---------------------------------------------------------------------------


class TestCanonicalizerUnit(unittest.TestCase):
    def test_whitespace_only_behavior_unchanged(self):
        for text in ("  a   b  ", "x\ty\n z", "plain"):
            self.assertEqual(canonicalize_surface(text), collapse_whitespace(text))

    def test_collapse_whitespace_itself_unchanged(self):
        self.assertEqual(collapse_whitespace("  a   b  "), "a b")
        self.assertEqual(collapse_whitespace(None), "")

    def test_equivalences_map_to_canonical(self):
        for variant in (
            "List the things Atlas can do.",
            "List what Atlas can do.",
            "Can you tell me what's available?",
            "what's available?",
            "What is available?",
            "What can Atlas do?",
            "what do you do",
        ):
            with self.subTest(variant=variant):
                self.assertEqual(
                    canonicalize_surface(variant), "what capabilities do you have"
                )

    def test_leading_frames_are_stripped(self):
        self.assertEqual(
            canonicalize_surface("Can you check the system status?"),
            "check the system status?",
        )
        self.assertEqual(
            canonicalize_surface("Could you check that again?"),
            "check that again?",
        )
        self.assertEqual(
            canonicalize_surface("Please investigate the memory architecture."),
            "investigate the memory architecture.",
        )

    def test_existing_canonical_phrases_unchanged(self):
        for text in (
            "what can you do",
            "status",
            "hello",
            "who are you",
            "What capabilities do you have?",
        ):
            with self.subTest(text=text):
                self.assertIn(canonicalize_surface(text), (text, text.rstrip("?")))

    def test_governed_sentence_unchanged(self):
        self.assertEqual(
            canonicalize_surface("Investigate the memory architecture."),
            "Investigate the memory architecture.",
        )

    def test_unknown_text_unchanged(self):
        for text in (
            "Check it.",
            "Look at that.",
            "The other one.",
            "Fix this.",
            "blorptastic quux",
            "We voted against the rule.",
        ):
            with self.subTest(text=text):
                self.assertEqual(canonicalize_surface(text), collapse_whitespace(text))

    def test_no_overmatch_inside_longer_sentences(self):
        for text in (
            "Tell me what is available on the network.",
            "List the things Atlas can do today and tomorrow.",
        ):
            with self.subTest(text=text):
                self.assertEqual(canonicalize_surface(text), collapse_whitespace(text))
        # A leading politeness frame may be stripped, but the sentence must not
        # be rewritten into a capabilities request.
        self.assertNotEqual(
            canonicalize_surface("Please clarify what's available in the scheduler."),
            "what capabilities do you have",
        )

    def test_bounds(self):
        self.assertEqual(canonicalize_surface("x" * (MAX_SURFACE_INPUT_CHARS + 5)),
                         "x" * (MAX_SURFACE_INPUT_CHARS + 5))
        self.assertLessEqual(len(_SURFACE_EQUIVALENCES), MAX_EQUIVALENCE_ENTRIES)
        for variant, canonical in _SURFACE_EQUIVALENCES:
            self.assertLessEqual(len(variant), MAX_EQUIVALENCE_PHRASE_CHARS)
            self.assertLessEqual(len(canonical), MAX_EQUIVALENCE_PHRASE_CHARS)

    def test_empty_and_non_string(self):
        self.assertEqual(canonicalize_surface(""), "")
        self.assertEqual(canonicalize_surface("   "), "")
        self.assertEqual(canonicalize_surface(None), "")

    def test_deterministic(self):
        for text in ("Can you tell me what's available?", "Could you check that again?"):
            with self.subTest(text=text):
                self.assertEqual(
                    canonicalize_surface(text), canonicalize_surface(text)
                )

    def test_stdlib_only_no_model_imports(self):
        source = (
            _REPO_ROOT / "atlas" / "conversation" / "normalization.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        banned = ("openai", "anthropic", "ollama", "requests", "httpx", "urllib")
        for module in imported:
            self.assertFalse(module.startswith(banned), module)


# ---------------------------------------------------------------------------
# 2. Builtin intent integration
# ---------------------------------------------------------------------------


class TestBuiltinIntegration(unittest.TestCase):
    def setUp(self):
        self.svc = BuiltinResponseService()

    def _classify(self, text):
        classified = self.svc._classify(text, TaskIntake().intake(text), None)
        return classified[0] if isinstance(classified, tuple) else classified

    def test_new_equivalences_reach_capabilities(self):
        for text in (
            "List the things Atlas can do.",
            "Can you tell me what's available?",
            "what's available?",
            "What can Atlas do?",
        ):
            with self.subTest(text=text):
                self.assertEqual(self._classify(text), "capabilities")

    def test_existing_builtin_intents_unchanged(self):
        for text, expected in (
            ("hello", "greeting"),
            ("status", "status"),
            ("what can you do", "help"),
            ("who are you", "identity"),
            ("What did we find?", None),
        ):
            with self.subTest(text=text):
                classified = self._classify(text)
                if expected is None:
                    self.assertNotEqual(classified, "capabilities")
                else:
                    self.assertEqual(classified, expected)

    def test_l10_regressions_still_classify(self):
        for text, expected in (
            ("Can you tell me what you're able to do?", "capabilities"),
            ("what's going on right now", "status"),
            ("thanks!", "acknowledgement"),
        ):
            with self.subTest(text=text):
                self.assertEqual(self._classify(text), expected)


# ---------------------------------------------------------------------------
# 3. End-to-end ConversationService behavior
# ---------------------------------------------------------------------------


class TestEndToEndVariations(unittest.TestCase):
    def test_supported_variations_reach_capabilities(self):
        for text in (
            "Can you tell me what's available?",
            "List the things Atlas can do.",
            "What can Atlas do?",
        ):
            with self.subTest(text=text):
                service = _service()
                message = service.send(text)
                self.assertEqual(_intent(message), "capabilities")
                self.assertEqual(_FailingAI.calls, 0)

    def test_status_frames(self):
        for text in ("Can you check the system status?", "Please check the status"):
            with self.subTest(text=text):
                service = _service()
                self.assertEqual(_intent(service.send(text)), "status")

    def test_frame_query_reaches_capabilities(self):
        service = _service()
        self.assertEqual(
            _intent(service.send("I'd like to know what capabilities are available.")),
            "capabilities",
        )

    def test_negative_and_boundary_cases_remain_unsupported(self):
        for text in ("Check it.", "Look at that.", "The other one.", "Fix this."):
            with self.subTest(text=text):
                service = _service()
                message = service.send(text)
                self.assertEqual(_intent(message), "unsupported")
                self.assertTrue(message.content)

    def test_no_overmatch_remains_unsupported(self):
        service = _service()
        self.assertEqual(
            _intent(service.send("Tell me what is available on the network.")),
            "unsupported",
        )

    def test_governed_request_keeps_its_governed_path(self):
        service = _service(investigation=True)
        message = service.send("Please investigate the memory architecture.")
        self.assertIsNone(_intent(message))
        self.assertIsNotNone((message.metadata or {}).get("investigation"))
        # Canonicalization must not rewrite the governed target.
        self.assertTrue(
            (message.metadata or {})["investigation"]["target"].startswith(
                "Please investigate the memory architecture"
            )
        )

    def test_governed_task_type_unchanged(self):
        for text in (
            "Investigate the memory architecture.",
            "Can you investigate the memory architecture?",
        ):
            with self.subTest(text=text):
                spec = TaskIntake().intake(text)
                self.assertIs(spec.task_type, TaskType.INVESTIGATION_REQUEST)

    def test_send_stream_parity(self):
        text = "Can you tell me what's available?"
        sent = _service().send(text)
        streamed = "".join(_service().stream(text))
        self.assertEqual(sent.content, streamed)

    def test_deterministic_repeat(self):
        contents = set()
        for _ in range(3):
            contents.add(_service().send("List the things Atlas can do.").content)
        self.assertEqual(len(contents), 1)

    def test_l10_topic_recall_unchanged(self):
        service = _service(investigation=True)
        service.send("Investigate the memory architecture.")
        message = service.send("Do you remember what we discussed?")
        self.assertEqual(_intent(message), "conversation_recall")
        self.assertEqual((message.metadata or {}).get("recall_source"), "topic")


# ---------------------------------------------------------------------------
# 4. Reference / repeat behavior conservation
# ---------------------------------------------------------------------------


class TestReferenceRepeatConservation(unittest.TestCase):
    def test_frame_stripped_repeat_is_recognized(self):
        self.assertTrue(is_repeat_request("Could you check that again?"))
        self.assertTrue(is_repeat_request("check that again"))

    def test_repeat_without_operation_still_fails_closed(self):
        service = _service()
        self.assertEqual(_intent(service.send("Could you check that again?")), "unsupported")

    def test_repeat_after_governed_operation_reuses_existing_behavior(self):
        service = _service(investigation=True)
        service.send("Investigate the memory architecture.")
        message = service.send("Could you check that again?")
        self.assertIsNotNone((message.metadata or {}).get("investigation"))
        self.assertEqual(
            (message.metadata or {})["investigation"]["target"],
            "Investigate the memory architecture",
        )

    def test_ambiguity_behavior_unchanged(self):
        service = _service(investigation=True)
        service.send("Investigate the memory architecture.")
        message = service.send("What did you find?")
        self.assertIn("I need a bit more detail", message.content)


# ---------------------------------------------------------------------------
# 5. Contract stability
# ---------------------------------------------------------------------------


class TestContractsUnchanged(unittest.TestCase):
    def test_turn_meaning_fields_unchanged(self):
        names = {f.name for f in dataclasses.fields(TurnMeaning)}
        self.assertEqual(
            names, {"intent", "uncertainty", "reference", "source_text", "provenance"}
        )

    def test_canonicalization_does_not_rewrite_stored_intent(self):
        # Classification may canonicalize; the stored TaskSpec content must keep
        # the user's original wording.
        spec = TaskIntake().intake("Can you investigate the memory architecture?")
        self.assertEqual(spec.intent, "Can you investigate the memory architecture?")
        self.assertNotIn("what capabilities do you have", spec.goal)

    def test_turn_meaning_builds(self):
        from atlas.conversation.turn_meaning import build_turn_meaning

        spec = TaskIntake().intake("Can you tell me what's available?")
        meaning = build_turn_meaning(spec, "Can you tell me what's available?")
        self.assertIsInstance(meaning, TurnMeaning)


if __name__ == "__main__":
    unittest.main()
