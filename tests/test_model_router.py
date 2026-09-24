"""
Tests for Atlas Model Router.
"""

import unittest

from atlas.ai.routing.models import ModelProfile, RoutingRequest
from atlas.ai.routing.registry import ModelProfileRegistry
from atlas.ai.routing.router import ModelRouter


class TestModelRouter(unittest.TestCase):
    """Tests for ModelRouter."""

    def test_single_profile(self):
        """Should route to the only registered profile."""

        registry = ModelProfileRegistry()
        registry.register(
            ModelProfile(
                provider_name="Mock Provider",
                model_name="atlas-mock-v1",
                complexity_score=0.5,
                priority=10,
            )
        )

        router = ModelRouter(registry)
        request = RoutingRequest(complexity=0.3)

        decision = router.route(request)

        self.assertIsNotNone(decision)
        self.assertEqual(decision.provider_name, "Mock Provider")
        self.assertEqual(decision.model_name, "atlas-mock-v1")

    def test_multiple_profiles(self):
        """Should select the best matching profile among many.

        Selecting an external provider requires the explicit opt-in
        (deny-by-default); with it enabled, policy selection applies unchanged.
        """

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

        router = ModelRouter(registry, external_providers=True)
        request = RoutingRequest(complexity=0.7)

        decision = router.route(request)

        self.assertIsNotNone(decision)
        self.assertEqual(decision.provider_name, "Ollama")
        self.assertEqual(decision.model_name, "qwen3:8b")

    def test_fallback(self):
        """Should include eligible fallback options when selecting.

        With the explicit external-providers opt-in enabled, the fallback
        chain contains only real providers — the deterministic no-network
        tier is excluded from selection entirely (NLU-0).
        """

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
        registry.register(
            ModelProfile(
                provider_name="LM Studio",
                model_name="qwen3:8b",
                complexity_score=0.9,
                priority=15,
            )
        )

        router = ModelRouter(registry, external_providers=True)
        request = RoutingRequest(complexity=0.7)

        decision = router.route(request)

        self.assertIsNotNone(decision)
        self.assertEqual(decision.provider_name, "Ollama")
        self.assertEqual(decision.model_name, "qwen3:8b")
        self.assertEqual(
            decision.fallback_chain,
            [("LM Studio", "qwen3:8b")],
        )

    def test_deny_by_default_never_selects_external(self):
        """Without the opt-in, an external provider is never selected."""

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
        for complexity in (0.3, 0.7, 0.9, 1.0):
            with self.subTest(complexity=complexity):
                decision = router.route(RoutingRequest(complexity=complexity))
                self.assertIsNotNone(decision)
                self.assertEqual(decision.provider_name, "Mock Provider")

    def test_missing_context(self):
        """Should return None when no profiles are registered."""

        registry = ModelProfileRegistry()
        router = ModelRouter(registry)
        request = RoutingRequest(complexity=0.5)

        decision = router.route(request)

        self.assertIsNone(decision)


if __name__ == "__main__":
    unittest.main()
