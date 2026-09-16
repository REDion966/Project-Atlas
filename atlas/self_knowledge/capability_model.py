"""Atlas Self-Knowledge — Canonical Capability Model (C5.1).

A deterministic, read-only, capability-centric VIEW projected from Atlas's
existing authoritative runtime sources. It is NOT a registry: it registers
nothing, persists nothing, and mutates nothing. The existing registries remain
authoritative for their own data.

Authoritative source mapping (which source is authoritative for what):

* ``ComponentRegistry`` (``atlas.lifecycle.component_registry``) is authoritative
  for: which components exist, which components provide which capability, the
  providing component's package/module, and component health status.
* ``CapabilityRegistry`` (``atlas.reasoning.execution.registry``) is authoritative
  for: which capability *handlers* are registered (names only).
* ``ToolRegistry`` (``atlas.tools.registry``) is authoritative for: which tools
  are registered.

Sources that are deliberately NOT merged into entries:

* ``CapabilityProfiler.DEFAULT_CAPABILITIES`` is a hard-coded seed list of
  abstract ability names; it is not derived from the runtime registries and is
  therefore not authoritative for runtime capability existence. Including it
  would silently invent capabilities.
* Per-track catalogs are registration inputs (their metadata is already
  registered into the ``ComponentRegistry``); the registry is authoritative for
  the runtime result.

Classification is derived from actual repository evidence (the providing
component's ``package``), never from capability-name semantics. When a
classification cannot be established honestly, it is reported as ``unknown``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any

#: Evidence rule: capabilities provided by components in this package prefix
#: interact with optional external AI models.
_EXTERNAL_MODEL_PACKAGE_PREFIX = "atlas.ai"


class CapabilityKind(str, Enum):
    """Whether an entry is a capability or a registered tool."""

    CAPABILITY = "capability"
    TOOL = "tool"


class CapabilityDependency(str, Enum):
    """What an entry depends on (evidence-derived; never guessed)."""

    DETERMINISTIC = "deterministic"
    EXTERNAL_MODEL_DEPENDENT = "external_model_dependent"
    UNKNOWN = "unknown"


class CapabilityAvailability(str, Enum):
    """Availability derived from existing component health (read-only)."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class CapabilitySourceKind(str, Enum):
    """Existing authoritative sources a capability claim may come from."""

    COMPONENT_REGISTRY = "component_registry"
    CAPABILITY_REGISTRY = "capability_registry"
    TOOL_REGISTRY = "tool_registry"


@dataclass(frozen=True, slots=True)
class CapabilitySource:
    """One provenance reference for a capability claim."""

    kind: str
    reference: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "reference": self.reference, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class CapabilityEntry:
    """Canonical capability-centric entry (immutable)."""

    name: str
    kind: CapabilityKind
    dependency: CapabilityDependency
    availability: CapabilityAvailability
    components: tuple[str, ...] = ()
    sources: tuple[CapabilitySource, ...] = ()
    health: tuple[tuple[str, str], ...] = ()
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "dependency": self.dependency.value,
            "availability": self.availability.value,
            "components": list(self.components),
            "sources": [s.to_dict() for s in self.sources],
            "health": [list(h) for h in self.health],
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class CapabilityModel:
    """Canonical, deterministic, read-only capability model (immutable)."""

    entries: tuple[CapabilityEntry, ...]
    component_count: int
    capability_count: int
    tool_count: int
    dependency_counts: tuple[tuple[str, int], ...]
    availability_counts: tuple[tuple[str, int], ...]
    health_counts: tuple[tuple[str, int], ...]
    source_counts: tuple[tuple[str, int], ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_count": self.component_count,
            "capability_count": self.capability_count,
            "tool_count": self.tool_count,
            "entry_count": len(self.entries),
            "dependency_counts": [list(x) for x in self.dependency_counts],
            "availability_counts": [list(x) for x in self.availability_counts],
            "health_counts": [list(x) for x in self.health_counts],
            "source_counts": [list(x) for x in self.source_counts],
            "limitations": list(self.limitations),
            "entries": [e.to_dict() for e in self.entries],
        }

    def to_markdown(self) -> str:
        """Render the model deterministically as markdown text."""
        lines = [
            "# Atlas Canonical Capability Model",
            "",
            "Read-only deterministic projection of existing Atlas capability "
            "sources. Nothing was modified.",
            "",
            "## Summary",
            f"- Components: {self.component_count}",
            f"- Capabilities: {self.capability_count}",
            f"- Tools: {self.tool_count}",
            "- Dependency: "
            + (
                ", ".join(f"{k}={v}" for k, v in self.dependency_counts)
                or "(none)"
            ),
            "- Availability: "
            + (
                ", ".join(f"{k}={v}" for k, v in self.availability_counts)
                or "(none)"
            ),
            "- Component health: "
            + (
                ", ".join(f"{k}={v}" for k, v in self.health_counts)
                or "(none)"
            ),
            "- Sources: "
            + (
                ", ".join(f"{k}={v}" for k, v in self.source_counts)
                or "(none)"
            ),
        ]
        if self.limitations:
            lines.append("")
            lines.append("## Evidence-based limitations")
            for item in self.limitations:
                lines.append(f"- {item}")

        lines.append("")
        lines.append("## Entries")
        for entry in self.entries:
            sources = "; ".join(
                f"{s.kind}:{s.reference}" for s in entry.sources
            )
            lines.append(
                f"- `{entry.name}` [{entry.kind.value}] "
                f"dependency={entry.dependency.value} "
                f"availability={entry.availability.value} "
                f"components={','.join(entry.components) or '-'} "
                f"sources={sources}"
            )
            for limitation in entry.limitations:
                lines.append(f"    - limitation: {limitation}")
        return "\n".join(lines)


