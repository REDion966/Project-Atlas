"""
Atlas Workspace Service

Coordinates workspace operations.
"""

from __future__ import annotations

from pathlib import Path

from atlas.workspace.enums import (
    PermissionLevel,
    ResourceType,
)
from atlas.workspace.models.permission import Permission
from atlas.workspace.models.project import Project
from atlas.workspace.models.resource import Resource
from atlas.workspace.models.workspace import Workspace
from atlas.workspace.permission_manager import PermissionManager
from atlas.workspace.project_manager import ProjectManager
from atlas.workspace.resource_manager import ResourceManager
from atlas.workspace.workspace_manager import WorkspaceManager
from atlas.workspace.member_manager import MemberManager
from atlas.workspace.models.member import Member
from atlas.workspace.models.settings import WorkspaceSettings
from atlas.workspace.tag_manager import TagManager
from atlas.workspace.models.tag import Tag


class WorkspaceService:
    """High-level workspace service."""

    def __init__(self) -> None:
        self.workspace_manager = WorkspaceManager()

        self.project_manager: ProjectManager | None = None
        self.resource_manager: ResourceManager | None = None
        self.permission_manager: PermissionManager | None = None
        self.member_manager: MemberManager | None = None
        self.tag_manager: TagManager | None = None

    @property
    def workspace(self) -> Workspace | None:
        """Return current workspace."""

        return self.workspace_manager.workspace

    def create_workspace(
        self,
        name: str,
    ) -> Workspace:
        """Create a workspace."""

        workspace = self.workspace_manager.create(
            name,
        )

        self.project_manager = ProjectManager(
            workspace,
        )

        self.permission_manager = PermissionManager(
            workspace,
        )

        self.member_manager = MemberManager(
            workspace,
        )

        self.tag_manager = TagManager(
            workspace,
        )

        return workspace

    def load_workspace(
        self,
        path: Path,
    ) -> Workspace:
        """Load a workspace."""

        workspace = self.workspace_manager.load(
            path,
        )

        self.project_manager = ProjectManager(
            workspace,
        )

        self.permission_manager = PermissionManager(
            workspace,
        )

        self.member_manager = MemberManager(
            workspace,
        )

        self.tag_manager = TagManager(
            workspace,
        )

        return workspace

    def save_workspace(
        self,
        path: Path,
    ) -> None:
        """Save current workspace."""

        self.workspace_manager.save(path)

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def create_project(
        self,
        name: str,
        description: str = "",
    ) -> Project:
        """Create a project."""

        if self.project_manager is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        project = self.project_manager.create_project(
            name,
            description,
        )

        self.resource_manager = ResourceManager(
            project,
        )

        self.tag_manager = TagManager(
            project,
        )

        return project

    def get_project(
        self,
        project_id: str,
    ) -> Project | None:
        """Return a project."""

        if self.project_manager is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        project = self.project_manager.get_project(
            project_id,
        )

        if project is not None:
            self.resource_manager = ResourceManager(
                project,
            )
            self.tag_manager = TagManager(
                project,
            )

        return project

    def list_projects(
        self,
    ) -> list[Project]:
        """Return all projects."""

        if self.project_manager is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        return self.project_manager.list_projects()

    def delete_project(
        self,
        project_id: str,
    ) -> bool:
        """Delete a project."""

        if self.project_manager is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        deleted = self.project_manager.delete_project(
            project_id,
        )

        if deleted:
            self.resource_manager = None
            self.tag_manager = None
        return deleted

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------

    def create_resource(
        self,
        name: str,
        resource_type: ResourceType = ResourceType.FILE,
        path: str = "",
        description: str = "",
    ) -> Resource:
        """Create a resource."""

        if self.resource_manager is None:
            raise RuntimeError(
                "No project selected."
            )

        return self.resource_manager.create_resource(
            name,
            resource_type,
            path,
            description,
        )

    def get_resource(
        self,
        resource_id: str,
    ) -> Resource | None:
        """Return a resource."""

        if self.resource_manager is None:
            raise RuntimeError(
                "No project selected."
            )

        return self.resource_manager.get_resource(
            resource_id,
        )

    def list_resources(
        self,
    ) -> list[Resource]:
        """Return all resources."""

        if self.resource_manager is None:
            raise RuntimeError(
                "No project selected."
            )

        return self.resource_manager.list_resources()

    def delete_resource(
        self,
        resource_id: str,
    ) -> bool:
        """Delete a resource."""

        if self.resource_manager is None:
            raise RuntimeError(
                "No project selected."
            )

        return self.resource_manager.delete_resource(
            resource_id,
        )

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    def create_permission(
        self,
        name: str,
        level: PermissionLevel = PermissionLevel.READ,
    ) -> Permission:
        """Create a permission."""

        if self.permission_manager is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        return self.permission_manager.create_permission(
            name,
            level,
        )

    def get_permission(
        self,
        permission_id: str,
    ) -> Permission | None:
        """Return a permission."""

        if self.permission_manager is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        return self.permission_manager.get_permission(
            permission_id,
        )

    def list_permissions(
        self,
    ) -> list[Permission]:
        """Return all permissions."""

        if self.permission_manager is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        return self.permission_manager.list_permissions()

    def delete_permission(
        self,
        permission_id: str,
    ) -> bool:
        """Delete a permission."""

        if self.permission_manager is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        return self.permission_manager.delete_permission(
            permission_id,
        )

    # ------------------------------------------------------------------
    # Workspace
    # ------------------------------------------------------------------

    def create_member(
        self,
        name: str,
    ) -> Member:
        """Create a member."""

        if self.member_manager is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        return self.member_manager.create_member(
            name,
        )

    def get_member(
        self,
        member_id: str,
    ) -> Member | None:
        """Return a member."""

        if self.member_manager is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        return self.member_manager.get_member(
            member_id,
        )

    def list_members(
        self,
    ) -> list[Member]:
        """Return all members."""

        if self.member_manager is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        return self.member_manager.list_members()

    def delete_member(
        self,
        member_id: str,
    ) -> bool:
        """Delete a member."""

        if self.member_manager is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        return self.member_manager.delete_member(
            member_id,
        )

    def get_settings(
        self,
    ) -> WorkspaceSettings:
        """Return workspace settings."""

        if self.workspace is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        return self.workspace.settings

    def update_settings(
        self,
        settings: WorkspaceSettings,
    ) -> None:
        """Replace workspace settings."""

        if self.workspace is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        self.workspace.settings = settings
        self.workspace.touch()
    
    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def create_tag(
        self,
        name: str,
        color: str = "#4F46E5",
    ) -> Tag:
        """Create a tag."""

        if self.tag_manager is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        return self.tag_manager.create_tag(
            name,
            color,
        )


    def get_tag(
        self,
        tag_id: str,
    ) -> Tag | None:
        """Return a tag."""

        if self.tag_manager is None:
            raise RuntimeError(
            "No workspace loaded."
        )

        return self.tag_manager.get_tag(
            tag_id,
        )

    def list_tags(
        self,
    ) -> list[Tag]:
        """Return all tags."""

        if self.tag_manager is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        return self.tag_manager.list_tags()


    def delete_tag(
        self,
        tag_id: str,
    ) -> bool:
        """Delete a tag."""

        if self.tag_manager is None:
            raise RuntimeError(
            "No workspace loaded."
        )

        return self.tag_manager.delete_tag(
            tag_id,
        )
    
    def close_workspace(
        self,
    ) -> None:
        """Close current workspace."""

        self.workspace_manager.close()

        self.project_manager = None
        self.resource_manager = None
        self.permission_manager = None
        self.member_manager = None
