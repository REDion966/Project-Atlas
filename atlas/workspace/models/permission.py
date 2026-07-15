"""
Atlas Permission
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import uuid

from atlas.workspace.enums import PermissionLevel


@dataclass(slots=True)
class Permission:
    """Represents a project permission."""

    id: str = field(
        default_factory=lambda: str(uuid.uuid4())
    )

    name: str = ""

    level: PermissionLevel = PermissionLevel.READ

    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    updated_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    def change_level(
        self,
        level: PermissionLevel,
    ) -> None:
        """Change permission level."""

        self.level = level
        self.touch()

    def touch(self) -> None:
        """Update timestamp."""

        self.updated_at = datetime.now(UTC)

    def to_dict(self) -> dict:
        """Serialize permission."""

        return {
            "id": self.id,
            "name": self.name,
            "level": self.level.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> "Permission":
        """Deserialize permission."""

        return cls(
            id=data["id"],
            name=data["name"],
            level=PermissionLevel(
                data["level"]
            ),
            created_at=datetime.fromisoformat(
                data["created_at"]
            ),
            updated_at=datetime.fromisoformat(
                data["updated_at"]
            ),
        )