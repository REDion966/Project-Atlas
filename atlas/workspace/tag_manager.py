"""
Atlas Tag Manager

Handles workspace tags.
"""

from __future__ import annotations

from atlas.workspace.models.tag import Tag
from atlas.workspace.models.workspace import Workspace


class TagManager:
    """Manage workspace tags."""

    def __init__(
        self,
        workspace: Workspace,
    ) -> None:
        self.workspace = workspace

    def create_tag(
        self,
        name: str,
        color: str = "#4F46E5",
    ) -> Tag:
        """Create a tag."""

        tag = Tag(
            name=name,
            color=color,
        )

        self.workspace.tags.append(tag)
        self.workspace.touch()

        return tag

    def get_tag(
        self,
        tag_id: str,
    ) -> Tag | None:
        """Return a tag."""

        for tag in self.workspace.tags:
            if tag.id == tag_id:
                return tag

        return None

    def list_tags(
        self,
    ) -> list[Tag]:
        """Return all tags."""

        return self.workspace.tags.copy()

    def delete_tag(
        self,
        tag_id: str,
    ) -> bool:
        """Delete a tag."""

        tag = self.get_tag(tag_id)

        if tag is None:
            return False

        self.workspace.tags.remove(tag)
        self.workspace.touch()

        return True