"""
Atlas Memory Model

Represents a single memory item stored by Atlas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from atlas.memory.enums import MemoryImportance, MemoryType


def utc_now() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class Memory:
    """Represents a memory record."""

    id: str
    title: str
    content: str

    memory_type: MemoryType = MemoryType.GENERAL
    importance: MemoryImportance = MemoryImportance.NORMAL

    tags: list[str] = field(default_factory=list)

    source: str = "user"

    created_at: str = field(default_factory=utc_now)

    updated_at: str = field(default_factory=utc_now)

    def touch(self) -> None:
        """Update the modification timestamp."""
        self.updated_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        """Convert the memory to a dictionary."""

        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "importance": self.importance.value,
            "tags": self.tags,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Memory":
        """Create a Memory instance from a dictionary."""

        return cls(
            id=data["id"],
            title=data["title"],
            content=data["content"],
            memory_type=MemoryType(
                data.get(
                    "memory_type",
                    MemoryType.GENERAL.value,
                )
            ),
            importance=MemoryImportance(
                data.get(
                    "importance",
                    MemoryImportance.NORMAL.value,
                )
            ),
            tags=data.get("tags", []),
            source=data.get("source", "user"),
            created_at=data.get(
                "created_at",
                utc_now(),
            ),
            updated_at=data.get(
                "updated_at",
                utc_now(),
            ),
        )