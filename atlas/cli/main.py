"""
Atlas Workspace CLI Entry Point.
"""

from __future__ import annotations

import argparse

from atlas.cli.commands import (
    workspace_create,
    project_create,
)
from atlas.workspace.workspace_service import WorkspaceService


def main() -> None:
    """Run the Atlas Workspace CLI."""

    parser = argparse.ArgumentParser(
        prog="atlas",
        description="Atlas Workspace CLI",
    )

    subparsers = parser.add_subparsers(
        dest="command",
    )

    # -----------------------------
    # Workspace Commands
    # -----------------------------

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

    # -----------------------------
    # Project Commands
    # -----------------------------

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

    args = parser.parse_args()

    service = WorkspaceService()

    if (
        args.command == "workspace"
        and args.action == "create"
    ):
        workspace_create(
            service,
            args.name,
        )

    elif (
        args.command == "project"
        and args.action == "create"
    ):
        project_create(
            service,
            args.name,
        )


if __name__ == "__main__":
    main()