"""Atlas Toolchain — Skill Registry (Phase 18.3).

Manages the lifecycle of registered :class:`Skill` objects. Pure data
management with no infrastructure dependencies — mirrors the
:class:`~atlas.tools.registry.ToolRegistry` contract so the two registries
compose without coupling.

The registry is additive-only: registering a new skill never modifies an
existing one (duplicate ``skill_id`` raises ``ValueError``). Deprecation
is a status transition, not a deletion, preserving audit history.
"""

from __future__ import annotations

from atlas.toolchain.models import Skill, SkillKind, SkillStatus


class SkillRegistry:
    """Manages the lifecycle of registered skills.

    This is a pure data-management component with no infrastructure
    dependencies. It does not call AI providers, access memory, query
    knowledge, or interact with the EventBus. It does not execute tools
    or tool chains — it only stores and retrieves :class:`Skill` metadata.
    """

    def __init__(self) -> None:
        """Initialise an empty skill registry."""
        self._skills: dict[str, Skill] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, skill: Skill) -> None:
        """Add a skill to the registry.

        Args:
            skill: The :class:`Skill` instance to register.

        Raises:
            ValueError: If a skill with the same ``skill_id`` is already
                registered.
        """
        if skill.skill_id in self._skills:
            raise ValueError(
                f"Skill '{skill.skill_id}' is already registered."
            )
        self._skills[skill.skill_id] = skill

    def unregister(self, skill_id: str) -> None:
        """Remove a skill from the registry by id.

        Args:
            skill_id: The id of the skill to remove.

        Raises:
            KeyError: If no skill with the given id is registered.
        """
        if skill_id not in self._skills:
            raise KeyError(
                f"Skill '{skill_id}' is not registered."
            )
        del self._skills[skill_id]

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, skill_id: str) -> Skill | None:
        """Look up a skill by id.

        Args:
            skill_id: The id of the skill to retrieve.

        Returns:
            The :class:`Skill` instance if found, or ``None``.
        """
        return self._skills.get(skill_id)

    def get_by_name(self, name: str) -> Skill | None:
        """Look up a skill by its human-readable name.

        If multiple skills share the same name, the first one encountered
        (insertion order) is returned.

        Args:
            name: The human-readable name to search for.

        Returns:
            The first matching :class:`Skill`, or ``None``.
        """
        for skill in self._skills.values():
            if skill.name == name:
                return skill
        return None

    # ------------------------------------------------------------------
    # Listing / filtering
    # ------------------------------------------------------------------

    def list(self) -> list[Skill]:
        """Return all registered skills sorted by id.

        Returns:
            A list of all registered :class:`Skill` instances.
        """
        return sorted(self._skills.values(), key=lambda s: s.skill_id)

    def list_active(self) -> list[Skill]:
        """Return all active skills sorted by id.

        Returns:
            A list of :class:`Skill` instances with ``status == ACTIVE``.
        """
        return sorted(
            (s for s in self._skills.values() if s.is_active),
            key=lambda s: s.skill_id,
        )

    def find_by_category(self, category: str) -> list[Skill]:
        """Filter skills by category.

        Args:
            category: The category to filter by.

        Returns:
            A list of matching :class:`Skill` instances sorted by id.
        """
        return sorted(
            (s for s in self._skills.values() if s.category == category),
            key=lambda s: s.skill_id,
        )

    def find_by_tag(self, tag: str) -> list[Skill]:
        """Filter skills by tag.

        Args:
            tag: The tag to filter by.

        Returns:
            A list of :class:`Skill` instances that have the given tag,
            sorted by id.
        """
        return sorted(
            (s for s in self._skills.values() if tag in s.tags),
            key=lambda s: s.skill_id,
        )

    def find_by_kind(self, kind: SkillKind) -> list[Skill]:
        """Filter skills by kind.

        Args:
            kind: The :class:`SkillKind` to filter by.

        Returns:
            A list of matching :class:`Skill` instances sorted by id.
        """
        return sorted(
            (s for s in self._skills.values() if s.kind == kind),
            key=lambda s: s.skill_id,
        )

    def find_by_tool(self, tool_name: str) -> list[Skill]:
        """Find skills that wrap a given tool (BUILTIN) or reference it in
        their chain (COMPOSED/LEARNED).

        Args:
            tool_name: The tool name to search for.

        Returns:
            A list of matching :class:`Skill` instances sorted by id.
        """
        results: list[Skill] = []
        for skill in self._skills.values():
            if skill.is_builtin and skill.tool_name == tool_name:
                results.append(skill)
            elif skill.chain is not None and tool_name in skill.chain.tool_names:
                results.append(skill)
        return sorted(results, key=lambda s: s.skill_id)

    # ------------------------------------------------------------------
    # Status transitions (additive — never delete)
    # ------------------------------------------------------------------

    def activate(self, skill_id: str) -> Skill:
        """Transition a skill to ACTIVE status.

        Returns a *new* :class:`Skill` instance with the updated status
        (skills are frozen). The registry replaces the old entry.

        Args:
            skill_id: The id of the skill to activate.

        Raises:
            KeyError: If the skill is not registered.

        Returns:
            The newly activated :class:`Skill` instance.
        """
        existing = self._require(skill_id)
        if existing.status == SkillStatus.ACTIVE:
            return existing
        updated = _with_status(existing, SkillStatus.ACTIVE)
        self._skills[skill_id] = updated
        return updated

    def deactivate(self, skill_id: str) -> Skill:
        """Transition a skill to DEPRECATED status.

        Args:
            skill_id: The id of the skill to deactivate.

        Raises:
            KeyError: If the skill is not registered.

        Returns:
            The newly deprecated :class:`Skill` instance.
        """
        existing = self._require(skill_id)
        if existing.status == SkillStatus.DEPRECATED:
            return existing
        updated = _with_status(existing, SkillStatus.DEPRECATED)
        self._skills[skill_id] = updated
        return updated

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def count(self) -> int:
        """Number of registered skills."""
        return len(self._skills)

    @property
    def active_count(self) -> int:
        """Number of active skills."""
        return sum(1 for s in self._skills.values() if s.is_active)

    @property
    def skill_ids(self) -> list[str]:
        """Sorted list of registered skill ids."""
        return sorted(self._skills.keys())

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Remove all registered skills."""
        self._skills.clear()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require(self, skill_id: str) -> Skill:
        """Return the skill or raise KeyError."""
        skill = self._skills.get(skill_id)
        if skill is None:
            raise KeyError(f"Skill '{skill_id}' is not registered.")
        return skill


# ---------------------------------------------------------------------------
# Helpers (frozen-dataclass status transition)
# ---------------------------------------------------------------------------


def _with_status(skill: Skill, status: SkillStatus) -> Skill:
    """Return a copy of ``skill`` with a new ``status``.

    Skills are frozen dataclasses; this helper performs a non-mutating
    status transition by reconstructing the dataclass with all original
    fields except ``status``.
    """
    return Skill(
        skill_id=skill.skill_id,
        name=skill.name,
        description=skill.description,
        kind=skill.kind,
        category=skill.category,
        tool_name=skill.tool_name,
        chain=skill.chain,
        tags=skill.tags,
        status=status,
        created_at=skill.created_at,
        metadata=skill.metadata,
    )