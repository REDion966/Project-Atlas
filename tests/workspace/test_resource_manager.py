"""
Tests for ResourceManager.
"""

import unittest

from atlas.workspace.models.project import Project
from atlas.workspace.resource_manager import ResourceManager


class TestResourceManager(unittest.TestCase):

    def test_create_resource(self):
        project = Project(name="Atlas")
        manager = ResourceManager(project)

        resource = manager.create_resource(
            "README.md"
        )

        self.assertEqual(
            resource.name,
            "README.md",
        )

        self.assertEqual(
            len(project.resources),
            1,
        )

    def test_get_resource(self):
        project = Project(name="Atlas")
        manager = ResourceManager(project)

        resource = manager.create_resource(
            "README.md"
        )

        loaded = manager.get_resource(
            resource.id
        )

        self.assertEqual(
            loaded,
            resource,
        )

    def test_list_resources(self):
        project = Project(name="Atlas")
        manager = ResourceManager(project)

        manager.create_resource("A")
        manager.create_resource("B")

        self.assertEqual(
            len(manager.list_resources()),
            2,
        )

    def test_delete_resource(self):
        project = Project(name="Atlas")
        manager = ResourceManager(project)

        resource = manager.create_resource(
            "README.md"
        )

        self.assertTrue(
            manager.delete_resource(
                resource.id
            )
        )

        self.assertEqual(
            len(manager.list_resources()),
            0,
        )


if __name__ == "__main__":
    unittest.main()