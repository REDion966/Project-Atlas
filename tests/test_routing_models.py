"""
Tests for Atlas AI Routing Models.
"""

import unittest

from atlas.ai.routing.models import (
    ModelProfile,
    RoutingDecision,
    RoutingRequest,
)


class TestModelProfile(unittest.TestCase):
    """Tests for ModelProfile dataclass."""

    def test_create_profile(self):
        """Should create a model profile with expected values."""

        profile = ModelProfile(
            provider_name="Ollama",
            model_name="qwen3:8b",
            complexity_score=0.8,
            latency_class="medium",
            cost_tier=0.2,
            supported_tasks=["conversation", "analysis"],
            priority=20,
            metadata={"source": "test"},
        )

        self.assertEqual(profile.provider_name, "Ollama")
        self.assertEqual(profile.model_name, "qwen3:8b")
        self.assertEqual(profile.complexity_score, 0.8)
        self.assertEqual(profile.latency_class, "medium")
        self.assertEqual(profile.cost_tier, 0.2)
        self.assertEqual(profile.supported_tasks, ["conversation", "analysis"])
        self.assertEqual(profile.priority, 20)
        self.assertEqual(profile.metadata, {"source": "test"})

    def test_default_values(self):
        """Should use sensible defaults for optional fields."""

        profile = ModelProfile(
            provider_name="Mock Provider",
            model_name="atlas-mock-v1",
        )

        self.assertEqual(profile.complexity_score, 0.5)
        self.assertEqual(profile.latency_class, "medium")
        self.assertEqual(profile.cost_tier, 0.5)
        self.assertEqual(profile.supported_tasks, [])
        self.assertEqual(profile.priority, 0)
        self.assertEqual(profile.metadata, {})


class TestRoutingRequest(unittest.TestCase):
    """Tests for RoutingRequest dataclass."""

    def test_create_request(self):
        """Should create a routing request with expected values."""

        request = RoutingRequest(
            complexity=0.7,
            latency_requirement="fast",
            task_type="analysis",
            context_size=1000,
            metadata={"source": "test"},
        )

        self.assertEqual(request.complexity, 0.7)
        self.assertEqual(request.latency_requirement, "fast")
        self.assertEqual(request.task_type, "analysis")
        self.assertEqual(request.context_size, 1000)
        self.assertEqual(request.metadata, {"source": "test"})

    def test_default_values(self):
        """Should use sensible defaults for optional fields."""

        request = RoutingRequest()

        self.assertEqual(request.complexity, 0.5)
        self.assertEqual(request.latency_requirement, "any")
        self.assertEqual(request.task_type, "conversation")
        self.assertEqual(request.context_size, 0)
        self.assertEqual(request.metadata, {})


class TestRoutingDecision(unittest.TestCase):
    """Tests for RoutingDecision dataclass."""

    def test_create_decision(self):
        """Should create a routing decision with expected values."""

        decision = RoutingDecision(
            provider_name="Ollama",
            model_name="qwen3:8b",
            confidence=1.0,
            reason="Best match",
            fallback_chain=[("Mock Provider", "atlas-mock-v1")],
            metadata={"complexity": 0.7},
        )

        self.assertEqual(decision.provider_name, "Ollama")
        self.assertEqual(decision.model_name, "qwen3:8b")
        self.assertEqual(decision.confidence, 1.0)
        self.assertEqual(decision.reason, "Best match")
        self.assertEqual(
            decision.fallback_chain,
            [("Mock Provider", "atlas-mock-v1")],
        )
        self.assertEqual(decision.metadata, {"complexity": 0.7})

    def test_default_values(self):
        """Should use sensible defaults for optional fields."""

        decision = RoutingDecision(
            provider_name="Mock Provider",
            model_name="atlas-mock-v1",
        )

        self.assertEqual(decision.confidence, 1.0)
        self.assertEqual(decision.reason, "")
        self.assertEqual(decision.fallback_chain, [])
        self.assertEqual(decision.metadata, {})


if __name__ == "__main__":
    unittest.main()
