"""
Atlas Resource Manager

High-level interface for managing resources.
"""

from __future__ import annotations

from atlas.workspace.enums import ResourceType
from atlas.workspace.models.project import Project
from atlas.workspace.models.resource import Resource


class ResourceManager:
    """Manages resources inside a project."""

    def __init__(
        self,
        project: Project,
    ) -> None:
        self._project = project

    def create_resource(
        self,
        name: str,
        resource_type: ResourceType = ResourceType.FILE,
        path: str = "",
        description: str = "",
    ) -> Resource:
        """Create a new resource."""

        resource = Resource(
            name=name,
            resource_type=resource_type,
            path=path,
            description=description,
        )

        self._project.resources.append(resource)
        self._project.touch()

        return resource

    def get_resource(
        self,
        resource_id: str,
    ) -> Resource | None:
        """Return a resource."""

        for resource in self._project.resources:
            if resource.id == resource_id:
                return resource

        return None

    def list_resources(
        self,
    ) -> list[Resource]:
        """Return all resources."""

        return self._project.resources.copy()

    def delete_resource(
        self,
        resource_id: str,
    ) -> bool:
        """Delete a resource."""

        for resource in self._project.resources:
            if resource.id == resource_id:
                self._project.resources.remove(resource)
                self._project.touch()
                return True

        return False