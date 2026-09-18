"""Tests for Phase 1 — Built-In Conversational Response Service.

Covers:
- greeting, help, identity, capabilities, status, and unsupported intents;
- grounding in the injected ToolRegistry / KnowledgeManager (no invented
  capabilities);
- graceful degradation when collaborators are absent;
- the governed-pipeline guard (lifecycle task types and
  needs-clarification specs are never claimed);
- ConversationService send/stream integration: builtin answers casual turns
  without calling any AI provider; governed turns still reach the AI path.

All tests are pure/deterministic. No provider network calls are made.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from atlas.ai.ai_manager import AIManager
from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.message import Message
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.knowledge.knowledge_manager import KnowledgeManager
from atlas.tools.models import Tool
from atlas.tools.registry import ToolRegistry


def _manager():
    manager = AIManager()
    manager.initialize(
        provider="Mock Provider",
        model="atlas-mock-v1",
        timeout=300,
    )
    return manager


def _registry_with_tools() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="code_inspector",
            description="Inspect code files deterministically.",
            category="code",
        )
    )
    registry.register(
        Tool(
            name="workspace_search",
            description="Search the workspace.",
            category="system",
            tags=["status", "health"],
        )
    )
    return registry


def _knowledge() -> KnowledgeManager:
    manager = KnowledgeManager()
    manager.remember(
        title="Project Atlas Core",
        content="Phase 6 introduces deterministic-first operation.",
        source="docs/test_source.md",
    )
    return manager


def _service(builtin=None, ai=None, **kwargs):
    manager = ai if ai is not None else _manager().service
    return ConversationService(
        manager,
        task_intake=TaskIntake(),
        builtin_response=builtin,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Intent classification / rendering
# ---------------------------------------------------------------------------


class TestBuiltinIntentClassification(unittest.TestCase):
    def setUp(self):
        self.svc = BuiltinResponseService(
            tool_registry=_registry_with_tools(),
            knowledge_manager=_knowledge(),
        )

    def test_greeting(self):
        for text in ("hello", "Hi Atlas", "hey"):
            self.assertTrue(self.svc.handles(text), text)

    def test_help(self):
        for text in ("help", "What can you do?", "show me the commands", "how do I use this?"):
            msg = self.svc.respond(text)
            self.assertIsNotNone(msg, text)

    def test_identity(self):
        for text in ("Who are you?", "What is Atlas?", "Tell me about yourself"):
            msg = self.svc.respond(text)
            self.assertIsNotNone(msg, text)
            self.assertIn("Atlas", msg.content)

    def test_capabilities(self):
        msg = self.svc.respond("What capabilities and tools do you have?")
        self.assertIsNotNone(msg)
        self.assertIn("code_inspector", msg.content)
        self.assertIn("workspace_search", msg.content)

    def test_status(self):
        msg = self.svc.respond("status", message_count=5)
        self.assertIsNotNone(msg)
        self.assertIn("2", msg.content)
        self.assertIn("5", msg.content)

    def test_unsupported(self):
        msg = self.svc.respond("!!!")
        self.assertIsNotNone(msg)
        self.assertEqual(msg.metadata["builtin_intent"], "unsupported")
        self.assertIn("cannot answer", msg.content)

    def test_governed_lifecycle_never_claimed(self):
        from dataclasses import replace

        spec = TaskIntake().intake("add a new capability to Atlas for scheduling")
        self.assertEqual(spec.task_type, TaskType.DEVELOPMENT_REQUEST)
        self.assertIsNone(self.svc.respond("add a new capability to Atlas for scheduling", spec=spec))
        self.assertFalse(self.svc.handles("add a new capability to Atlas for scheduling", spec=spec))

        other = TaskIntake().intake("Hello Atlas")
        clarified = replace(other, needs_clarification=True)
        self.assertIsNone(self.svc.respond("Hello Atlas", spec=clarified))

    def test_metadata_marks_builtin_no_model(self):
        msg = self.svc.respond("hello")
        self.assertTrue(msg.metadata.get("builtin_response"))
        self.assertEqual(msg.metadata.get("builtin_intent"), "greeting")
        self.assertFalse(msg.metadata.get("model_used"))

    def test_never_invents_capabilities_without_registry(self):
        bare = BuiltinResponseService()
        msg = bare.respond("what tools do you have?")
        self.assertIsNotNone(msg)
        self.assertNotIn("code_inspector", msg.content)
        self.assertIn("No tools or capabilities are currently registered", msg.content)

    def test_status_degrades_without_collaborators(self):
        bare = BuiltinResponseService()
        msg = bare.respond("status")
        self.assertIsNotNone(msg)
        self.assertIn("unknown", msg.content)

    def test_stream_yields_single_chunk(self):
        chunks = list(self.svc.respond_stream("hello"))
        self.assertEqual(len(chunks), 1)
        self.assertIn("Atlas", chunks[0])

    def test_stream_empty_when_unclaimed(self):
        from dataclasses import replace

        spec = TaskIntake().intake("Hello Atlas")
        clarified = replace(spec, needs_clarification=True)
        self.assertEqual(list(self.svc.respond_stream("Hello Atlas", spec=clarified)), [])

    def test_capability_question_not_hijacked_by_identity(self):
        for text in ("What are you capable of?", "What are you capable of doing?"):
            msg = self.svc.respond(text)
            self.assertIsNotNone(msg, text)
            self.assertEqual(msg.metadata["builtin_intent"], "capabilities", text)

    def test_identity_questions_still_identity(self):
        for text in ("What are you?", "Who are you?", "Tell me about yourself."):
            msg = self.svc.respond(text)
            self.assertIsNotNone(msg, text)
            self.assertEqual(msg.metadata["builtin_intent"], "identity", text)

    def test_existing_capability_queries_unchanged(self):
        for text in (
            "What capabilities do you currently have?",
            "What capabilities and tools do you have?",
        ):
            msg = self.svc.respond(text)
            self.assertIsNotNone(msg, text)
            self.assertEqual(msg.metadata["builtin_intent"], "capabilities", text)

    def test_recall_phrasing_with_investigation_noun(self):
        msg = self.svc.respond("Do you remember our investigation?")
        self.assertIsNotNone(msg)
        self.assertEqual(msg.metadata["builtin_intent"], "recall")


# ---------------------------------------------------------------------------
# ConversationService integration
# ---------------------------------------------------------------------------


class TestBuiltinConversationIntegration(unittest.TestCase):
    def test_send_answers_greeting_without_ai(self):
        ai = MagicMock()
        svc = _service(
            BuiltinResponseService(tool_registry=_registry_with_tools()),
            ai=ai,
        )
        response = svc.send("Hello Atlas")
        self.assertEqual(response.role, "assistant")
        self.assertIn("Atlas", response.content)
        self.assertTrue(response.metadata.get("builtin_response"))
        ai.chat.assert_not_called()

    def test_send_answers_help_identity_status_capabilities(self):
        svc = _service(BuiltinResponseService(tool_registry=_registry_with_tools()))
        for text, marker in (
            ("help", "deterministically"),
            ("Who are you?", "Atlas"),
            ("status", "deterministic"),
            ("list tools", "code_inspector"),
        ):
            with self.subTest(text=text):
                self.assertIn(marker, svc.send(text).content)

    def test_send_answers_unsupported_without_ai(self):
        ai = MagicMock()
        svc = _service(BuiltinResponseService(), ai=ai)
        response = svc.send("!!!")
        self.assertIn("cannot answer", response.content)
        ai.chat.assert_not_called()

    def test_send_governed_turn_still_reaches_ai(self):
        ai = MagicMock()
        bridge = MagicMock(return_value="governed prep complete")
        svc = _service(
            BuiltinResponseService(tool_registry=_registry_with_tools()),
            ai=ai,
            development_bridge=bridge,
        )
        response = svc.send("add a new capability to Atlas for scheduling")
        bridge.assert_called_once()
        self.assertEqual(response.content, "governed prep complete")

    def test_send_without_builtin_preserves_ai_path(self):
        ai = MagicMock()
        ai.chat.return_value = MagicMock(text="Model generated response.")
        svc = _service(None, ai=ai)
        response = svc.send("Hello Atlas")
        ai.chat.assert_called_once()
        self.assertEqual(response.content, "Model generated response.")

    def test_stream_answers_greeting_without_ai(self):
        ai = MagicMock()
        svc = _service(
            BuiltinResponseService(tool_registry=_registry_with_tools()),
            ai=ai,
        )
        chunks = list(svc.stream("hello"))
        self.assertEqual(len(chunks), 1)
        self.assertIn("Atlas", chunks[0])
        ai.stream_chat.assert_not_called()

    def test_stream_governed_turn_still_reaches_ai(self):
        ai = MagicMock()
        ai.stream_chat.return_value = iter(["chunk"])
        svc = _service(None, ai=ai)
        self.assertEqual(list(svc.stream("hello")), ["chunk"])

    def test_messages_recorded_in_conversation(self):
        svc = _service(BuiltinResponseService())
        svc.send("hello")
        messages = svc.conversation.messages
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, "user")
        self.assertEqual(messages[1].role, "assistant")

    def test_setter_wires_service(self):
        svc = _service(None)
        self.assertIsNone(svc.builtin_response)
        builtin = BuiltinResponseService()
        svc.set_builtin_response(builtin)
        self.assertIs(svc.builtin_response, builtin)


if __name__ == "__main__":
    unittest.main()
