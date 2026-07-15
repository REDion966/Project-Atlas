import tempfile
import unittest
from pathlib import Path

from atlas.workspace.models.resource import Resource


class TestResource(unittest.TestCase):

    def test_create_resource(self):
        resource = Resource(name="README")

        self.assertEqual(resource.name, "README")

    def test_rename_resource(self):
        resource = Resource(name="Old")

        resource.rename("New")

        self.assertEqual(resource.name, "New")

    def test_exists(self):
        with tempfile.NamedTemporaryFile() as file:
            resource = Resource(path=file.name)

            self.assertTrue(resource.exists())

    def test_not_exists(self):
        resource = Resource(path="not_existing_file.txt")

        self.assertFalse(resource.exists())

    def test_to_dict(self):
        resource = Resource(name="Atlas")

        data = resource.to_dict()

        self.assertEqual(data["name"], "Atlas")

    def test_from_dict(self):
        resource = Resource(name="Atlas")

        loaded = Resource.from_dict(
            resource.to_dict()
        )

        self.assertEqual(
            loaded.name,
            resource.name,
        )

        self.assertEqual(
            loaded.id,
            resource.id,
        )


if __name__ == "__main__":
    unittest.main()