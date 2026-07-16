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

    def test_add_resource(self):
        from atlas.workspace.models.resource import Resource

        project = Project(name="Atlas")

        resource = Resource(
            name="README.md"
        )

        project.add_resource(resource)

        self.assertEqual(
            len(project.resources),
            1,
        )

    def test_get_resource(self):
        from atlas.workspace.models.resource import Resource

        project = Project(name="Atlas")

        resource = Resource(
            name="README.md"
        )

        project.add_resource(resource)

        self.assertEqual(
            project.get_resource(resource.id),
            resource,
        )

    def test_remove_resource(self):
        from atlas.workspace.models.resource import Resource

        project = Project(name="Atlas")

        resource = Resource(
            name="README.md"
        )

        project.add_resource(resource)

        self.assertTrue(
            project.remove_resource(resource.id)
        )

        self.assertEqual(
            len(project.resources),
            0,
        )

    def test_list_resources(self):
        from atlas.workspace.models.resource import Resource

        project = Project(name="Atlas")

        project.add_resource(
            Resource(name="A")
        )

        project.add_resource(
            Resource(name="B")
        )

        resources = project.list_resources()

        self.assertEqual(
            len(resources),
            2,
        )

        self.assertIsNot(
            resources,
            project.resources,
        )    


if __name__ == "__main__":
    unittest.main()