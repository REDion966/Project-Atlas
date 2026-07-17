"""
Tests for WorkspaceService.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()