"""
Tests for the Atlas Capability Execution Layer (Phase 6.3).

Covers:
  - ExecutionResult data model
  - CapabilityHandler type alias
  - CapabilityRegistry (register, unregister, get, has, clear, errors)
  - CapabilityDispatcher (dispatch, missing handler, handler exceptions)
"""

import unittest
import inspect

from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.models import ExecutionResult, CapabilityHandler
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher


# ---------------------------------------------------------------------------
# Helper factories for use across test classes
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


def _make_failing_handler(error_msg: str = "handler failed"):
    """Return a CapabilityHandler that raises an exception."""
    def handler(params: dict) -> ExecutionResult:
        msg = error_msg
        raise RuntimeError(msg)
    return handler


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExecutionResult(unittest.TestCase):
    """Tests for ExecutionResult data model."""

    def test_creation_with_all_fields(self):
        """An ExecutionResult can be created with all fields."""
        result = ExecutionResult(
            capability="conversation",
            success=True,
            output={"reply": "Hello"},
            error="",
            metadata={"duration_ms": 42},
        )
        self.assertEqual(result.capability, "conversation")
        self.assertTrue(result.success)
        self.assertEqual(result.output["reply"], "Hello")
        self.assertEqual(result.error, "")
        self.assertEqual(result.metadata["duration_ms"], 42)

    def test_default_values(self):
        """ExecutionResult has sensible defaults."""
        result = ExecutionResult()
        self.assertEqual(result.capability, "")
        self.assertFalse(result.success)
        self.assertEqual(result.output, {})
        self.assertEqual(result.error, "")
        self.assertEqual(result.metadata, {})

    def test_success_vs_failure(self):
        """Success and failure states are correctly represented."""
        success_result = ExecutionResult(capability="test", success=True)
        failure_result = ExecutionResult(capability="test", success=False, error="boom")

        self.assertTrue(success_result.success)
        self.assertFalse(failure_result.success)
        self.assertEqual(failure_result.error, "boom")


class TestCapabilityHandler(unittest.TestCase):
    """Tests for the CapabilityHandler type alias."""

    def test_handler_is_callable(self):
        """A CapabilityHandler must be a callable that returns ExecutionResult."""
        def handler(params: dict) -> ExecutionResult:
            return ExecutionResult(capability="test", success=True)

        # Verify the handler conforms to the type alias
        result: ExecutionResult = handler({"key": "value"})
        self.assertIsInstance(result, ExecutionResult)
        self.assertTrue(result.success)

    def test_handler_receives_parameters(self):
        """The handler receives parameters and can use them."""
        def handler(params: dict) -> ExecutionResult:
            return ExecutionResult(
                capability="test",
                success=True,
                output={"input": params.get("query", "")},
            )

        result = handler({"query": "hello"})
        self.assertEqual(result.output["input"], "hello")

    def test_handler_can_fail(self):
        """A handler can return a failure ExecutionResult."""
        def handler(params: dict) -> ExecutionResult:
            return ExecutionResult(
                capability="test",
                success=False,
                error="Something went wrong",
            )

        result = handler({})
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Something went wrong")


class TestCapabilityRegistry(unittest.TestCase):
    """Tests for CapabilityRegistry."""

    def setUp(self):
        self.registry = CapabilityRegistry()

    def test_register_and_get(self):
        """A handler can be registered and retrieved."""
        handler = _make_handler()
        self.registry.register("conversation", handler)

        retrieved = self.registry.get("conversation")
        self.assertIsNotNone(retrieved)
        self.assertIs(retrieved, handler)

    def test_register_duplicate_raises(self):
        """Registering the same name twice raises ValueError."""
        handler = _make_handler()
        self.registry.register("test", handler)

        with self.assertRaises(ValueError) as ctx:
            self.registry.register("test", _make_handler())
        self.assertIn("test", str(ctx.exception))

    def test_get_nonexistent_returns_none(self):
        """Getting an unregistered name returns None."""
        result = self.registry.get("nonexistent")
        self.assertIsNone(result)

    def test_has_registered(self):
        """has() returns True for registered capabilities."""
        self.registry.register("analysis", _make_handler())
        self.assertTrue(self.registry.has("analysis"))
        self.assertFalse(self.registry.has("nonexistent"))

    def test_unregister(self):
        """A handler can be unregistered."""
        self.registry.register("task", _make_handler())
        self.assertTrue(self.registry.has("task"))

        self.registry.unregister("task")
        self.assertFalse(self.registry.has("task"))

    def test_unregister_nonexistent_raises(self):
        """Unregistering a missing name raises KeyError."""
        with self.assertRaises(KeyError) as ctx:
            self.registry.unregister("missing")
        self.assertIn("missing", str(ctx.exception))

    def test_registered_names(self):
        """registered_names returns sorted list of names."""
        self.registry.register("z_last", _make_handler())
        self.registry.register("a_first", _make_handler())

        names = self.registry.registered_names
        self.assertEqual(names, ["a_first", "z_last"])

    def test_count(self):
        """count returns the number of registered handlers."""
        self.assertEqual(self.registry.count, 0)

        self.registry.register("a", _make_handler())
        self.assertEqual(self.registry.count, 1)

        self.registry.register("b", _make_handler())
        self.assertEqual(self.registry.count, 2)

    def test_clear(self):
        """clear removes all registered handlers."""
        self.registry.register("a", _make_handler())
        self.registry.register("b", _make_handler())
        self.assertEqual(self.registry.count, 2)

        self.registry.clear()
        self.assertEqual(self.registry.count, 0)

    def test_empty_registry_properties(self):
        """An empty registry has correct default properties."""
        self.assertEqual(self.registry.count, 0)
        self.assertEqual(self.registry.registered_names, [])

    def test_handler_execution_through_registry(self):
        """A handler retrieved from the registry can be executed."""
        def handler(params: dict) -> ExecutionResult:
            return ExecutionResult(capability="greet", success=True, output={"msg": "hi"})

        self.registry.register("greet", handler)
        retrieved = self.registry.get("greet")
        self.assertIsNotNone(retrieved)

        result = retrieved({})
        self.assertIsInstance(result, ExecutionResult)
        self.assertEqual(result.capability, "greet")
        self.assertEqual(result.output["msg"], "hi")


