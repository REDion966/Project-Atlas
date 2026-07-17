"""
Atlas Tag

Represents a workspace tag.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import uuid


@dataclass(slots=True)
class Tag:
    """Represents a workspace tag."""

    id: str = field(
        default_factory=lambda: str(uuid.uuid4())
    )

    name: str = ""

    color: str = "#4F46E5"

    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    updated_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    def rename(
        self,
        name: str,
    ) -> None:
        """Rename the tag."""

        self.name = name
        self.touch()

    def set_color(
        self,
        color: str,
    ) -> None:
        """Update tag color."""

        self.color = color
        self.touch()

    def touch(
        self,
    ) -> None:
        """Update modification timestamp."""

        self.updated_at = datetime.now(UTC)

    def to_dict(
        self,
    ) -> dict:
        """Serialize tag."""

        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> "Tag":
        """Deserialize tag."""

        return cls(
            id=data["id"],
            name=data["name"],
            color=data.get(
                "color",
                "#4F46E5",
            ),
            created_at=datetime.fromisoformat(
                data["created_at"]
            ),
            updated_at=datetime.fromisoformat(
                data["updated_at"]
            ),
        )