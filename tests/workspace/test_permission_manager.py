"""
Tests for PermissionManager.
"""

import unittest

from atlas.workspace.enums import PermissionLevel
from atlas.workspace.models.workspace import Workspace
from atlas.workspace.permission_manager import PermissionManager


class TestPermissionManager(unittest.TestCase):

    def test_create_permission(self):
        workspace = Workspace()
        manager = PermissionManager(workspace)

        permission = manager.create_permission(
            "admin",
            PermissionLevel.FULL,
        )

        self.assertEqual(
            permission.name,
            "admin",
        )

        self.assertEqual(
            len(workspace.members),
            1,
        )

    def test_get_permission(self):
        workspace = Workspace()
        manager = PermissionManager(workspace)

        permission = manager.create_permission(
            "admin",
            PermissionLevel.FULL,
        )

        loaded = manager.get_permission(
            permission.id
        )

        self.assertEqual(
            loaded,
            permission,
        )

    def test_list_permissions(self):
        workspace = Workspace()
        manager = PermissionManager(workspace)

        manager.create_permission(
            "admin",
            PermissionLevel.FULL,
        )

        manager.create_permission(
            "viewer",
            PermissionLevel.READ,
        )

        self.assertEqual(
            len(manager.list_permissions()),
            2,
        )

    def test_delete_permission(self):
        workspace = Workspace()
        manager = PermissionManager(workspace)

        permission = manager.create_permission(
            "admin",
            PermissionLevel.FULL,
        )

        self.assertTrue(
            manager.delete_permission(
                permission.id
            )
        )

        self.assertEqual(
            len(manager.list_permissions()),
            0,
        )


if __name__ == "__main__":
    unittest.main()