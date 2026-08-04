"""Phase 18.7 — Toolchain capability handler tests.

Covers:
  - registration (all four capabilities registered)
  - handler execution (execute_chain, run_skill, effectiveness, skills)
  - dependency injection (custom components injected)
  - fail closed (missing input, unknown skill, no invoker)
"""

from __future__ import annotations

from typing import Any

import pytest

from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.toolchain.capability_handlers import (
    ToolchainCapabilityFactory,
    toolchain_handlers,
)
from atlas.toolchain.effectiveness import ToolEffectivenessTracker
from atlas.toolchain.executor import RiskPolicy, ToolChainExecutor
from atlas.toolchain.models import (
    Skill,
    SkillKind,
    SkillStatus,
    ToolChain,
    ToolChainPlan,
    ToolChainResult,
    ToolStep,
)
from atlas.toolchain.planner import ToolChainPlanner
from atlas.toolchain.registry import SkillRegistry


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeTool:
    """A tool-like object for the planner."""

    def __init__(
        self,
        name: str = "read_file",
        category: str = "file",
        description: str = "Read a file from disk.",
        tags: list[str] | None = None,
    ) -> None:
        self.name = name
        self.category = category
        self.description = description
        self.tags = tags or ["file"]


class FakeToolProvider:
    """A tool provider returning a fixed list of tools."""

    def __init__(self, tools: list[Any] | None = None) -> None:
        self._tools = tools or [FakeTool()]

    def list(self) -> list[Any]:
        return list(self._tools)


