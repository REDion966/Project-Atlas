"""
Tests for the Atlas Capability Router (Phase 6.4).

Covers:
  - ExecutionRoute data model
  - CapabilityRouter (route, empty list, missing handlers, order preservation)
  - CapabilityRouter.can_route
  - No external dependencies verification
"""

import unittest
import inspect

from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.models import ExecutionRoute
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.execution.models import ExecutionResult, CapabilityHandler


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_handler(success: bool = True, output: dict | None = None):
    """Return a CapabilityHandler that returns a fixed result."""
    def handler(params: dict) -> ExecutionResult:
        return ExecutionResult(
            capability="test",
            success=success,
            output=output or {"received": params},
        )
    return handler


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExecutionRoute(unittest.TestCase):
    """Tests for ExecutionRoute data model."""

    def test_creation_with_all_fields(self):
        """An ExecutionRoute can be created with all fields."""
        route = ExecutionRoute(
            capability="conversation",
            handler_name="conversation",
            parameters={"action": "respond"},
            strategy="default",
            metadata={"priority": 10, "reason": "Test"},
        )
        self.assertEqual(route.capability, "conversation")
        self.assertEqual(route.handler_name, "conversation")
        self.assertEqual(route.parameters["action"], "respond")
        self.assertEqual(route.strategy, "default")
        self.assertEqual(route.metadata["priority"], 10)

    def test_default_values(self):
        """ExecutionRoute has sensible defaults."""
        route = ExecutionRoute()
        self.assertEqual(route.capability, "")
        self.assertEqual(route.handler_name, "")
        self.assertEqual(route.parameters, {})
        self.assertEqual(route.strategy, "default")
        self.assertEqual(route.metadata, {})

    def test_strategy_default(self):
        """The default strategy is 'default'."""
        route = ExecutionRoute(capability="test", handler_name="test")
        self.assertEqual(route.strategy, "default")


class TestCapabilityRouter(unittest.TestCase):
    """Tests for CapabilityRouter."""

    def setUp(self):
        self.registry = CapabilityRegistry()
        self.router = CapabilityRouter(self.registry)

    def test_route_empty_list(self):
        """Routing an empty list returns an empty list."""
        routes = self.router.route([])
        self.assertEqual(routes, [])

    def test_route_single_capability(self):
        """A single registered capability is routed successfully."""
        self.registry.register("conversation", _make_handler())

        capabilities = [
            Capability(
                name="conversation",
                priority=10,
                reason="Test",
                metadata={"action": "respond"},
            ),
        ]

        routes = self.router.route(capabilities)

        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0].capability, "conversation")
        self.assertEqual(routes[0].handler_name, "conversation")
        self.assertEqual(routes[0].parameters, {"action": "respond"})
        self.assertEqual(routes[0].strategy, "default")
        self.assertEqual(routes[0].metadata["priority"], 10)
        self.assertEqual(routes[0].metadata["reason"], "Test")

    def test_route_multiple_capabilities(self):
        """Multiple capabilities are routed in order."""
        self.registry.register("conversation", _make_handler())
        self.registry.register("knowledge_retrieval", _make_handler())

        capabilities = [
            Capability(name="conversation", priority=10),
            Capability(name="knowledge_retrieval", priority=8),
        ]

        routes = self.router.route(capabilities)

        self.assertEqual(len(routes), 2)
        self.assertEqual(routes[0].capability, "conversation")
        self.assertEqual(routes[1].capability, "knowledge_retrieval")

    def test_route_missing_handler_skipped(self):
        """A capability with no registered handler is omitted from routes."""
        self.registry.register("conversation", _make_handler())

        capabilities = [
            Capability(name="conversation", priority=10),
            Capability(name="unregistered_cap", priority=5),
        ]

        routes = self.router.route(capabilities)

        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0].capability, "conversation")

    def test_route_all_missing_returns_empty(self):
        """When no capabilities have handlers, an empty list is returned."""
        capabilities = [
            Capability(name="missing_a", priority=10),
            Capability(name="missing_b", priority=5),
        ]

        routes = self.router.route(capabilities)

        self.assertEqual(routes, [])

    def test_route_preserves_capability_order(self):
        """Routes are returned in the same order as input capabilities."""
        self.registry.register("a", _make_handler())
        self.registry.register("b", _make_handler())
        self.registry.register("c", _make_handler())

        capabilities = [
            Capability(name="c", priority=1),
            Capability(name="a", priority=3),
            Capability(name="b", priority=2),
        ]

        routes = self.router.route(capabilities)

        self.assertEqual(len(routes), 3)
        self.assertEqual(routes[0].capability, "c")
        self.assertEqual(routes[1].capability, "a")
        self.assertEqual(routes[2].capability, "b")

    def test_route_parameters_are_copied(self):
        """Route parameters are a copy of capability metadata, not a reference."""
        self.registry.register("test", _make_handler())

        metadata = {"key": "value"}
        capabilities = [
            Capability(name="test", priority=10, metadata=metadata),
        ]

        routes = self.router.route(capabilities)
        self.assertEqual(routes[0].parameters, {"key": "value"})

        # Modifying the original metadata should not affect the route
        metadata["key"] = "changed"
        self.assertEqual(routes[0].parameters["key"], "value")

    def test_can_route_returns_true_for_registered(self):
        """can_route returns True when a handler is registered."""
        self.registry.register("conversation", _make_handler())
        capability = Capability(name="conversation", priority=10)
        self.assertTrue(self.router.can_route(capability))

    def test_can_route_returns_false_for_unregistered(self):
        """can_route returns False when no handler is registered."""
        capability = Capability(name="nonexistent", priority=10)
        self.assertFalse(self.router.can_route(capability))

    def test_can_route_after_unregister(self):
        """can_route returns False after a handler is unregistered."""
        self.registry.register("temp", _make_handler())
        capability = Capability(name="temp", priority=10)
        self.assertTrue(self.router.can_route(capability))

        self.registry.unregister("temp")
        self.assertFalse(self.router.can_route(capability))


class TestCapabilityRouterNoDependencies(unittest.TestCase):
    """Verify CapabilityRouter has no external dependencies."""

    def test_router_has_no_external_dependencies(self):
        """CapabilityRouter does not import AI, memory, knowledge, EventBus, or services."""
        source = inspect.getsource(CapabilityRouter)
        self.assertNotIn("AIService", source)
        self.assertNotIn("Memory", source)
        self.assertNotIn("Knowledge", source)
        self.assertNotIn("EventBus", source)
        self.assertNotIn("Service", source)


if __name__ == "__main__":
    unittest.main()