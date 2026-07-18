from atlas.workspace.workspace_service import WorkspaceService


def test_workspace_creation():

    service = WorkspaceService()

    workspace = service.create_workspace(
        "Atlas Development"
    )

    assert workspace.name == "Atlas Development"