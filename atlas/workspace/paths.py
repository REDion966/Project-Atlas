"""
Atlas Workspace Paths

Provides standard filesystem locations used by Atlas.
"""

from __future__ import annotations

from pathlib import Path


# Atlas configuration directory
ATLAS_DIR = Path.home() / ".atlas"

# Default workspace file
DEFAULT_WORKSPACE = ATLAS_DIR / "workspace.json"


def ensure_atlas_directory() -> Path:
    """
    Ensure the Atlas configuration directory exists.

    Returns:
        Path to the Atlas configuration directory.
    """

    ATLAS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    return ATLAS_DIR