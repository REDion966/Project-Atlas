"""
Atlas CLI Commands.
"""

from __future__ import annotations

from atlas.workspace.paths import DEFAULT_WORKSPACE
from atlas.workspace.workspace_service import WorkspaceService
from atlas.workspace.enums import PermissionLevel


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

def permission_add(
    service: WorkspaceService,
    name: str,
    level: str,
) -> None:
    """Add a permission."""

    try:
        permission = service.create_permission(
            name,
            PermissionLevel[level.upper()],
        )
    except KeyError:
        print(
            "Invalid permission level."
        )
        return
    except RuntimeError as error:
        print(error)
        return

    service.save_workspace(
        DEFAULT_WORKSPACE,
    )

    print(
        f"Permission '{permission.name}' added."
    )

def permission_list(
    service: WorkspaceService,
) -> None:
    """List all permissions."""

    try:
        permissions = service.list_permissions()
    except RuntimeError as error:
        print(error)
        return

    if not permissions:
        print(
            "No permissions found."
        )
        return

    print("\nPermissions\n")

    for index, permission in enumerate(
        permissions,
        start=1,
    ):
        print(
            f"{index}. "
            f"{permission.name} "
            f"({permission.level.name})"
        )

    print()

def permission_remove(
    service: WorkspaceService,
    permission_id: str,
) -> None:
    """Remove a permission."""

    try:
        deleted = service.delete_permission(
            permission_id,
        )
    except RuntimeError as error:
        print(error)
        return

    if not deleted:
        print(
            "Permission not found."
        )
        return

    service.save_workspace(
        DEFAULT_WORKSPACE,
    )

    print(
        "Permission removed."
    )

def member_add(
    service: WorkspaceService,
    name: str,
) -> None:
    """Add a workspace member."""

    try:
        member = service.create_member(
            name,
        )
    except RuntimeError as error:
        print(error)
        return

    service.save_workspace(
        DEFAULT_WORKSPACE,
    )

    print(
        f"Member '{member.name}' added."
    )


def member_list(
    service: WorkspaceService,
) -> None:
    """List workspace members."""

    try:
        members = service.list_members()
    except RuntimeError as error:
        print(error)
        return

    if not members:
        print(
            "No members found."
        )
        return

    print("\nMembers\n")

    for index, member in enumerate(
        members,
        start=1,
    ):
        print(
            f"{index}. "
            f"{member.name}"
        )

    print()


def member_remove(
    service: WorkspaceService,
    member_id: str,
) -> None:
    """Remove a workspace member."""

    try:
        deleted = service.delete_member(
            member_id,
        )
    except RuntimeError as error:
        print(error)
        return

    if not deleted:
        print(
            "Member not found."
        )
        return

    service.save_workspace(
        DEFAULT_WORKSPACE,
    )

    print(
        "Member removed."
    )    