"""
Atlas Lifecycle — Component Registry.

Observation-only registry of Atlas components. Tracks what components
exist, where they live, their dependencies, capabilities, and health
state.

This registry NEVER modifies components, restarts services, repairs
failures, or triggers evolution. It is purely observational.

Phase 13.2 — Self Model Expansion.
"""

from datetime import datetime

from atlas.lifecycle.models import ComponentMetadata, ComponentStatus


class ComponentRegistry:
    """
    Observation-only registry of Atlas components.

    Provides:
      - Registration of component metadata
      - Querying by name, package, or capability
      - Status observation (read-only over component lifecycle)
      - Capability-to-component mapping

    This registry has no knowledge of how to start, stop, modify, or
    repair components. It only records what it is told.
    """

    def __init__(self) -> None:
        self._components: dict[str, ComponentMetadata] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, metadata: ComponentMetadata) -> None:
        """Register a component's metadata.

        Args:
            metadata: The ComponentMetadata to register.

        Raises:
            ValueError: If a component with the same name is already
                registered.
        """
        if metadata.name in self._components:
            raise ValueError(
                f"Component '{metadata.name}' is already registered."
            )
        self._components[metadata.name] = metadata

    def register_or_update(self, metadata: ComponentMetadata) -> None:
        """Register or update component metadata.

        Unlike register(), this method silently updates an existing
        registration rather than raising. Useful for runtime status
        corrections where the component identity is known.

        Args:
            metadata: The ComponentMetadata to register or update.
        """
        self._components[metadata.name] = metadata

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get(self, name: str) -> ComponentMetadata | None:
        """Look up a component by name.

        Args:
            name: The component name (e.g. "memory_service").

        Returns:
            The ComponentMetadata, or None if not found.
        """
        return self._components.get(name)

    def get_all(self) -> list[ComponentMetadata]:
        """Return metadata for all registered components.

        Returns:
            A list of ComponentMetadata instances, sorted by name.
        """
        return sorted(
            self._components.values(),
            key=lambda c: c.name,
        )

    def get_by_package(self, package: str) -> list[ComponentMetadata]:
        """Return all components that belong to a given package.

        Args:
            package: The package path (e.g. "atlas.memory").

        Returns:
            A list of matching ComponentMetadata instances, sorted by name.
        """
        return sorted(
            [c for c in self._components.values() if c.package == package],
            key=lambda c: c.name,
        )

    def get_by_capability(self, capability: str) -> list[ComponentMetadata]:
        """Return all components that provide a given capability.

        Args:
            capability: The capability string (e.g. "memory_search").

        Returns:
            A list of matching ComponentMetadata instances, sorted by name.
        """
        return sorted(
            [
                c for c in self._components.values()
                if capability in c.provided_capabilities
            ],
            key=lambda c: c.name,
        )

    def get_by_status(self, status: ComponentStatus) -> list[ComponentMetadata]:
        """Return all components with a given status.

        Args:
            status: The ComponentStatus to filter by.

        Returns:
            A list of matching ComponentMetadata instances, sorted by name.
        """
        return sorted(
            [c for c in self._components.values() if c.status == status],
            key=lambda c: c.name,
        )

    # ------------------------------------------------------------------
    # Status observation
    # ------------------------------------------------------------------

    def update_status(
        self,
        name: str,
        status: ComponentStatus,
    ) -> bool:
        """Update the health status of a registered component.

        Because ComponentMetadata is frozen, this creates a replacement
        record with the new status and updated timestamp.

        Args:
            name: The component name.
            status: The new ComponentStatus.

        Returns:
            True if the component was found and updated. False if no
            component with that name is registered.
        """
        existing = self._components.get(name)
        if existing is None:
            return False

        updated = ComponentMetadata(
            name=existing.name,
            package=existing.package,
            module_path=existing.module_path,
            description=existing.description,
            version=existing.version,
            status=status,
            dependencies=existing.dependencies,
            provided_capabilities=existing.provided_capabilities,
            registered_at=existing.registered_at,
            last_health_check=datetime.now(),
        )
        self._components[name] = updated
        return True

    # ------------------------------------------------------------------
    # Capability mapping
    # ------------------------------------------------------------------

    def get_capability_map(self) -> dict[str, list[str]]:
        """Return a mapping of capability → list of component names.

        Returns:
            A dict where keys are capability strings and values are
            lists of component names that provide that capability.
        """
        mapping: dict[str, list[str]] = {}
        for component in self._components.values():
            for capability in component.provided_capabilities:
                if capability not in mapping:
                    mapping[capability] = []
                mapping[capability].append(component.name)
        return mapping

    def get_all_component_names(self) -> list[str]:
        """Return sorted list of all registered component names."""
        return sorted(self._components.keys())

    def get_all_capabilities(self) -> list[str]:
        """Return sorted list of all unique capabilities across components."""
        capabilities: set[str] = set()
        for component in self._components.values():
            capabilities.update(component.provided_capabilities)
        return sorted(capabilities)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def component_count(self) -> int:
        """Return the number of registered components."""
        return len(self._components)

    def clear(self) -> None:
        """Remove all registered components.

        Useful primarily for testing. Does not affect the components
        themselves — only removes their metadata from this registry.
        """
        self._components.clear()

    def summary(self) -> dict:
        """Return a human-readable summary of the registry state.

        Returns:
            A dict with component_count, status counts, and
            capability_count.
        """
        statuses = {
            status: len(self.get_by_status(status))
            for status in ComponentStatus
        }
        return {
            "component_count": self.component_count,
            "status_counts": statuses,
            "capability_count": len(self.get_all_capabilities()),
            "total_dependencies": sum(
                len(c.dependencies) for c in self._components.values()
            ),
        }