def _status_name(status: Any) -> str:
    """Return a stable string for a ComponentStatus (Enum.name, not value)."""
    name = getattr(status, "name", None)
    if isinstance(name, str) and name:
        return name
    return str(status)


def _derive_availability(statuses: list[str]) -> CapabilityAvailability:
    """Derive availability from existing component health status names."""
    unique = set(statuses)
    if "OFFLINE" in unique:
        return CapabilityAvailability.UNAVAILABLE
    if "DEGRADED" in unique:
        return CapabilityAvailability.DEGRADED
    if "HEALTHY" in unique:
        return CapabilityAvailability.AVAILABLE
    return CapabilityAvailability.UNKNOWN


class CapabilityModelBuilder:
    """Projects existing authoritative sources into a CapabilityModel.

    Read-only and deterministic: it never mutates the supplied registries.
    """

    def build(
        self,
        component_registry: Any,
        capability_registry: Any | None = None,
        tool_registry: Any | None = None,
    ) -> CapabilityModel:
        # name -> accumulator
        acc: dict[str, dict[str, Any]] = {}

        def _entry(name: str) -> dict[str, Any]:
            return acc.setdefault(
                name,
                {
                    "components": {},  # name -> package
                    "sources": [],
                    "health": {},
                    "is_tool": False,
                },
            )

        # --- ComponentRegistry (authoritative for components/capabilities) ---
        components: list[Any] = []
        if component_registry is not None:
            components = list(component_registry.get_all())
            for component in components:
                cname = str(getattr(component, "name", "") or "")
                package = str(getattr(component, "package", "") or "")
                module_path = str(getattr(component, "module_path", "") or "")
                status = _status_name(getattr(component, "status", None))
                for cap in tuple(getattr(component, "provided_capabilities", ()) or ()):
                    cap_name = str(cap)
                    item = _entry(cap_name)
                    item["components"][cname] = package
                    item["health"][cname] = status
                    item["sources"].append(
                        CapabilitySource(
                            kind=CapabilitySourceKind.COMPONENT_REGISTRY.value,
                            reference=cname,
                            detail=(
                                f"package={package}; module={module_path}"
                                if module_path
                                else f"package={package}"
                            ),
                        )
                    )

        # --- CapabilityRegistry (authoritative for handler names) ---
        if capability_registry is not None:
            names = getattr(capability_registry, "registered_names", None)
            if names is None:
                names = []
            for name in names:
                item = _entry(str(name))
                item["sources"].append(
                    CapabilitySource(
                        kind=CapabilitySourceKind.CAPABILITY_REGISTRY.value,
                        reference=str(name),
                    )
                )

        # --- ToolRegistry (authoritative for tools) ---
        if tool_registry is not None:
            for tool in tool_registry.list():
                tname = str(getattr(tool, "name", "") or "")
                if not tname:
                    continue
                category = str(getattr(tool, "category", "") or "")
                item = _entry(tname)
                item["is_tool"] = True
                item["sources"].append(
                    CapabilitySource(
                        kind=CapabilitySourceKind.TOOL_REGISTRY.value,
                        reference=tname,
                        detail=f"category={category}" if category else "",
                    )
                )

        entries: list[CapabilityEntry] = []
        for name in sorted(acc):
            item = acc[name]
            component_names = tuple(sorted(item["components"]))
            packages = sorted(set(item["components"].values()))
            is_tool = bool(item["is_tool"])

            # Classification (evidence-derived; never guessed).
            if any(p.startswith(_EXTERNAL_MODEL_PACKAGE_PREFIX) for p in packages):
                dependency = CapabilityDependency.EXTERNAL_MODEL_DEPENDENT
            elif component_names or is_tool:
                dependency = CapabilityDependency.DETERMINISTIC
            else:
                dependency = CapabilityDependency.UNKNOWN

            health = tuple(sorted(item["health"].items()))
            availability = _derive_availability([s for _, s in health])

            limitations: list[str] = []
            if dependency is CapabilityDependency.EXTERNAL_MODEL_DEPENDENT:
                limitations.append(
                    "Requires an optional external AI model (providing "
                    "component package 'atlas.ai'); unavailable when no "
                    "external model is configured."
                )
            elif dependency is CapabilityDependency.UNKNOWN:
                limitations.append(
                    "Dependency classification could not be established from "
                    "available evidence (no providing component or tool)."
                )

            entries.append(
                CapabilityEntry(
                    name=name,
                    kind=CapabilityKind.TOOL if is_tool else CapabilityKind.CAPABILITY,
                    dependency=dependency,
                    availability=availability,
                    components=component_names,
                    sources=tuple(
                        sorted(
                            item["sources"],
                            key=lambda s: (s.kind, s.reference, s.detail),
                        )
                    ),
                    health=health,
                    limitations=tuple(limitations),
                )
            )

        component_count = len(components)
        capability_count = sum(1 for e in entries if e.kind is CapabilityKind.CAPABILITY)
        tool_count = sum(1 for e in entries if e.kind is CapabilityKind.TOOL)

        dependency_counts = tuple(
            sorted(Counter(e.dependency.value for e in entries).items())
        )
        availability_counts = tuple(
            sorted(Counter(e.availability.value for e in entries).items())
        )
        health_counts = tuple(
            sorted(Counter(_status_name(getattr(c, "status", None)) for c in components).items())
        )
        source_counts = tuple(
            sorted(
                Counter(s.kind for e in entries for s in e.sources).items()
            )
        )

        # Model-level, evidence-based limitations (only when the evidence
        # exists; never "absence of evidence is evidence of absence").
        model_limitations: list[str] = []
        external = sum(
            1 for e in entries if e.dependency is CapabilityDependency.EXTERNAL_MODEL_DEPENDENT
        )
        unknown = sum(
            1 for e in entries if e.dependency is CapabilityDependency.UNKNOWN
        )
        unavailable = sum(
            1 for e in entries if e.availability is CapabilityAvailability.UNAVAILABLE
        )
        degraded = sum(
            1 for e in entries if e.availability is CapabilityAvailability.DEGRADED
        )
        if external:
            model_limitations.append(
                f"{external} capability entr(ies) depend on an optional "
                "external AI model and are unavailable without one."
            )
        if unknown:
            model_limitations.append(
                f"{unknown} entr(ies) have an unestablished dependency "
                "classification (no providing component or tool)."
            )
        if unavailable:
            model_limitations.append(
                f"{unavailable} entr(ies) are currently unavailable (providing "
                "component OFFLINE)."
            )
        if degraded:
            model_limitations.append(
                f"{degraded} entr(ies) are currently degraded (providing "
                "component DEGRADED)."
            )

        return CapabilityModel(
            entries=tuple(entries),
            component_count=component_count,
            capability_count=capability_count,
            tool_count=tool_count,
            dependency_counts=dependency_counts,
            availability_counts=availability_counts,
            health_counts=health_counts,
            source_counts=source_counts,
            limitations=tuple(model_limitations),
        )


def build_capability_model(
    component_registry: Any,
    capability_registry: Any | None = None,
    tool_registry: Any | None = None,
) -> CapabilityModel:
    """Convenience function: build the canonical capability model."""
    return CapabilityModelBuilder().build(
        component_registry,
        capability_registry=capability_registry,
        tool_registry=tool_registry,
    )
