"""Phase 18.4 — ToolChainPlanner tests."""

from dataclasses import dataclass, field
from typing import Any

import pytest

from atlas.toolchain.catalog import MAX_PLAN_STEPS
from atlas.toolchain.models import ToolChainPlan, ToolStep
from atlas.toolchain.planner import ToolChainPlanner, ToolProvider


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeTool:
    """Minimal tool-like object satisfying the planner's duck-typing."""

    name: str
    description: str = ""
    category: str = "utility"
    tags: list[str] = field(default_factory=list)


class FakeToolRegistry:
    """Fake tool provider implementing the ToolProvider protocol."""

    def __init__(self, tools: list[FakeTool] | None = None) -> None:
        self._tools = tools or []

    def list(self) -> list[FakeTool]:
        return list(self._tools)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_fake_registry_satisfies_protocol(self):
        registry = FakeToolRegistry()
        assert isinstance(registry, ToolProvider)

    def test_real_tool_registry_satisfies_protocol(self):
        from atlas.tools.registry import ToolRegistry

        registry = ToolRegistry()
        assert isinstance(registry, ToolProvider)


class TestConstruction:
    def test_no_provider(self):
        planner = ToolChainPlanner()
        assert not planner.has_provider

    def test_with_provider(self):
        planner = ToolChainPlanner(FakeToolRegistry())
        assert planner.has_provider


class TestInferCategory:
    def setup_method(self):
        self.planner = ToolChainPlanner()

    def test_file_keyword(self):
        assert self.planner.infer_category("read a file") == "file"

    def test_search_keyword(self):
        assert self.planner.infer_category("find documents") == "search"

    def test_code_keyword(self):
        assert self.planner.infer_category("refactor the code") == "code"

    def test_network_keyword(self):
        assert self.planner.infer_category("make an http request") == "network"

    def test_system_keyword(self):
        assert self.planner.infer_category("run a shell command") == "system"

    def test_analysis_keyword(self):
        assert self.planner.infer_category("analyze the report") == "analysis"

    def test_research_keyword(self):
        assert self.planner.infer_category("investigate the topic") == "research"

    def test_memory_keyword(self):
        assert self.planner.infer_category("recall a memory") == "memory"

    def test_knowledge_keyword(self):
        assert self.planner.infer_category("learn new knowledge") == "knowledge"

    def test_planning_keyword(self):
        assert self.planner.infer_category("plan the schedule") == "planning"

    def test_reasoning_keyword(self):
        assert self.planner.infer_category("infer the conclusion") == "reasoning"

    def test_no_match_returns_default(self):
        assert self.planner.infer_category("do something random") == "utility"


class TestInferStrategy:
    def setup_method(self):
        self.planner = ToolChainPlanner()

    def test_fallback_marker(self):
        assert self.planner.infer_strategy("try fallback approach") == "fallback"

    def test_parallel_marker(self):
        assert self.planner.infer_strategy("run parallel batch") == "parallel"

    def test_default_sequential(self):
        assert self.planner.infer_strategy("read a file") == "sequential"

    def test_empty_goal(self):
        assert self.planner.infer_strategy("") == "sequential"


class TestInferDepth:
    def setup_method(self):
        self.planner = ToolChainPlanner()

    def test_short_goal(self):
        assert self.planner.infer_depth("read file") == 1

    def test_medium_goal(self):
        goal = " ".join(["word"] * 15)
        assert self.planner.infer_depth(goal) == 2

    def test_long_goal(self):
        goal = " ".join(["word"] * 30)
        assert self.planner.infer_depth(goal) == 3

    def test_empty_goal(self):
        assert self.planner.infer_depth("") == 1


class TestRankTools:
    def setup_method(self):
        self.planner = ToolChainPlanner()
        self.echo = FakeTool(name="echo", description="echo input", tags=["debug"])
        self.search = FakeTool(
            name="search", description="search files", tags=["search", "find"]
        )
        self.analyze = FakeTool(
            name="analyze", description="analyze data", tags=["analysis"]
        )

    def test_name_match_ranks_highest(self):
        ranked = self.planner.rank_tools("echo", [self.echo, self.search, self.analyze])
        assert ranked[0].name == "echo"

    def test_tag_match(self):
        ranked = self.planner.rank_tools("debug mode", [self.echo, self.analyze])
        assert ranked[0].name == "echo"

    def test_description_match(self):
        ranked = self.planner.rank_tools("input and output", [self.echo, self.search])
        assert ranked[0].name == "echo"

    def test_tie_breaker_alphabetical(self):
        tool_x = FakeTool(name="alpha", description="zzz")
        tool_y = FakeTool(name="beta", description="zzz")
        ranked = self.planner.rank_tools("zzz", [tool_y, tool_x])
        assert ranked[0].name == "alpha"
        assert ranked[1].name == "beta"

    def test_empty_goal_returns_all(self):
        tools = [self.echo, self.search]
        ranked = self.planner.rank_tools("", tools)
        assert len(ranked) == 2

    def test_empty_tools_returns_empty(self):
        ranked = self.planner.rank_tools("test", [])
        assert ranked == []


