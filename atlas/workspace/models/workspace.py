"""
Atlas Workspace

Represents a workspace containing projects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import uuid

from atlas.workspace.models.member import Member
from atlas.workspace.models.project import Project
from atlas.workspace.models.settings import WorkspaceSettings
from atlas.workspace.models.tag import Tag


@dataclass(slots=True)
class Workspace:
    """Represents an Atlas workspace."""

    id: str = field(
        default_factory=lambda: str(uuid.uuid4())
    )

    name: str = "Default Workspace"

    projects: list[Project] = field(
        default_factory=list
    )

    members: list[Member] = field(
        default_factory=list
    )

    description: str = ""

    owner: str = ""

    created_by: str = ""

    tags: list[Tag] = field(
        default_factory=list
    )

    settings: WorkspaceSettings = field(
        default_factory=WorkspaceSettings,
    )

    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    updated_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    last_opened_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    archived: bool = False

    def rename(
        self,
        name: str,
    ) -> None:
        """Rename the workspace."""

        self.name = name
        self.touch()

    def archive(
        self,
    ) -> None:
        """Archive the workspace."""

        self.archived = True
        self.touch()

    def restore(
        self,
    ) -> None:
        """Restore the workspace."""

        self.archived = False
        self.touch()

    def add_project(
        self,
        project: Project,
    ) -> None:
        """Add a project."""

        self.projects.append(project)
        self.touch()

    def remove_project(
        self,
        project_id: str,
    ) -> bool:
        """Remove a project."""

        for project in self.projects:
            if project.id == project_id:
                self.projects.remove(project)
                self.touch()
                return True

        return False

    def get_project(
        self,
        project_id: str,
    ) -> Project | None:
        """Return a project."""

        for project in self.projects:
            if project.id == project_id:
                return project

        return None

    def list_projects(
        self,
    ) -> list[Project]:
        """Return all projects."""

        return self.projects.copy()

    def touch(
        self,
    ) -> None:
        """Update modification time."""

        self.updated_at = datetime.now(UTC)

    def to_dict(
        self,
    ) -> dict:
        """Serialize workspace."""

        return {
            "id": self.id,
            "name": self.name,
            "projects": [
                project.to_dict()
                for project in self.projects
            ],
            "members": [
                member.to_dict()
                for member in self.members
            ],
            "description": self.description,
            "owner": self.owner,
            "created_by": self.created_by,
            "tags": [
                tag.to_dict()
                for tag in self.tags
            ],
            "settings": self.settings.to_dict(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_opened_at": self.last_opened_at.isoformat(),
            "archived": self.archived,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> "Workspace":
        """Deserialize workspace."""

        return cls(
            id=data["id"],
            name=data["name"],
            projects=[
                Project.from_dict(project)
                for project in data.get(
                    "projects",
                    [],
                )
            ],
            members=[
                Member.from_dict(member)
                for member in data.get(
                    "members",
                    [],
                )
            ],
            description=data.get(
                "description",
                "",
            ),
            owner=data.get(
                "owner",
                "",
            ),
            created_by=data.get(
                "created_by",
                "",
            ),
            tags=[
                Tag.from_dict(tag)
                for tag in data.get(
                    "tags",
                    [],
                )
            ],
            settings=WorkspaceSettings.from_dict(
                data.get("settings", {})
            ),
            created_at=datetime.fromisoformat(
                data["created_at"]
            ),
            updated_at=datetime.fromisoformat(
                data["updated_at"]
            ),
            last_opened_at=datetime.fromisoformat(
                data.get(
                    "last_opened_at",
                    data["updated_at"],
                )
            ),
            archived=data.get(
                "archived",
                False,
            ),
        )
