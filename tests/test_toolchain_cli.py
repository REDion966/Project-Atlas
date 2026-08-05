"""Phase 18.10 — Toolchain CLI tests.

Covers:
  - toolchain plan (deterministic plan output, no execution)
  - toolchain execute (fail-closed on missing goal; delegates to executor)
  - skill list / lookup (registry reads only)
  - skill activate (GOVERNED via the ingest bridge; never mutates the
    registry directly; fails closed without a sink)
  - parsers register the expected commands
"""

from __future__ import annotations

from atlas.reasoning.execution.models import ExecutionResult
from atlas.toolchain.capability_handlers import ToolchainCapabilityFactory
from atlas.toolchain.cli_commands import (
    build_skill_parser,
    build_toolchain_parser,
    main_skill,
    main_toolchain,
    run_execute,
    run_plan,
    run_skill_activate,
    run_skill_list,
    run_skill_lookup,
)
from atlas.toolchain.evolution_integration import IngestHandoffResult
from atlas.toolchain.models import Skill, SkillKind, SkillStatus


def make_skill(
    skill_id: str = "skill:cli:1",
    name: str = "Read File",
    status: SkillStatus = SkillStatus.DRAFT,
) -> Skill:
    return Skill(
        skill_id=skill_id,
        name=name,
        description="Reads a file.",
        kind=SkillKind.BUILTIN,
        category="file",
        tool_name="read_file",
        status=status,
    )


class TestParsers:
    def test_toolchain_parser_has_plan_and_execute(self):
        parser = build_toolchain_parser()
        plan = parser.parse_args(["plan", "Read a file"])
        assert plan.action == "plan"
        assert plan.goal == "Read a file"
        execute = parser.parse_args(["execute", "Read a file"])
        assert execute.action == "execute"

    def test_skill_parser_has_list_lookup_activate(self):
        parser = build_skill_parser()
        listed = parser.parse_args(["list"])
        assert listed.action == "list"
        looked = parser.parse_args(["lookup", "--id", "skill:x"])
        assert looked.action == "lookup"
        assert looked.skill_id == "skill:x"
        activated = parser.parse_args(["activate", "--name", "Read File"])
        assert activated.action == "activate"
        assert activated.name == "Read File"


class TestToolchainPlan:
    def test_plan_produces_successful_result(self):
        factory = ToolchainCapabilityFactory()
        result = run_plan(factory, "Read a file")
        assert result.success
        plan = result.output["plan"]
        assert plan["plan_id"].startswith("plan::")
        assert plan["goal"] == "Read a file"

    def test_plan_is_deterministic(self):
        factory = ToolchainCapabilityFactory()
        first = run_plan(factory, "Search for data")
        second = run_plan(factory, "Search for data")
        assert first.output["plan"]["plan_id"] == second.output["plan"]["plan_id"]
        assert first.output["plan"]["strategy"] == second.output["plan"]["strategy"]


class TestToolchainExecute:
    def test_execute_missing_goal_fails_closed(self):
        factory = ToolchainCapabilityFactory()
        result = run_execute(factory, "")
        assert not result.success
        assert "goal" in result.error.lower()

    def test_execute_delegates_to_executor(self):
        factory = ToolchainCapabilityFactory()
        # No invoker wired → the executor fails closed with a descriptive error.
        result = run_execute(factory, "Read a file")
        assert not result.success
        assert result.output == {"result": result.output["result"]}


class TestSkillList:
    def test_lists_registered_skills(self):
        factory = ToolchainCapabilityFactory()
        factory.registry.register(make_skill())
        result = run_skill_list(factory)
        assert result.success
        skill_ids = {s["skill_id"] for s in result.output["skills"]}
        assert "skill:cli:1" in skill_ids

    def test_active_only_filter(self):
        factory = ToolchainCapabilityFactory()
        factory.registry.register(make_skill())  # DRAFT
        result = run_skill_list(factory, active_only=True)
        assert result.success
        assert result.output["skills"] == []


