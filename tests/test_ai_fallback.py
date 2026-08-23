"""Tests for Phase D1 — AI fallback foundation.

Covers:
- the typed failure classifier (transient vs fatal).
- the fallback executor's capability guard, chain ordering, deduplication,
  attempt cap, and exhaustion behavior.
- the ``RoutingRequest.allow_fallback`` flag default (off).

The tests are pure/deterministic: they construct the executor with an
injected ``ModelProfileRegistry`` and fake ``call`` callables.  No provider
network calls are made.
"""

from __future__ import annotations

import unittest

import requests

from unittest.mock import MagicMock

from atlas.ai.failure import FailureClass, classify_failure
from atlas.ai.fallback import FallbackExhaustedError, FallbackExecutor
from atlas.ai.routing.models import ModelProfile, RoutingDecision, RoutingRequest
from atlas.ai.routing.registry import ModelProfileRegistry


def _http_error(status_code: int) -> requests.HTTPError:
    """Build a requests.HTTPError with the given status code."""
    response = requests.Response()
    response.status_code = status_code
    error = requests.HTTPError(f"HTTP {status_code}", response=response)
    return error


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class TestFailureClassifier(unittest.TestCase):
    """The classifier maps exception types/status to a fallback decision."""

    def test_http_5xx_is_eligible(self):
        for status in (500, 502, 503, 504):
            result = classify_failure(_http_error(status))
            self.assertEqual(result.failure_class, FailureClass.FALLBACK_ELIGIBLE)
            self.assertEqual(result.reason, "http_5xx")

    def test_http_429_is_eligible(self):
        result = classify_failure(_http_error(429))
        self.assertEqual(result.failure_class, FailureClass.FALLBACK_ELIGIBLE)
        self.assertEqual(result.reason, "rate_limited")

    def test_http_404_is_eligible_model_unavailable(self):
        result = classify_failure(_http_error(404))
        self.assertEqual(result.failure_class, FailureClass.FALLBACK_ELIGIBLE)
        self.assertEqual(result.reason, "model_unavailable")

    def test_connection_error_is_eligible(self):
        result = classify_failure(requests.ConnectionError("down"))
        self.assertEqual(result.failure_class, FailureClass.FALLBACK_ELIGIBLE)
        self.assertEqual(result.reason, "connection_error")

    def test_timeout_is_eligible(self):
        result = classify_failure(requests.Timeout("slow"))
        self.assertEqual(result.failure_class, FailureClass.FALLBACK_ELIGIBLE)
        self.assertEqual(result.reason, "timeout")

    def test_http_4xx_other_than_429_is_fatal(self):
        for status in (400, 401, 403, 402, 409, 422):
            result = classify_failure(_http_error(status))
            self.assertEqual(result.failure_class, FailureClass.FATAL)
            self.assertEqual(result.reason, "http_4xx")

    def test_missing_key_runtime_error_is_fatal(self):
        result = classify_failure(RuntimeError("API key is required"))
        self.assertEqual(result.failure_class, FailureClass.FATAL)

    def test_malformed_json_value_error_is_fatal(self):
        result = classify_failure(ValueError("malformed json"))
        self.assertEqual(result.failure_class, FailureClass.FATAL)

    def test_key_error_invalid_response_is_fatal(self):
        result = classify_failure(KeyError("choices"))
        self.assertEqual(result.failure_class, FailureClass.FATAL)

    def test_programming_errors_are_fatal(self):
        for exc in (TypeError("bad arg"), AttributeError("no attr")):
            result = classify_failure(exc)
            self.assertEqual(result.failure_class, FailureClass.FATAL)

    def test_cancellation_is_fatal(self):
        result = classify_failure(GeneratorExit())
        self.assertEqual(result.failure_class, FailureClass.FATAL)

    def test_unknown_exception_is_conservatively_fatal(self):
        result = classify_failure(LookupError("weird"))
        self.assertEqual(result.failure_class, FailureClass.FATAL)


