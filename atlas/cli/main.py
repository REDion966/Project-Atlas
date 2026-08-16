"""
Atlas Workspace CLI Entry Point.
"""

from __future__ import annotations

import argparse

from atlas.cli.commands import (
    member_add,
    member_list,
    member_remove,
    permission_add,
    permission_list,
    permission_remove,
    project_create,
    resource_add,
    resource_list,
    resource_remove,
    tag_add,
    tag_list,
    tag_remove,
    workspace_create,
)
from atlas.reasoning.execution.models import ExecutionResult
from atlas.research.capability_handlers import ResearchCapabilityFactory
from atlas.workspace.loader import (
    load_workspace_service,
)


def _print_result(result: ExecutionResult) -> int:
    """Print an ExecutionResult and return a process exit code."""
    if not result.success:
        print(f"error: {result.error}")
        return 1
    print(result.output)
    return 0


def main() -> None:
    """Run the Atlas Workspace CLI."""

    parser = argparse.ArgumentParser(
        prog="atlas",
        description="Atlas Workspace CLI",
    )

    subparsers = parser.add_subparsers(
        dest="command",
    )

    # -------------------------
    # Workspace Commands
    # -------------------------

    workspace_parser = subparsers.add_parser(
        "workspace",
        help="Workspace commands",
    )

    workspace_parser.add_argument(
        "action",
        choices=[
            "create",
        ],
    )

    workspace_parser.add_argument(
        "name",
    )

    # -------------------------
    # Project Commands
    # -------------------------

    project_parser = subparsers.add_parser(
        "project",
        help="Project commands",
    )

    project_parser.add_argument(
        "action",
        choices=[
            "create",
        ],
    )

    project_parser.add_argument(
        "name",
    )

    # -------------------------
    # Resource Commands
    # -------------------------

    resource_parser = subparsers.add_parser(
        "resource",
        help="Resource commands",
    )

    resource_parser.add_argument(
        "action",
        choices=[
            "add",
            "list",
            "remove",
        ],
    )

    resource_parser.add_argument(
        "name",
        nargs="?",
    )

    # -------------------------
    # Permission Commands
    # -------------------------

    permission_parser = subparsers.add_parser(
        "permission",
        help="Permission commands",
    )

    permission_parser.add_argument(
        "action",
        choices=[
            "add",
            "list",
            "remove",
        ],
    )

    permission_parser.add_argument(
        "name",
        nargs="?",
    )

    permission_parser.add_argument(
        "level",
        nargs="?",
    )

    # -------------------------
    # Member Commands
    # -------------------------

    member_parser = subparsers.add_parser(
        "member",
        help="Member commands",
    )

    member_parser.add_argument(
        "action",
        choices=[
            "add",
            "list",
            "remove",
        ],
    )

    member_parser.add_argument(
        "name",
        nargs="?",
    )

    # -------------------------
    # Tag Commands
    # -------------------------

    tag_parser = subparsers.add_parser(
        "tag",
        help="Tag commands",
    )

    tag_parser.add_argument(
        "action",
        choices=[
            "add",
            "list",
            "remove",
        ],
    )

    tag_parser.add_argument(
        "name",
        nargs="?",
    )

    # -------------------------
    # Research Commands (Phase 17.9)
    # -------------------------

    research_parser = subparsers.add_parser(
        "research",
        help="Research commands",
    )

    research_parser.add_argument(
        "action",
        choices=[
            "query",
            "verify",
            "summarize",
        ],
    )

    research_parser.add_argument(
        "question",
        nargs="?",
    )

    research_parser.add_argument(
        "--query-id",
        default="cli",
    )

    research_parser.add_argument(
        "--source",
        action="append",
        default=[],
    )

    research_parser.add_argument(
        "--claim",
        action="append",
        default=[],
    )

    research_parser.add_argument(
        "--report-id",
        default="",
    )

    # -------------------------
    # Evolution Proposals (read-only audit; Post-Core F8)
    # -------------------------

    proposals_parser = subparsers.add_parser(
        "proposals",
        help="Evolution proposal inspection (read-only)",
    )
    proposals_parser.add_argument(
        "action",
        choices=["list", "show", "audit"],
    )
    proposals_parser.add_argument(
        "proposal_id",
        nargs="?",
    )
    proposals_parser.add_argument(
        "--pending",
        action="store_true",
        help="list only pending proposals",
    )

    # -------------------------
    # Toolchain Commands (Phase 18.10)
    # -------------------------

    toolchain_parser = subparsers.add_parser(
        "toolchain",
        help="Toolchain commands",
    )

    toolchain_parser.add_argument(
        "action",
        choices=[
            "plan",
            "execute",
        ],
    )

    toolchain_parser.add_argument(
        "goal",
        nargs="?",
    )

    toolchain_parser.add_argument(
        "--category",
        default="",
    )

    toolchain_parser.add_argument(
        "--max-steps",
        type=int,
        default=8,
    )

    toolchain_parser.add_argument(
        "--parameter",
        action="append",
        default=[],
    )

    # -------------------------
    # Reasoning Commands (Track D)
    # -------------------------

    reasoning_parser = subparsers.add_parser(
        "reasoning",
        help="Advanced reasoning commands",
    )

    reasoning_parser.add_argument(
        "action",
        choices=[
            "trace",
            "causal",
            "counterfactual",
            "hypotheses",
            "verify",
            "meta",
            "ingest",
        ],
    )

    reasoning_parser.add_argument(
        "question",
        nargs="?",
    )

    reasoning_parser.add_argument(
        "--source",
        default="",
    )

    reasoning_parser.add_argument(
        "--target",
        default="",
    )

    reasoning_parser.add_argument(
        "--event",
        default="",
    )

    reasoning_parser.add_argument(
        "--assumption",
        default="",
    )

    reasoning_parser.add_argument(
        "--claim",
        default="",
    )

    reasoning_parser.add_argument(
        "--trace-id",
        default="",
    )

    reasoning_parser.add_argument(
        "--content",
        default="",
    )

    reasoning_parser.add_argument(
        "--strategy-name",
        default="",
    )

    reasoning_parser.add_argument(
        "--confidence",
        type=float,
        default=0.0,
    )

    reasoning_parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
    )

    reasoning_parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
    )

    reasoning_parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )

    reasoning_parser.add_argument(
        "--set-id",
        default="",
    )

    reasoning_parser.add_argument(
        "--report-id",
        default="",
    )

    reasoning_parser.add_argument(
        "--assessment-id",
        default="",
    )

    reasoning_parser.add_argument(
        "--result-id",
        default="",
    )

    # -------------------------
    # Memory Commands (Track C)
    # -------------------------

    memory_parser = subparsers.add_parser(
        "memory",
        help="Long-term memory commands",
    )

    memory_parser.add_argument(
        "action",
        choices=[
            "episodes",
            "procedures",
            "consolidate",
        ],
    )

    memory_parser.add_argument(
        "--limit",
        type=int,
        default=100,
    )

    memory_parser.add_argument(
        "--outcome",
        default="",
    )

    memory_parser.add_argument(
        "--since",
        default="",
    )

    memory_parser.add_argument(
        "--category",
        default="",
    )

    memory_parser.add_argument(
        "--tool",
        default="",
    )

    memory_parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    # -------------------------
    # Skill Commands (Phase 18.10)
    # -------------------------

    skill_parser = subparsers.add_parser(
        "skill",
        help="Skill commands",
    )

    skill_parser.add_argument(
        "action",
        choices=[
            "list",
            "lookup",
            "activate",
        ],
    )

    skill_parser.add_argument(
        "--active-only",
        action="store_true",
    )

    skill_parser.add_argument(
        "--category",
        default="",
    )

    skill_parser.add_argument(
        "--tag",
        default="",
    )

    skill_parser.add_argument(
        "--id",
        dest="skill_id",
        default="",
    )

    skill_parser.add_argument(
        "--name",
        dest="skill_name",
        default="",
    )

    args = parser.parse_args()

    service = load_workspace_service()

    # -------------------------
    # Workspace
    # -------------------------

    if (
        args.command == "workspace"
        and args.action == "create"
    ):
        workspace_create(
            service,
            args.name,
        )
        return

    # -------------------------
    # Project
    # -------------------------

    if (
        args.command == "project"
        and args.action == "create"
    ):
        project_create(
            service,
            args.name,
        )
        return

    # -------------------------
    # Proposals (read-only audit; Post-Core F8)
    # -------------------------

    if args.command == "proposals":
        _run_proposals(args)
        return

    # -------------------------
    # Resource
    # -------------------------

    if args.command == "resource":

        if args.action == "add":
            resource_add(
                service,
                args.name,
            )
            return

        if args.action == "list":
            resource_list(
                service,
            )
            return

        if args.action == "remove":
            resource_remove(
                service,
                args.name,
            )
            return

    # -------------------------
    # Permission
    # -------------------------

    if args.command == "permission":

        if args.action == "add":
            permission_add(
                service,
                args.name,
                args.level,
            )
            return

        if args.action == "list":
            permission_list(
                service,
            )
            return

        if args.action == "remove":
            permission_remove(
                service,
                args.name,
            )
            return

    # -------------------------
    # Member
    # -------------------------

    if args.command == "member":

        if args.action == "add":
            member_add(
                service,
                args.name,
            )
            return

        if args.action == "list":
            member_list(
                service,
            )
            return

        if args.action == "remove":
            member_remove(
                service,
                args.name,
            )
            return

    # -------------------------
    # Tag
    # -------------------------

    if args.command == "tag":

        if args.action == "add":
            tag_add(
                service,
                args.name,
            )
            return

        if args.action == "list":
            tag_list(
                service,
            )
            return

        if args.action == "remove":
            tag_remove(
                service,
                args.name,
            )
            return

    # -------------------------
    # Research (presentation-only; Phase 17.9)
    # -------------------------

    if args.command == "research":
        _run_research(args)
        return

    # -------------------------
    # Toolchain (presentation-only; Phase 18.10)
    # -------------------------

    if args.command == "toolchain":
        _run_toolchain(args)
        return

    # -------------------------
    # Skill (presentation-only; Phase 18.10)
    # -------------------------

    if args.command == "skill":
        _run_skill(args)
        return

    # -------------------------
    # Memory (presentation-only; Track C)
    # -------------------------

    if args.command == "memory":
        _run_memory(args)
        return

    # -------------------------
    # Reasoning (presentation-only; Track D)
    # -------------------------

    if args.command == "reasoning":
        _run_reasoning(args)
        return

    parser.print_help()