class FakeInvoker:
    """A tool invoker that always succeeds (or always fails)."""

    def __init__(self, *, succeed: bool = True, output: dict | None = None) -> None:
        self._succeed = succeed
        self._output = output or {"result": "ok"}

    def execute_by_name(
        self,
        name: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._succeed:
            return {
                "success": False,
                "output": {},
                "error": f"Tool '{name}' failed (fake).",
                "execution_time_ms": 1.0,
            }
        return {
            "success": True,
            "output": self._output,
            "error": "",
            "execution_time_ms": 1.0,
        }


def make_factory(
    *,
    with_invoker: bool = True,
    with_provider: bool = True,
    skills: list[Skill] | None = None,
    tracker: ToolEffectivenessTracker | None = None,
) -> ToolchainCapabilityFactory:
    """Build a factory with sensible test defaults."""
    provider = FakeToolProvider() if with_provider else None
    planner = ToolChainPlanner(tool_provider=provider)
    invoker = FakeInvoker() if with_invoker else None
    executor = ToolChainExecutor(tool_invoker=invoker)
    registry = SkillRegistry()
    for skill in skills or []:
        registry.register(skill)
    return ToolchainCapabilityFactory(
        planner=planner,
        executor=executor,
        registry=registry,
        tracker=tracker or ToolEffectivenessTracker(),
    )


def make_builtin_skill(
    skill_id: str = "skill:test:1",
    name: str = "Read File",
    tool_name: str = "read_file",
    status: SkillStatus = SkillStatus.ACTIVE,
) -> Skill:
    return Skill(
        skill_id=skill_id,
        name=name,
        description="Reads a file from disk.",
        kind=SkillKind.BUILTIN,
        category="file",
        tool_name=tool_name,
        status=status,
    )


def make_composed_skill(
    skill_id: str = "skill:test:2",
    name: str = "Search And Read",
) -> Skill:
    chain = ToolChain(
        chain_id="chain::test:2",
        goal="Search and read a file.",
        steps=(
            ToolStep(step_id="step:0000", tool_name="search"),
            ToolStep(step_id="step:0001", tool_name="read_file"),
        ),
        strategy="sequential",
    )
    return Skill(
        skill_id=skill_id,
        name=name,
        description="Searches then reads.",
        kind=SkillKind.COMPOSED,
        category="search",
        chain=chain,
        status=SkillStatus.ACTIVE,
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_four_capabilities_registered(self) -> None:
        factory = make_factory()
        registry = CapabilityRegistry()
        factory.register(registry)
        assert set(registry.registered_names) == {
            "toolchain.execute_chain",
            "toolchain.run_skill",
            "toolchain.effectiveness",
            "toolchain.skills",
        }

    def test_handlers_are_callables(self) -> None:
        handlers = make_factory().handlers()
        for name, handler in handlers.items():
            result = handler({"x": 1})
            assert result is not None
            assert result.capability == name

    def test_module_level_convenience(self) -> None:
        handlers = toolchain_handlers()
        assert set(handlers.keys()) == {
            "toolchain.execute_chain",
            "toolchain.run_skill",
            "toolchain.effectiveness",
            "toolchain.skills",
        }


# ---------------------------------------------------------------------------
# toolchain.execute_chain
# ---------------------------------------------------------------------------


class TestExecuteChain:
    def test_requires_goal_or_chain_or_plan(self) -> None:
        handler = make_factory().handlers()["toolchain.execute_chain"]
        result = handler({})
        assert not result.success
        assert "goal" in result.error.lower()

    def test_execute_from_goal(self) -> None:
        handler = make_factory().handlers()["toolchain.execute_chain"]
        result = handler({"goal": "read a file"})
        assert result.success
        assert "result" in result.output

    def test_execute_from_chain(self) -> None:
        chain = ToolChain(
            chain_id="chain::direct",
            goal="Direct chain.",
            steps=(ToolStep(step_id="step:0000", tool_name="read_file"),),
            strategy="sequential",
        )
        handler = make_factory().handlers()["toolchain.execute_chain"]
        result = handler({"chain": chain})
        assert result.success

    def test_execute_from_plan(self) -> None:
        plan = ToolChainPlan(
            plan_id="plan::direct",
            goal="Direct plan.",
            steps=(ToolStep(step_id="step:0000", tool_name="read_file"),),
            strategy="sequential",
        )
        handler = make_factory().handlers()["toolchain.execute_chain"]
        result = handler({"plan": plan})
        assert result.success

    def test_fail_closed_no_invoker(self) -> None:
        handler = make_factory(with_invoker=False).handlers()["toolchain.execute_chain"]
        result = handler({"goal": "read a file"})
        assert not result.success
        assert result.error

    def test_deterministic_output(self) -> None:
        handler = make_factory().handlers()["toolchain.execute_chain"]
        params = {"goal": "read a file"}
        first = handler(params)
        second = handler(params)
        assert first.success == second.success
        assert first.output["result"]["success"] == second.output["result"]["success"]


# ---------------------------------------------------------------------------
# toolchain.run_skill
# ---------------------------------------------------------------------------


class TestRunSkill:
    def test_requires_skill_id(self) -> None:
        handler = make_factory().handlers()["toolchain.run_skill"]
        result = handler({})
        assert not result.success
        assert "skill_id" in result.error

    def test_unknown_skill_fail_closed(self) -> None:
        handler = make_factory().handlers()["toolchain.run_skill"]
        result = handler({"skill_id": "skill:nonexistent"})
        assert not result.success
        assert "not found" in result.error

    def test_inactive_skill_fail_closed(self) -> None:
        skill = make_builtin_skill(status=SkillStatus.DEPRECATED)
        handler = make_factory(skills=[skill]).handlers()["toolchain.run_skill"]
        result = handler({"skill_id": skill.skill_id})
        assert not result.success
        assert "not active" in result.error

    def test_run_builtin_skill(self) -> None:
        skill = make_builtin_skill()
        handler = make_factory(skills=[skill]).handlers()["toolchain.run_skill"]
        result = handler({"skill_id": skill.skill_id})
        assert result.success
        assert "result" in result.output
        assert "skill" in result.output

    def test_run_composed_skill(self) -> None:
        skill = make_composed_skill()
        handler = make_factory(skills=[skill]).handlers()["toolchain.run_skill"]
        result = handler({"skill_id": skill.skill_id})
        assert result.success

    def test_fail_closed_no_invoker(self) -> None:
        skill = make_builtin_skill()
        handler = make_factory(
            with_invoker=False, skills=[skill]
        ).handlers()["toolchain.run_skill"]
        result = handler({"skill_id": skill.skill_id})
        assert not result.success


# ---------------------------------------------------------------------------
# toolchain.effectiveness
# ---------------------------------------------------------------------------


class TestEffectiveness:
    def test_single_tool_score(self) -> None:
        tracker = ToolEffectivenessTracker()
        tracker.record("read_file", success=True, execution_time_ms=10.0)
        handler = make_factory(tracker=tracker).handlers()["toolchain.effectiveness"]
        result = handler({"tool_name": "read_file"})
        assert result.success
        assert "score" in result.output
        assert result.output["score"]["tool_name"] == "read_file"

    def test_all_scores(self) -> None:
        tracker = ToolEffectivenessTracker()
        tracker.record("read_file", success=True, execution_time_ms=10.0)
        tracker.record("search", success=False, execution_time_ms=20.0)
        handler = make_factory(tracker=tracker).handlers()["toolchain.effectiveness"]
        result = handler({})
        assert result.success
        assert "scores" in result.output
        assert len(result.output["scores"]) == 2

    def test_unobserved_tool_returns_default(self) -> None:
        handler = make_factory().handlers()["toolchain.effectiveness"]
        result = handler({"tool_name": "unknown_tool"})
        assert result.success
        assert result.output["score"]["tool_name"] == "unknown_tool"


# ---------------------------------------------------------------------------
# toolchain.skills
# ---------------------------------------------------------------------------


class TestSkills:
    def test_list_all(self) -> None:
        s1 = make_builtin_skill()
        s2 = make_composed_skill()
        handler = make_factory(skills=[s1, s2]).handlers()["toolchain.skills"]
        result = handler({})
        assert result.success
        assert result.metadata["count"] == 2

    def test_filter_active_only(self) -> None:
        s1 = make_builtin_skill()
        s2 = make_builtin_skill(
            skill_id="skill:test:2", status=SkillStatus.DEPRECATED
        )
        handler = make_factory(skills=[s1, s2]).handlers()["toolchain.skills"]
        result = handler({"active_only": True})
        assert result.success
        assert result.metadata["count"] == 1

    def test_filter_by_category(self) -> None:
        s1 = make_builtin_skill()
        s2 = make_composed_skill()
        handler = make_factory(skills=[s1, s2]).handlers()["toolchain.skills"]
        result = handler({"category": "file"})
        assert result.success
        assert result.metadata["count"] == 1

    def test_filter_by_kind(self) -> None:
        s1 = make_builtin_skill()
        s2 = make_composed_skill()
        handler = make_factory(skills=[s1, s2]).handlers()["toolchain.skills"]
        result = handler({"kind": "BUILTIN"})
        assert result.success
        assert result.metadata["count"] == 1

    def test_unknown_kind_fail_closed(self) -> None:
        handler = make_factory().handlers()["toolchain.skills"]
        result = handler({"kind": "NONEXISTENT"})
        assert not result.success
        assert "Unknown skill kind" in result.error

    def test_empty_registry(self) -> None:
        handler = make_factory().handlers()["toolchain.skills"]
        result = handler({})
        assert result.success
        assert result.metadata["count"] == 0


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------


class TestDependencyInjection:
    def test_custom_components_injected(self) -> None:
        planner = ToolChainPlanner()
        executor = ToolChainExecutor()
        registry = SkillRegistry()
        tracker = ToolEffectivenessTracker()
        factory = ToolchainCapabilityFactory(
            planner=planner,
            executor=executor,
            registry=registry,
            tracker=tracker,
        )
        assert factory.planner is planner
        assert factory.executor is executor
        assert factory.registry is registry
        assert factory.tracker is tracker

    def test_defaults_created(self) -> None:
        factory = ToolchainCapabilityFactory()
        assert factory.planner is not None
        assert factory.executor is not None
        assert factory.registry is not None
        assert factory.tracker is not None

    def test_register_into_fresh_registry(self) -> None:
        factory = make_factory()
        registry = CapabilityRegistry()
        assert registry.count == 0
        factory.register(registry)
        assert registry.count == 4