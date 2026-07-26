"""
Phase 6.9 — Tool Intelligence Wiring Integration Tests

Validates that CognitionService optionally runs tool intelligence
when a ToolEngine is injected alongside the reasoning pipeline,
while preserving backward compatibility when it is not.
"""

import unittest

from atlas.cognition.decision import CognitionDecision
from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.controller import ReasoningController
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.services.cognition_service import CognitionService
from atlas.tools.builtins import BUILTIN_TOOLS
from atlas.tools.engine import ToolEngine
from atlas.tools.executor import ToolExecutor
from atlas.tools.registry import ToolRegistry
from atlas.tools.selector import ToolSelector


def _simple_handler(params: dict) -> ExecutionResult:
    """A simple handler that returns a successful execution result."""
    return ExecutionResult(
        capability=params.get("action", "unknown"),
        success=True,
        output={"received": params},
    )


class TestCognitionServiceWithoutTools(unittest.TestCase):
    """Backward compatibility when no ToolEngine is injected."""

    def setUp(self):
        self.registry = CapabilityRegistry()
        self.registry.register("conversation", _simple_handler)

        self.service = CognitionService(
            reasoning_controller=ReasoningController(),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=self.registry,
            capability_router=CapabilityRouter(self.registry),
            capability_dispatcher=CapabilityDispatcher(self.registry),
        )
        self.service.start()

    def tearDown(self):
        self.service.stop()

    def test_tool_engine_property_is_none_by_default(self):
        """tool_engine property returns None when not injected."""
        self.assertIsNone(self.service.tool_engine)

    def test_process_runs_without_tools(self):
        """Pipeline runs normally without tool engine."""
        decision = self.service.process("Hello")
        self.assertIn("reasoning", decision.data)
        self.assertNotIn("tool_results", decision.data)

    def test_status_reports_no_tools(self):
        """Status correctly reports has_tools=False."""
        status = self.service.status
        self.assertFalse(status["has_tools"])

    def test_existing_behavior_preserved(self):
        """Existing reasoning still works without tools."""
        decision = self.service.process("Hello world")
        self.assertIn("reasoning", decision.data)
        self.assertIsInstance(decision, CognitionDecision)


class TestCognitionServiceWithTools(unittest.TestCase):
    """CognitionService works correctly with ToolEngine injected."""

    def setUp(self):
        self.registry = CapabilityRegistry()
        self.registry.register("conversation", _simple_handler)

        self.tool_registry = ToolRegistry()
        for tool in BUILTIN_TOOLS:
            self.tool_registry.register(tool)
        self.tool_selector = ToolSelector()
        self.tool_executor = ToolExecutor(self.tool_registry)
        self.tool_engine = ToolEngine(
            self.tool_registry,
            self.tool_selector,
            self.tool_executor,
        )

        self.service = CognitionService(
            reasoning_controller=ReasoningController(),
            capability_analyzer=CapabilityAnalyzer(),
            capability_registry=self.registry,
            capability_router=CapabilityRouter(self.registry),
            capability_dispatcher=CapabilityDispatcher(self.registry),
            tool_engine=self.tool_engine,
        )
        self.service.start()

    def tearDown(self):
        self.service.stop()

    def test_tool_engine_property_is_injected(self):
        """tool_engine property returns the injected engine."""
        self.assertIs(self.service.tool_engine, self.tool_engine)

    def test_status_reports_has_tools(self):
        """Status correctly reports has_tools=True."""
        status = self.service.status
        self.assertTrue(status["has_tools"])

    def test_tool_results_in_decision(self):
        """Tool results appear in decision.data when engine is injected."""
        decision = self.service.process("Hello")
        self.assertIn("tool_results", decision.data)

    def test_tool_results_has_expected_structure(self):
        """Tool results in decision.data has correct fields."""
        decision = self.service.process("Test input")
        self.assertIn("tool_results", decision.data)

        tool_results = decision.data["tool_results"]
        self.assertIn("tool_name", tool_results)
        self.assertIn("success", tool_results)
        self.assertIn("output", tool_results)
        self.assertIn("error", tool_results)
        self.assertIn("execution_time_ms", tool_results)

    def test_tools_do_not_break_existing_behavior(self):
        """Existing reasoning still works with tools."""
        decision = self.service.process("Hello world")

        self.assertIn("reasoning", decision.data)
        self.assertIn("tool_results", decision.data)
        self.assertIsInstance(decision, CognitionDecision)


class TestCognitionServiceToolsWithoutPipeline(unittest.TestCase):
    """Tools are skipped when no reasoning pipeline is available."""

    def setUp(self):
        self.tool_registry = ToolRegistry()
        for tool in BUILTIN_TOOLS:
            self.tool_registry.register(tool)
        self.tool_selector = ToolSelector()
        self.tool_executor = ToolExecutor(self.tool_registry)
        self.tool_engine = ToolEngine(
            self.tool_registry,
            self.tool_selector,
            self.tool_executor,
        )

        self.service = CognitionService(
            tool_engine=self.tool_engine,
        )
        self.service.start()

    def tearDown(self):
        self.service.stop()

    def test_no_tools_without_pipeline(self):
        """No tool results when reasoning pipeline didn't run."""
        decision = self.service.process("Hello")
        self.assertNotIn("tool_results", decision.data)

    def test_status_still_reports_has_tools(self):
        """Status still reports has_tools=True even without pipeline."""
        status = self.service.status
        self.assertTrue(status["has_tools"])


class TestAtlasKernelToolWiring(unittest.TestCase):
    """Integration test verifying ToolEngine is wired in Atlas.start()."""

    def test_tool_engine_created_in_atlas_start(self):
        """Atlas.start() creates and injects a ToolEngine."""
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            cognition_service = atlas.container.get("cognition_service")
            self.assertIsNotNone(cognition_service.tool_engine)
            self.assertIsInstance(
                cognition_service.tool_engine,
                ToolEngine,
            )
        finally:
            atlas.shutdown()

    def test_tool_engine_cleaned_up_on_shutdown(self):
        """Atlas.shutdown() nullifies the tool engine."""
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        atlas.start()
        atlas.shutdown()
        self.assertIsNone(atlas._tool_engine)
        self.assertIsNone(atlas._tool_executor)
        self.assertIsNone(atlas._tool_selector)
        self.assertIsNone(atlas._tool_registry)

    def test_tool_engine_not_in_service_container(self):
        """ToolEngine is a private dependency, not in ServiceContainer."""
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            expected_keys = {
                "ai", "conversation", "memory", "knowledge",
                "cognition", "cognitive", "cognition_service",
                "cognition_api", "tasks",
                "runtime_coordinator", "understanding",
                "world_model", "evolution_observer", "learning_engine",
                "identity",
            }
            self.assertEqual(
                set(atlas.container.names()),
                expected_keys,
            )
        finally:
            atlas.shutdown()

    def test_tool_engine_available_via_cognition_service(self):
        """ToolEngine is accessible through cognition_service."""
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            cognition_service = atlas.container.get("cognition_service")
            self.assertTrue(cognition_service.status["has_tools"])
        finally:
            atlas.shutdown()

    def test_builtin_tools_registered_on_start(self):
        """Built-in tools (echo, list_tools) are registered on start."""
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            cognition_service = atlas.container.get("cognition_service")
            tool_engine = cognition_service.tool_engine
            tools = tool_engine.available_tools()
            tool_names = [t.name for t in tools]
            self.assertIn("echo", tool_names)
            self.assertIn("list_tools", tool_names)
        finally:
            atlas.shutdown()


if __name__ == "__main__":
    unittest.main()