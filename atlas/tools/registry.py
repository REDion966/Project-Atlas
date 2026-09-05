"""
Atlas Tool Registry

Manages the lifecycle of registered tools.
Pure data management with no infrastructure dependencies.

Phase 6.9 — Tool Intelligence Foundation.
"""

from __future__ import annotations

from atlas.tools.models import Tool


class ToolRegistry:
    """
    Manages the lifecycle of registered tools.

    This is a pure data management component with no infrastructure
    dependencies. It does not call AI providers, access memory, query
    knowledge, or interact with the EventBus.
    """

    def __init__(self) -> None:
        """Initialise an empty tool registry."""
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """
        Add a tool to the registry.

        Args:
            tool: The Tool instance to register.

        Raises:
            ValueError: If a tool with the same name is already
                registered.
        """
        if tool.name in self._tools:
            raise ValueError(
                f"Tool '{tool.name}' is already registered."
            )
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """
        Remove a tool from the registry by name.

        Args:
            name: The name of the tool to remove.

        Raises:
            KeyError: If no tool with the given name is registered.
        """
        if name not in self._tools:
            raise KeyError(
                f"Tool '{name}' is not registered."
            )
        del self._tools[name]

    def get(self, name: str) -> Tool | None:
        """
        Look up a tool by name.

        Args:
            name: The name of the tool to retrieve.

        Returns:
            The Tool instance if found, or None if not registered.
        """
        return self._tools.get(name)

    def list(self) -> list[Tool]:
        """
        Return all registered tools.

        Returns:
            A list of all registered Tool instances, sorted by name.
        """
        return sorted(self._tools.values(), key=lambda t: t.name)

    def find_by_category(self, category: str) -> list[Tool]:
        """
        Filter tools by category.

        Args:
            category: The category to filter by.

        Returns:
            A list of Tool instances matching the category, sorted by
            name.
        """
        return sorted(
            (t for t in self._tools.values() if t.category == category),
            key=lambda t: t.name,
        )

    def find_by_tag(self, tag: str) -> list[Tool]:
        """
        Filter tools by tag.

        Args:
            tag: The tag to filter by.

        Returns:
            A list of Tool instances that have the given tag, sorted
            by name.
        """
        return sorted(
            (t for t in self._tools.values() if tag in t.tags),
            key=lambda t: t.name,
        )

    @property
    def count(self) -> int:
        """
        Return the number of registered tools.

        Returns:
            The count of registered tools.
        """
        return len(self._tools)

    def clear(self) -> None:
        """Remove all registered tools."""
        self._tools.clear()