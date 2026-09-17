"""Tests for Phase 3 — built-in answers from Atlas-owned state.

Covers:
- listing available capabilities (tools + reasoning capabilities);
- explaining a named registered capability/tool (and honest unknown);
- status grounded in container/memory/knowledge snapshots;
- deterministic memory/knowledge recall (hit, miss, unwired);
- supported commands + safe next steps;
- conservative fallthrough to the unsupported notice;
- ConversationService + kernel integration with realistic fixtures.

All tests are pure/deterministic. No provider network calls are made.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.task_intake import TaskIntake
from atlas.knowledge.knowledge_manager import KnowledgeManager
from atlas.memory.models.memory import Memory
from atlas.memory.service.memory_manager_service import MemoryManagerService
from atlas.memory.ranking.ranking_engine import RankingEngine
from atlas.memory.repository.memory_repository import MemoryRepository
from atlas.memory.search.search_engine import MemorySearchEngine
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.tools.models import Tool
from atlas.tools.registry import ToolRegistry


def _tools() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="code_inspector",
            description="Inspect code files deterministically.",
            category="code",
            tags=["analysis"],
        )
    )
    registry.register(
        Tool(
            name="workspace_search",
            description="Search the workspace.",
            category="system",
        )
    )
    return registry


def _capabilities() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register("toolchain.execute_chain", lambda params: None)
    registry.register("memory.semantic_query", lambda params: None)
    return registry


def _knowledge() -> KnowledgeManager:
    manager = KnowledgeManager()
    manager.remember(
        title="IsoDate Policy",
        content="IsoDate values use UTC midnight for deterministic tests.",
        source="docs/isodate.md",
    )
    manager.remember(
        title="Unrelated Note",
        content="The office plants need water on Fridays.",
        source="docs/plants.md",
    )
    return manager


class _InMemoryRepository(MemoryRepository):
    """In-memory stub bypassing file storage (same pattern as
    tests/memory/test_memory_service.py::_MockRepository)."""

    def __init__(self) -> None:
        self._memories: dict = {}

    def load(self) -> dict:
        return self._memories

    def add(self, memory: Memory) -> None:
        self._memories[memory.id] = memory.to_dict()

    def get(self, memory_id: str) -> Memory | None:
        data = self._memories.get(memory_id)
        if data is None:
            return None
        return Memory.from_dict(data)


def _memory() -> MemoryManagerService:
    repository = _InMemoryRepository()
    service = MemoryManagerService(
        repository=repository,
        ranking_engine=RankingEngine(),
        search_engine=MemorySearchEngine(repository, RankingEngine()),
    )
    service.add_memory(
        Memory(id="m1", title="IsoDate decision", content="IsoDate at UTC midnight.")
    )
    service.add_memory(
        Memory(id="m2", title="Lunch", content="Tacos on Thursdays.")
    )
    return service


def _full() -> BuiltinResponseService:
    return BuiltinResponseService(
        tool_registry=_tools(),
        knowledge_manager=_knowledge(),
        capability_registry=_capabilities(),
        memory_service=_memory(),
        service_names=["ai", "conversation", "memory"],
        started=True,
    )


# ---------------------------------------------------------------------------
# Capability listing + explanation
# ---------------------------------------------------------------------------


class TestCapabilityAnswers(unittest.TestCase):
    def test_list_shows_tools_and_capabilities(self):
        msg = _full().respond("what capabilities do you have?")
        self.assertIsNotNone(msg)
        self.assertEqual(msg.metadata["builtin_intent"], "capabilities")
        self.assertIn("code_inspector", msg.content)
        self.assertIn("toolchain.execute_chain", msg.content)
        self.assertIn("memory.semantic_query", msg.content)

    def test_list_without_anything_registered_is_honest(self):
        msg = BuiltinResponseService().respond("list tools")
        self.assertIsNotNone(msg)
        self.assertIn("No tools or capabilities are currently registered", msg.content)

    def test_explain_registered_tool(self):
        msg = _full().respond("what is code_inspector")
        self.assertIsNotNone(msg)
        self.assertEqual(msg.metadata["builtin_intent"], "capability_detail")
        self.assertIn("code_inspector", msg.content)
        self.assertIn("Inspect code files deterministically", msg.content)

    def test_explain_registered_capability(self):
        msg = _full().respond("tell me about toolchain.execute_chain")
        self.assertIsNotNone(msg)
        self.assertEqual(msg.metadata["builtin_intent"], "capability_detail")
        self.assertIn("toolchain.execute_chain", msg.content)
        self.assertIn("confirmed registered", msg.content)

    def test_explain_unknown_name_is_unsupported(self):
        msg = _full().respond("explain foobar_nonexistent_xyz")
        self.assertIsNotNone(msg)
        self.assertEqual(msg.metadata["builtin_intent"], "unsupported")
        self.assertIn("cannot answer", msg.content)

    def test_explain_without_registry_is_unsupported(self):
        msg = BuiltinResponseService().respond("explain code_inspector")
        self.assertIsNotNone(msg)
        self.assertEqual(msg.metadata["builtin_intent"], "unsupported")

    def test_explain_does_not_hijack_identity(self):
        msg = _full().respond("tell me about yourself")
        self.assertIsNotNone(msg)
        self.assertEqual(msg.metadata["builtin_intent"], "identity")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class TestStatusAnswers(unittest.TestCase):
    def test_status_reports_confirmed_state(self):
        msg = _full().respond("status", message_count=4)
        self.assertIsNotNone(msg)
        self.assertIn("Registered tools: 2.", msg.content)
        self.assertIn("Knowledge entries: 2.", msg.content)
        self.assertIn("Stored memories: 2.", msg.content)
        self.assertIn("ai", msg.content)
        self.assertIn("Runtime: started.", msg.content)
        self.assertIn("Messages in this conversation: 4.", msg.content)

    def test_status_marks_unavailable_state(self):
        msg = BuiltinResponseService().respond("status")
        self.assertIsNotNone(msg)
        self.assertIn("unknown (no tool registry wired)", msg.content)
        self.assertIn("unknown (no knowledge manager wired)", msg.content)
        self.assertIn("unknown (no memory service wired)", msg.content)
        self.assertIn("unknown (no container snapshot)", msg.content)
        self.assertIn("unknown (no lifecycle snapshot)", msg.content)

    def test_status_not_started(self):
        svc = BuiltinResponseService(started=False)
        msg = svc.respond("status")
        self.assertIn("Runtime: not started", msg.content)


# ---------------------------------------------------------------------------
# Memory / knowledge recall
# ---------------------------------------------------------------------------


class TestRecallAnswers(unittest.TestCase):
    def test_recall_memory_hit(self):
        msg = _full().respond("do you remember IsoDate")
        self.assertIsNotNone(msg)
        self.assertEqual(msg.metadata["builtin_intent"], "recall")
        self.assertIn("IsoDate decision", msg.content)
        self.assertIn("UTC midnight", msg.content)

    def test_recall_knowledge_hit(self):
        svc = BuiltinResponseService(knowledge_manager=_knowledge())
        msg = svc.respond("what do you know about IsoDate")
        self.assertIsNotNone(msg)
        self.assertEqual(msg.metadata["builtin_intent"], "recall")
        self.assertIn("IsoDate Policy", msg.content)
        self.assertIn("docs/isodate.md", msg.content)

    def test_recall_miss_is_honest(self):
        msg = _full().respond("do you remember zzzqqqx_no_such_topic")
        self.assertIsNotNone(msg)
        self.assertEqual(msg.metadata["builtin_intent"], "recall")
        self.assertIn("No memory or knowledge entry matched", msg.content)

    def test_recall_unwired_is_honest(self):
        msg = BuiltinResponseService().respond("do you remember IsoDate")
        self.assertIsNotNone(msg)
        self.assertIn("not wired", msg.content)
        self.assertNotIn("IsoDate decision", msg.content)

    def test_bare_remember_without_topic_is_unsupported(self):
        msg = _full().respond("do you remember?")
        self.assertIsNotNone(msg)
        self.assertEqual(msg.metadata["builtin_intent"], "unsupported")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


class TestCommandAnswers(unittest.TestCase):
    def test_commands_lists_real_surfaces(self):
        msg = _full().respond("what commands can I use")
        self.assertIsNotNone(msg)
        self.assertEqual(msg.metadata["builtin_intent"], "commands")
        for marker in (
            "atlas capabilities",
            "atlas memory search",
            "atlas proposals",
            "investigate",
            "approval",
        ):
            self.assertIn(marker, msg.content)

    def test_safe_next_steps(self):
        msg = _full().respond("what are the safe next steps")
        self.assertIsNotNone(msg)
        self.assertEqual(msg.metadata["builtin_intent"], "commands")
        self.assertIn("Nothing here modifies the repository", msg.content)


# ---------------------------------------------------------------------------
# Integration: ConversationService + kernel wiring
# ---------------------------------------------------------------------------


class TestStateAnswersIntegration(unittest.TestCase):
    def _service(self):
        ai = MagicMock()
        return ConversationService(
            ai,
            task_intake=TaskIntake(),
            builtin_response=BuiltinResponseService(
                tool_registry=_tools(),
                knowledge_manager=_knowledge(),
                capability_registry=_capabilities(),
                memory_service=_memory(),
                service_names=["ai", "conversation"],
                started=True,
            ),
        ), ai

    def test_send_state_turns_without_ai(self):
        service, ai = self._service()
        for text in (
            "what capabilities do you have",
            "what is code_inspector",
            "status",
            "do you remember IsoDate",
            "what commands can I use",
        ):
            with self.subTest(text=text):
                response = service.send(text)
                self.assertEqual(response.role, "assistant")
                self.assertTrue(response.metadata.get("builtin_response"))
        ai.chat.assert_not_called()
        ai.stream_chat.assert_not_called()

    def test_stream_state_turn_without_ai(self):
        service, ai = self._service()
        chunks = list(service.stream("tell me about memory.semantic_query"))
        self.assertEqual(len(chunks), 1)
        self.assertIn("memory.semantic_query", chunks[0])
        ai.stream_chat.assert_not_called()

    def test_kernel_wires_phase3_collaborators(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            builtin = atlas.builtin_response
            self.assertIsNotNone(builtin)
            self.assertIs(builtin.capability_registry, atlas._capability_registry)
            self.assertIs(builtin.memory_service, atlas._memory_service)
        finally:
            atlas.shutdown()


if __name__ == "__main__":
    unittest.main()
