"""
Tests for Atlas CLI commands.
"""

from __future__ import annotations

from sys import stdout
import unittest
from io import StringIO
from unittest.mock import patch

from atlas.cli.commands import (
    project_create,
    resource_add,
    resource_list,
    resource_remove,
    workspace_create,
)
from atlas.services import service
from atlas.workspace.workspace_service import WorkspaceService


class TestCLICommands(unittest.TestCase):
    """Tests for CLI command functions."""

    @patch("atlas.cli.commands.DEFAULT_WORKSPACE")
    @patch("sys.stdout", new_callable=StringIO)
    def test_workspace_create(
        self,
        stdout: StringIO,
        workspace_path,
    ) -> None:
        workspace_path.exists.return_value = False

        service = WorkspaceService()

        workspace_create(
            service,
            "Atlas",
        )

        output = stdout.getvalue()

        self.assertIn(
            "Workspace 'Atlas' created.",
            output,
        )

    @patch("atlas.cli.commands.DEFAULT_WORKSPACE")
    @patch("sys.stdout", new_callable=StringIO)
    def test_workspace_create_existing(
        self,
        stdout: StringIO,
        workspace_path,
    ) -> None:
        workspace_path.exists.return_value = True

        service = WorkspaceService()

        workspace_create(
            service,
            "Atlas",
        )

        output = stdout.getvalue()

        self.assertIn(
            "A workspace already exists.",
            output,
        )

    @patch("atlas.cli.commands.DEFAULT_WORKSPACE")
    @patch("sys.stdout", new_callable=StringIO)
    def test_project_create(
        self,
        stdout: StringIO,
        workspace_path,
    ) -> None:
        workspace_path.exists.return_value = False

        service = WorkspaceService()

        service.create_workspace("Atlas")

        project_create(
            service,
            "Website",
        )

        output = stdout.getvalue()

        self.assertIn(
            "Project 'Website' created.",
            output,
        )

    @patch("atlas.cli.commands.DEFAULT_WORKSPACE")
    @patch("sys.stdout", new_callable=StringIO)
    def test_resource_list(
        self,
        stdout: StringIO,
        workspace_path,
    ) -> None:
        workspace_path.exists.return_value = False

        service = WorkspaceService()

        service.create_workspace("Atlas")
        service.create_project("Project A")

        service.create_resource("README.md")
        service.create_resource("LICENSE")

        resource_list(service)

        output = stdout.getvalue()

        self.assertIn(
            "README.md",
            output,
        )

        self.assertIn(
            "LICENSE",
            output,
        )

    @patch("atlas.cli.commands.DEFAULT_WORKSPACE")
    @patch("sys.stdout", new_callable=StringIO)
    def test_resource_remove(
        self,
        stdout: StringIO,
        workspace_path,
    ) -> None:
        workspace_path.exists.return_value = False

        service = WorkspaceService()

        service.create_workspace("Atlas")
        service.create_project("Project A")

        resource = service.create_resource(
            "README.md"
        )

        resource_remove(
            service,
            resource.id,
        )

        output = stdout.getvalue()

        self.assertIn(
            "Resource removed.",
            output,
        )


if __name__ == "__main__":
    unittest.main()