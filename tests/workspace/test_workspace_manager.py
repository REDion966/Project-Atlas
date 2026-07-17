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

    def test_rename_workspace(self) -> None:
        manager = WorkspaceManager()

        manager.create("Old")

        manager.rename_workspace("New")

        self.assertEqual(
            manager.workspace.name,
            "New",
        )

    def test_rename_workspace_no_workspace(self) -> None:
        manager = WorkspaceManager()

        with self.assertRaises(RuntimeError):
            manager.rename_workspace("New")

    def test_archive_workspace(self) -> None:
        manager = WorkspaceManager()

        manager.create("Test")

        manager.archive_workspace()

        self.assertTrue(
            manager.workspace.archived,
        )

    def test_archive_workspace_no_workspace(self) -> None:
        manager = WorkspaceManager()

        with self.assertRaises(RuntimeError):
            manager.archive_workspace()

    def test_restore_workspace(self) -> None:
        manager = WorkspaceManager()

        manager.create("Test")

        manager.archive_workspace()

        self.assertTrue(
            manager.workspace.archived,
        )

        manager.restore_workspace()

        self.assertFalse(
            manager.workspace.archived,
        )

    def test_restore_workspace_no_workspace(self) -> None:
        manager = WorkspaceManager()

        with self.assertRaises(RuntimeError):
            manager.restore_workspace()

    def test_export_workspace_creates_file(self) -> None:
        manager = WorkspaceManager()

        manager.create("Atlas")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "export.json"

            manager.export_workspace(path)

            self.assertTrue(path.exists())

    def test_export_without_workspace_raises(self) -> None:
        manager = WorkspaceManager()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "export.json"

            with self.assertRaises(RuntimeError):
                manager.export_workspace(path)

    def test_import_workspace_replaces_current(self) -> None:
        manager = WorkspaceManager()

        original = manager.create("Original")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "workspace.json"

            original.rename("ToExport")
            manager.export_workspace(path)

            manager.create("Override")

            loaded = manager.import_workspace(path)

            self.assertEqual(
                loaded.id,
                original.id,
            )

            self.assertEqual(
                loaded.name,
                "ToExport",
            )

            self.assertIs(
                manager.workspace,
                loaded,
            )

    def test_imported_workspace_matches_exported(self) -> None:
        manager = WorkspaceManager()

        workspace = manager.create("Atlas")

        with tempfile.TemporaryDirectory() as tmpdir:
            export_path = Path(tmpdir) / "export.json"
            manager.export_workspace(export_path)

            manager.close()

            imported = manager.import_workspace(export_path)

            self.assertEqual(
                imported.to_dict(),
                workspace.to_dict(),
            )

if __name__ == "__main__":
    unittest.main()
