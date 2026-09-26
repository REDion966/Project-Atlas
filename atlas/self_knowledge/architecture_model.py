"""Atlas Self-Knowledge — Architecture Model (Phase 1.2).

A deterministic, read-only, architecture-centric VIEW projected from Atlas's
existing authoritative structural sources. It is NOT a registry: it registers
nothing, persists nothing, and mutates nothing. The existing sources remain
authoritative for their own data.

Authoritative source mapping (which source is authoritative for what):

* ``ComponentRegistry`` (``atlas.lifecycle.component_registry``) is authoritative
  for: which components exist, the providing package, the declared entry module
  path, the declared responsibility (``ComponentMetadata.description``), the
  declared component dependencies, the declared provided capabilities, and
  component health status.
* ``CapabilityModel`` (``atlas.self_knowledge.capability_model``) is authoritative
  for: which capabilities/tools exist and which components provide them.
* ``RepositoryMap`` (``atlas.research.repository_map``) is authoritative for: which
  repository modules exist, their paths, their import-graph relationships, and the
  structurally-extracted symbols (classes/functions/methods) each module defines.

The model reports only what those sources provide. It never infers a
responsibility, interface, or data flow that no authoritative source records; an
absent fact is reported as absent. The declared scope boundaries (interfaces /
contracts and state / data flow are not represented) are stated explicitly so a
consumer cannot mistake absence for fact.

Pure logic: stdlib imports only. No AI, no network, no storage, no kernel access,
no execution, no governance surface.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

#: Bounds applied to rendered/returned text so a malformed source cannot produce
#: unbounded output.
_MAX_TEXT_CHARS: int = 400
_MAX_IMPACT_ITEMS: int = 200


class ArchitectureSourceKind(str, Enum):
    """Existing authoritative source an architecture claim may come from."""

    COMPONENT_REGISTRY = "component_registry"
    CAPABILITY_MODEL = "capability_model"
    REPOSITORY_MAP = "repository_map"


@dataclass(frozen=True, slots=True)
class ArchitectureSource:
    """One provenance reference for an architecture claim."""

    kind: str
    reference: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "reference": self.reference, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class ComponentArchitectureEntry:
    """Architecture view of one registered component (immutable)."""

    name: str
    package: str
    module_path: str
    responsibility: str
    status: str
    declared_dependencies: tuple[str, ...] = ()
    provided_capabilities: tuple[str, ...] = ()
    capability_names: tuple[str, ...] = ()
    sources: tuple[ArchitectureSource, ...] = ()
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "package": self.package,
            "module_path": self.module_path,
            "responsibility": self.responsibility,
            "status": self.status,
            "declared_dependencies": list(self.declared_dependencies),
            "provided_capabilities": list(self.provided_capabilities),
            "capability_names": list(self.capability_names),
            "sources": [s.to_dict() for s in self.sources],
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class SubsystemEntry:
    """Architecture view of one package-level subsystem (immutable)."""

    package: str
    components: tuple[str, ...] = ()
    provided_capabilities: tuple[str, ...] = ()
    module_count: int = 0
    outbound_component_dependencies: tuple[str, ...] = ()
    sources: tuple[ArchitectureSource, ...] = ()
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "components": list(self.components),
            "provided_capabilities": list(self.provided_capabilities),
            "module_count": self.module_count,
            "outbound_component_dependencies": list(
                self.outbound_component_dependencies
            ),
            "sources": [s.to_dict() for s in self.sources],
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class LocateResult:
    """Evidence-only answer to "where does this capability/module live?"."""

    query: str
    found: bool
    matched_kind: str = "none"
    symbol: str = ""
    components: tuple[str, ...] = ()
    packages: tuple[str, ...] = ()
    module_paths: tuple[str, ...] = ()
    module: str = ""
    dependencies: tuple[str, ...] = ()
    dependents: tuple[str, ...] = ()
    impact: tuple[str, ...] = ()
    sources: tuple[ArchitectureSource, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "found": self.found,
            "matched_kind": self.matched_kind,
            "symbol": self.symbol,
            "components": list(self.components),
            "packages": list(self.packages),
            "module_paths": list(self.module_paths),
            "module": self.module,
            "dependencies": list(self.dependencies),
            "dependents": list(self.dependents),
            "impact": list(self.impact),
            "sources": [s.to_dict() for s in self.sources],
        }


@dataclass(frozen=True, slots=True)
class ArchitectureModel:
    """Canonical, deterministic, read-only architecture model (immutable).

    ``repository_map`` and ``capability_index`` are held only so :meth:`locate`
    can answer structural questions; neither is serialized by :meth:`to_dict`.
    """

    subsystems: tuple[SubsystemEntry, ...]
    components: tuple[ComponentArchitectureEntry, ...]
    component_count: int
    subsystem_count: int
    capability_entry_count: int
    module_count: int
    edge_count: int
    status_counts: tuple[tuple[str, int], ...]
    source_counts: tuple[tuple[str, int], ...]
    limitations: tuple[str, ...]
    #: Structurally-extracted repository symbols (Stage A2); 0 without a map.
    symbol_count: int = 0
    capability_index: tuple[tuple[str, tuple[str, ...]], ...] = ()
    repository_map: Any = None

    # ------------------------------------------------------------------
    # Serialization / rendering
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_count": self.component_count,
            "subsystem_count": self.subsystem_count,
            "capability_entry_count": self.capability_entry_count,
            "module_count": self.module_count,
            "edge_count": self.edge_count,
            "symbol_count": self.symbol_count,
            "status_counts": [list(x) for x in self.status_counts],
            "source_counts": [list(x) for x in self.source_counts],
            "limitations": list(self.limitations),
            "subsystems": [s.to_dict() for s in self.subsystems],
            "components": [c.to_dict() for c in self.components],
        }

    def to_markdown(self) -> str:
        """Render the model deterministically as markdown text."""
        lines = [
            "# Atlas Architecture Self-Knowledge Model",
            "",
            "Read-only deterministic projection of existing Atlas structural "
            "sources. Nothing was modified.",
            "",
            "## Summary",
            f"- Components: {self.component_count}",
            f"- Subsystems (packages): {self.subsystem_count}",
            f"- Capability-model entries: {self.capability_entry_count}",
            f"- Repository modules: {self.module_count}",
            f"- Repository import edges: {self.edge_count}",
            f"- Repository symbols: {self.symbol_count}",
            "- Component health: "
            + (
                ", ".join(f"{k}={v}" for k, v in self.status_counts) or "(none)"
            ),
            "- Evidence sources: "
            + (
                ", ".join(f"{k}={v}" for k, v in self.source_counts) or "(none)"
            ),
        ]
        if self.limitations:
            lines.append("")
            lines.append("## Evidence-based limitations / scope boundaries")
            for item in self.limitations:
                lines.append(f"- {item}")

        lines.append("")
        lines.append("## Subsystems")
        for subsystem in self.subsystems:
            lines.append(
                f"- `{subsystem.package}` components={len(subsystem.components)} "
                f"modules={subsystem.module_count} "
                f"capabilities={len(subsystem.provided_capabilities)}"
            )
            for limitation in subsystem.limitations:
                lines.append(f"    - limitation: {limitation}")

        lines.append("")
        lines.append("## Components")
        for component in self.components:
            lines.append(
                f"- `{component.name}` [{component.package}] "
                f"status={component.status} "
                f"entry=`{component.module_path or '-'}` "
                f"responsibility={component.responsibility or '(none declared)'}"
            )
            for limitation in component.limitations:
                lines.append(f"    - limitation: {limitation}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Evidence-only lookup
    # ------------------------------------------------------------------

    def locate(self, query: str) -> LocateResult:
        """Return the evidence Atlas holds for ``query`` (never a recommendation).

        Resolves, in order, an exact capability/tool name, an exact component
        name, an exact repository module, or a package. Returns only what the
        authoritative sources record; an unknown query is reported as not found.
        """
        text = (query or "").strip()
        if not text:
            return LocateResult(query=query or "", found=False, matched_kind="none")

        components_by_name = {c.name: c for c in self.components}
        capability_map = {name: comps for name, comps in self.capability_index}

        # 1. Capability / tool name.
        if text in capability_map:
            names = tuple(capability_map[text])
            members = [components_by_name[n] for n in names if n in components_by_name]
            return LocateResult(
                query=text,
                found=True,
                matched_kind="capability",
                components=names,
                packages=tuple(sorted({c.package for c in members if c.package})),
                module_paths=tuple(
                    sorted({c.module_path for c in members if c.module_path})
                ),
                sources=(ArchitectureSource(
                    ArchitectureSourceKind.CAPABILITY_MODEL.value, text
                ),),
            )

        # 2. Component name.
        if text in components_by_name:
            component = components_by_name[text]
            return LocateResult(
                query=text,
                found=True,
                matched_kind="component",
                components=(component.name,),
                packages=(component.package,) if component.package else (),
                module_paths=(component.module_path,) if component.module_path else (),
                sources=(
                    ArchitectureSource(
                        ArchitectureSourceKind.COMPONENT_REGISTRY.value, component.name
                    ),
                ),
            )

        # 3. Repository module / package.
        repository_map = self.repository_map
        if repository_map is not None:
            modules = tuple(getattr(repository_map, "modules", ()) or ())
            module_names = {info.module for info in modules}
            components = self.components

            if text in module_names:
                info = next(m for m in modules if m.module == text)
                is_package = bool(getattr(info, "is_package", False))
                if is_package:
                    packages = (text,)
                    related = tuple(
                        sorted(
                            c.name
                            for c in components
                            if c.package == text
                            or c.package.startswith(text + ".")
                        )
                    )
                else:
                    parent = text.rsplit(".", 1)[0] if "." in text else ""
                    packages = (parent,) if parent else ()
                    related = (
                        tuple(sorted(c.name for c in components if c.package == parent))
                        if parent
                        else ()
                    )
                return LocateResult(
                    query=text,
                    found=True,
                    matched_kind="module",
                    module=text,
                    packages=packages,
                    components=related,
                    dependencies=tuple(
                        _bounded(
                            getattr(repository_map, "dependencies_of", None), text
                        )
                    ),
                    dependents=tuple(
                        _bounded(getattr(repository_map, "dependents_of", None), text)
                    ),
                    impact=tuple(
                        _bounded(getattr(repository_map, "impact_set", None), text)
                    ),
                    sources=(
                        ArchitectureSource(
                            ArchitectureSourceKind.REPOSITORY_MAP.value, text
                        ),
                    ),
                )

            # Package prefix: no exact module, but nested modules exist.
            if any(m.startswith(text + ".") for m in module_names):
                return LocateResult(
                    query=text,
                    found=True,
                    matched_kind="package",
                    packages=(text,),
                    components=tuple(
                        sorted(
                            c.name
                            for c in components
                            if c.package == text
                            or c.package.startswith(text + ".")
                        )
                    ),
                    sources=(
                        ArchitectureSource(
                            ArchitectureSourceKind.REPOSITORY_MAP.value, text
                        ),
                    ),
                )

            # Symbol-level structure (Stage A2): a class / function / method the
            # repository actually defines. Evidence-only — the owning module and
            # any component registered for that package; unknown symbols are not
            # invented.
            finder = getattr(repository_map, "find_symbol", None)
            if callable(finder):
                try:
                    matches = tuple(finder(text))
                except Exception:
                    matches = ()
                if matches:
                    top = matches[0]
                    symbol = _clean_text(getattr(top, "qualified", ""))
                    module_name = _clean_text(getattr(top, "module", ""))
                    parent = (
                        module_name.rsplit(".", 1)[0]
                        if "." in module_name
                        else ""
                    )
                    related = (
                        tuple(
                            sorted(c.name for c in components if c.package == parent)
                        )
                        if parent
                        else ()
                    )
                    return LocateResult(
                        query=text,
                        found=True,
                        matched_kind="symbol",
                        symbol=symbol,
                        module=module_name,
                        packages=(parent,) if parent else (),
                        components=related,
                        sources=(
                            ArchitectureSource(
                                ArchitectureSourceKind.REPOSITORY_MAP.value, symbol
                            ),
                        ),
                    )

        return LocateResult(query=text, found=False, matched_kind="none")


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _bounded(callable_or_none: Any, argument: str) -> list[str]:
    """Best-effort bounded call to a repository-map query (fail-soft)."""
    if callable_or_none is None:
        return []
    try:
        result = callable_or_none(argument)
    except Exception:
        return []
    items = sorted(str(x) for x in (result or ()))
    return items[:_MAX_IMPACT_ITEMS]


def _status_name(status: Any) -> str:
    """Return a stable string for a ComponentStatus (Enum.name, not value)."""
    name = getattr(status, "name", None)
    if isinstance(name, str) and name:
        return name
    return str(status) if status is not None else "UNKNOWN"


def _clean_text(value: Any, limit: int = _MAX_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


class ArchitectureModelBuilder:
    """Projects existing authoritative sources into an ArchitectureModel.

    Read-only and deterministic: it never mutates the supplied sources. Missing
    or malformed sources degrade gracefully — the projection reports what it has
    and states what it does not.
    """

    def build(
        self,
        component_registry: Any,
        capability_model: Any | None = None,
        repository_map: Any | None = None,
    ) -> ArchitectureModel:
        components = self._collect_components(component_registry)
        capability_index = self._capability_index(capability_model)
        modules = self._collect_modules(repository_map)

        component_entries = self._build_components(components, capability_index)
        package_modules = self._package_module_counts(components, modules)
        subsystems = self._build_subsystems(
            component_entries, package_modules, has_repository_map=bool(modules)
        )

        status_counts = tuple(
            sorted(Counter(c.status for c in component_entries).items())
        )

        all_sources = [
            source
            for entry in (*subsystems, *component_entries)
            for source in entry.sources
        ]
        source_counts = tuple(
            sorted(Counter(source.kind for source in all_sources).items())
        )

        limitations = self._model_limitations(
            capability_model, repository_map, components, modules
        )

        symbol_count = 0
        counter = getattr(repository_map, "symbol_count", None)
        if callable(counter):
            try:
                symbol_count = int(counter())
            except Exception:
                symbol_count = 0

        return ArchitectureModel(
            subsystems=subsystems,
            components=component_entries,
            component_count=len(component_entries),
            subsystem_count=len(subsystems),
            capability_entry_count=len(capability_index),
            module_count=len(modules),
            edge_count=sum(len(m.internal_imports) for m in modules),
            symbol_count=symbol_count,
            status_counts=status_counts,
            source_counts=source_counts,
            limitations=limitations,
            capability_index=tuple(sorted(capability_index.items())),
            repository_map=repository_map if modules else None,
        )

    # ------------------------------------------------------------------
    # Source collection (fail-soft)
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_components(component_registry: Any) -> list[Any]:
        if component_registry is None:
            return []
        try:
            components = list(component_registry.get_all())
        except Exception:
            return []
        return sorted(components, key=lambda c: str(getattr(c, "name", "") or ""))

    @staticmethod
    def _capability_index(capability_model: Any | None) -> dict[str, tuple[str, ...]]:
        if capability_model is None:
            return {}
        entries = getattr(capability_model, "entries", None)
        if not entries:
            return {}
        index: dict[str, tuple[str, ...]] = {}
        for entry in entries:
            name = _clean_text(getattr(entry, "name", ""))
            if not name:
                continue
            members = tuple(
                sorted(
                    {
                        str(component)
                        for component in (getattr(entry, "components", ()) or ())
                        if str(component)
                    }
                )
            )
            index[name] = members
        return index

    @staticmethod
    def _collect_modules(repository_map: Any | None) -> list[Any]:
        if repository_map is None:
            return []
        modules = getattr(repository_map, "modules", None)
        if not modules:
            return []
        return list(modules)

    # ------------------------------------------------------------------
    # Projection
    # ------------------------------------------------------------------

    @staticmethod
    def _build_components(
        components: list[Any],
        capability_index: dict[str, tuple[str, ...]],
    ) -> tuple[ComponentArchitectureEntry, ...]:
        entries: list[ComponentArchitectureEntry] = []
        for component in components:
            name = str(getattr(component, "name", "") or "")
            if not name:
                continue
            package = str(getattr(component, "package", "") or "")
            module_path = str(getattr(component, "module_path", "") or "")
            responsibility = _clean_text(getattr(component, "description", ""))
            status = _status_name(getattr(component, "status", None))
            dependencies = tuple(
                sorted(
                    {
                        str(dep)
                        for dep in (getattr(component, "dependencies", ()) or ())
                        if str(dep)
                    }
                )
            )
            provided = tuple(
                sorted(
                    {
                        str(cap)
                        for cap in (
                            getattr(component, "provided_capabilities", ()) or ()
                        )
                        if str(cap)
                    }
                )
            )
            capability_names = tuple(
                sorted(
                    cap_name
                    for cap_name, members in capability_index.items()
                    if name in members
                )
            )

            detail = f"package={package}" if package else "package=unknown"
            if module_path:
                detail = f"{detail}; module={module_path}"

            limitations: list[str] = []
            if not responsibility:
                limitations.append(
                    "No declared responsibility "
                    "(ComponentMetadata.description is empty)."
                )

            entries.append(
                ComponentArchitectureEntry(
                    name=name,
                    package=package,
                    module_path=module_path,
                    responsibility=responsibility,
                    status=status,
                    declared_dependencies=dependencies,
                    provided_capabilities=provided,
                    capability_names=capability_names,
                    sources=(
                        ArchitectureSource(
                            ArchitectureSourceKind.COMPONENT_REGISTRY.value,
                            name,
                            detail=detail,
                        ),
                    ),
                    limitations=tuple(limitations),
                )
            )
        return tuple(entries)

    @staticmethod
    def _package_module_counts(
        components: list[Any],
        modules: list[Any],
    ) -> dict[str, int]:
        """Count repository modules within each registered package subtree.

        A module is counted for every package it is contained in (a nested
        package is also inside its parents), so the result is deterministic and
        independent of iteration order.
        """
        packages = {
            str(getattr(c, "package", "") or "")
            for c in components
            if str(getattr(c, "package", "") or "")
        }
        counts: dict[str, int] = {package: 0 for package in packages}
        for info in modules:
            module = str(getattr(info, "module", "") or "")
            for package in packages:
                if module == package or module.startswith(package + "."):
                    counts[package] += 1
        return counts

    @staticmethod
    def _build_subsystems(
        component_entries: tuple[ComponentArchitectureEntry, ...],
        package_modules: dict[str, int],
        has_repository_map: bool,
    ) -> tuple[SubsystemEntry, ...]:
        grouped: dict[str, list[ComponentArchitectureEntry]] = {}
        for entry in component_entries:
            grouped.setdefault(entry.package or "(unknown)", []).append(entry)

        subsystems: list[SubsystemEntry] = []
        for package in sorted(grouped):
            members = grouped[package]
            member_names = {m.name for m in members}
            provided = tuple(
                sorted({cap for m in members for cap in m.provided_capabilities})
            )
            outbound = tuple(
                sorted(
                    {
                        dep
                        for m in members
                        for dep in m.declared_dependencies
                        if dep not in member_names
                    }
                )
            )
            module_count = package_modules.get(package, 0)

            sources = [
                ArchitectureSource(
                    ArchitectureSourceKind.COMPONENT_REGISTRY.value,
                    package,
                    detail=f"{len(members)} component(s)",
                )
            ]
            limitations: list[str] = []
            if has_repository_map:
                sources.append(
                    ArchitectureSource(
                        ArchitectureSourceKind.REPOSITORY_MAP.value,
                        package,
                        detail=f"{module_count} module(s)",
                    )
                )
                if module_count == 0:
                    limitations.append(
                        "No repository-map module found under this package."
                    )

            subsystems.append(
                SubsystemEntry(
                    package=package,
                    components=tuple(sorted(m.name for m in members)),
                    provided_capabilities=provided,
                    module_count=module_count,
                    outbound_component_dependencies=outbound,
                    sources=tuple(sources),
                    limitations=tuple(limitations),
                )
            )
        return tuple(subsystems)

    @staticmethod
    def _model_limitations(
        capability_model: Any | None,
        repository_map: Any | None,
        components: list[Any],
        modules: list[Any],
    ) -> tuple[str, ...]:
        # Declared scope boundaries: always true of this model by design, stated
        # so absence of data cannot be mistaken for a fact.
        limitations: list[str] = [
            "Interfaces/contracts are not represented (no authoritative source "
            "records them).",
            "State/data-flow is not represented (only static import edges are "
            "available).",
        ]
        if capability_model is None:
            limitations.append(
                "Capability model unavailable; the capability join is omitted."
            )
        if not repository_map or not modules:
            limitations.append(
                "Repository map unavailable; module-level facts are omitted."
            )
        else:
            packages = {
                str(getattr(c, "package", "") or "")
                for c in components
                if str(getattr(c, "package", "") or "")
            }
            unmapped = 0
            for info in modules:
                module = str(getattr(info, "module", "") or "")
                if not any(
                    module == package or module.startswith(package + ".")
                    for package in packages
                ):
                    unmapped += 1
            if unmapped:
                limitations.append(
                    f"{unmapped} repository module(s) are not described by any "
                    "registered component (responsibility unknown)."
                )
        return tuple(limitations)


def build_architecture_model(
    component_registry: Any,
    capability_model: Any | None = None,
    repository_map: Any | None = None,
) -> ArchitectureModel:
    """Convenience function: build the canonical architecture model."""
    return ArchitectureModelBuilder().build(
        component_registry,
        capability_model=capability_model,
        repository_map=repository_map,
    )