def _run_proposals(args: argparse.Namespace) -> None:
    """Dispatch ``atlas proposals list|show|audit``.

    Post-Core F8 — presentation-only, read-only audit surface. Delegates
    to the EvolutionExecutionEngine's read-only proposal retrieval APIs.
    None of the actions approve, execute, reject, or defer proposals and
    none touch governance.
    """
    from atlas.cli.evolution_commands import (
        cmd_proposals_audit,
        cmd_proposals_list,
        cmd_proposals_show,
    )
    from atlas.kernel.atlas import Atlas

    if not getattr(args, "action", ""):
        print("error: proposals requires an action (list|show|audit)")
        return

    atlas = Atlas()
    try:
        atlas.start()
        engine = atlas.execution_engine
    except Exception as exc:
        print(f"error: failed to load Atlas: {exc}")
        return

    try:
        if args.action == "list":
            print(cmd_proposals_list(engine, args))
            return
        if args.action == "show":
            print(cmd_proposals_show(engine, args))
            return
        if args.action == "audit":
            print(cmd_proposals_audit(engine, args))
            return
    finally:
        atlas.shutdown()


def _run_research(args: argparse.Namespace) -> None:
    """Dispatch ``atlas research query|verify|summarize``.

    Presentation-only: delegates to the Track A capability handlers. Never
    mutates state, never writes knowledge, never touches the evolution
    pipeline directly.
    """
    factory = ResearchCapabilityFactory()

    if args.action == "query":
        if not args.question:
            print("error: research query requires a question")
            return
        handler = factory.handlers()["research.query"]
        _print_result(
            handler(
                {
                    "question": args.question,
                    "query_id": args.query_id,
                    "sources": args.source,
                }
            )
        )
        return

    if args.action == "verify":
        if not args.claim:
            print("error: research verify requires at least one --claim")
            return
        from atlas.research.cli_commands import run_verify

        _print_result(run_verify(factory, args.claim, args.source))
        return

    if args.action == "summarize":
        if args.report_id:
            from atlas.research.cli_commands import run_summarize

            _print_result(run_summarize(factory, args.report_id))
            return
        print({"summary": "no report id provided (research persistence is additive)"})
        return


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