class TestPlan:
    def test_empty_goal_returns_empty_plan(self):
        planner = ToolChainPlanner(FakeToolRegistry())
        plan = planner.plan("")
        assert plan.is_empty
        assert plan.step_count == 0
        assert plan.metadata.get("empty") is True

    def test_no_provider_returns_empty_plan(self):
        planner = ToolChainPlanner()
        plan = planner.plan("read a file")
        assert plan.is_empty

    def test_plan_with_matching_tools(self):
        tools = [
            FakeTool(name="read_file", description="read a file", category="file"),
            FakeTool(name="write_file", description="write a file", category="file"),
            FakeTool(name="search", description="search files", category="search"),
        ]
        planner = ToolChainPlanner(FakeToolRegistry(tools))
        plan = planner.plan("read a file")
        assert not plan.is_empty
        assert plan.step_count >= 1
        # read_file should rank highest (name + description match)
        assert plan.steps[0].tool_name == "read_file"

    def test_plan_respects_max_steps(self):
        tools = [FakeTool(name=f"tool_{i}", category="utility") for i in range(20)]
        planner = ToolChainPlanner(FakeToolRegistry(tools))
        plan = planner.plan("do something", max_steps=3)
        assert plan.step_count <= 3

    def test_plan_max_steps_capped_at_catalog_max(self):
        tools = [FakeTool(name=f"tool_{i}", category="utility") for i in range(50)]
        planner = ToolChainPlanner(FakeToolRegistry(tools))
        plan = planner.plan("do something", max_steps=100)
        assert plan.step_count <= MAX_PLAN_STEPS

    def test_plan_strategy_inferred(self):
        planner = ToolChainPlanner(FakeToolRegistry())
        plan = planner.plan("try fallback approach")
        assert plan.strategy == "fallback"

    def test_plan_depth_inferred(self):
        planner = ToolChainPlanner(FakeToolRegistry())
        plan = planner.plan("read file")
        assert plan.max_depth == 1

    def test_plan_explicit_category(self):
        tools = [
            FakeTool(name="search_tool", description="search", category="search"),
            FakeTool(name="file_tool", description="file", category="file"),
        ]
        planner = ToolChainPlanner(FakeToolRegistry(tools))
        plan = planner.plan("do something", category="search")
        assert all(s.tool_name == "search_tool" for s in plan.steps)

    def test_plan_explicit_max_depth(self):
        planner = ToolChainPlanner(FakeToolRegistry())
        plan = planner.plan("read file", max_depth=5)
        assert plan.max_depth == 5

    def test_plan_id_is_deterministic(self):
        planner = ToolChainPlanner(FakeToolRegistry())
        plan1 = planner.plan("read a file")
        plan2 = planner.plan("read a file")
        assert plan1.plan_id == plan2.plan_id

    def test_plan_id_differs_for_different_goals(self):
        planner = ToolChainPlanner(FakeToolRegistry())
        plan1 = planner.plan("read a file")
        plan2 = planner.plan("write a file")
        assert plan1.plan_id != plan2.plan_id

    def test_plan_steps_have_sequential_ids(self):
        tools = [
            FakeTool(name="a", category="utility"),
            FakeTool(name="b", category="utility"),
            FakeTool(name="c", category="utility"),
        ]
        planner = ToolChainPlanner(FakeToolRegistry(tools))
        plan = planner.plan("do something")
        step_ids = [s.step_id for s in plan.steps]
        assert step_ids == ["step:0000", "step:0001", "step:0002"]

    def test_plan_metadata_contains_category(self):
        planner = ToolChainPlanner(FakeToolRegistry())
        plan = planner.plan("read a file")
        assert plan.metadata["category"] == "file"

    def test_plan_metadata_contains_counts(self):
        tools = [FakeTool(name="read_file", category="file")]
        planner = ToolChainPlanner(FakeToolRegistry(tools))
        plan = planner.plan("read a file")
        assert plan.metadata["candidate_count"] == 1
        assert plan.metadata["ranked_count"] == 1

    def test_plan_goal_preserved(self):
        planner = ToolChainPlanner(FakeToolRegistry())
        plan = planner.plan("read a file")
        assert plan.goal == "read a file"

    def test_plan_returns_toolchainplan_type(self):
        planner = ToolChainPlanner(FakeToolRegistry())
        plan = planner.plan("read a file")
        assert isinstance(plan, ToolChainPlan)

    def test_plan_steps_are_toolstep_type(self):
        tools = [FakeTool(name="echo", category="utility")]
        planner = ToolChainPlanner(FakeToolRegistry(tools))
        plan = planner.plan("echo")
        for step in plan.steps:
            assert isinstance(step, ToolStep)

    def test_plan_category_fallback_to_all_tools(self):
        """When no tools match the inferred category, all tools are considered."""
        tools = [
            FakeTool(name="network_tool", category="network"),
        ]
        planner = ToolChainPlanner(FakeToolRegistry(tools))
        plan = planner.plan("read a file")  # infers "file" but only network tools
        assert not plan.is_empty
        assert plan.steps[0].tool_name == "network_tool"

    def test_plan_with_provider_exception_returns_empty(self):
        class BrokenProvider:
            def list(self):
                raise RuntimeError("broken")

        planner = ToolChainPlanner(BrokenProvider())
        plan = planner.plan("read a file")
        assert plan.is_empty


class TestDeterminism:
    def test_same_goal_same_steps(self):
        tools = [
            FakeTool(name="read_file", description="read", category="file"),
            FakeTool(name="write_file", description="write", category="file"),
        ]
        planner = ToolChainPlanner(FakeToolRegistry(tools))
        plan1 = planner.plan("read a file")
        plan2 = planner.plan("read a file")
        assert plan1.steps == plan2.steps
        assert plan1.strategy == plan2.strategy
        assert plan1.max_depth == plan2.max_depth