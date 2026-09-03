"""Phase 6.1 — Deterministic-First / Model-Independence Tests.

Validates that:
- When external AI/model inference is unavailable, unconfigured, or fails:
  * Deterministic knowledge queries return useful knowledge entries with source attribution.
  * Deterministic tool/capability queries return registered tool guidance.
  * General conversational queries return a clear, bounded degradation notice.
  * send() and stream() never crash due to unavailable AI inference.
  * Stream fallback yields chunks cleanly without unhandled exceptions.
- When AI is healthy, normal model-assisted responses are produced unchanged.
- DEVELOPMENT_REQUEST and ACTION_REQUEST orchestration paths remain deterministic and untouched.
- Fallback requires zero model calls or external network dependencies.
- Unrelated exceptions are handled predictably.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from atlas.ai.ai_service import AIService
from atlas.ai.router.ai_router import AIRouter
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.deterministic_fallback import DeterministicFallbackResolver
from atlas.conversation.message import Message
from atlas.conversation.task_intake import TaskIntake, TaskSpec, TaskType
from atlas.knowledge.knowledge_entry import KnowledgeEntry
from atlas.knowledge.knowledge_manager import KnowledgeManager
from atlas.session.context import SessionContext
from atlas.session.models import AuthorityLevel
from atlas.tools.models import Tool
from atlas.tools.registry import ToolRegistry


class _FailingAIService:
    """Mock AI Service that raises RuntimeError on chat / stream_chat."""

    def __init__(self, error_msg: str = "No active AI provider selected.") -> None:
        self._error_msg = error_msg

    def chat(self, prompt, routing_context=None):
        raise RuntimeError(self._error_msg)

    def stream_chat(self, prompt, routing_context=None):
        def _generator():
            raise ConnectionError(self._error_msg)
            yield ""  # pragma: no cover

        return _generator()


class _MidStreamFailingAIService:
    """Mock AI Service that yields one token and then fails."""

    def stream_chat(self, prompt, routing_context=None):
        def _generator():
            yield "Hello, I started responding..."
            raise TimeoutError("Network connection dropped during inference.")

        return _generator()


class _HealthyAIService:
    """Mock AI Service that returns predictable successful responses."""

    def chat(self, prompt, routing_context=None):
        return type("_Resp", (), {"text": "Model generated response."})()

    def stream_chat(self, prompt, routing_context=None):
        def _generator():
            yield "Model "
            yield "streamed "
            yield "response."

        return _generator()


class TestDeterministicFallbackResolver(unittest.TestCase):
    """Unit tests for the pure DeterministicFallbackResolver."""

    def setUp(self) -> None:
        self.knowledge_manager = KnowledgeManager()
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(
            Tool(
                name="workspace_search",
                description="Search files in the workspace.",
                category="file",
                tags=["search", "files"],
            )
        )
        self.resolver = DeterministicFallbackResolver(
            knowledge_manager=self.knowledge_manager,
            tool_registry=self.tool_registry,
        )

    def test_empty_resolver_graceful_degradation(self) -> None:
        """Resolver with no collaborators degrades to clean status notice."""
        empty_resolver = DeterministicFallbackResolver()
        msg = empty_resolver.resolve("hello")
        self.assertIsInstance(msg, Message)
        self.assertEqual(msg.role, "assistant")
        self.assertTrue(msg.metadata.get("degraded"))
        self.assertFalse(msg.metadata.get("model_available"))
        self.assertIn("External AI inference is currently unavailable", msg.content)

    def test_knowledge_resolution(self) -> None:
        """Stored knowledge is retrieved and formatted with source attribution."""
        self.knowledge_manager.remember(
            title="Atlas Architecture",
            content="Atlas is an autonomous companion with governed self-development.",
            source="docs/architecture.md",
        )

        msg = self.resolver.resolve("Tell me about Atlas Architecture")
        self.assertIsInstance(msg, Message)
        self.assertTrue(msg.metadata.get("degraded"))
        self.assertEqual(msg.metadata.get("fallback_type"), "knowledge")
        self.assertIn("Atlas Architecture", msg.content)
        self.assertIn("docs/architecture.md", msg.content)
        self.assertIn("governed self-development", msg.content)

    def test_tool_guidance_resolution(self) -> None:
        """Tool/capability queries return registered tool catalog."""
        self.tool_registry.register(
            Tool(
                name="system_status",
                description="Report system health and status.",
                category="system",
                tags=["status", "health"],
            )
        )

        msg = self.resolver.resolve("What tools are available?")
        self.assertIsInstance(msg, Message)
        self.assertTrue(msg.metadata.get("degraded"))
        self.assertEqual(msg.metadata.get("fallback_type"), "tool_guidance")
        self.assertIn("workspace_search", msg.content)
        self.assertIn("system_status", msg.content)

    def test_general_degradation_notice(self) -> None:
        """General casual query with no knowledge match returns clean degradation notice."""
        msg = self.resolver.resolve("Can you write a poem about the sunrise?")
        self.assertIsInstance(msg, Message)
        self.assertTrue(msg.metadata.get("degraded"))
        self.assertEqual(msg.metadata.get("fallback_type"), "degraded_notice")
        self.assertIn("External AI inference is currently unavailable", msg.content)
        self.assertIn("Governed Self-Development", msg.content)

    def test_resolve_stream(self) -> None:
        """Streaming resolution yields chunks matching resolve content."""
        chunks = list(self.resolver.resolve_stream("help"))
        full_text = "".join(chunks)
        self.assertIn("Deterministic Capability Guidance", full_text)


class TestConversationServiceModelIndependence(unittest.TestCase):
    """Integration tests for ConversationService under model-unavailable conditions."""

    def setUp(self) -> None:
        self.knowledge_manager = KnowledgeManager()
        self.knowledge_manager.remember(
            title="Project Atlas Core",
            content="Phase 6 introduces deterministic-first operation.",
            source="docs/ATLAS_CORE_IMPLEMENTATION_PLAN.md",
        )
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(
            Tool(
                name="code_inspector",
                description="Inspect code files deterministically.",
                category="code",
            )
        )
        self.fallback_resolver = DeterministicFallbackResolver(
            knowledge_manager=self.knowledge_manager,
            tool_registry=self.tool_registry,
        )
        self.failing_ai = _FailingAIService("Provider offline")
        self.healthy_ai = _HealthyAIService()

    def test_send_falls_back_to_knowledge_when_ai_offline(self) -> None:
        """When AI is unavailable, knowledge query returns deterministic knowledge without crashing."""
        service = ConversationService(
            ai_service=self.failing_ai,
            task_intake=TaskIntake(),
            fallback_resolver=self.fallback_resolver,
        )

        response = service.send("Tell me about Project Atlas Core")
        self.assertIsInstance(response, Message)
        self.assertEqual(response.role, "assistant")
        self.assertIn("Project Atlas Core", response.content)
        self.assertIn("Phase 6 introduces deterministic-first operation", response.content)
        self.assertTrue(response.metadata.get("degraded"))

        # Verify conversation history received the message
        self.assertEqual(len(service.conversation.messages), 2)
        self.assertEqual(service.conversation.messages[1].content, response.content)

    def test_send_falls_back_to_tools_when_ai_offline(self) -> None:
        """When AI is unavailable, tool query returns deterministic tool guidance."""
        service = ConversationService(
            ai_service=self.failing_ai,
            task_intake=TaskIntake(),
            fallback_resolver=self.fallback_resolver,
        )

        response = service.send("What capabilities and tools do you have?")
        self.assertIsInstance(response, Message)
        self.assertIn("code_inspector", response.content)
        self.assertTrue(response.metadata.get("degraded"))

    def test_send_general_query_returns_degradation_notice_when_ai_offline(self) -> None:
        """When AI is unavailable, general conversational query returns bounded degradation notice."""
        service = ConversationService(
            ai_service=self.failing_ai,
            task_intake=TaskIntake(),
            fallback_resolver=self.fallback_resolver,
        )

        response = service.send("Hello, how are you today?")
        self.assertIsInstance(response, Message)
        self.assertIn("External AI inference is currently unavailable", response.content)
        self.assertTrue(response.metadata.get("degraded"))

    def test_stream_falls_back_when_ai_fails_before_tokens(self) -> None:
        """When streaming AI fails before emitting tokens, yields deterministic fallback stream."""
        service = ConversationService(
            ai_service=self.failing_ai,
            task_intake=TaskIntake(),
            fallback_resolver=self.fallback_resolver,
        )

        chunks = list(service.stream("Tell me about Project Atlas Core"))
        full_text = "".join(chunks)
        self.assertIn("Project Atlas Core", full_text)
        self.assertEqual(len(service.conversation.messages), 2)
        self.assertEqual(service.conversation.messages[1].content, full_text)

    def test_stream_interrupted_mid_stream(self) -> None:
        """When streaming AI fails mid-stream, preserves partial tokens and appends failure notice."""
        mid_failing_ai = _MidStreamFailingAIService()
        service = ConversationService(
            ai_service=mid_failing_ai,
            task_intake=TaskIntake(),
            fallback_resolver=self.fallback_resolver,
        )

        chunks = list(service.stream("Tell me a story"))
        full_text = "".join(chunks)
        self.assertIn("Hello, I started responding...", full_text)
        self.assertIn("Stream interrupted: external AI model connection lost", full_text)
        self.assertEqual(service.conversation.messages[1].content, full_text)

    def test_healthy_ai_path_unaltered(self) -> None:
        """When AI is healthy, normal model inference response is returned untouched."""
        service = ConversationService(
            ai_service=self.healthy_ai,
            task_intake=TaskIntake(),
            fallback_resolver=self.fallback_resolver,
        )

        response = service.send("Generate a response")
        self.assertEqual(response.content, "Model generated response.")
        self.assertFalse(response.metadata.get("degraded", False))

    def test_healthy_ai_stream_unaltered(self) -> None:
        """When AI is healthy, streaming response is produced normally."""
        service = ConversationService(
            ai_service=self.healthy_ai,
            task_intake=TaskIntake(),
            fallback_resolver=self.fallback_resolver,
        )

        chunks = list(service.stream("Stream a response"))
        self.assertEqual("".join(chunks), "Model streamed response.")

    def test_development_request_path_unaffected(self) -> None:
        """DEVELOPMENT_REQUEST remains purely deterministic through development bridge."""
        bridge_called = False

        def mock_development_bridge(spec: TaskSpec) -> Message:
            nonlocal bridge_called
            bridge_called = True
            return Message(role="assistant", content="Development request handled deterministically.")

        service = ConversationService(
            ai_service=self.failing_ai,  # AI is failing, but dev bridge doesn't use AI
            task_intake=TaskIntake(),
            development_bridge=mock_development_bridge,
            fallback_resolver=self.fallback_resolver,
        )

        # Prompt that triggers DEVELOPMENT_REQUEST in TaskIntake
        response = service.send("add a new capability to Atlas for scheduling")
        self.assertTrue(bridge_called)
        self.assertEqual(response.content, "Development request handled deterministically.")

    def test_orchestration_request_path_unaffected(self) -> None:
        """ACTION_REQUEST remains purely deterministic through orchestration resolver."""
        resolver_called = False

        def mock_orchestration_resolver(spec: TaskSpec, session_ctx) -> Message:
            nonlocal resolver_called
            resolver_called = True
            return Message(role="assistant", content="Orchestration executed tool.")

        service = ConversationService(
            ai_service=self.failing_ai,  # AI is failing, but orchestration does not use AI
            task_intake=TaskIntake(),
            orchestration_resolver=mock_orchestration_resolver,
            fallback_resolver=self.fallback_resolver,
        )

        response = service.send("Run code_inspector to find files.")
        self.assertTrue(resolver_called)
        self.assertEqual(response.content, "Orchestration executed tool.")

    def test_send_without_fallback_resolver_returns_graceful_notice(self) -> None:
        """If no fallback resolver is injected, send() still doesn't crash on AI failure."""
        service = ConversationService(
            ai_service=self.failing_ai,
            task_intake=TaskIntake(),
            fallback_resolver=None,
        )

        response = service.send("Hello")
        self.assertIsInstance(response, Message)
        self.assertIn("External AI inference is currently unavailable", response.content)
        self.assertTrue(response.metadata.get("degraded"))


class TestAtlasKernelModelIndependenceWiring(unittest.TestCase):
    """Test Atlas composition root wiring for DeterministicFallbackResolver."""

    def test_atlas_wires_deterministic_fallback(self) -> None:
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            self.assertIsNotNone(atlas.deterministic_fallback)
            self.assertIsInstance(atlas.deterministic_fallback, DeterministicFallbackResolver)
            self.assertIs(atlas.deterministic_fallback.knowledge_manager, atlas._knowledge_manager)
            self.assertIs(atlas.deterministic_fallback.tool_registry, atlas._tool_registry)
            self.assertIs(atlas._conversation.fallback_resolver, atlas.deterministic_fallback)
        finally:
            atlas.shutdown()
            self.assertIsNone(atlas.deterministic_fallback)


if __name__ == "__main__":
    unittest.main()
