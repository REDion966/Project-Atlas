"""
Atlas Project Manager

High-level interface for managing projects.
"""

from __future__ import annotations

from atlas.workspace.models.project import Project
from atlas.workspace.models.workspace import Workspace


class ProjectManager:
    """Manages projects inside a workspace."""

    def __init__(
        self,
        workspace: Workspace,
    ) -> None:
        self._workspace = workspace

    def create_project(
        self,
        name: str,
        description: str = "",
    ) -> Project:
        """Create a new project."""

        project = Project(
            name=name,
            description=description,
        )

        self._workspace.add_project(project)

        return project

    def get_project(
        self,
        project_id: str,
    ) -> Project | None:
        """Return a project."""

        return self._workspace.get_project(
            project_id
        )

    def list_projects(
        self,
    ) -> list[Project]:
        """Return all projects."""

        return self._workspace.list_projects()

    def delete_project(
        self,
        project_id: str,
    ) -> bool:
        """Delete a project."""

        return self._workspace.remove_project(
            project_id
        )