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
    workspace_create,
)
from atlas.workspace.loader import (
    load_workspace_service,
)


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


if __name__ == "__main__":
    main()