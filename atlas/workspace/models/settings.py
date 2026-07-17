"""
Atlas WorkspaceSettings

Represents workspace configuration settings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class WorkspaceSettings:
    """Represents workspace configuration settings."""

    version: str = "1.0"

    autosave: bool = True

    default_project_id: str = ""

    ai_provider: str = ""

    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    updated_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    def touch(
        self,
    ) -> None:
        """Update modification timestamp."""

        self.updated_at = datetime.now(UTC)

    def to_dict(
        self,
    ) -> dict:
        """Serialize settings."""

        return {
            "version": self.version,
            "autosave": self.autosave,
            "default_project_id": self.default_project_id,
            "ai_provider": self.ai_provider,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> "WorkspaceSettings":
        """Deserialize settings."""

        return cls(
            version=data.get(
                "version",
                "1.0",
            ),
            autosave=data.get(
                "autosave",
                True,
            ),
            default_project_id=data.get(
                "default_project_id",
                "",
            ),
            ai_provider=data.get(
                "ai_provider",
                "",
            ),
            created_at=datetime.fromisoformat(
                data["created_at"]
            ),
            updated_at=datetime.fromisoformat(
                data["updated_at"]
            ),
        )
