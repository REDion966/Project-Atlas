"""
Atlas Workspace Manager

High-level interface for managing workspaces.
"""

from __future__ import annotations

from pathlib import Path

from atlas.workspace.models.workspace import Workspace
from atlas.workspace.storage import WorkspaceStorage
from atlas.workspace.models.project import Project


class WorkspaceManager:
    """Manages workspace lifecycle."""

    def __init__(self) -> None:
        self._workspace: Workspace | None = None

    @property
    def workspace(self) -> Workspace | None:
        """Return the current workspace."""

        return self._workspace

    def create(self, name: str) -> Workspace:
        """Create a new workspace."""

        self._workspace = Workspace(name=name)

        return self._workspace

    def load(self, path: str | Path) -> Workspace:
        """Load a workspace."""

        self._workspace = WorkspaceStorage.load(path)

        return self._workspace

    def save(self, path: str | Path) -> None:
        """Save the current workspace."""

        if self._workspace is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        WorkspaceStorage.save(
            self._workspace,
            path,
        )

    def close(self) -> None:
        """Close the current workspace."""

        self._workspace = None

    def create_project(
        self,
        name: str,
        description: str = "",
    ) -> Project:
        """Create a project in the current workspace."""

        if self._workspace is None:
            raise RuntimeError(
                "No workspace loaded."
            )

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

        if self._workspace is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        return self._workspace.get_project(
            project_id
        )

    def list_projects(self) -> list[Project]:
        """Return all projects."""

        if self._workspace is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        return self._workspace.list_projects()

    def delete_project(
        self,
        project_id: str,
    ) -> bool:
        """Delete a project."""

        if self._workspace is None:
            raise RuntimeError(
                "No workspace loaded."
            )

        return self._workspace.remove_project(
            project_id
        )    