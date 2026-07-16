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

    id: str = field(
        default_factory=lambda: str(uuid.uuid4())
    )

    name: str = ""

    resource_type: ResourceType = ResourceType.FILE

    path: str = ""

    description: str = ""

    enabled: bool = True

    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    updated_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    def rename(self, name: str) -> None:
        """Rename the resource."""

        self.name = name
        self.touch()

    def disable(self) -> None:
        """Disable the resource."""

        self.enabled = False
        self.touch()

    def enable(self) -> None:
        """Enable the resource."""

        self.enabled = True
        self.touch()

    def touch(self) -> None:
        """Update modification timestamp."""

        self.updated_at = datetime.now(UTC)

    def exists(self) -> bool:
        """Return whether the resource exists."""

        if not self.path:
            return False

        return Path(self.path).exists()

    def to_dict(self) -> dict:
        """Serialize the resource."""

        return {
            "id": self.id,
            "name": self.name,
            "resource_type": self.resource_type.value,
            "path": self.path,
            "description": self.description,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> "Resource":
        """Deserialize the resource."""

        return cls(
            id=data["id"],
            name=data["name"],
            resource_type=ResourceType(
                data["resource_type"]
            ),
            path=data.get("path", ""),
            description=data.get(
                "description",
                "",
            ),
            enabled=data.get(
                "enabled",
                True,
            ),
            created_at=datetime.fromisoformat(
                data["created_at"]
            ),
            updated_at=datetime.fromisoformat(
                data["updated_at"]
            ),
        )