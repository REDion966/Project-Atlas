"""
Tests for ProjectManager.
"""

import unittest

from atlas.workspace.models.workspace import Workspace
from atlas.workspace.project_manager import ProjectManager


class TestProjectManager(unittest.TestCase):

    def test_create_project(self):
        workspace = Workspace()
        manager = ProjectManager(workspace)

        project = manager.create_project("Atlas")

        self.assertEqual(
            project.name,
            "Atlas",
        )

        self.assertEqual(
            len(workspace.projects),
            1,
        )

    def test_get_project(self):
        workspace = Workspace()
        manager = ProjectManager(workspace)

        project = manager.create_project("Atlas")

        loaded = manager.get_project(project.id)

        self.assertEqual(
            loaded,
            project,
        )

    def test_list_projects(self):
        workspace = Workspace()
        manager = ProjectManager(workspace)

        manager.create_project("A")
        manager.create_project("B")

        self.assertEqual(
            len(manager.list_projects()),
            2,
        )

    def test_delete_project(self):
        workspace = Workspace()
        manager = ProjectManager(workspace)

        project = manager.create_project("Atlas")

        self.assertTrue(
            manager.delete_project(project.id)
        )

        self.assertEqual(
            len(manager.list_projects()),
            0,
        )


if __name__ == "__main__":
    unittest.main()