"""
Atlas Workspace Service

Coordinates workspace operations.
"""

from __future__ import annotations

from pathlib import Path

from atlas.workspace.enums import ResourceType
from atlas.workspace.models.workspace import Workspace
from atlas.workspace.models.project import Project
from atlas.workspace.models.resource import Resource
from atlas.workspace.workspace_manager import WorkspaceManager
from atlas.workspace.project_manager import ProjectManager
from atlas.workspace.resource_manager import ResourceManager


class WorkspaceService:
    """High-level workspace service."""

    def __init__(self) -> None:
        self.workspace_manager = WorkspaceManager()
        self.project_manager: ProjectManager | None = None
        self.resource_manager: ResourceManager | None = None

    @property
    def workspace(self) -> Workspace | None:
        """Return current workspace."""

        return self.workspace_manager.workspace

    def create_workspace(
        self,
        name: str,
    ) -> Workspace:
        """Create a workspace."""

        workspace = self.workspace_manager.create(name)
        self.project_manager = ProjectManager(workspace)

        return workspace

    def load_workspace(
        self,
        path: Path,
    ) -> Workspace:
        """Load a workspace."""

        workspace = self.workspace_manager.load(path)
        self.project_manager = ProjectManager(workspace)

        return workspace

    def save_workspace(
        self,
        path: Path,
    ) -> None:
        """Save current workspace."""

        self.workspace_manager.save(path)

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

        self.resource_manager = ResourceManager(project)

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
            project_id
        )

        if project is not None:
            self.resource_manager = ResourceManager(project)

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
            project_id
        )

        if deleted:
            self.resource_manager = None

        return deleted

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
            resource_id
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
            resource_id
        )

    def close_workspace(self) -> None:
        """Close current workspace."""

        self.workspace_manager.close()
        self.project_manager = None
        self.resource_manager = None