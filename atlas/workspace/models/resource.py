"""
Atlas Resource

Represents a resource attached to a project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import uuid

from atlas.workspace.enums import ResourceType


@dataclass(slots=True)
class Resource:
    """Represents a project resource."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    name: str = ""

    path: str = ""

    type: ResourceType = ResourceType.FILE

    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    updated_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    def exists(self) -> bool:
        """Return True if the resource exists."""

        return Path(self.path).exists()

    def rename(self, name: str) -> None:
        """Rename the resource."""

        self.name = name
        self.touch()

    def touch(self) -> None:
        """Update modification time."""

        self.updated_at = datetime.now(UTC)

    def to_dict(self) -> dict:
        """Serialize resource."""

        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "type": self.type.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Resource":
        """Deserialize resource."""

        return cls(
            id=data["id"],
            name=data["name"],
            path=data["path"],
            type=ResourceType(data["type"]),
            created_at=datetime.fromisoformat(
                data["created_at"]
            ),
            updated_at=datetime.fromisoformat(
                data["updated_at"]
            ),
        )