"""
Atlas Member

Represents a workspace member.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import uuid


@dataclass(slots=True)
class Member:
    """Represents a workspace member."""

    id: str = field(
        default_factory=lambda: str(uuid.uuid4())
    )

    name: str = ""

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
        """Rename the member."""

        self.name = name
        self.touch()

    def touch(
        self,
    ) -> None:
        """Update modification timestamp."""

        self.updated_at = datetime.now(UTC)

    def to_dict(
        self,
    ) -> dict:
        """Serialize the member."""

        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> "Member":
        """Deserialize the member."""

        return cls(
            id=data["id"],
            name=data["name"],
            created_at=datetime.fromisoformat(
                data["created_at"]
            ),
            updated_at=datetime.fromisoformat(
                data["updated_at"]
            ),
        )