def _run_toolchain(args: argparse.Namespace) -> None:
    """Dispatch ``atlas toolchain plan|execute``.

    Presentation-only: delegates to the Track B capability factory. Never
    mutates state, never mutates the skill registry, never touches the
    evolution pipeline directly.
    """
    from atlas.toolchain.capability_handlers import ToolchainCapabilityFactory

    factory = ToolchainCapabilityFactory()

    if args.action == "plan":
        if not args.goal:
            print("error: toolchain plan requires a goal")
            return
        from atlas.toolchain.cli_commands import run_plan

        _print_result(run_plan(factory, args.goal, args.category, args.max_steps))
        return

    if args.action == "execute":
        if not args.goal:
            print("error: toolchain execute requires a goal")
            return
        from atlas.toolchain.cli_commands import run_execute

        _print_result(run_execute(factory, args.goal, _parameters(args.parameter)))
        return


def _run_skill(args: argparse.Namespace) -> None:
    """Dispatch ``atlas skill list|lookup|activate``.

    Presentation-only: delegates to the Track B capability factory. Skill
    activation is governed — it builds a KNOWLEDGE EvolutionRequest and
    passes it through the ingest bridge, never mutating the registry.
    """
    from atlas.toolchain.capability_handlers import ToolchainCapabilityFactory

    factory = ToolchainCapabilityFactory()

    if args.action == "list":
        from atlas.toolchain.cli_commands import run_skill_list

        _print_result(run_skill_list(factory, args.active_only, args.category, args.tag))
        return

    if args.action == "lookup":
        from atlas.toolchain.cli_commands import run_skill_lookup

        _print_result(run_skill_lookup(factory, args.skill_id, args.skill_name))
        return

    if args.action == "activate":
        from atlas.toolchain.cli_commands import run_skill_activate

        _print_result(run_skill_activate(factory, args.skill_id, args.skill_name))
        return