class TestSkillLookup:
    def test_lookup_by_id(self):
        factory = ToolchainCapabilityFactory()
        factory.registry.register(make_skill())
        result = run_skill_lookup(factory, skill_id="skill:cli:1")
        assert result.success
        assert result.output["skill"]["skill_id"] == "skill:cli:1"

    def test_lookup_missing_fails(self):
        factory = ToolchainCapabilityFactory()
        result = run_skill_lookup(factory, skill_id="skill:nope")
        assert not result.success
        assert "not found" in result.error

    def test_lookup_never_mutates_registry(self):
        factory = ToolchainCapabilityFactory()
        factory.registry.register(make_skill())
        run_skill_lookup(factory, skill_id="skill:cli:1")
        assert factory.registry.count == 1
        skill = factory.registry.get("skill:cli:1")
        assert skill is not None
        assert skill.status == SkillStatus.DRAFT


class TestSkillActivate:
    class FakeSink:
        def __init__(self, accepted=True):
            self.accepted = accepted
            self.received = None

        def enqueue_request(self, request):
            self.received = request
            return IngestHandoffResult(
                accepted=self.accepted,
                request_id=request.request_id,
                error="" if self.accepted else "refused",
            )

    def test_activation_already_active_is_not_governed(self):
        factory = ToolchainCapabilityFactory()
        skill = make_skill()
        skill = Skill(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            kind=skill.kind,
            category=skill.category,
            tool_name=skill.tool_name,
            status=SkillStatus.ACTIVE,
        )
        factory.registry.register(skill)
        sink = self.FakeSink()
        from atlas.toolchain.evolution_integration import ToolchainIngestBridge

        bridge = ToolchainIngestBridge(sink=sink)
        result = run_skill_activate(factory, skill_id=skill.skill_id, bridge=bridge)
        assert result.success
        # Already-active skills require no mutation, so no governed request.
        assert result.metadata["governed"] is False
        assert result.metadata["reason"] == "already_active"
        assert sink.received is None

    def test_activation_fails_closed_without_sink(self):
        factory = ToolchainCapabilityFactory()
        factory.registry.register(make_skill())
        result = run_skill_activate(factory, skill_id="skill:cli:1")
        assert not result.success
        assert "not wired" in result.error

    def test_activation_never_mutates_registry(self):
        factory = ToolchainCapabilityFactory()
        factory.registry.register(make_skill())
        run_skill_activate(factory, skill_id="skill:cli:1")
        skill = factory.registry.get("skill:cli:1")
        assert skill is not None
        assert skill.status == SkillStatus.DRAFT
        assert factory.registry.count == 1

    def test_activation_accepted_sink(self):
        factory = ToolchainCapabilityFactory()
        factory.registry.register(make_skill())
        sink = self.FakeSink(accepted=True)
        from atlas.toolchain.evolution_integration import ToolchainIngestBridge

        bridge = ToolchainIngestBridge(sink=sink)
        result = run_skill_activate(factory, skill_id="skill:cli:1", bridge=bridge)
        assert result.success
        assert result.output["accepted"] is True
        assert result.output["governed"] is True
        assert sink.received is not None

    def test_activation_refused_sink_fails_closed(self):
        factory = ToolchainCapabilityFactory()
        factory.registry.register(make_skill())
        sink = self.FakeSink(accepted=False)
        from atlas.toolchain.evolution_integration import ToolchainIngestBridge

        bridge = ToolchainIngestBridge(sink=sink)
        result = run_skill_activate(factory, skill_id="skill:cli:1", bridge=bridge)
        assert not result.success
        assert result.error == "refused"


class TestCLIEntryPoints:
    def test_main_toolchain_plan_prints(self, capsys):
        code = main_toolchain(["plan", "Read a file"])
        assert code == 0
        out = capsys.readouterr().out
        assert "plan::" in out

    def test_main_skill_list_empty(self, capsys):
        code = main_skill(["list"])
        assert code == 0
        out = capsys.readouterr().out
        assert "skills" in out
