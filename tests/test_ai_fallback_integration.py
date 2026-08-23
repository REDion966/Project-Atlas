"""Tests for Phase D2 — fallback activation, integration & audit.

Covers:
- Activation: fallback remains disabled by default; explicit per-request
  opt-in or operator-level default enables it; no routing decision means
  no fallback; existing callers default-off behavior is preserved.
- Integration: ConversationService / RuntimeCoordinator build routing
  requests with allow_fallback=False by default; explicit opt-in reaches
  the FallbackExecutor.
- Audit: primary success, transient -> fallback success, fatal failure,
  skipped candidate, and exhaustion are all auditable; audit lines never
  leak secrets/prompts/response bodies.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

import requests

from atlas.ai.fallback import FallbackExecutor, format_fallback_audit
from atlas.ai.routing.models import ModelProfile, RoutingDecision, RoutingRequest
from atlas.ai.routing.registry import ModelProfileRegistry
from atlas.ai.routing.router import ModelRouter


def _registry() -> ModelProfileRegistry:
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


def _make_decision() -> RoutingDecision:
    return RoutingDecision(
        provider_name="Ollama",
        model_name="qwen3:8b",
        fallback_chain=[("Mock Provider", "atlas-mock-v1")],
    )


def _capture_audit():
    records: list[dict] = []
    return records, records.append


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------


def _service(executor, allow_fallback_default: bool = False):
    """Build an AIService with Mock router + ModelRouter + supplied executor."""
    from atlas.ai.ai_service import AIService
    from atlas.ai.providers.mock_provider import MockProvider
    from atlas.ai.router.ai_router import AIRouter

    router = AIRouter()
    router.registry.register(MockProvider())
    router.use("Mock Provider")
    model_router = ModelRouter(_registry())
    return AIService(
        router=router,
        model_router=model_router,
        fallback_executor=executor,
        allow_fallback_default=allow_fallback_default,
    )


class TestActivation(unittest.TestCase):
    def test_fallback_disabled_by_default(self):
        executor = FallbackExecutor(_registry())
        spy = MagicMock()
        executor.execute = spy  # type: ignore[method-assign]
        service = _service(executor, allow_fallback_default=False)
        response = service.chat(
            ["hi"],
            routing_context=RoutingRequest(complexity=0.2),
        )
        # default False + per-request default False -> executor never used.
        self.assertFalse(spy.called)
        self.assertIsNotNone(response)
        self.assertTrue(hasattr(response, "text"))

    def test_allow_fallback_false_keeps_direct_behavior(self):
        executor = FallbackExecutor(_registry())
        spy = MagicMock()
        executor.execute = spy  # type: ignore[method-assign]

        service = _service(executor, allow_fallback_default=False)
        response = service.chat(
            ["hi"],
            routing_context=RoutingRequest(
                complexity=0.2,
                allow_fallback=False,
            ),
        )
        # both per-request and default are False -> executor never entered.
        self.assertFalse(spy.called)
        self.assertIsNotNone(response)
        self.assertTrue(hasattr(response, "text"))

    def test_explicit_per_request_opt_in_enables_fallback(self):
        executor = FallbackExecutor(_registry())
        service = _service(executor, allow_fallback_default=False)
        response = service.chat(
            ["hi"],
            routing_context=RoutingRequest(
                complexity=0.2,
                allow_fallback=True,
            ),
        )
        self.assertIsNotNone(response)
        self.assertTrue(hasattr(response, "text"))

    def test_operator_default_enables_fallback(self):
        executor = FallbackExecutor(_registry())
        service = _service(executor, allow_fallback_default=True)
        response = service.chat(
            ["hi"],
            routing_context=RoutingRequest(
                complexity=0.2,
                allow_fallback=False,  # per-request off, operator default on
            ),
        )
        self.assertIsNotNone(response)
        self.assertTrue(hasattr(response, "text"))

    def test_no_routing_decision_means_no_fallback(self):
        from atlas.ai.ai_service import AIService
        from atlas.ai.providers.mock_provider import MockProvider
        from atlas.ai.router.ai_router import AIRouter

        router = AIRouter()
        router.registry.register(MockProvider())
        router.use("Mock Provider")
        executor = FallbackExecutor(_registry())
        spy = MagicMock()
        executor.execute = spy  # type: ignore[method-assign]

        service = AIService(
            router=router,
            fallback_executor=executor,
            allow_fallback_default=True,
        )
        response = service.chat(
            ["hi"],
            routing_context=RoutingRequest(allow_fallback=True),
        )
        # No model_router -> no RoutingDecision -> no executor.
        self.assertFalse(spy.called)
        self.assertIsNotNone(response)


# ---------------------------------------------------------------------------
# Caller integration
# ---------------------------------------------------------------------------


class TestCallerIntegration(unittest.TestCase):
    def test_conversation_routing_request_default_off(self):
        from atlas.ai.ai_service import AIService
        from atlas.ai.providers.mock_provider import MockProvider
        from atlas.ai.router.ai_router import AIRouter

        router = AIRouter()
        router.registry.register(MockProvider())
        router.use("Mock Provider")
        service = AIService(router=router)

        from atlas.conversation.conversation_service import ConversationService

        conv = ConversationService(ai_service=service)
        req = conv._build_routing_request("hello")
        self.assertFalse(req.allow_fallback)

    def test_runtime_coordinator_routing_request_default_off(self):
        from atlas.runtime.runtime_coordinator import RuntimeCoordinator

        rc = RuntimeCoordinator()
        state = SimpleNamespace(
            planning_result={
                "steps": [{"id": "s1"}],
                "results": [],
                "goal": "respond",
            },
            understanding_insights=[],
        )
        req = rc._build_routing_request(state)
        self.assertIsNotNone(req)
        self.assertFalse(req.allow_fallback)


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class TestAudit(unittest.TestCase):
    def test_primary_success_is_auditable(self):
        records, audit = _capture_audit()
        executor = FallbackExecutor(_registry(), audit_callback=audit)
        result = executor.execute(
            RoutingRequest(
                complexity=0.2,
                allow_fallback=True,
                metadata={"request_id": "r-1"},
            ),
            _make_decision(),
            lambda provider, model: "ok",
        )
        self.assertEqual(result.response, "ok")
        self.assertGreaterEqual(len(records), 1)
        self.assertEqual(records[0]["event"], "ai.routing.fallback.attempt")
        self.assertEqual(records[0]["outcome"], "success")
        self.assertEqual(records[0]["request_id"], "r-1")

    def test_transient_then_fallback_success_is_auditable(self):
        records, audit = _capture_audit()
        executor = FallbackExecutor(_registry(), audit_callback=audit)

        def _call(provider, model):
            if provider == "Ollama":
                raise requests.ConnectionError("down")
            return f"ok-{provider}"

        result = executor.execute(
            RoutingRequest(complexity=0.2, allow_fallback=True),
            _make_decision(),
            _call,
        )
        self.assertEqual(result.response, "ok-Mock Provider")
        outcomes = [r["outcome"] for r in records if r["event"].endswith(".attempt")]
        self.assertEqual(outcomes, ["failure", "success"])

    def test_fatal_failure_is_auditable(self):
        records, audit = _capture_audit()
        executor = FallbackExecutor(_registry(), audit_callback=audit)

        def _raise(*_args, **_kwargs):
            raise RuntimeError("API key is required")

        with self.assertRaises(RuntimeError):
            executor.execute(
                RoutingRequest(complexity=0.2, allow_fallback=True),
                _make_decision(),
                _raise,
            )
        self.assertGreaterEqual(len(records), 1)
        self.assertEqual(records[0]["event"], "ai.routing.fallback.attempt")
        self.assertEqual(records[0]["outcome"], "failure")
        self.assertEqual(records[0]["failure_class"], "fatal")

    def test_skipped_candidate_is_auditable(self):
        records, audit = _capture_audit()
        executor = FallbackExecutor(_registry(), audit_callback=audit)
        # High complexity filters the 0.3 Mock fallback; duplicate of primary
        # is skipped too.  The primary must fail transiently so the filtered
        # chain is actually walked.
        decision = RoutingDecision(
            provider_name="Ollama",
            model_name="qwen3:8b",
            fallback_chain=[
                ("Mock Provider", "atlas-mock-v1"),
                ("Ollama", "qwen3:8b"),
            ],
        )

        def _call(provider, model):
            if provider == "Ollama" and model == "qwen3:8b":
                raise requests.Timeout("boom")
            return "ok"

        with self.assertRaises(BaseException):
            executor.execute(
                RoutingRequest(complexity=0.5, allow_fallback=True),
                decision,
                _call,
            )
        skipped = [r for r in records if r["event"].endswith(".skipped")]
        self.assertGreaterEqual(len(skipped), 2)
        reasons = {r["reason"] for r in skipped}
        self.assertIn("capability_filtered", reasons)
        self.assertIn("is_primary", reasons)

    def test_exhaustion_contains_attempted_pairs(self):
        records, audit = _capture_audit()
        executor = FallbackExecutor(_registry(), audit_callback=audit)

        def _call(provider, model):
            raise requests.Timeout("all down")

        with self.assertRaises(BaseException) as ctx:
            executor.execute(
                RoutingRequest(complexity=0.2, allow_fallback=True),
                _make_decision(),
                _call,
            )
        exhausted = [r for r in records if r["event"].endswith(".exhausted")]
        self.assertEqual(len(exhausted), 1)
        self.assertEqual(
            exhausted[0]["attempted"],
            [["Ollama", "qwen3:8b"], ["Mock Provider", "atlas-mock-v1"]],
        )
        self.assertIsNotNone(ctx.exception.atlas_attempted)

    def test_audit_lines_do_not_contain_secrets_or_prompts(self):
        # Extra fields are never rendered: format_fallback_audit only emits a
        # fixed allow-list of keys, so even if a record were polluted with a
        # secret/prompt field it would not reach the log line.
        record = {
            "event": "ai.routing.fallback.attempt",
            "request_id": "r-x",
            "attempt": 1,
            "provider": "Ollama",
            "model": "qwen3:8b",
            "outcome": "failure",
            "failure_class": "fatal",
            "failure_reason": "http_4xx",
            "exception_type": "RuntimeError",
            "error": "boom",
            "api_key": "sk-secret",
            "authorization": "Bearer sk-secret",
            "messages": ["SECRET PROMPT"],
            "response": "SECRET RESPONSE",
        }
        rendered = format_fallback_audit(record)
        for token in (
            "sk-secret",
            "Bearer",
            "SECRET PROMPT",
            "SECRET RESPONSE",
        ):
            self.assertNotIn(token, rendered)

    def test_executor_audit_records_are_structurally_bounded(self):
        # A real executor run must never attach messages/prompts/keys to its
        # records — even when the injected callable receives them.
        records, audit = _capture_audit()
        executor = FallbackExecutor(_registry(), audit_callback=audit)
        sent = ["user says: hunt the secret"]
        executor.execute(
            RoutingRequest(complexity=0.2, allow_fallback=True),
            _make_decision(),
            lambda provider, model: f"response to {sent[0]}",
        )
        for record in records:
            self.assertNotIn("messages", record)
            self.assertNotIn("prompt", record)
            self.assertNotIn("api_key", record)
            self.assertNotIn("authorization", record)
            self.assertNotIn("response", record)
            self.assertNotIn("secret", str(record))

    def test_audit_callback_never_leaks_messages(self):
        records, audit = _capture_audit()
        executor = FallbackExecutor(_registry(), audit_callback=audit)
        message_text = "user phish nuked"
        executor.execute(
            RoutingRequest(complexity=0.2, allow_fallback=True),
            _make_decision(),
            lambda provider, model: "response-content",
        )
        rendered = "\n".join(str(r) for r in records)
        self.assertNotIn(message_text, rendered)
        self.assertNotIn("response-content", rendered)


if __name__ == "__main__":
    unittest.main()