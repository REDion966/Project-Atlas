import unittest

from atlas.workspace.models.project import Project


class TestProject(unittest.TestCase):

    def test_create_project(self):
        project = Project(name="Atlas")

        self.assertEqual(project.name, "Atlas")
        self.assertFalse(project.archived)

    def test_rename_project(self):
        project = Project(name="Old")

        project.rename("New")

        self.assertEqual(project.name, "New")

    def test_archive_project(self):
        project = Project()

        project.archive()

        self.assertTrue(project.archived)

    def test_restore_project(self):
        project = Project()

        project.archive()
        project.restore()

        self.assertFalse(project.archived)

    def test_to_dict(self):
        project = Project(name="Atlas")

        data = project.to_dict()

        self.assertEqual(data["name"], "Atlas")

    def test_from_dict(self):
        project = Project(name="Atlas")

        loaded = Project.from_dict(
            project.to_dict()
        )

        self.assertEqual(
            loaded.name,
            project.name,
        )

        self.assertEqual(
            loaded.id,
            project.id,
        )


if __name__ == "__main__":
    unittest.main()