class TestCapabilityDispatcher(unittest.TestCase):
    """Tests for CapabilityDispatcher."""

    def setUp(self):
        self.registry = CapabilityRegistry()
        self.dispatcher = CapabilityDispatcher(self.registry)

    def test_dispatch_empty_list(self):
        """Dispatching an empty list returns an empty list."""
        results = self.dispatcher.dispatch([])
        self.assertEqual(results, [])

    def test_dispatch_single_capability(self):
        """A single registered capability is dispatched successfully."""
        def handler(params: dict) -> ExecutionResult:
            return ExecutionResult(
                capability="conversation",
                success=True,
                output={"handled": True, "params": params},
            )

        self.registry.register("conversation", handler)

        capabilities = [
            Capability(
                name="conversation",
                priority=10,
                reason="Test",
                metadata={"action": "respond"},
            ),
        ]

        results = self.dispatcher.dispatch(capabilities)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].capability, "conversation")
        self.assertTrue(results[0].output["handled"])

    def test_dispatch_multiple_capabilities(self):
        """Multiple capabilities are dispatched in order."""
        def conv_handler(params: dict) -> ExecutionResult:
            return ExecutionResult(capability="conversation", success=True)

        def knowledge_handler(params: dict) -> ExecutionResult:
            return ExecutionResult(capability="knowledge_retrieval", success=True)

        self.registry.register("conversation", conv_handler)
        self.registry.register("knowledge_retrieval", knowledge_handler)

        capabilities = [
            Capability(name="conversation", priority=10),
            Capability(name="knowledge_retrieval", priority=8),
        ]

        results = self.dispatcher.dispatch(capabilities)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].capability, "conversation")
        self.assertEqual(results[1].capability, "knowledge_retrieval")
        self.assertTrue(all(r.success for r in results))

    def test_dispatch_missing_handler(self):
        """A capability with no registered handler returns a failed result."""
        capabilities = [
            Capability(
                name="unregistered_cap",
                priority=5,
                reason="No handler exists",
            ),
        ]

        results = self.dispatcher.dispatch(capabilities)

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertIn("No handler registered", results[0].error)
        self.assertEqual(results[0].capability, "unregistered_cap")

    def test_dispatch_handler_raises_exception(self):
        """A handler that raises an exception returns a failed result."""

        self.registry.register("faulty", _make_failing_handler("internal error"))

        capabilities = [
            Capability(name="faulty", priority=10, reason="Will fail"),
        ]

        results = self.dispatcher.dispatch(capabilities)

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertIn("internal error", results[0].error)

    def test_dispatch_mixed_success_failure(self):
        """Some capabilities succeed while others fail."""
        def good_handler(params: dict) -> ExecutionResult:
            return ExecutionResult(capability="good", success=True)

        self.registry.register("good", good_handler)

        capabilities = [
            Capability(name="good", priority=10),
            Capability(name="missing", priority=5),
        ]

        results = self.dispatcher.dispatch(capabilities)

        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].capability, "good")
        self.assertFalse(results[1].success)
        self.assertEqual(results[1].capability, "missing")

    def test_dispatch_preserves_capability_order(self):
        """Results are returned in the same order as input capabilities."""
        def handler_a(params: dict) -> ExecutionResult:
            return ExecutionResult(capability="a", success=True)

        def handler_b(params: dict) -> ExecutionResult:
            return ExecutionResult(capability="b", success=True)

        def handler_c(params: dict) -> ExecutionResult:
            return ExecutionResult(capability="c", success=True)

        self.registry.register("a", handler_a)
        self.registry.register("b", handler_b)
        self.registry.register("c", handler_c)

        capabilities = [
            Capability(name="c", priority=1),
            Capability(name="a", priority=3),
            Capability(name="b", priority=2),
        ]

        results = self.dispatcher.dispatch(capabilities)

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].capability, "c")
        self.assertEqual(results[1].capability, "a")
        self.assertEqual(results[2].capability, "b")


class TestCapabilityDispatcherNoDependencies(unittest.TestCase):
    """Verify CapabilityDispatcher has no external dependencies."""

    def test_dispatcher_has_no_external_dependencies(self):
        """CapabilityDispatcher does not import AI, memory, knowledge, EventBus, or services."""
        source = inspect.getsource(CapabilityDispatcher)
        self.assertNotIn("AIService", source)
        self.assertNotIn("Memory", source)
        self.assertNotIn("Knowledge", source)
        self.assertNotIn("EventBus", source)
        self.assertNotIn("Service", source)


class TestCapabilityRegistryNoDependencies(unittest.TestCase):
    """Verify CapabilityRegistry has no external dependencies."""

    def test_registry_has_no_external_dependencies(self):
        """CapabilityRegistry does not import AI, memory, knowledge, EventBus, or services."""
        source = inspect.getsource(CapabilityRegistry)
        self.assertNotIn("AIService", source)
        self.assertNotIn("Memory", source)
        self.assertNotIn("Knowledge", source)
        self.assertNotIn("EventBus", source)
        self.assertNotIn("Service", source)


if __name__ == "__main__":
    unittest.main()