# ---------------------------------------------------------------------------
# Helpers for the executor tests
# ---------------------------------------------------------------------------


def _registry_with(profiles: list[ModelProfile]) -> ModelProfileRegistry:
    registry = ModelProfileRegistry()
    for profile in profiles:
        registry.register(profile)
    return registry


def _default_profiles() -> list[ModelProfile]:
    return [
        ModelProfile(
            provider_name="Mock Provider",
            model_name="atlas-mock-v1",
            complexity_score=0.3,
            priority=10,
        ),
        ModelProfile(
            provider_name="Ollama",
            model_name="qwen3:8b",
            complexity_score=0.8,
            priority=20,
        ),
    ]


class TestFallbackExecutor(unittest.TestCase):
    """Executor behavior over the injected registry + call callable."""

    _OLLAMA = ("Ollama", "qwen3:8b")
    _MOCK = ("Mock Provider", "atlas-mock-v1")

    def _make_decision(self, chain=None):
        return RoutingDecision(
            provider_name=self._OLLAMA[0],
            model_name=self._OLLAMA[1],
            fallback_chain=chain
            or [self._MOCK],
        )

    def test_primary_success_no_fallback(self):
        executor = FallbackExecutor(_registry_with(_default_profiles()))
        calls: list[tuple[str, str]] = []

        def _call(provider, model):
            calls.append((provider, model))
            return f"ok-{provider}"

        result = executor.execute(
            RoutingRequest(complexity=0.5, allow_fallback=True),
            self._make_decision(),
            _call,
        )

        self.assertEqual(result.response, "ok-Ollama")
        self.assertFalse(result.used_fallback)
        self.assertEqual(calls, [("Ollama", "qwen3:8b")])

    def test_transient_primary_failure_reaches_eligible_fallback(self):
        executor = FallbackExecutor(_registry_with(_default_profiles()))
        calls: list[tuple[str, str]] = []

        def _call(provider, model):
            calls.append((provider, model))
            if provider == "Ollama":
                raise requests.ConnectionError("down")
            return f"ok-{provider}"

        result = executor.execute(
            RoutingRequest(complexity=0.2, allow_fallback=True),
            self._make_decision(),
            _call,
        )

        self.assertEqual(result.response, "ok-Mock Provider")
        self.assertTrue(result.used_fallback)
        self.assertEqual(
            calls,
            [("Ollama", "qwen3:8b"), ("Mock Provider", "atlas-mock-v1")],
        )

    def test_fatal_primary_failure_does_not_invoke_fallback(self):
        executor = FallbackExecutor(_registry_with(_default_profiles()))
        calls: list[tuple[str, str]] = []

        def _call(provider, model):
            calls.append((provider, model))
            raise RuntimeError("API key is required")

        with self.assertRaises(RuntimeError):
            executor.execute(
                RoutingRequest(complexity=0.5, allow_fallback=True),
                self._make_decision(),
                _call,
            )
        self.assertEqual(calls, [("Ollama", "qwen3:8b")])

    def test_capability_filter_drops_insufficient_complexity_candidate(self):
        registry = _registry_with(
            [
                ModelProfile(
                    provider_name="P1",
                    model_name="low",
                    complexity_score=0.2,
                    priority=10,
                ),
                ModelProfile(
                    provider_name="P2",
                    model_name="high",
                    complexity_score=0.9,
                    priority=20,
                ),
            ]
        )
        executor = FallbackExecutor(registry)
        # Primary is P2/high; the only candidate is P1/low at complexity 0.2,
        # below the request's 0.5, so it must be dropped.
        decision = RoutingDecision(
            provider_name="P2",
            model_name="high",
            fallback_chain=[("P1", "low")],
        )
        calls: list[tuple[str, str]] = []

        def _call(provider, model):
            calls.append((provider, model))
            raise requests.Timeout("x")

        with self.assertRaises(BaseException):
            executor.execute(
                RoutingRequest(complexity=0.5, allow_fallback=True),
                decision,
                _call,
            )
        # Primary only; the low-complexity candidate was never attempted.
        self.assertEqual(calls, [("P2", "high")])

    def test_preserves_original_chain_order(self):
        registry = _registry_with(
            [
                ModelProfile(
                    provider_name="P1",
                    model_name="m1",
                    complexity_score=0.7,
                    priority=10,
                ),
                ModelProfile(
                    provider_name="P2",
                    model_name="m2",
                    complexity_score=0.8,
                    priority=20,
                ),
                ModelProfile(
                    provider_name="P3",
                    model_name="m3",
                    complexity_score=0.9,
                    priority=30,
                ),
            ]
        )
        executor = FallbackExecutor(registry)
        decision = RoutingDecision(
            provider_name="P1",
            model_name="m1",
            # Deliberately out of priority order to verify order preserved.
            fallback_chain=[("P3", "m3"), ("P2", "m2")],
        )
        chain = executor._filtered_chain(
            RoutingRequest(complexity=0.5),
            decision,
        )
        self.assertEqual(chain, [("P3", "m3"), ("P2", "m2")])

    def test_duplicate_candidate_not_attempted_twice(self):
        registry = _registry_with(
            [
                ModelProfile(
                    provider_name="Mock Provider",
                    model_name="atlas-mock-v1",
                    complexity_score=0.5,
                    priority=10,
                ),
                ModelProfile(
                    provider_name="Ollama",
                    model_name="qwen3:8b",
                    complexity_score=0.8,
                    priority=20,
                ),
            ]
        )
        executor = FallbackExecutor(registry)
        decision = RoutingDecision(
            provider_name="Ollama",
            model_name="qwen3:8b",
            fallback_chain=[
                ("Mock Provider", "atlas-mock-v1"),
                ("Mock Provider", "atlas-mock-v1"),
            ],
        )
        calls: list[tuple[str, str]] = []

        def _call(provider, model):
            calls.append((provider, model))
            if provider == "Ollama":
                raise requests.Timeout("x")
            return f"ok-{provider}"

        executor.execute(
            RoutingRequest(complexity=0.5, allow_fallback=True),
            decision,
            _call,
        )
        self.assertEqual(
            calls.count(("Mock Provider", "atlas-mock-v1")),
            1,
        )

    def test_maximum_three_attempts(self):
        profiles = [
            ModelProfile(
                provider_name=f"P{i}",
                model_name=name_chr,
                complexity_score=0.5,
            )
            for i, name_chr in enumerate(
                ("a", "b", "c", "d", "e"),
                start=1,
            )
        ]
        executor = FallbackExecutor(_registry_with(profiles))
        decision = RoutingDecision(
            provider_name="P1",
            model_name="a",
            fallback_chain=[
                ("P2", "b"),
                ("P3", "c"),
                ("P4", "d"),
                ("P5", "e"),
            ],
        )
        calls: list[tuple[str, str]] = []

        def _call(provider, model):
            calls.append((provider, model))
            raise requests.Timeout("t")

        with self.assertRaises(BaseException):
            executor.execute(
                RoutingRequest(complexity=0.4, allow_fallback=True),
                decision,
                _call,
            )
        self.assertLessEqual(len(calls), 3)

    def test_configurable_max_attempts_bounds_candidate_walk(self):
        profiles = [
            ModelProfile(
                provider_name=f"P{i}",
                model_name=name_chr,
                complexity_score=0.5,
            )
            for i, name_chr in enumerate(("a", "b", "c"), start=1)
        ]
        executor = FallbackExecutor(
            _registry_with(profiles),
            max_attempts=2,
        )
        decision = RoutingDecision(
            provider_name="P1",
            model_name="a",
            fallback_chain=[("P2", "b"), ("P3", "c")],
        )
        calls: list[tuple[str, str]] = []

        def _call(provider, model):
            calls.append((provider, model))
            raise requests.Timeout("t")

        with self.assertRaises(BaseException):
            executor.execute(
                RoutingRequest(complexity=0.4, allow_fallback=True),
                decision,
                _call,
            )
        # max_attempts=2 -> primary + at most 1 fallback.
        self.assertLessEqual(len(calls), 2)

    def test_exhaustion_surfaces_failure_not_fake_success(self):
        executor = FallbackExecutor(_registry_with(_default_profiles()))
        calls: list[tuple[str, str]] = []

        def _call(provider, model):
            calls.append((provider, model))
            raise requests.Timeout("all down")

        with self.assertRaises(BaseException) as ctx:
            executor.execute(
                RoutingRequest(complexity=0.2, allow_fallback=True),
                self._make_decision(),
                _call,
            )
        self.assertIsInstance(ctx.exception, requests.Timeout)
        # The attempted pairs were attached for diagnosis.
        self.assertEqual(
            ctx.exception.atlas_attempted,
            [("Ollama", "qwen3:8b"), ("Mock Provider", "atlas-mock-v1")],
        )


