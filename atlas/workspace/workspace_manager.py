"""
Atlas Workspace Manager

High-level interface for managing workspaces.
"""

from __future__ import annotations

from pathlib import Path

from atlas.workspace.models.workspace import Workspace
from atlas.workspace.storage import WorkspaceStorage


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