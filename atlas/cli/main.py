"""
Atlas Workspace CLI Entry Point.
"""

from __future__ import annotations

import argparse

from atlas.cli.commands import (
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
        
if __name__ == "__main__":
    main()