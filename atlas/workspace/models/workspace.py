"""
Atlas Workspace

Represents a workspace containing projects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import uuid

from atlas.workspace.models.project import Project
from atlas.workspace.models.permission import Permission


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

    members: list[Permission] = field(
    default_factory=list
    )

    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    updated_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

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
    
    def list_projects(self) -> list[Project]:
        """Return all projects."""

        return self.projects.copy()

    def touch(self) -> None:
        """Update modification time."""

        self.updated_at = datetime.now(UTC)

    def to_dict(self) -> dict:
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
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
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
                for project in data["projects"]
            ],
            members=[
                Permission.from_dict(member)
                for member in data.get("members", [])
            ],
            created_at=datetime.fromisoformat(
                data["created_at"]
            ),
            updated_at=datetime.fromisoformat(
                data["updated_at"]
            ),
        )