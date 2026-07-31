"""
Atlas Lifecycle Package.

Phase 13.2 — Added ComponentRegistry, ComponentMetadata,
ComponentStatus, and core component definitions for structural
self-observation.
"""

from atlas.lifecycle.lifecycle_manager import LifecycleManager
from atlas.lifecycle.phases import LifecyclePhase
from atlas.lifecycle.hooks import LifecycleHooks

# --- Phase 13.2: Component Registry ---
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.component_definitions import CORE_COMPONENTS

__all__ = [
    "ComponentMetadata",
    "ComponentRegistry",
    "ComponentStatus",
    "CORE_COMPONENTS",
    "LifecycleHooks",
    "LifecycleManager",
    "LifecyclePhase",
]
