"""
Tests for Atlas Routing Policy.
"""

import unittest

from atlas.ai.routing.models import ModelProfile, RoutingRequest
from atlas.ai.routing.policy import RoutingPolicy


class TestRoutingPolicy(unittest.TestCase):
    """Tests for RoutingPolicy."""

    def setUp(self):
        self.policy = RoutingPolicy()

        self.fast_profile = ModelProfile(
            provider_name="Mock Provider",
            model_name="atlas-mock-v1",
            complexity_score=0.3,
            latency_class="fast",
            cost_tier=0.1,
            priority=10,
        )

        self.powerful_profile = ModelProfile(
            provider_name="Ollama",
            model_name="qwen3:8b",
            complexity_score=0.8,
            latency_class="medium",
            cost_tier=0.2,
            priority=20,
        )

    def test_select_matching_profile(self):
        """Should select the profile matching the request complexity."""

        request = RoutingRequest(complexity=0.5)

        decision = self.policy.select(
            request,
            [self.fast_profile, self.powerful_profile],
        )

        self.assertIsNotNone(decision)
        self.assertEqual(decision.provider_name, "Ollama")
        self.assertEqual(decision.model_name, "qwen3:8b")
        self.assertEqual(decision.confidence, 1.0)
        self.assertIn("Selected", decision.reason)

    def test_select_cheapest_matching_profile(self):
        """Should prefer the cheapest profile that satisfies complexity."""

        request = RoutingRequest(complexity=0.2)

        decision = self.policy.select(
            request,
            [self.powerful_profile, self.fast_profile],
        )

        self.assertIsNotNone(decision)
        self.assertEqual(decision.provider_name, "Mock Provider")
        self.assertEqual(decision.model_name, "atlas-mock-v1")

    def test_fallback_when_no_match(self):
        """Should fall back to highest priority when no profile matches."""

        request = RoutingRequest(complexity=0.9)

        decision = self.policy.select(
            request,
            [self.fast_profile, self.powerful_profile],
        )

        self.assertIsNotNone(decision)
        self.assertEqual(decision.provider_name, "Ollama")
        self.assertEqual(decision.model_name, "qwen3:8b")
        self.assertEqual(decision.confidence, 0.5)
        self.assertIn("falling back", decision.reason)

    def test_priority_fallback_ordering(self):
        """Fallback chain should be ordered by priority descending."""

        request = RoutingRequest(complexity=0.9)

        decision = self.policy.select(
            request,
            [self.fast_profile, self.powerful_profile],
        )

        self.assertEqual(
            decision.fallback_chain,
            [("Mock Provider", "atlas-mock-v1")],
        )

    def test_empty_profiles_returns_none(self):
        """Should return None when no profiles are available."""

        request = RoutingRequest(complexity=0.5)

        decision = self.policy.select(request, [])

        self.assertIsNone(decision)

    def test_exact_complexity_match(self):
        """Should handle exact complexity boundary."""

        request = RoutingRequest(complexity=0.3)

        decision = self.policy.select(
            request,
            [self.fast_profile, self.powerful_profile],
        )

        self.assertIsNotNone(decision)
        self.assertEqual(decision.provider_name, "Mock Provider")
        self.assertEqual(decision.model_name, "atlas-mock-v1")


if __name__ == "__main__":
    unittest.main()
