"""
Atlas Workspace Storage

Handles saving and loading workspaces.
"""

from __future__ import annotations

import json
from pathlib import Path

from atlas.workspace.models.workspace import Workspace


class WorkspaceStorage:
    """Handles persistent workspace storage."""

    @staticmethod
    def save(workspace: Workspace, path: str | Path) -> None:
        """Save a workspace to disk."""

        file_path = Path(path)

        file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with file_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                workspace.to_dict(),
                file,
                indent=4,
            )

    @staticmethod
    def load(path: str | Path) -> Workspace:
        """Load a workspace from disk."""

        file_path = Path(path)

        with file_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        return Workspace.from_dict(data)

    @staticmethod
    def exists(path: str | Path) -> bool:
        """Return True if a workspace exists."""

        return Path(path).exists()

    @staticmethod
    def delete(path: str | Path) -> None:
        """Delete a stored workspace."""

        file_path = Path(path)

        if file_path.exists():
            file_path.unlink()