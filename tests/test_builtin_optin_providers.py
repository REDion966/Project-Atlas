"""Tests for Phase 4 — external providers as explicit opt-in augmentations.

Covers:
- disabled (default): routing never selects an external provider; the
  active provider is the local no-network tier;
- enabled: routing, fallback chains, and per-provider calls behave as before;
- provider failure / timeout / unavailability on the AI path falls back to
  the built-in response engine with a useful deterministic response;
- the conversational timeout bound reaches the provider call instead of the
  full configured timeout.

All tests are deterministic. Provider HTTP is blocked or faked; no live
network is used. No provider abstraction code is deleted by these tests.
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

import requests

from atlas.ai.ai_manager import AIManager
from atlas.ai.routing.models import ModelProfile, RoutingRequest
from atlas.ai.routing.registry import ModelProfileRegistry
from atlas.ai.routing.router import ModelRouter
from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.task_intake import TaskIntake
from atlas.knowledge.knowledge_manager import KnowledgeManager
from atlas.tools.models import Tool
from atlas.tools.registry import ToolRegistry


def _profiles() -> ModelProfileRegistry:
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
    return registry


def _tools() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="code_inspector",
            description="Inspect code files deterministically.",
            category="code",
        )
    )
    return registry


def _builtin() -> BuiltinResponseService:
    return BuiltinResponseService(
        tool_registry=_tools(),
        knowledge_manager=KnowledgeManager(),
    )


def _block_http(test_case):
    """Fail loudly if any provider HTTP is attempted."""
    test_case.addCleanup(patch.stopall)

    def _forbidden(*args, **kwargs):
        raise AssertionError("provider HTTP must not be called")

    patch("requests.post", side_effect=_forbidden).start()
    patch("requests.get", side_effect=_forbidden).start()


# ---------------------------------------------------------------------------
# Router gate: external selection requires the opt-in
# ---------------------------------------------------------------------------


class TestRouterOptInGate(unittest.TestCase):
    def test_disabled_routes_only_local(self):
        router = ModelRouter(_profiles(), external_providers=False)
        for complexity in (0.1, 0.3, 0.5, 0.9, 1.0):
            decision = router.route(RoutingRequest(complexity=complexity))
            self.assertIsNotNone(decision)
            with self.subTest(complexity=complexity):
                self.assertEqual(decision.provider_name, "Mock Provider")

    def test_disabled_empty_local_tier_returns_none(self):
        registry = ModelProfileRegistry()
        registry.register(
            ModelProfile(
                provider_name="Ollama",
                model_name="qwen3:8b",
                complexity_score=0.8,
                priority=20,
            )
        )
        router = ModelRouter(registry, external_providers=False)
        self.assertIsNone(router.route(RoutingRequest(complexity=0.5)))

    def test_disabled_excludes_unknown_provider(self):
        # Deny-by-default: an unrecognized provider name is excluded
        # without the opt-in, even at a matching complexity.
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
                provider_name="MysteryCloud",
                model_name="mystery-1",
                complexity_score=0.9,
                priority=99,
            )
        )
        router = ModelRouter(registry, external_providers=False)
        for complexity in (0.5, 0.9, 1.0):
            decision = router.route(RoutingRequest(complexity=complexity))
            self.assertIsNotNone(decision)
            with self.subTest(complexity=complexity):
                self.assertEqual(decision.provider_name, "Mock Provider")

    def test_disabled_unknown_only_returns_none(self):
        registry = ModelProfileRegistry()
        registry.register(
            ModelProfile(
                provider_name="MysteryCloud",
                model_name="mystery-1",
                complexity_score=0.9,
                priority=99,
            )
        )
        router = ModelRouter(registry, external_providers=False)
        self.assertIsNone(router.route(RoutingRequest(complexity=0.9)))

    def test_enabled_unknown_provider_selectable(self):
        # With the explicit opt-in, policy selection applies unchanged —
        # including to unrecognized names.
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
                provider_name="MysteryCloud",
                model_name="mystery-1",
                complexity_score=0.9,
                priority=99,
            )
        )
        router = ModelRouter(registry, external_providers=True)
        decision = router.route(RoutingRequest(complexity=0.9))
        self.assertIsNotNone(decision)
        self.assertEqual(decision.provider_name, "MysteryCloud")

    def test_enabled_preserves_external_selection(self):
        router = ModelRouter(_profiles(), external_providers=True)
        decision = router.route(RoutingRequest(complexity=0.5))
        self.assertIsNotNone(decision)
        self.assertEqual(decision.provider_name, "Ollama")
        low = router.route(RoutingRequest(complexity=0.2))
        # NLU-0: with the opt-in enabled the deterministic no-network tier is
        # excluded, so even a low-complexity turn selects the registered real
        # provider rather than the cheapest mock profile.
        self.assertEqual(low.provider_name, "Ollama")

    def test_default_is_disabled(self):
        router = ModelRouter(_profiles())
        self.assertFalse(router.external_providers)
        decision = router.route(RoutingRequest(complexity=0.9))
        self.assertEqual(decision.provider_name, "Mock Provider")


# ---------------------------------------------------------------------------
# NLU-0: explicit real-provider opt-in excludes the deterministic tier
# ---------------------------------------------------------------------------


class TestOptInExcludesDeterministicTier(unittest.TestCase):
    """The explicit real-provider opt-in must prevent the deterministic
    no-network tier from winning ordinary conversational routing on cost."""

    def test_ordinary_conversation_selects_real_provider(self):
        router = ModelRouter(_profiles(), external_providers=True)
        decision = router.route(RoutingRequest(complexity=0.3))
        self.assertIsNotNone(decision)
        self.assertEqual(decision.provider_name, "Ollama")
        self.assertEqual(decision.model_name, "qwen3:8b")

    def test_deterministic_tier_never_wins_on_cost(self):
        router = ModelRouter(_profiles(), external_providers=True)
        for complexity in (0.1, 0.2, 0.3, 0.5, 0.8, 1.0):
            with self.subTest(complexity=complexity):
                decision = router.route(RoutingRequest(complexity=complexity))
                self.assertIsNotNone(decision)
                self.assertEqual(decision.provider_name, "Ollama")

    def test_deterministic_tier_preserved_when_no_real_provider(self):
        # Opt-in enabled but ONLY the deterministic tier registered: the
        # deterministic floor is preserved (no silent external resolution,
        # no empty decision).
        registry = ModelProfileRegistry()
        registry.register(
            ModelProfile(
                provider_name="Mock Provider",
                model_name="atlas-mock-v1",
                complexity_score=0.3,
                priority=10,
            )
        )
        router = ModelRouter(registry, external_providers=True)
        decision = router.route(RoutingRequest(complexity=0.3))
        self.assertIsNotNone(decision)
        self.assertEqual(decision.provider_name, "Mock Provider")

    def test_optin_does_not_enable_remote_when_disabled(self):
        # Deny-by-default: with the opt-in OFF, every remote provider name is
        # excluded regardless of complexity.
        registry = ModelProfileRegistry()
        registry.register(
            ModelProfile(
                provider_name="Mock Provider",
                model_name="atlas-mock-v1",
                complexity_score=0.3,
                priority=10,
            )
        )
        for remote in ("OpenAI", "Anthropic", "OpenRouter", "LM Studio"):
            registry.register(
                ModelProfile(
                    provider_name=remote,
                    model_name="remote-1",
                    complexity_score=0.9,
                    priority=99,
                )
            )
        router = ModelRouter(registry, external_providers=False)
        for complexity in (0.3, 0.6, 0.9, 1.0):
            with self.subTest(complexity=complexity):
                decision = router.route(RoutingRequest(complexity=complexity))
                self.assertEqual(decision.provider_name, "Mock Provider")

    def test_local_provider_names_semantics_unchanged(self):
        # NLU-0 must not redefine the no-network tier that the final-response
        # acceptance gate consumes.
        from atlas.ai.routing.models import LOCAL_PROVIDER_NAMES

        self.assertEqual(frozenset({"Mock Provider"}), LOCAL_PROVIDER_NAMES)


# ---------------------------------------------------------------------------
# AIManager gate: active provider stays local without opt-in
# ---------------------------------------------------------------------------


class TestAIManagerOptInGate(unittest.TestCase):
    def test_disabled_activates_local_tier(self):
        manager = AIManager()
        manager.initialize(
            provider="Ollama",
            model="qwen3:8b",
            timeout=30,
        )
        self.assertEqual(manager.provider.name(), "Mock Provider")
        self.assertEqual(manager.configured_provider, "Ollama")
        self.assertFalse(manager.external_providers)

    def test_enabled_activates_configured_provider(self):
        manager = AIManager()
        manager.initialize(
            provider="Ollama",
            model="qwen3:8b",
            timeout=30,
            external_providers=True,
        )
        self.assertEqual(manager.provider.name(), "Ollama")
        self.assertTrue(manager.external_providers)

    def test_disabled_direct_chat_never_hits_network(self):
        _block_http(self)
        manager = AIManager()
        manager.initialize(
            provider="Ollama",
            model="qwen3:8b",
            timeout=30,
        )
        response = manager.service.chat(["hello"])
        self.assertIn("Atlas", response.text)


# ---------------------------------------------------------------------------
# Executable fallback to built-in on provider failure
# ---------------------------------------------------------------------------


class _FailingAIService:
    def __init__(self, exc):
        self._exc = exc

    def chat(self, *args, **kwargs):
        raise self._exc

    def stream_chat(self, *args, **kwargs):
        def _gen():
            raise self._exc
            yield ""  # pragma: no cover

        return _gen()


def _service(ai, builtin=True, **kwargs):
    return ConversationService(
        ai,
        task_intake=TaskIntake(),
        builtin_response=_builtin() if builtin else None,
        **kwargs,
    )


class TestBuiltinFallbackAfterFailure(unittest.TestCase):
    TURNS = ("hello", "help", "Who are you?", "status", "blorptastic quux")

    def test_casual_turns_answered_pre_ai_without_failure_flag(self):
        # Casual turns are claimed by the builtin engine before the AI
        # path, so no failure occurs and no failure flag is set — even
        # when the AI service would fail.
        _block_http(self)
        service = _service(_FailingAIService(ConnectionError("down")))
        for text in self.TURNS:
            with self.subTest(text=text):
                response = service.send(text)
                self.assertTrue(response.metadata.get("builtin_response"))
                self.assertFalse(
                    response.metadata.get("fallback_after_provider_failure", False)
                )
                self.assertTrue(response.content)

    def test_legacy_turn_failure_falls_back_to_builtin_send(self):
        # Legacy intake-less turns reach the AI path; when it fails, the
        # built-in engine answers text-only and marks the fallback.
        _block_http(self)
        service = ConversationService(
            _FailingAIService(ConnectionError("down")),
            task_intake=None,
            builtin_response=_builtin(),
        )
        for text in self.TURNS:
            with self.subTest(text=text):
                response = service.send(text)
                self.assertTrue(response.metadata.get("builtin_response"))
                self.assertTrue(
                    response.metadata.get("fallback_after_provider_failure")
                )
                self.assertTrue(response.content)

    def test_timeout_falls_back_to_builtin_send(self):
        _block_http(self)
        service = ConversationService(
            _FailingAIService(requests.Timeout("slow")),
            task_intake=None,
            builtin_response=_builtin(),
        )
        response = service.send("hello")
        self.assertTrue(response.metadata.get("builtin_response"))
        self.assertTrue(
            response.metadata.get("fallback_after_provider_failure")
        )

    def test_failure_falls_back_to_builtin_stream(self):
        _block_http(self)
        service = ConversationService(
            _FailingAIService(ConnectionError("down")),
            task_intake=None,
            builtin_response=_builtin(),
        )
        chunks = list(service.stream("hello"))
        self.assertEqual(len(chunks), 1)
        self.assertIn("Atlas", chunks[0])

    def test_unavailable_falls_back_to_builtin(self):
        _block_http(self)
        service = ConversationService(
            _FailingAIService(RuntimeError("No active provider")),
            task_intake=None,
            builtin_response=_builtin(),
        )
        response = service.send("status")
        self.assertTrue(response.metadata.get("builtin_response"))
        self.assertTrue(
            response.metadata.get("fallback_after_provider_failure")
        )

    def test_no_builtin_no_fallback_resolver_keeps_bounded_notice(self):
        service = ConversationService(
            _FailingAIService(ConnectionError("down")),
            task_intake=TaskIntake(),
            builtin_response=None,
            fallback_resolver=None,
        )
        response = service.send("hello")
        self.assertIn("currently unavailable", response.content)


# ---------------------------------------------------------------------------
# Conversational timeout bound reaches the provider call
# ---------------------------------------------------------------------------


class TestConversationalTimeoutBound(unittest.TestCase):
    def test_bound_is_carried_in_routing_metadata(self):
        service = ConversationService(
            MagicMock(),
            task_intake=TaskIntake(),
            provider_call_timeout_s=7.5,
        )
        request = service._build_routing_request(
            "Generate a response", service._intake("Generate a response", 0)
        )
        self.assertEqual(request.metadata.get("conversation_timeout_s"), 7.5)

    def test_absent_bound_leaves_provider_default(self):
        service = ConversationService(MagicMock(), task_intake=TaskIntake())
        request = service._build_routing_request(
            "Generate a response", service._intake("Generate a response", 0)
        )
        self.assertNotIn("conversation_timeout_s", request.metadata)

    def test_bound_reaches_provider_call(self):
        from atlas.ai.ai_service import AIService
        from atlas.ai.providers.mock_provider import MockProvider
        from atlas.ai.router.ai_router import AIRouter

        seen = {}

        class _RecordingProvider(MockProvider):
            def chat(self, messages, model=None, timeout=None):
                seen["timeout"] = timeout
                return super().chat(messages, model=model, timeout=timeout)

        router = AIRouter()
        router.registry.register(_RecordingProvider())
        router.use("Mock Provider")
        service = AIService(router=router)
        service.chat(
            ["hello"],
            routing_context=RoutingRequest(
                complexity=0.3, metadata={"conversation_timeout_s": 7.5}
            ),
        )
        self.assertEqual(seen.get("timeout"), 7.5)

    def test_bound_defaults_to_none_without_metadata(self):
        from atlas.ai.ai_service import AIService

        self.assertIsNone(
            AIService._conversation_timeout(RoutingRequest(complexity=0.3))
        )
        self.assertIsNone(AIService._conversation_timeout(None))

    def test_opted_in_provider_timeout_falls_back_to_builtin(self):
        # A real OllamaProvider whose HTTP raises Timeout (as requests
        # would after the per-call bound): the conversational turn must
        # return a useful builtin response instead of propagating.
        from unittest.mock import patch

        from atlas.ai.ai_service import AIService
        from atlas.ai.providers.ollama_provider import OllamaProvider
        from atlas.ai.router.ai_router import AIRouter

        seen_timeout = {}

        def _timeout_post(*args, **kwargs):
            seen_timeout["timeout"] = kwargs.get("timeout")
            raise requests.Timeout("timed out")

        router = AIRouter()
        router.registry.register(OllamaProvider(model="qwen3:8b", timeout=300))
        router.use("Ollama")
        ai = AIService(router=router)
        service = ConversationService(
            ai,
            task_intake=None,
            builtin_response=_builtin(),
            provider_call_timeout_s=7.5,
        )
        with patch("requests.post", side_effect=_timeout_post):
            start = time.monotonic()
            response = service.send("hello")
            elapsed = time.monotonic() - start
        # The per-call bound reached the provider instead of the 300s default.
        self.assertEqual(seen_timeout.get("timeout"), 7.5)
        self.assertTrue(response.metadata.get("builtin_response"))
        self.assertTrue(
            response.metadata.get("fallback_after_provider_failure")
        )
        self.assertLess(elapsed, 60.0)


if __name__ == "__main__":
    unittest.main()
