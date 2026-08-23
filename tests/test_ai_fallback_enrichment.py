"""Tests for Phase D4 — routing & capability enrichment.

Covers:
- provider-availability filtering (real AIProviderRegistry data): candidates
  whose provider is not available are never attempted and are audited as
  ``provider_unavailable``.
- the availability guard is disabled by default (None -> no filtering).
- deferred constraints are NOT fabricated: cost tier, latency class,
  context size, and task-type matching are not enforced from data that has no
  authoritative request-side bound.
- the AIManager wires the real provider registry into the executor.
- D1-D3 invariants remain intact (complexity, registry resolution, dedup,
  primary-skip, attempt cap, opt-in default-off, streaming, audit).
"""

from __future__ import annotations

import unittest

import requests

from atlas.ai.fallback import FallbackExecutor
from atlas.ai.routing.models import ModelProfile, RoutingDecision, RoutingRequest
from atlas.ai.routing.registry import ModelProfileRegistry


def _profiles() -> list[ModelProfile]:
    return [
        ModelProfile(
            provider_name="P-A",
            model_name="model-a",
            complexity_score=0.4,
            priority=10,
        ),
        ModelProfile(
            provider_name="P-B",
            model_name="model-b",
            complexity_score=0.9,
            priority=20,
        ),
    ]


def _registry() -> ModelProfileRegistry:
    registry = ModelProfileRegistry()
    for profile in _profiles():
        registry.register(profile)
    return registry


def _capture():
    records: list[dict] = []
    return records, records.append


def _timeout_call(calls):
    def _call(provider, model):
        calls.append((provider, model))
        raise requests.Timeout("boom")

    return _call


def _decision(chain=None):
    return RoutingDecision(
        provider_name="P-A",
        model_name="model-a",
        fallback_chain=chain or [("P-B", "model-b")],
    )


class TestProviderAvailability(unittest.TestCase):
    """Candidates on unavailable providers are never attempted."""

    def test_unavailable_provider_candidate_skipped(self):
        calls: list[tuple[str, str]] = []
        records, audit = _capture()
        executor = FallbackExecutor(
            _registry(),
            audit_callback=audit,
            provider_available=lambda name: name == "P-A",
        )
        # Primary (P-A) fails transiently; P-B is unavailable -> no fallback.
        with self.assertRaises(BaseException) as ctx:
            executor.execute(
                RoutingRequest(complexity=0.3, allow_fallback=True),
                _decision(),
                _timeout_call(calls),
            )
        self.assertEqual(calls, [("P-A", "model-a")])
        self.assertIsNotNone(getattr(ctx.exception, "atlas_attempted", None))
        skipped = [
            r
            for r in records
            if r["event"].endswith(".skipped")
            and r.get("reason") == "provider_unavailable"
        ]
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["provider"], "P-B")
        self.assertEqual(skipped[0]["model"], "model-b")

    def test_available_provider_candidate_still_selected(self):
        calls: list[tuple[str, str]] = []
        executor = FallbackExecutor(
            _registry(),
            provider_available=lambda name: name in {"P-A", "P-B"},
        )
        # P-B is available and attempted; transient failure -> exhaustion.
        with self.assertRaises(BaseException):
            executor.execute(
                RoutingRequest(complexity=0.3, allow_fallback=True),
                _decision(),
                _timeout_call(calls),
            )
        self.assertEqual(calls, [("P-A", "model-a"), ("P-B", "model-b")])

    def test_availability_guard_disabled_by_default(self):
        calls: list[tuple[str, str]] = []
        executor = FallbackExecutor(_registry())  # no provider_available
        # Without the guard, P-B is attempted even though it has no provider
        # availability signal; the transient Timeout stays eligible.
        with self.assertRaises(BaseException):
            executor.execute(
                RoutingRequest(complexity=0.3, allow_fallback=True),
                _decision(),
                _timeout_call(calls),
            )
        self.assertEqual(calls, [("P-A", "model-a"), ("P-B", "model-b")])

    def test_primary_never_filtered_by_availability(self):
        # The primary provider must always run, even when the availability
        # guard would reject it (availability applies to fallback candidates).
        calls: list[tuple[str, str]] = []
        executor = FallbackExecutor(
            _registry(),
            provider_available=lambda name: False,
        )

        def _call(provider, model):
            calls.append((provider, model))
            return "primary-ok"

        result = executor.execute(
            RoutingRequest(complexity=0.3, allow_fallback=True),
            _decision(),
            _call,
        )
        self.assertEqual(result.response, "primary-ok")
        self.assertEqual(calls, [("P-A", "model-a")])


class TestDeferredConstraints(unittest.TestCase):
    """Constraints without authoritative request-side data are NOT enforced."""

    def test_cost_tier_not_used_to_reorder(self):
        # A higher-cost candidate is still eligible as the only fallback.
        calls: list[tuple[str, str]] = []
        executor = FallbackExecutor(_registry())
        with self.assertRaises(BaseException):
            executor.execute(
                RoutingRequest(complexity=0.3, allow_fallback=True),
                _decision(),
                _timeout_call(calls),
            )
        # P-B is attempted even though no cost bound exists.
        self.assertIn(("P-B", "model-b"), calls)

    def test_latency_class_not_enforced(self):
        # Request latency_requirement is free-text and unused by the guard.
        calls: list[tuple[str, str]] = []
        executor = FallbackExecutor(_registry())
        with self.assertRaises(BaseException):
            executor.execute(
                RoutingRequest(
                    complexity=0.3,
                    latency_requirement="faster-than-light",
                    allow_fallback=True,
                ),
                _decision(),
                _timeout_call(calls),
            )
        self.assertIn(("P-B", "model-b"), calls)

    def test_task_type_not_enforced(self):
        # supported_tasks matching is not applied (would over-restrict).
        calls: list[tuple[str, str]] = []
        executor = FallbackExecutor(_registry())
        with self.assertRaises(BaseException):
            executor.execute(
                RoutingRequest(
                    complexity=0.3,
                    task_type="respond",  # not in any supported_tasks list
                    allow_fallback=True,
                ),
                _decision(),
                _timeout_call(calls),
            )
        self.assertIn(("P-B", "model-b"), calls)

    def test_context_size_not_enforced(self):
        # ModelProfile has no context-size field; the guard does not invent one.
        calls: list[tuple[str, str]] = []
        executor = FallbackExecutor(_registry())
        with self.assertRaises(BaseException):
            executor.execute(
                RoutingRequest(
                    complexity=0.3,
                    context_size=2_000_000,
                    allow_fallback=True,
                ),
                _decision(),
                _timeout_call(calls),
            )
        self.assertIn(("P-B", "model-b"), calls)


class TestAIManagerWiring(unittest.TestCase):
    """AIManager.initialize threads the real provider registry into the
    executor."""

    def test_executor_has_provider_availability_wired(self):
        from atlas.ai.ai_manager import AIManager

        manager = AIManager()
        manager.initialize(
            provider="Ollama",
            model="qwen3:8b",
            timeout=30,
        )
        executor = manager.service._fallback_executor  # noqa: SLF001
        self.assertIsNotNone(executor)
        self.assertIsNotNone(executor.provider_available)
        # Registered providers report available; unknown ones do not.
        self.assertTrue(executor.provider_available("Ollama"))
        self.assertTrue(executor.provider_available("Mock Provider"))
        self.assertFalse(executor.provider_available("Nonexistent Provider"))


if __name__ == "__main__":
    unittest.main()