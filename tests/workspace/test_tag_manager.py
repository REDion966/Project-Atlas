"""
Tests for TagManager.
"""

import unittest

from atlas.workspace.models.project import Project
from atlas.workspace.tag_manager import TagManager


class TestTagManager(unittest.TestCase):

    def test_create_tag(self):
        project = Project()
        manager = TagManager(project)

        manager.create_tag("python")

        self.assertEqual(
            len(project.tags),
            1,
        )

        self.assertEqual(
            project.tags[0],
            "python",
        )

    def test_delete_tag(self):
        project = Project()
        manager = TagManager(project)

        manager.create_tag("python")

        self.assertTrue(
            manager.delete_tag("python")
        )

        self.assertEqual(
            len(project.tags),
            0,
        )

    def test_list_tags(self):
        project = Project()
        manager = TagManager(project)

        manager.create_tag("python")
        manager.create_tag("atlas")

        tags = manager.list_tags()

        self.assertEqual(
            len(tags),
            2,
        )

        self.assertIsNot(
            tags,
            project.tags,
        )

    def test_has_tag(self):
        project = Project()
        manager = TagManager(project)

        manager.create_tag("python")

        self.assertTrue(
            manager.has_tag("python")
        )

        self.assertFalse(
            manager.has_tag("java")
        )


if __name__ == "__main__":
    unittest.main()