"""Atlas Toolchain — CLI Commands (Phase 18.10).

Presentation-only wrappers for the Track B surface:

  atlas toolchain plan    — deterministic goal decomposition (planner)
  atlas toolchain execute — execute a goal/chain/plan via the executor
  atlas skill list        — list registered skills (with optional filters)
  atlas skill lookup      — look up a skill by id or name
  atlas skill activate    — GOVERNED skill activation through the evolution
                            ingest bridge (never mutates the registry)

Skill activation NEVER calls ``SkillRegistry.activate()`` from Track B code.
Instead it builds a governed INFORMATION-scope KNOWLEDGE ``EvolutionRequest``
(via :class:`~atlas.toolchain.evolution_integration.ToolchainEvolutionTracker`)
and passes it through the :class:`ToolchainIngestBridge` to the Phase 16
governed sink. Without a sink, activation fails closed — the registry is
never mutated directly, and the request is never applied by Track B.

No kernel, runtime, dispatcher, scheduler, gateway, storage, events, or AI
imports — presentation layer only, mirroring
:mod:`atlas.research.cli_commands` (Track A).
"""

from __future__ import annotations

import argparse
import sys

from atlas.reasoning.execution.models import ExecutionResult
from atlas.toolchain.capability_handlers import ToolchainCapabilityFactory
from atlas.toolchain.catalog import MAX_PLAN_STEPS
from atlas.toolchain.evolution_integration import (
    IngestHandoffResult,
    ToolchainIngestBridge,
)
from atlas.toolchain.models import Skill


