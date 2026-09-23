"""Phase 5.3 — Capability discovery: evidence contract.

Investigation result: Atlas already discovers capabilities deterministically and
model-independently, so no semantic/LLM discovery was introduced.

* ``CapabilityAnalyzer`` maps reasoning plan-step actions to capability names via
  the deterministic action map (respond→conversation, query→knowledge_retrieval,
  analyze→analysis, execute→task_execution, idle→noop; unknown→general).
* ``CapabilityModel.entries`` is the bounded inventory of declared/registered
  capabilities.
* ``ToolSelector`` performs deterministic keyword tool discovery.
"""

from __future__ import annotations

from atlas.reasoning.capabilities.analyzer import CapabilityAnalyzer
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.models import ReasoningPlan, ReasoningStep
from atlas.tools.models import Tool, ToolRequest
from atlas.tools.selector import ToolSelector


class TestPhase53CapabilityDiscovery:
    def test_analyzer_discovers_capabilities_from_plan_actions(self):
        plan = ReasoningPlan(
            goal="g",
            steps=[ReasoningStep(action="respond"), ReasoningStep(action="query")],
        )
        discovered = {c.name for c in CapabilityAnalyzer().analyze(plan)}
        assert discovered == {"conversation", "knowledge_retrieval"}

    def test_unknown_action_is_discovered_as_general_and_not_routable(self):
        plan = ReasoningPlan(goal="g", steps=[ReasoningStep(action="frobnicate")])
        capabilities = CapabilityAnalyzer().analyze(plan)
        assert capabilities[0].name == "general"
        # An unknown/unregistered capability is never routed.
        assert CapabilityRouter(CapabilityRegistry()).route(capabilities) == []

    def test_known_vs_unknown_is_distinguishable(self):
        registry = CapabilityRegistry()
        registry.register("conversation", lambda params: None)
        router = CapabilityRouter(registry)
        assert router.can_route(type("C", (), {"name": "conversation"})()) is True
        assert router.can_route(type("C", (), {"name": "general"})()) is False

    def test_tool_discovery_is_deterministic(self):
        tools = [
            Tool(name="echo", description="Echo text", category="utility"),
            Tool(name="search", description="Search the web", category="search"),
        ]
        selector = ToolSelector()
        picked = selector.select(ToolRequest(goal="search the web"), tools)
        assert picked and picked[0].name == "search"
        # No tools available → honest empty result.
        assert selector.select(ToolRequest(goal="search the web"), []) == []
