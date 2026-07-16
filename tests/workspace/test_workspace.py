import unittest

from atlas.workspace.models.project import Project
from atlas.workspace.models.workspace import Workspace


class TestWorkspace(unittest.TestCase):

    def test_add_project(self):
        workspace = Workspace()
        project = Project(name="Atlas")

        workspace.add_project(project)

        self.assertEqual(
            len(workspace.projects),
            1,
        )

    def test_get_project(self):
        workspace = Workspace()
        project = Project(name="Atlas")

        workspace.add_project(project)

        self.assertEqual(
            workspace.get_project(project.id),
            project,
        )

    def test_remove_project(self):
        workspace = Workspace()
        project = Project(name="Atlas")

        workspace.add_project(project)

        self.assertTrue(
            workspace.remove_project(project.id)
        )

        self.assertEqual(
            len(workspace.projects),
            0,
        )

    def test_to_dict(self):
        workspace = Workspace()

        data = workspace.to_dict()

        self.assertEqual(
            data["name"],
            workspace.name,
        )

    def test_from_dict(self):
        workspace = Workspace()

        loaded = Workspace.from_dict(
            workspace.to_dict()
        )

        self.assertEqual(
            loaded.id,
            workspace.id,
        )

    def test_list_projects(self):
        workspace = Workspace()

        workspace.add_project(
            Project(name="Project A")
        )

        workspace.add_project(
            Project(name="Project B")
        )

        projects = workspace.list_projects()

        self.assertEqual(
            len(projects),
            2,
        )

        self.assertIsNot(
            projects,
            workspace.projects,
        )

if __name__ == "__main__":
    unittest.main()