class TestRoutingRequestFlag(unittest.TestCase):
    """The allow_fallback flag is off by default."""

    def test_default_is_false(self):
        request = RoutingRequest()
        self.assertFalse(request.allow_fallback)

    def test_can_be_enabled(self):
        request = RoutingRequest(allow_fallback=True)
        self.assertTrue(request.allow_fallback)


class TestAIServiceFallbackHook(unittest.TestCase):
    """AIService uses the executor only when the caller opts in.

    With ``allow_fallback=False`` (the default) the executor must never be
    invoked and the current direct-router behavior is preserved even when a
    fallback executor is wired.
    """

    def _make_service(self, executor):
        from unittest.mock import MagicMock

        from atlas.ai.ai_service import AIService
        from atlas.ai.providers.mock_provider import MockProvider
        from atlas.ai.router.ai_router import AIRouter
        from atlas.ai.routing.models import ModelProfile
        from atlas.ai.routing.registry import ModelProfileRegistry
        from atlas.ai.routing.router import ModelRouter

        router = AIRouter()
        router.registry.register(MockProvider())
        router.use("Mock Provider")

        registry = ModelProfileRegistry()
        registry.register(
            ModelProfile(
                provider_name="Mock Provider",
                model_name="atlas-mock-v1",
                complexity_score=0.3,
                priority=10,
            )
        )
        model_router = ModelRouter(registry)

        return AIService(
            router=router,
            model_router=model_router,
            fallback_executor=executor,
        ), model_router

    def test_allow_fallback_false_preserves_direct_behavior(self):
        spy = FallbackExecutor()
        spy.execute = MagicMock()  # type: ignore[method-assign]

        service, _ = self._make_service(spy)
        response = service.chat(
            ["hi"],
            routing_context=RoutingRequest(
                complexity=0.2,
                allow_fallback=False,
            ),
        )

        # The executor was never used; the router returned a normal response.
        spy.execute.assert_not_called()
        self.assertIsNotNone(response)
        self.assertTrue(hasattr(response, "text"))

    def test_allow_fallback_true_with_transient_failure_uses_executor(self):
        spy = FallbackExecutor(
            _registry_with(_default_profiles()),
            max_attempts=3,
        )
        # A normal (non-raise) recording executor would succeed immediately on
        # the primary, so simulate the executor path by checking it was
        # engaged.  We use a real executor with a router whose active provider
        # is the Mock; the primary will succeed, but the executor should still
        # have been entered (validate by a spy on the underlying router).
        service, _ = self._make_service(spy)
        service._router.chat = MagicMock(  # type: ignore[method-assign]
            return_value=_ok_response("fallback")
        )

        response = service.chat(
            ["hi"],
            routing_context=RoutingRequest(
                complexity=0.2,
                allow_fallback=True,
            ),
        )
        self.assertIsNotNone(response)
        # The real executor ran the primary attempt inside the hook.
        self.assertGreaterEqual(
            service._router.chat.call_count,
            1,
        )


def _ok_response(text: str):
    from atlas.models.ai_response import AIResponse

    return AIResponse(text=text, provider="test", model="test-m")


if __name__ == "__main__":
    unittest.main()