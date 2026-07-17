"""
Tests for TagManager.
"""

import unittest

from atlas.workspace.models.tag import Tag
from atlas.workspace.models.workspace import Workspace
from atlas.workspace.tag_manager import TagManager


class TestTagManager(unittest.TestCase):

    def test_create_tag(self):
        workspace = Workspace()
        manager = TagManager(workspace)

        tag = manager.create_tag("python")

        self.assertIsInstance(tag, Tag)
        self.assertEqual(tag.name, "python")
        self.assertEqual(len(workspace.tags), 1)
        self.assertIs(workspace.tags[0], tag)

    def test_get_tag(self):
        workspace = Workspace()
        manager = TagManager(workspace)

        created = manager.create_tag("python")
        found = manager.get_tag(created.id)

        self.assertIs(found, created)

    def test_get_tag_missing(self):
        workspace = Workspace()
        manager = TagManager(workspace)

        found = manager.get_tag("non-existent")
        self.assertIsNone(found)

    def test_list_tags(self):
        workspace = Workspace()
        manager = TagManager(workspace)

        tag1 = manager.create_tag("python")
        tag2 = manager.create_tag("atlas")

        tags = manager.list_tags()

        self.assertEqual(len(tags), 2)
        self.assertIn(tag1, tags)
        self.assertIn(tag2, tags)
        self.assertIsNot(tags, workspace.tags)

    def test_delete_tag(self):
        workspace = Workspace()
        manager = TagManager(workspace)

        tag = manager.create_tag("python")

        self.assertTrue(manager.delete_tag(tag.id))
        self.assertEqual(len(workspace.tags), 0)

    def test_delete_tag_missing(self):
        workspace = Workspace()
        manager = TagManager(workspace)

        self.assertFalse(manager.delete_tag("non-existent"))


if __name__ == "__main__":
    unittest.main()
