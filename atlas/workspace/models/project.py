"""
Atlas Project

Represents a project inside an Atlas workspace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import uuid
from atlas.workspace.models.resource import Resource


@dataclass(slots=True)
class Project:
    """Represents an Atlas project."""

    id: str = field(
        default_factory=lambda: str(uuid.uuid4())
    )

    name: str = ""

    description: str = ""

    tags: list[str] = field(
        default_factory=list
    )

    resources: list[Resource] = field(
        default_factory=list
    )

    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    updated_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    archived: bool = False

    def rename(self, name: str) -> None:
        """Rename the project."""

        self.name = name
        self.touch()

    def archive(self) -> None:
        """Archive the project."""

        self.archived = True
        self.touch()

    def restore(self) -> None:
        """Restore the project."""

        self.archived = False
        self.touch()

    def touch(self) -> None:
        """Update the modification timestamp."""

        self.updated_at = datetime.now(UTC)

    def to_dict(self) -> dict:
        """Convert the project into a dictionary."""

        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "resources": [
                resource.to_dict()
                for resource in self.resources
            ],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "archived": self.archived,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> "Project":
        """Create a Project from a dictionary."""

        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            tags=data.get("tags", []),
            resources=[
                Resource.from_dict(resource)
                for resource in data.get(
                    "resources",
                    [],
                )
            ],
            created_at=datetime.fromisoformat(
                data["created_at"]
            ),
            updated_at=datetime.fromisoformat(
                data["updated_at"]
            ),
            archived=data.get(
                "archived",
                False,
            ),
        )