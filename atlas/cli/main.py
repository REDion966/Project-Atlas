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


if __name__ == "__main__":
    main()
