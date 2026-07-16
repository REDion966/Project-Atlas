"""
Atlas Tag Manager

High-level interface for managing project tags.
"""

from __future__ import annotations

from atlas.workspace.models.project import Project


class TagManager:
    """Manages project tags."""

    def __init__(
        self,
        project: Project,
    ) -> None:
        self._project = project

    def create_tag(
        self,
        tag: str,
    ) -> None:
        """Create a tag."""

        if tag not in self._project.tags:
            self._project.tags.append(tag)
            self._project.touch()

    def delete_tag(
        self,
        tag: str,
    ) -> bool:
        """Delete a tag."""

        if tag in self._project.tags:
            self._project.tags.remove(tag)
            self._project.touch()
            return True

        return False

    def list_tags(
        self,
    ) -> list[str]:
        """Return all tags."""

        return self._project.tags.copy()

    def has_tag(
        self,
        tag: str,
    ) -> bool:
        """Return whether a tag exists."""

        return tag in self._project.tags