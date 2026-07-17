"""
Atlas CLI Commands.
"""

from __future__ import annotations

from atlas.workspace.paths import DEFAULT_WORKSPACE
from atlas.workspace.workspace_service import WorkspaceService


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

    workspace = service.create_workspace(name)

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


def resource_add(
    service: WorkspaceService,
    name: str,
) -> None:
    """Add a resource to the current project."""

    try:
        resource = service.create_resource(
            name,
        )
    except RuntimeError as error:
        print(error)
        return

    service.save_workspace(
        DEFAULT_WORKSPACE,
    )

    print(
        f"Resource '{resource.name}' added."
    )

def resource_list(
    service: WorkspaceService,
) -> None:
    """List all resources."""

    try:
        resources = service.list_resources()
    except RuntimeError as error:
        print(error)
        return

    if not resources:
        print("No resources found.")
        return

    print("\nResources\n")

    for index, resource in enumerate(
        resources,
        start=1,
    ):
        print(
            f"{index}. {resource.name}"
        )

def resource_remove(
    service: WorkspaceService,
    resource_id: str,
) -> None:
    """Remove a resource."""

    try:
        deleted = service.delete_resource(
            resource_id,
        )
    except RuntimeError as error:
        print(error)
        return

    if not deleted:
        print(
            "Resource not found."
        )
        return

    service.save_workspace(
        DEFAULT_WORKSPACE,
    )

    print(
        "Resource removed."
    )    

    print()    