def _run_reasoning(args: argparse.Namespace) -> None:
    """Dispatch ``atlas reasoning trace|causal|counterfactual|hypotheses|verify|meta|ingest``.

    Presentation-only: delegates to the Track D capability handlers. Query
    commands are read-only; ``ingest`` is governed — it builds a KNOWLEDGE
    EvolutionRequest and passes it through the ingest bridge, never mutating
    any store directly.
    """
    from atlas.advanced_reasoning.cli_commands import (
        run_causal,
        run_counterfactual,
        run_hypotheses,
        run_ingest,
        run_meta,
        run_trace,
        run_verify,
    )
    from atlas.advanced_reasoning.capability_handlers import (
        AdvancedReasoningCapabilityFactory,
    )

    factory = AdvancedReasoningCapabilityFactory()

    if args.action == "trace":
        if not args.question:
            print("error: reasoning trace requires a question")
            return
        _print_result(
            run_trace(factory, args.question, args.max_steps, args.trace_id)
        )
        return

    if args.action == "causal":
        if not args.source or not args.target:
            print("error: reasoning causal requires --source and --target")
            return
        _print_result(run_causal(factory, args.source, args.target, args.max_depth))
        return

    if args.action == "counterfactual":
        if not args.event or not args.assumption:
            print("error: reasoning counterfactual requires --event and --assumption")
            return
        _print_result(
            run_counterfactual(
                factory, args.event, args.assumption, args.max_depth, args.result_id
            )
        )
        return

    if args.action == "hypotheses":
        if not args.question:
            print("error: reasoning hypotheses requires a claim")
            return
        _print_result(run_hypotheses(factory, args.question, args.limit, args.set_id))
        return

    if args.action == "verify":
        if not args.trace_id and not args.claim:
            print("error: reasoning verify requires a --trace-id or --claim")
            return
        _print_result(run_verify(factory, args.trace_id, args.claim, args.report_id))
        return

    if args.action == "meta":
        _print_result(run_meta(factory, args.limit, args.assessment_id))
        return

    if args.action == "ingest":
        _print_result(
            run_ingest(
                factory,
                trace_id=args.trace_id,
                content=args.content,
                strategy_name=args.strategy_name,
                confidence=args.confidence,
            )
        )
        return


def _run_memory(args: argparse.Namespace) -> None:
    """Dispatch ``atlas memory episodes|procedures|consolidate``.

    Presentation-only: delegates to the Track C capability handlers. Query
    commands are read-only; ``consolidate`` is governed — it builds a MEMORY
    EvolutionRequest and passes it through the ingest bridge, never mutating
    the repositories directly.
    """
    from atlas.longterm.capability_handlers import LongTermCapabilityFactory
    from atlas.longterm.cli_commands import (
        run_consolidate,
        run_episodes,
        run_procedures,
    )

    factory = LongTermCapabilityFactory()

    if args.action == "episodes":
        _print_result(
            run_episodes(
                factory,
                args.limit,
                args.outcome,
                args.since,
            )
        )
        return

    if args.action == "procedures":
        _print_result(
            run_procedures(
                factory,
                args.limit,
                args.category,
                args.tool,
            )
        )
        return

    if args.action == "consolidate":
        _print_result(run_consolidate(factory, dry_run=args.dry_run))
        return


if __name__ == "__main__":
    main()
