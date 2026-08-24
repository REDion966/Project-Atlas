"""Duck-typed helpers to build ``LifecycleTarget`` descriptors.

These helpers NEVER import concrete registries — they read plain attributes from
duck-typed registry objects so the lifecycle package stays decoupled from
concrete AI/toolchain/evolution packages (matching the F1/F2 seam pattern).
"""

from __future__ import annotations

from atlas.evolution.lifecycle.models import (
    LifecycleTarget,
    LifecycleTargetKind,
)


def target_from_model(profile) -> LifecycleTarget:
    """Build a lifecycle target for an AI model profile.

    Reads plain attributes from a ModelProfile-like object:
    ``provider_name``, ``model_name``, ``metadata`` (dict).
    """
    provider = getattr(profile, "provider_name", "unknown")
    model = getattr(profile, "model_name", "unknown")
    metadata = dict(getattr(profile, "metadata", {}) or {})

    status = str(metadata.get("status", "") or "")
    deprecated = bool(metadata.get("deprecated", False))
    replacement = str(metadata.get("replacement", "") or "")
    available = metadata.get("available")
    if available is not None:
        available = bool(available)
    domains = frozenset({"MODEL", "PROVIDER"})
    deps = frozenset({f"PROVIDER:{provider}"}) if provider else frozenset()

    return LifecycleTarget(
        target_kind=LifecycleTargetKind.MODEL,
        identifier=f"{provider}:{model}",
        status=status,
        available=available,
        deprecated=deprecated,
        replacement=replacement,
        affected_domains=domains,
        dependency_entity_keys=deps,
        knowledge_dependencies=frozenset(),
        metadata=metadata,
    )


def target_from_tool(tool) -> LifecycleTarget:
    """Build a lifecycle target from a Tool-like object."""
    name = getattr(tool, "name", "")
    if not name:
        raise ValueError("tool must carry a 'name' attribute")
    metadata = dict(getattr(tool, "metadata", {}) or {})
    status = str(metadata.get("status", "") or "")
    deprecated = bool(metadata.get("deprecated", False))
    replacement = str(metadata.get("replacement", "") or "")
    available = metadata.get("available", None)
    if available is not None:
        available = bool(available)
    return LifecycleTarget(
        target_kind=LifecycleTargetKind.TOOL,
        identifier=name,
        status=status,
        available=available,
        deprecated=deprecated,
        replacement=replacement,
        affected_domains=frozenset(),
        dependency_entity_keys=frozenset(),
        knowledge_dependencies=frozenset(),
        metadata=metadata,
    )


def target_from_skill(skill) -> LifecycleTarget:
    """Build a lifecycle target from a Skill-like object."""
    skill_id = getattr(skill, "skill_id", "") or str(skill)
    status = getattr(skill, "status", None)
    status_str = status.name if hasattr(status, "name") else str(status or "")
    metadata = dict(getattr(skill, "metadata", {}) or {})
    deprecated = bool(metadata.get("deprecated", False) or status_str.upper() == "DEPRECATED")
    replacement = str(metadata.get("replacement", "") or "")
    return LifecycleTarget(
        target_kind=LifecycleTargetKind.SKILL,
        identifier=skill_id,
        status=status_str,
        deprecated=deprecated,
        replacement=replacement,
        affected_domains=frozenset(),
        dependency_entity_keys=frozenset(),
        knowledge_dependencies=frozenset(),
        metadata=metadata,
    )


def target_from_capability(name: str) -> LifecycleTarget:
    """Build a lifecycle target from a plain capability/subject name."""
    return LifecycleTarget(
        target_kind=LifecycleTargetKind.CAPABILITY,
        identifier=name,
    )


def targets_from_registries(
    model_registry=None,
    tool_registry=None,
    capability_registry=None,
    skill_registry=None,
) -> "list[LifecycleTarget]":
    """Build lifecycle targets from existing registries via duck-typed access.

    Each registry may be ``None`` (skipped). This is a read-only snapshot:
    the lifecycle assessor never mutates the registries.
    """
    targets: list[LifecycleTarget] = []
    if model_registry is not None:
        for profile in _list_profiles(model_registry):
            targets.append(target_from_model(profile))
    if tool_registry is not None:
        for tool in _list_tools(tool_registry):
            targets.append(target_from_tool(tool))
    if capability_registry is not None:
        for name in _registered_names(capability_registry):
            targets.append(target_from_capability(name))
    if skill_registry is not None:
        for skill in _list_skills(skill_registry):
            targets.append(target_from_skill(skill))
    return targets


def _list_profiles(registry):
    """Return profile-like objects from a duck-typed registry, or ()."""
    list_fn = getattr(registry, "list_profiles", None) or getattr(registry, "list", None)
    if list_fn is None:
        return ()
    try:
        return tuple(list_fn())
    except Exception:
        return ()


def _list_tools(registry):
    list_fn = getattr(registry, "list", None)
    if list_fn is None:
        return ()
    try:
        return tuple(list_fn())
    except Exception:
        return ()


def _registered_names(registry):
    prop = getattr(registry, "registered_names", None)
    if callable(prop):
        try:
            return tuple(prop)
        except Exception:
            return ()
    return ()


def _list_skills(registry):
    list_fn = getattr(registry, "list", None)
    if list_fn is None:
        return ()
    try:
        return tuple(list_fn())
    except Exception:
        return ()