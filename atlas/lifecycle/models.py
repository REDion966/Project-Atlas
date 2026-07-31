"""
Atlas Lifecycle — Data Models for Component Registry.

Pure data models for tracking Atlas components, their structure,
dependencies, capabilities, and health state.

Phase 13.2 — Self Model Expansion.

No business logic. No infrastructure. Observation-only.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto


class ComponentStatus(Enum):
    """Current health state of a registered component.

    HEALTHY: Component is functioning normally.
    DEGRADED: Component is operational but impaired.
    OFFLINE: Component is not available.
    UNKNOWN: Health has not been assessed.
    """

    HEALTHY = auto()
    DEGRADED = auto()
    OFFLINE = auto()
    UNKNOWN = auto()


@dataclass(frozen=True, slots=True)
class ComponentMetadata:
    """
    Structural metadata about a single Atlas component.

    This is an observation record. It describes what a component is,
    where it lives, what it depends on, and what it provides.

    All fields are populated at registration time and are immutable
    for the lifetime of the component session. Status can be updated
    independently via ComponentRegistry.update_status().

    Attributes:
        name: Short unique name for the component (e.g. "memory_service").
        package: Python package the component belongs to
            (e.g. "atlas.memory.service").
        module_path: Full dotted module path to the component class
            (e.g. "atlas.memory.service.memory_manager_service").
        description: Human-readable explanation of the component's role.
        version: Component version number. Starts at 1.
        status: Current health state. Defaults to UNKNOWN.
        dependencies: List of component names this component
            depends on. Empty if none.
        provided_capabilities: List of capability strings this
            component provides (e.g. "memory_search", "tool_execution").
        registered_at: When this component was registered.
        last_health_check: When the component's health was last
            assessed. None if never checked.
    """

    name: str
    package: str
    module_path: str
    description: str = ""
    version: int = 1
    status: ComponentStatus = ComponentStatus.UNKNOWN
    dependencies: list[str] = field(default_factory=list)
    provided_capabilities: list[str] = field(default_factory=list)
    registered_at: datetime = field(default_factory=datetime.now)
    last_health_check: datetime | None = None
