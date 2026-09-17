"""Tests for Phase 2 — built-in deterministic conversation by default.

Proves that normal CLI conversation (greeting, help, identity, status,
unsupported free-form) completes through the built-in deterministic engine
without any provider HTTP call, even when provider HTTP is mocked to fail,
and that a no-provider startup plus normal conversation completes promptly.

All tests are deterministic. External providers remain optional
integrations; no provider code is deleted or bypassed by these tests.
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import patch

import requests

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.task_intake import TaskIntake
from atlas.knowledge.knowledge_manager import KnowledgeManager
from atlas.tools.models import Tool
from atlas.tools.registry import ToolRegistry


def _http_forbidden(*args, **kwargs):
    raise AssertionError(
        "provider HTTP must not be called for built-in conversation"
    )


class _FailingHttpSession:
    """requests.Session double whose request always fails."""

    def request(self, *args, **kwargs):
        raise AssertionError(
            "provider HTTP must not be called for built-in conversation"
        )


def _block_provider_http(test_case):
    """Block every provider HTTP path for the duration of a test."""
    test_case.addCleanup(patch.stopall)
    patch("requests.post", side_effect=_http_forbidden).start()
    patch("requests.get", side_effect=_http_forbidden).start()
    patch("requests.Session", return_value=_FailingHttpSession()).start()


def _no_provider_ai():
    """AIService double simulating no reachable provider at all."""

    class _NoProvider:
        def chat(self, *args, **kwargs):
            raise ConnectionError("no provider reachable")

        def stream_chat(self, *args, **kwargs):
            def _gen():
                raise ConnectionError("no provider reachable")
                yield ""  # pragma: no cover

            return _gen()

    return _NoProvider()


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="code_inspector",
            description="Inspect code files deterministically.",
            category="code",
        )
    )
    return registry


def _service(ai=None):
    return ConversationService(
        ai if ai is not None else _no_provider_ai(),
        task_intake=TaskIntake(),
        builtin_response=BuiltinResponseService(
            tool_registry=_registry(),
            knowledge_manager=KnowledgeManager(),
        ),
    )


# ---------------------------------------------------------------------------
# Ordinary conversation never touches provider HTTP
# ---------------------------------------------------------------------------


class TestBuiltinDefaultConversation(unittest.TestCase):
    TURNS = (
        ("hello", "greeting"),
        ("help", "help"),
        ("Who are you?", "identity"),
        ("status", "status"),
        ("blorptastic quux", "unsupported"),
    )

    def test_send_turns_never_call_provider_http(self):
        _block_provider_http(self)
        service = _service()
        for text, intent in self.TURNS:
            with self.subTest(text=text):
                response = service.send(text)
                self.assertEqual(response.role, "assistant")
                self.assertTrue(response.content)
                self.assertTrue(response.metadata.get("builtin_response"))
                self.assertEqual(response.metadata.get("builtin_intent"), intent)
                self.assertFalse(response.metadata.get("model_used", False))

    def test_stream_turns_never_call_provider_http(self):
        _block_provider_http(self)
        service = _service()
        for text, _intent in self.TURNS:
            with self.subTest(text=text):
                chunks = list(service.stream(text))
                self.assertEqual(len(chunks), 1)
                self.assertTrue(chunks[0])

    def test_turns_complete_promptly(self):
        _block_provider_http(self)
        service = _service()
        start = time.monotonic()
        for text, _intent in self.TURNS:
            service.send(text)
            list(service.stream(text))
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 30.0, f"10 turns took {elapsed:.1f}s")

    def test_no_builtin_wired_still_never_touches_http(self):
        # Without the builtin service, casual turns fall through to the AI
        # path only if callers route there; the failing AI raises and the
        # test asserts the service surfaces the configured notice.
        _block_provider_http(self)
        service = ConversationService(
            _no_provider_ai(),
            task_intake=TaskIntake(),
            builtin_response=None,
            fallback_resolver=None,
        )
        response = service.send("hello")
        self.assertIn("External AI inference is currently unavailable", response.content)

    def test_governed_turns_still_bypass_builtin(self):
        _block_provider_http(self)
        service = _service()
        spec = service._intake("add a new capability to Atlas for scheduling")
        self.assertIsNone(
            service._builtin_response.respond(
                "add a new capability to Atlas for scheduling", spec=spec
            )
        )


# ---------------------------------------------------------------------------
# Casual complexity no longer selects an external provider
# ---------------------------------------------------------------------------


class TestCasualComplexityBaseline(unittest.TestCase):
    def test_casual_requests_route_to_mock_not_ollama(self):
        from atlas.ai.routing.models import RoutingRequest
        from atlas.ai.routing.registry import ModelProfileRegistry
        from atlas.ai.routing.router import ModelRouter
        from atlas.ai.routing.models import ModelProfile

        registry = ModelProfileRegistry()
        registry.register(
            ModelProfile(
                provider_name="Mock Provider",
                model_name="atlas-mock-v1",
                complexity_score=0.3,
                priority=10,
            )
        )
        registry.register(
            ModelProfile(
                provider_name="Ollama",
                model_name="qwen3:8b",
                complexity_score=0.8,
                priority=20,
            )
        )
        router = ModelRouter(registry)

        service = ConversationService(
            _no_provider_ai(),
            task_intake=TaskIntake(),
            builtin_response=None,
        )
        for text in ("hi", "hello", "Who are you?", "blorptastic quux"):
            request = service._build_routing_request(
                text, service._intake(text, 0)
            )
            decision = router.route(request)
            self.assertIsNotNone(decision, text)
            with self.subTest(text=text):
                self.assertEqual(decision.provider_name, "Mock Provider")


# ---------------------------------------------------------------------------
# No-provider kernel startup + conversation
# ---------------------------------------------------------------------------


class TestNoProviderKernelStartup(unittest.TestCase):
    def test_startup_and_conversation_with_http_blocked(self):
        _block_provider_http(self)
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            start = time.monotonic()
            atlas.start()
            startup_elapsed = time.monotonic() - start
            self.assertLess(startup_elapsed, 120.0)
            self.assertIsNotNone(atlas.builtin_response)

            for text in ("hello", "help", "Who are you?", "status"):
                with self.subTest(text=text):
                    message = atlas.chat(text)
                    self.assertEqual(message.role, "assistant")
                    self.assertTrue(message.content)
                    self.assertFalse(
                        message.metadata.get("model_used", False)
                    )
        finally:
            atlas.shutdown()


if __name__ == "__main__":
    unittest.main()
