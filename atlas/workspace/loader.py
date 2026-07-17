"""
Atlas Workspace Loader.

Loads the default workspace used by the CLI.
"""

from __future__ import annotations

from atlas.workspace.paths import (
    DEFAULT_WORKSPACE,
    ensure_atlas_directory,
)
from atlas.workspace.workspace_service import (
    WorkspaceService,
)


def load_workspace_service() -> WorkspaceService:
    """
    Load the default workspace service.

    Returns:
        WorkspaceService
    """

    ensure_atlas_directory()

    service = WorkspaceService()

    if DEFAULT_WORKSPACE.exists():
        service.load_workspace(
            DEFAULT_WORKSPACE
        )

    return service