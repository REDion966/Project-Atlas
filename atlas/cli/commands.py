"""
Atlas Workspace CLI Commands.
"""

from __future__ import annotations

from atlas.workspace.workspace_service import WorkspaceService
from atlas.workspace.paths import DEFAULT_WORKSPACE


def workspace_create(
    service: WorkspaceService,
    name: str,
) -> None:
    """Create a workspace."""

    if DEFAULT_WORKSPACE.exists():
        print(
            "A workspace already exists.\n"
            "Delete the existing workspace file "
            "or use a future reset command."
        )
        return

    workspace = service.create_workspace(
        name,
    )

    service.save_workspace(
        DEFAULT_WORKSPACE,
    )

    print(
        f"Workspace '{workspace.name}' created."
    )

def project_create(
    service: WorkspaceService,
    name: str,
) -> None:
    """Create a project."""

    project = service.create_project(name)

    service.save_workspace(
        DEFAULT_WORKSPACE,
    )

    print(
        f"Project '{project.name}' created."
    )