import unittest

from atlas.workspace.enums import PermissionLevel
from atlas.workspace.models.permission import Permission


class TestPermission(unittest.TestCase):

    def test_create_permission(self):
        permission = Permission(name="Filesystem")

        self.assertEqual(
            permission.level,
            PermissionLevel.READ,
        )

    def test_change_permission(self):
        permission = Permission()

        permission.change_level(
            PermissionLevel.FULL
        )

        self.assertEqual(
            permission.level,
            PermissionLevel.FULL,
        )

    def test_to_dict(self):
        permission = Permission(
            name="Filesystem"
        )

        data = permission.to_dict()

        self.assertEqual(
            data["name"],
            "Filesystem",
        )

    def test_from_dict(self):
        permission = Permission(
            name="Filesystem"
        )

        loaded = Permission.from_dict(
            permission.to_dict()
        )

        self.assertEqual(
            loaded.id,
            permission.id,
        )

        self.assertEqual(
            loaded.level,
            permission.level,
        )


if __name__ == "__main__":
    unittest.main()