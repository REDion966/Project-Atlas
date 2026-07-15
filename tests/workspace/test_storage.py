"""
Tests for WorkspaceStorage.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from atlas.workspace.storage.json_storage import WorkspaceStorage
from atlas.workspace.models.workspace import Workspace


class TestWorkspaceStorage(unittest.TestCase):
    """Tests for WorkspaceStorage."""

    def test_save_and_load(self) -> None:
        workspace = Workspace(name="Atlas")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "workspace.json"

            WorkspaceStorage.save(workspace, path)

            self.assertTrue(path.exists())

            loaded = WorkspaceStorage.load(path)

            self.assertEqual(
                loaded.id,
                workspace.id,
            )

            self.assertEqual(
                loaded.name,
                workspace.name,
            )

    def test_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "workspace.json"

            self.assertFalse(
                WorkspaceStorage.exists(path)
            )

            WorkspaceStorage.save(
                Workspace(),
                path,
            )

            self.assertTrue(
                WorkspaceStorage.exists(path)
            )

    def test_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "workspace.json"

            WorkspaceStorage.save(
                Workspace(),
                path,
            )

            self.assertTrue(path.exists())

            WorkspaceStorage.delete(path)

            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()