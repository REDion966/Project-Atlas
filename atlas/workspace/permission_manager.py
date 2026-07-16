"""
Atlas Permission Manager

High-level interface for managing workspace members.
"""

from __future__ import annotations

from atlas.workspace.enums import PermissionLevel
from atlas.workspace.models.permission import Permission
from atlas.workspace.models.workspace import Workspace


class PermissionManager:
    """Manages workspace permissions."""

    def __init__(
        self,
        workspace: Workspace,
    ) -> None:
        self._workspace = workspace

    def create_permission(
        self,
        name: str,
        level: PermissionLevel = PermissionLevel.READ,
    ) -> Permission:
        """Create a permission."""

        permission = Permission(
            name=name,
            level=level,
        )

        self._workspace.members.append(permission)
        self._workspace.touch()

        return permission

    def get_permission(
        self,
        permission_id: str,
    ) -> Permission | None:
        """Return a permission."""

        for permission in self._workspace.members:
            if permission.id == permission_id:
                return permission

        return None

    def list_permissions(
        self,
    ) -> list[Permission]:
        """Return all permissions."""

        return self._workspace.members.copy()

    def delete_permission(
        self,
        permission_id: str,
    ) -> bool:
        """Delete a permission."""

        for permission in self._workspace.members:
            if permission.id == permission_id:
                self._workspace.members.remove(permission)
                self._workspace.touch()
                return True

        return False