def build_toolchain_parser() -> argparse.ArgumentParser:
    """Build the ``atlas toolchain`` subparser (plan / execute)."""
    parser = argparse.ArgumentParser(
        prog="atlas toolchain", description="Atlas Toolchain CLI"
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    plan_parser = subparsers.add_parser("plan", help="Plan a goal into a tool chain")
    plan_parser.add_argument("goal", help="High-level goal to decompose")
    plan_parser.add_argument("--category", default="", help="Optional category hint")
    plan_parser.add_argument(
        "--max-steps", type=int, default=MAX_PLAN_STEPS, help="Max plan steps"
    )

    execute_parser = subparsers.add_parser(
        "execute", help="Execute a tool chain for a goal"
    )
    execute_parser.add_argument("goal", help="High-level goal to plan and execute")
    execute_parser.add_argument(
        "--parameter", action="append", default=[], help="Shared parameter key=value"
    )

    return parser


def build_skill_parser() -> argparse.ArgumentParser:
    """Build the ``atlas skill`` subparser (list / lookup / activate)."""
    parser = argparse.ArgumentParser(
        prog="atlas skill", description="Atlas Skill CLI"
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    list_parser = subparsers.add_parser("list", help="List registered skills")
    list_parser.add_argument("--active-only", action="store_true", help="Only active")
    list_parser.add_argument("--category", default="", help="Filter by category")
    list_parser.add_argument("--tag", default="", help="Filter by tag")

    lookup_parser = subparsers.add_parser("lookup", help="Look up a skill")
    identity_group = lookup_parser.add_mutually_exclusive_group(required=True)
    identity_group.add_argument("--id", dest="skill_id", default="", help="Skill id")
    identity_group.add_argument("--name", dest="name", default="", help="Skill name")

    activate_parser = subparsers.add_parser(
        "activate", help="Governed skill activation via the evolution pipeline"
    )
    activate_identity = activate_parser.add_mutually_exclusive_group(required=True)
    activate_identity.add_argument(
        "--id", dest="skill_id", default="", help="Skill id"
    )
    activate_identity.add_argument(
        "--name", dest="name", default="", help="Skill name"
    )

    return parser


def _print_result(result: ExecutionResult) -> int:
    if not result.success:
        print(f"error: {result.error}")
        return 1
    print(result.output)
    return 0


def _parameters(pairs: list[str]) -> dict[str, str]:
    """Parse ``key=value`` CLI parameters into a dict."""
    parameters: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            continue
        key, _, value = pair.partition("=")
        if key.strip():
            parameters[key.strip()] = value
    return parameters


# ---------------------------------------------------------------------------
# atlas toolchain
# ---------------------------------------------------------------------------


def run_plan(
    factory: ToolchainCapabilityFactory,
    goal: str,
    category: str = "",
    max_steps: int = MAX_PLAN_STEPS,
) -> ExecutionResult:
    """Present ``atlas toolchain plan`` (deterministic planner).

    Uses the injected planner directly — the plan is a blueprint artifact
    and never executes tools.
    """
    plan = factory.planner.plan(goal, category=category, max_steps=max_steps)
    return ExecutionResult(
        capability="toolchain.plan",
        success=True,
        output={"plan": plan.to_dict()},
        metadata={
            "handler": "toolchain.plan",
            "plan_id": plan.plan_id,
            "step_count": plan.step_count,
        },
    )


def run_execute(
    factory: ToolchainCapabilityFactory,
    goal: str,
    parameters: dict | None = None,
) -> ExecutionResult:
    """Present ``atlas toolchain execute`` (via the execute_chain handler).

    Fail-closed: a missing goal returns a failed ``ExecutionResult``.
    """
    if not goal or not goal.strip():
        return ExecutionResult(
            capability="toolchain.execute",
            success=False,
            error="'goal' is required",
            metadata={"handler": "toolchain.execute"},
        )
    handler = factory.handlers()["toolchain.execute_chain"]
    return handler(
        {
            "goal": goal,
            "parameters": parameters or {},
        }
    )


# ---------------------------------------------------------------------------
# atlas skill
# ---------------------------------------------------------------------------


def run_skill_list(
    factory: ToolchainCapabilityFactory,
    active_only: bool = False,
    category: str = "",
    tag: str = "",
) -> ExecutionResult:
    """Present ``atlas skill list`` (via the ``toolchain.skills`` handler)."""
    handler = factory.handlers()["toolchain.skills"]
    params: dict = {}
    if active_only:
        params["active_only"] = True
    if category:
        params["category"] = category
    if tag:
        params["tag"] = tag
    return handler(params)


def run_skill_lookup(
    factory: ToolchainCapabilityFactory,
    skill_id: str = "",
    name: str = "",
) -> ExecutionResult:
    """Present ``atlas skill lookup`` (id or name).

    Reads from the injected registry only — never mutates it.
    """
    if skill_id:
        skill: Skill | None = factory.registry.get(skill_id)
    elif name:
        skill = factory.registry.get_by_name(name)
    else:
        return ExecutionResult(
            capability="skill.lookup",
            success=False,
            error="either --id or --name is required",
            metadata={"handler": "skill.lookup"},
        )
    if skill is None:
        identifier = skill_id or name or ""
        return ExecutionResult(
            capability="skill.lookup",
            success=False,
            error=f"Skill '{identifier}' not found",
            metadata={"handler": "skill.lookup"},
        )
    return ExecutionResult(
        capability="skill.lookup",
        success=True,
        output={"skill": skill.to_dict()},
        metadata={
            "handler": "skill.lookup",
            "skill_id": skill.skill_id,
            "status": skill.status.name,
        },
    )


def run_skill_activate(
    factory: ToolchainCapabilityFactory,
    skill_id: str = "",
    name: str = "",
    bridge: ToolchainIngestBridge | None = None,
) -> ExecutionResult:
    """Present ``atlas skill activate`` — GOVERNED activation.

    NEVER mutates the :class:`SkillRegistry` directly. The skill's desired
    ACTIVE transition is encoded as an INFORMATION-scope KNOWLEDGE
    ``EvolutionRequest`` and passed through the injected
    :class:`ToolchainIngestBridge` to the Phase 16 governed sink. Without a
    sink the activation fails closed.
    """
    if skill_id:
        skill: Skill | None = factory.registry.get(skill_id)
    elif name:
        skill = factory.registry.get_by_name(name)
    else:
        return ExecutionResult(
            capability="skill.activate",
            success=False,
            error="either --id or --name is required",
            metadata={"handler": "skill.activate"},
        )
    if skill is None:
        identifier = skill_id or name or ""
        return ExecutionResult(
            capability="skill.activate",
            success=False,
            error=f"Skill '{identifier}' not found",
            metadata={"handler": "skill.activate"},
        )

    if skill.is_active:
        # No mutation required — no governed request is created.
        return ExecutionResult(
            capability="skill.activate",
            success=True,
            output={"skill_id": skill.skill_id, "status": "ACTIVE"},
            metadata={
                "handler": "skill.activate",
                "skill_id": skill.skill_id,
                "governed": False,
                "reason": "already_active",
            },
        )

    ingress = bridge or ToolchainIngestBridge()
    handoff: IngestHandoffResult = ingress.ingest(skill)
    if not handoff.accepted:
        return ExecutionResult(
            capability="skill.activate",
            success=False,
            error=handoff.error or "skill activation refused by evolution pipeline",
            output={"request_id": handoff.request_id},
            metadata={
                "handler": "skill.activate",
                "skill_id": skill.skill_id,
                "governed": True,
                "accepted": False,
            },
        )
    return ExecutionResult(
        capability="skill.activate",
        success=True,
        output={
            "request_id": handoff.request_id,
            "skill_id": skill.skill_id,
            "governed": True,
            "accepted": True,
        },
        metadata={
            "handler": "skill.activate",
            "skill_id": skill.skill_id,
            "governed": True,
            "accepted": True,
        },
    )


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def main_toolchain(argv: list[str] | None = None) -> int:
    """Entry point for ``atlas toolchain`` commands."""
    args = build_toolchain_parser().parse_args(argv)
    factory = ToolchainCapabilityFactory()

    if args.action == "plan":
        result = run_plan(factory, args.goal, args.category, args.max_steps)
        return _print_result(result)
    if args.action == "execute":
        result = run_execute(factory, args.goal, _parameters(args.parameter))
        return _print_result(result)
    print("no such toolchain command")
    return 1


def main_skill(argv: list[str] | None = None) -> int:
    """Entry point for ``atlas skill`` commands."""
    args = build_skill_parser().parse_args(argv)
    factory = ToolchainCapabilityFactory()

    if args.action == "list":
        result = run_skill_list(factory, args.active_only, args.category, args.tag)
        return _print_result(result)
    if args.action == "lookup":
        result = run_skill_lookup(factory, args.skill_id, args.name)
        return _print_result(result)
    if args.action == "activate":
        result = run_skill_activate(factory, args.skill_id, args.name)
        return _print_result(result)
    print("no such skill command")
    return 1


if __name__ == "__main__":
    sys.exit(main_toolchain())
