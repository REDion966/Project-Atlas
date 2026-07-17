"""
Tests for WorkspaceService.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from atlas.workspace.models.settings import WorkspaceSettings
from atlas.workspace.workspace_service import WorkspaceService


class TestWorkspaceService(unittest.TestCase):

    def test_create_workspace(self):
        service = WorkspaceService()

        workspace = service.create_workspace(
            "Atlas"
        )

        self.assertEqual(
            workspace.name,
            "Atlas",
        )

        self.assertIs(
            service.workspace,
            workspace,
        )

    def test_close_workspace(self):
        service = WorkspaceService()

        service.create_workspace("Atlas")
        service.close_workspace()

        self.assertIsNone(
            service.workspace
        )

    def test_save_and_load_workspace(self):
        service = WorkspaceService()

        workspace = service.create_workspace(
            "Atlas"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "workspace.json"

            service.save_workspace(path)

            service.close_workspace()

            loaded = service.load_workspace(path)

            self.assertEqual(
                loaded.id,
                workspace.id,
            )

            self.assertEqual(
                loaded.name,
                workspace.name,
            )

    def test_create_project(self):
        service = WorkspaceService()

        service.create_workspace("Atlas")

        project = service.create_project(
            "Project A"
        )

        self.assertEqual(
            project.name,
        "Project A",
        )

    def test_get_project(self):
        service = WorkspaceService()

        service.create_workspace("Atlas")

        project = service.create_project(
            "Project A"
        )

        loaded = service.get_project(
            project.id
        )

        self.assertEqual(
            loaded,
            project,
        )


    def test_list_projects(self):
        service = WorkspaceService()

        service.create_workspace("Atlas")

        service.create_project("A")
        service.create_project("B")

        self.assertEqual(
            len(service.list_projects()),
            2,
        )


    def test_delete_project(self):
        service = WorkspaceService()

        service.create_workspace("Atlas")

        project = service.create_project(
            "Project A"
        )

        self.assertTrue(
            service.delete_project(
                project.id
            )
        )

        self.assertEqual(
            len(service.list_projects()),
            0,
        )

    def test_create_resource(self):
        service = WorkspaceService()

        service.create_workspace("Atlas")

        service.create_project(
            "Project A"
        )

        resource = service.create_resource(
            "README.md"
        )

        self.assertEqual(
            resource.name,
            "README.md",
        )

    def test_get_resource(self):
        service = WorkspaceService()

        service.create_workspace("Atlas")

        service.create_project(
            "Project A"
        )

        resource = service.create_resource(
            "README.md"
        )

        loaded = service.get_resource(
            resource.id
        )

        self.assertEqual(
            loaded,
            resource,
        )

    def test_list_resources(self):
        service = WorkspaceService()

        service.create_workspace("Atlas")

        service.create_project(
            "Project A"
        )

        service.create_resource("A")
        service.create_resource("B")

        self.assertEqual(
            len(service.list_resources()),
            2,
        )

    def test_delete_resource(self):
        service = WorkspaceService()

        service.create_workspace("Atlas")

        service.create_project(
            "Project A"
        )

        resource = service.create_resource(
            "README.md"
        )

        self.assertTrue(
            service.delete_resource(
                resource.id
            )
        )

        self.assertEqual(
            len(service.list_resources()),
            0,
        )

    def test_close_clears_managers(self):
        service = WorkspaceService()

        service.create_workspace("Atlas")
        service.create_project("Project A")

        self.assertIsNotNone(
            service.project_manager
        )

        self.assertIsNotNone(
            service.resource_manager
        )

        service.close_workspace()

        self.assertIsNone(
            service.project_manager
        )

        self.assertIsNone(
            service.resource_manager
        )

        self.assertIsNone(
            service.workspace
        )

    def test_get_settings(self):
        service = WorkspaceService()

        service.create_workspace("Atlas")

        settings = service.get_settings()

        self.assertIsInstance(
            settings,
            WorkspaceSettings,
        )

        self.assertEqual(
            settings.version,
            "1.0",
        )

    def test_update_settings(self):
        service = WorkspaceService()

        service.create_workspace("Atlas")

        new_settings = WorkspaceSettings(
            version="2.0",
            autosave=False,
        )

        service.update_settings(new_settings)

        self.assertIs(
            service.get_settings(),
            new_settings,
        )

    def test_update_settings_updates_timestamp(self):
        service = WorkspaceService()

        service.create_workspace("Atlas")

        original_updated = service.workspace.updated_at

        new_settings = WorkspaceSettings(
            version="2.0",
        )

        service.update_settings(new_settings)

        self.assertGreater(
            service.workspace.updated_at,
            original_updated,
        )

    def test_get_settings_no_workspace(self):
        service = WorkspaceService()

        with self.assertRaises(RuntimeError):
            service.get_settings()

    def test_update_settings_no_workspace(self):
        service = WorkspaceService()

        with self.assertRaises(RuntimeError):
            service.update_settings(
                WorkspaceSettings()
            )

    def test_rename_workspace(self):
        service = WorkspaceService()

        service.create_workspace("Old")

        service.rename_workspace("New")

        self.assertEqual(
            service.workspace.name,
            "New",
        )

    def test_rename_workspace_no_workspace(self):
        service = WorkspaceService()

        with self.assertRaises(RuntimeError):
            service.rename_workspace("New")

    def test_archive_workspace(self):
        service = WorkspaceService()

        service.create_workspace("Test")

        service.archive_workspace()

        self.assertTrue(
            service.workspace.archived,
        )

    def test_archive_workspace_no_workspace(self):
        service = WorkspaceService()

        with self.assertRaises(RuntimeError):
            service.archive_workspace()

    def test_restore_workspace(self):
        service = WorkspaceService()

        service.create_workspace("Test")

        service.archive_workspace()

        self.assertTrue(
            service.workspace.archived,
        )

        service.restore_workspace()

        self.assertFalse(
            service.workspace.archived,
        )

    def test_restore_workspace_no_workspace(self):
        service = WorkspaceService()

        with self.assertRaises(RuntimeError):
            service.restore_workspace()

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    def test_export_workspace_creates_file(self):
        service = WorkspaceService()

        service.create_workspace("Atlas")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "export.json"

            service.export_workspace(path)

            self.assertTrue(path.exists())

    def test_export_without_workspace_raises(self):
        service = WorkspaceService()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "export.json"

            with self.assertRaises(RuntimeError):
                service.export_workspace(path)

    def test_import_workspace_restores_workspace(self):
        service = WorkspaceService()

        workspace = service.create_workspace("Atlas")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "workspace.json"

            service.save_workspace(path)

            service.close_workspace()

            loaded = service.import_workspace(path)

            self.assertEqual(
                loaded.id,
                workspace.id,
            )

            self.assertEqual(
                loaded.name,
                "Atlas",
            )

    def test_imported_workspace_matches_exported(self):
        service = WorkspaceService()

        workspace = service.create_workspace("Atlas")

        with tempfile.TemporaryDirectory() as tmpdir:
            export_path = Path(tmpdir) / "export.json"

            service.export_workspace(export_path)

            service.close_workspace()

            imported = service.import_workspace(export_path)

            self.assertEqual(
                imported.to_dict(),
                workspace.to_dict(),
            )

    def test_import_workspace_reinitialises_managers(self):
        service = WorkspaceService()

        service.create_workspace("Atlas")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "workspace.json"

            service.export_workspace(path)

            service.close_workspace()

            service.import_workspace(path)

            self.assertIsNotNone(
                service.project_manager,
            )

            self.assertIsNotNone(
                service.permission_manager,
            )

            self.assertIsNotNone(
                service.member_manager,
            )

if __name__ == "__main__":
    unittest.main()
