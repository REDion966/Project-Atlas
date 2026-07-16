"""
Tests for WorkspaceManager.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from atlas.workspace.workspace_manager import WorkspaceManager


class TestWorkspaceManager(unittest.TestCase):
    """Tests for WorkspaceManager."""

    def test_create_workspace(self) -> None:
        manager = WorkspaceManager()

        workspace = manager.create("Atlas")

        self.assertEqual(workspace.name, "Atlas")
        self.assertIs(manager.workspace, workspace)

    def test_close_workspace(self) -> None:
        manager = WorkspaceManager()

        manager.create("Atlas")
        manager.close()

        self.assertIsNone(manager.workspace)

    def test_save_and_load_workspace(self) -> None:
        manager = WorkspaceManager()

        workspace = manager.create("Atlas")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "workspace.json"

            manager.save(path)

            manager.close()

            loaded = manager.load(path)

            self.assertEqual(
                loaded.id,
                workspace.id,
            )

            self.assertEqual(
                loaded.name,
                workspace.name,
            )

    def test_save_without_workspace(self) -> None:
        manager = WorkspaceManager()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "workspace.json"

            with self.assertRaises(RuntimeError):
                manager.save(path)

    def test_create_project(self):
        manager = WorkspaceManager()

        manager.create("Atlas")

        project = manager.create_project(
            "Project A"
        )

        self.assertEqual(
            project.name,
            "Project A",
        )

    def test_get_project(self):
        manager = WorkspaceManager()

        manager.create("Atlas")

        project = manager.create_project(
            "Project A"
        )

        loaded = manager.get_project(
            project.id
        )

        self.assertEqual(
            loaded.id,
            project.id,
        )

    def test_list_projects(self):
        manager = WorkspaceManager()

        manager.create("Atlas")

        manager.create_project("A")
        manager.create_project("B")

        self.assertEqual(
            len(manager.list_projects()),
            2,
        )

    def test_delete_project(self):
        manager = WorkspaceManager()

        manager.create("Atlas")

        project = manager.create_project(
            "Project A"
        )

        self.assertTrue(
            manager.delete_project(
                project.id
            )
        )

        self.assertEqual(
            len(manager.list_projects()),
            0,
        )            


if __name__ == "__main__":
    unittest.main()