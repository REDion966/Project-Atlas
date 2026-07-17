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

    def test_metadata_to_dict(self):
        workspace = Workspace(
            name="Test",
            description="A test workspace",
            owner="alice",
            created_by="bob",
        )

        data = workspace.to_dict()

        self.assertEqual(
            data["description"],
            "A test workspace",
        )

        self.assertEqual(
            data["owner"],
            "alice",
        )

        self.assertEqual(
            data["created_by"],
            "bob",
        )

        self.assertIn(
            "last_opened_at",
            data,
        )

    def test_metadata_from_dict(self):
        workspace = Workspace(
            name="Test",
            description="A test workspace",
            owner="alice",
            created_by="bob",
        )

        loaded = Workspace.from_dict(
            workspace.to_dict()
        )

        self.assertEqual(
            loaded.description,
            "A test workspace",
        )

        self.assertEqual(
            loaded.owner,
            "alice",
        )

        self.assertEqual(
            loaded.created_by,
            "bob",
        )

        self.assertEqual(
            loaded.last_opened_at,
            workspace.last_opened_at,
        )

    def test_metadata_backwards_compat(self):
        workspace = Workspace(
            name="Legacy",
        )

        data = workspace.to_dict()

        del data["description"]
        del data["owner"]
        del data["created_by"]
        del data["last_opened_at"]

        loaded = Workspace.from_dict(data)

        self.assertEqual(
            loaded.description,
            "",
        )

        self.assertEqual(
            loaded.owner,
            "",
        )

        self.assertEqual(
            loaded.created_by,
            "",
        )

        self.assertEqual(
            loaded.last_opened_at,
            loaded.updated_at,
        )

    def test_rename(self):
        workspace = Workspace(name="Old")

        workspace.rename("New")

        self.assertEqual(
            workspace.name,
            "New",
        )

    def test_archive(self):
        workspace = Workspace()

        self.assertFalse(
            workspace.archived,
        )

        workspace.archive()

        self.assertTrue(
            workspace.archived,
        )

    def test_restore(self):
        workspace = Workspace()

        workspace.archive()

        self.assertTrue(
            workspace.archived,
        )

        workspace.restore()

        self.assertFalse(
            workspace.archived,
        )

    def test_rename_updates_timestamp(self):
        workspace = Workspace(name="Old")

        original_updated = workspace.updated_at

        workspace.rename("New")

        self.assertGreater(
            workspace.updated_at,
            original_updated,
        )

    def test_archive_updates_timestamp(self):
        workspace = Workspace()

        original_updated = workspace.updated_at

        workspace.archive()

        self.assertGreater(
            workspace.updated_at,
            original_updated,
        )

    def test_restore_updates_timestamp(self):
        workspace = Workspace()

        workspace.archive()

        original_updated = workspace.updated_at

        workspace.restore()

        self.assertGreater(
            workspace.updated_at,
            original_updated,
        )

    def test_archived_in_to_dict(self):
        workspace = Workspace()

        workspace.archive()

        data = workspace.to_dict()

        self.assertTrue(
            data["archived"],
        )

    def test_archived_from_dict(self):
        workspace = Workspace()

        workspace.archive()

        loaded = Workspace.from_dict(
            workspace.to_dict()
        )

        self.assertTrue(
            loaded.archived,
        )

    def test_archived_backwards_compat(self):
        workspace = Workspace()

        data = workspace.to_dict()

        del data["archived"]

        loaded = Workspace.from_dict(data)

        self.assertFalse(
            loaded.archived,
        )


if __name__ == "__main__":
    unittest.main()
