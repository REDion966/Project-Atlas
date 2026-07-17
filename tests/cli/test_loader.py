"""
Tests for workspace loader.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from atlas.workspace.loader import load_workspace_service


class TestWorkspaceLoader(unittest.TestCase):
    """Tests for loading the default workspace."""

    @patch("atlas.workspace.loader.DEFAULT_WORKSPACE")
    @patch("atlas.workspace.loader.ensure_atlas_directory")
    def test_load_without_workspace(
        self,
        ensure_dir,
        workspace_path,
    ) -> None:
        workspace_path.exists.return_value = False

        service = load_workspace_service()

        self.assertIsNone(
            service.workspace
        )

    @patch("atlas.workspace.loader.DEFAULT_WORKSPACE")
    @patch("atlas.workspace.loader.ensure_atlas_directory")
    def test_load_existing_workspace(
        self,
        ensure_dir,
        workspace_path,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "workspace.json"

            from atlas.workspace.workspace_service import (
                WorkspaceService,
            )

            service = WorkspaceService()
            service.create_workspace("Atlas")
            service.save_workspace(path)

            workspace_path.exists.return_value = True
            workspace_path.__fspath__.return_value = str(path)

            loaded = load_workspace_service()

            self.assertIsNotNone(
                loaded.workspace
            )

            self.assertEqual(
                loaded.workspace.name,
                "Atlas",
            )


if __name__ == "__main__":
    unittest.main()