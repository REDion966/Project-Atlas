"""
Phase 13.2 — Component Registry Tests.

Tests the observation-only component registry, data models, and
kernel wiring. Verifies that the registry correctly tracks what
components Atlas has without modifying them.

Pure logic tests. No AI. No infrastructure. No storage.
"""

import pytest
from datetime import datetime

from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.component_definitions import CORE_COMPONENTS


# ---------------------------------------------------------------------------
# Test: ComponentStatus
# ---------------------------------------------------------------------------


class TestComponentStatus:

    def test_has_expected_values(self):
        """All required ComponentStatus values exist."""
        assert ComponentStatus.HEALTHY is not None
        assert ComponentStatus.DEGRADED is not None
        assert ComponentStatus.OFFLINE is not None
        assert ComponentStatus.UNKNOWN is not None

    def test_values_are_unique(self):
        """No duplicate status values."""
        values = [s.value for s in ComponentStatus]
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# Test: ComponentMetadata
# ---------------------------------------------------------------------------


class TestComponentMetadata:

    def test_minimal_creation(self):
        """Create ComponentMetadata with only required fields."""
        meta = ComponentMetadata(
            name="test_component",
            package="atlas.test",
            module_path="atlas.test.component.TestComponent",
        )
        assert meta.name == "test_component"
        assert meta.package == "atlas.test"
        assert meta.module_path == "atlas.test.component.TestComponent"
        assert meta.description == ""
        assert meta.version == 1
        assert meta.status == ComponentStatus.UNKNOWN
        assert meta.dependencies == []
        assert meta.provided_capabilities == []
        assert isinstance(meta.registered_at, datetime)
        assert meta.last_health_check is None

    def test_full_creation(self):
        """Create ComponentMetadata with all fields."""
        meta = ComponentMetadata(
            name="full_component",
            package="atlas.full",
            module_path="atlas.full.component.FullComponent",
            description="A fully specified component.",
            version=3,
            status=ComponentStatus.HEALTHY,
            dependencies=["dep_a", "dep_b"],
            provided_capabilities=["cap_x", "cap_y"],
        )
        assert meta.description == "A fully specified component."
        assert meta.version == 3
        assert meta.status == ComponentStatus.HEALTHY
        assert meta.dependencies == ["dep_a", "dep_b"]
        assert meta.provided_capabilities == ["cap_x", "cap_y"]

    def test_is_frozen(self):
        """ComponentMetadata is immutable after creation."""
        meta = ComponentMetadata(
            name="frozen_comp",
            package="atlas.frozen",
            module_path="atlas.frozen.FrozenComponent",
        )
        with pytest.raises(AttributeError):
            meta.name = "changed"  # type: ignore

    def test_timestamp_generated_on_creation(self):
        """registered_at is set to the current time on creation."""
        meta = ComponentMetadata(
            name="timed",
            package="atlas.timed",
            module_path="atlas.timed.TimedComponent",
        )
        assert isinstance(meta.registered_at, datetime)
        # Should be very recent
        delta = datetime.now() - meta.registered_at
        assert delta.total_seconds() < 5


# ---------------------------------------------------------------------------
# Test: ComponentRegistry — Registration
# ---------------------------------------------------------------------------


class TestRegistration:

    def test_register_component(self):
        """A component can be registered."""
        registry = ComponentRegistry()
        meta = ComponentMetadata(
            name="reg_comp",
            package="atlas.reg",
            module_path="atlas.reg.RegComponent",
        )
        registry.register(meta)
        assert registry.component_count == 1

    def test_register_duplicate_raises(self):
        """Registering a duplicate name raises ValueError."""
        registry = ComponentRegistry()
        meta = ComponentMetadata(
            name="dup_comp",
            package="atlas.dup",
            module_path="atlas.dup.DupComponent",
        )
        registry.register(meta)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(meta)

    def test_register_or_update_silently_replaces(self):
        """register_or_update replaces existing without raising."""
        registry = ComponentRegistry()
        meta1 = ComponentMetadata(
            name="upd_comp",
            package="atlas.upd",
            module_path="atlas.upd.v1",
            version=1,
        )
        meta2 = ComponentMetadata(
            name="upd_comp",
            package="atlas.upd",
            module_path="atlas.upd.v2",
            version=2,
        )
        registry.register(meta1)
        registry.register_or_update(meta2)
        assert registry.component_count == 1
        assert registry.get("upd_comp").version == 2

    def test_clear_removes_all(self):
        """clear() removes all components."""
        registry = ComponentRegistry()
        registry.register(ComponentMetadata(
            name="clear_comp",
            package="atlas.clear",
            module_path="atlas.clear.ClearComponent",
        ))
        assert registry.component_count == 1
        registry.clear()
        assert registry.component_count == 0


# ---------------------------------------------------------------------------
# Test: ComponentRegistry — Querying
# ---------------------------------------------------------------------------


class TestQuerying:

    def test_get_returns_component(self):
        """get() returns the correct component."""
        registry = ComponentRegistry()
        meta = ComponentMetadata(
            name="get_comp",
            package="atlas.get",
            module_path="atlas.get.GetComponent",
        )
        registry.register(meta)
        result = registry.get("get_comp")
        assert result is not None
        assert result.name == "get_comp"

    def test_get_nonexistent_returns_none(self):
        """get() returns None for unknown names."""
        registry = ComponentRegistry()
        assert registry.get("nonexistent") is None

    def test_get_all_returns_sorted(self):
        """get_all() returns components sorted by name."""
        registry = ComponentRegistry()
        registry.register(ComponentMetadata(
            name="z_comp", package="a", module_path="a.z",
        ))
        registry.register(ComponentMetadata(
            name="a_comp", package="a", module_path="a.a",
        ))
        all_comps = registry.get_all()
        assert len(all_comps) == 2
        assert all_comps[0].name == "a_comp"
        assert all_comps[1].name == "z_comp"

    def test_get_by_package(self):
        """get_by_package() filters by package."""
        registry = ComponentRegistry()
        registry.register(ComponentMetadata(
            name="comp_a", package="atlas.a", module_path="atlas.a.A",
        ))
        registry.register(ComponentMetadata(
            name="comp_b", package="atlas.b", module_path="atlas.b.B",
        ))
        registry.register(ComponentMetadata(
            name="comp_c", package="atlas.a", module_path="atlas.a.C",
        ))
        results = registry.get_by_package("atlas.a")
        assert len(results) == 2
        assert all(c.package == "atlas.a" for c in results)

    def test_get_by_empty_package(self):
        """get_by_package returns empty list for unknown package."""
        registry = ComponentRegistry()
        results = registry.get_by_package("atlas.nonexistent")
        assert results == []

    def test_get_by_capability(self):
        """get_by_capability() finds components providing a capability."""
        registry = ComponentRegistry()
        registry.register(ComponentMetadata(
            name="search_engine",
            package="atlas.search",
            module_path="atlas.search.SearchEngine",
            provided_capabilities=["search", "index"],
        ))
        registry.register(ComponentMetadata(
            name="storage_engine",
            package="atlas.storage",
            module_path="atlas.storage.StorageEngine",
            provided_capabilities=["storage"],
        ))
        results = registry.get_by_capability("search")
        assert len(results) == 1
        assert results[0].name == "search_engine"

    def test_get_by_nonexistent_capability(self):
        """get_by_capability returns empty list for unknown capability."""
        registry = ComponentRegistry()
        results = registry.get_by_capability("nonexistent")
        assert results == []

    def test_get_all_component_names(self):
        """get_all_component_names returns sorted names."""
        registry = ComponentRegistry()
        registry.register(ComponentMetadata(
            name="z", package="a", module_path="a.z",
        ))
        registry.register(ComponentMetadata(
            name="a", package="a", module_path="a.a",
        ))
        assert registry.get_all_component_names() == ["a", "z"]


# ---------------------------------------------------------------------------
# Test: ComponentRegistry — Status Updates
# ---------------------------------------------------------------------------


class TestStatus:

    def test_update_status_changes_status(self):
        """update_status() changes the component's status."""
        registry = ComponentRegistry()
        meta = ComponentMetadata(
            name="status_comp",
            package="atlas.status",
            module_path="atlas.status.StatusComponent",
            status=ComponentStatus.UNKNOWN,
        )
        registry.register(meta)

        result = registry.update_status("status_comp", ComponentStatus.HEALTHY)
        assert result is True
        assert registry.get("status_comp").status == ComponentStatus.HEALTHY

    def test_update_status_sets_health_check_timestamp(self):
        """update_status() sets last_health_check timestamp."""
        registry = ComponentRegistry()
        meta = ComponentMetadata(
            name="health_comp",
            package="atlas.health",
            module_path="atlas.health.HealthComponent",
        )
        registry.register(meta)
        before = datetime.now()
        registry.update_status("health_comp", ComponentStatus.HEALTHY)
        updated = registry.get("health_comp")
        assert updated.last_health_check is not None
        assert updated.last_health_check >= before

    def test_update_nonexistent_returns_false(self):
        """update_status() returns False for unknown components."""
        registry = ComponentRegistry()
        result = registry.update_status("nonexistent", ComponentStatus.HEALTHY)
        assert result is False

    def test_get_by_status(self):
        """get_by_status() filters by status."""
        registry = ComponentRegistry()
        registry.register(ComponentMetadata(
            name="healthy_comp",
            package="atlas.test",
            module_path="atlas.test.Healthy",
            status=ComponentStatus.HEALTHY,
        ))
        registry.register(ComponentMetadata(
            name="unknown_comp",
            package="atlas.test",
            module_path="atlas.test.Unknown",
            status=ComponentStatus.UNKNOWN,
        ))
        healthy = registry.get_by_status(ComponentStatus.HEALTHY)
        assert len(healthy) == 1
        assert healthy[0].name == "healthy_comp"

    def test_update_status_preserves_other_fields(self):
        """update_status() preserves all other metadata fields."""
        registry = ComponentRegistry()
        meta = ComponentMetadata(
            name="preserve_comp",
            package="atlas.preserve",
            module_path="atlas.preserve.PreserveComponent",
            description="Original description.",
            version=5,
            dependencies=["dep_a"],
            provided_capabilities=["cap_x"],
        )
        registry.register(meta)
        registry.update_status("preserve_comp", ComponentStatus.DEGRADED)
        updated = registry.get("preserve_comp")
        assert updated.description == "Original description."
        assert updated.version == 5
        assert updated.dependencies == ["dep_a"]
        assert updated.provided_capabilities == ["cap_x"]


# ---------------------------------------------------------------------------
# Test: ComponentRegistry — Capability Mapping
# ---------------------------------------------------------------------------


class TestCapabilityMapping:

    def test_get_capability_map(self):
        """get_capability_map returns capability → component list."""
        registry = ComponentRegistry()
        registry.register(ComponentMetadata(
            name="a",
            package="p",
            module_path="p.a",
            provided_capabilities=["search", "store"],
        ))
        registry.register(ComponentMetadata(
            name="b",
            package="p",
            module_path="p.b",
            provided_capabilities=["search"],
        ))
        mapping = registry.get_capability_map()
        assert "search" in mapping
        assert "store" in mapping
        assert set(mapping["search"]) == {"a", "b"}
        assert mapping["store"] == ["a"]

    def test_get_all_capabilities(self):
        """get_all_capabilities returns unique sorted capabilities."""
        registry = ComponentRegistry()
        registry.register(ComponentMetadata(
            name="a",
            package="p",
            module_path="p.a",
            provided_capabilities=["z_cap", "a_cap"],
        ))
        registry.register(ComponentMetadata(
            name="b",
            package="p",
            module_path="p.b",
            provided_capabilities=["a_cap"],
        ))
        caps = registry.get_all_capabilities()
        assert caps == ["a_cap", "z_cap"]

    def test_empty_capability_map(self):
        """get_capability_map returns empty dict for empty registry."""
        registry = ComponentRegistry()
        assert registry.get_capability_map() == {}


# ---------------------------------------------------------------------------
# Test: ComponentRegistry — Summary
# ---------------------------------------------------------------------------


class TestSummary:

    def test_summary_empty_registry(self):
        """summary() works on an empty registry."""
        registry = ComponentRegistry()
        summary = registry.summary()
        assert summary["component_count"] == 0
        assert summary["capability_count"] == 0
        assert summary["total_dependencies"] == 0

    def test_summary_populated_registry(self):
        """summary() includes correct counts."""
        registry = ComponentRegistry()
        registry.register(ComponentMetadata(
            name="a",
            package="p",
            module_path="p.a",
            dependencies=["b"],
            provided_capabilities=["search"],
            status=ComponentStatus.HEALTHY,
        ))
        registry.register(ComponentMetadata(
            name="b",
            package="p",
            module_path="p.b",
            status=ComponentStatus.UNKNOWN,
        ))
        summary = registry.summary()
        assert summary["component_count"] == 2
        assert summary["capability_count"] == 1
        assert summary["total_dependencies"] == 1
        assert summary["status_counts"][ComponentStatus.HEALTHY] == 1
        assert summary["status_counts"][ComponentStatus.UNKNOWN] == 1


# ---------------------------------------------------------------------------
# Test: ComponentRegistry — Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:

    def test_empty_registry_get_all(self):
        """get_all() returns empty list for empty registry."""
        registry = ComponentRegistry()
        assert registry.get_all() == []

    def test_empty_registry_component_count(self):
        """component_count is 0 for empty registry."""
        registry = ComponentRegistry()
        assert registry.component_count == 0

    def test_empty_registry_component_names(self):
        """get_all_component_names returns empty list."""
        registry = ComponentRegistry()
        assert registry.get_all_component_names() == []

    def test_empty_registry_capabilities(self):
        """get_all_capabilities returns empty list."""
        registry = ComponentRegistry()
        assert registry.get_all_capabilities() == []

    def test_register_with_no_capabilities(self):
        """Components with no capabilities don't break queries."""
        registry = ComponentRegistry()
        registry.register(ComponentMetadata(
            name="empty",
            package="p",
            module_path="p.empty",
        ))
        assert registry.component_count == 1
        assert registry.get_all_capabilities() == []
        assert registry.get_capability_map() == {}

    def test_register_with_no_dependencies(self):
        """Components with no dependencies are tracked correctly."""
        registry = ComponentRegistry()
        registry.register(ComponentMetadata(
            name="independent",
            package="p",
            module_path="p.independent",
        ))
        assert registry.get("independent").dependencies == []
        assert registry.summary()["total_dependencies"] == 0


# ---------------------------------------------------------------------------
# Test: Core Component Definitions
# ---------------------------------------------------------------------------


class TestCoreComponents:

    def test_all_definitions_have_required_fields(self):
        """Every core definition has name, package, module_path."""
        for comp in CORE_COMPONENTS:
            assert comp.name, f"Missing name in {comp}"
            assert comp.package, f"Missing package in {comp.name}"
            assert comp.module_path, f"Missing module_path in {comp.name}"

    def test_all_definitions_have_unique_names(self):
        """No duplicate names across core definitions."""
        names = [c.name for c in CORE_COMPONENTS]
        assert len(names) == len(set(names))

    def test_core_component_count(self):
        """Verify the expected number of core components."""
        assert len(CORE_COMPONENTS) == 26

    def test_core_components_use_unknown_status(self):
        """Core definitions default to UNKNOWN status."""
        for comp in CORE_COMPONENTS:
            assert comp.status == ComponentStatus.UNKNOWN, (
                f"{comp.name} has status {comp.status}"
            )

    def test_expected_components_present(self):
        """Key expected components are in the definitions."""
        names = {c.name for c in CORE_COMPONENTS}
        assert "memory_service" in names
        assert "understanding_engine" in names
        assert "reasoning_controller" in names
        assert "tool_engine" in names
        assert "identity_engine" in names
        assert "self_model_engine" in names
        assert "runtime_coordinator" in names
        assert "intelligence_engine" in names
        assert "evolution_memory" in names
        assert "conversation_service" in names


# ---------------------------------------------------------------------------
# Test: Full Registry With Core Components
# ---------------------------------------------------------------------------


class TestFullRegistry:

    def test_register_all_core_components(self):
        """All 27 core components can be registered without errors."""
        registry = ComponentRegistry()
        for comp in CORE_COMPONENTS:
            registry.register(comp)
        assert registry.component_count == len(CORE_COMPONENTS)

    def test_update_all_to_healthy(self):
        """All core components can be marked HEALTHY."""
        registry = ComponentRegistry()
        for comp in CORE_COMPONENTS:
            registry.register(comp)

        for comp in registry.get_all():
            registry.update_status(comp.name, ComponentStatus.HEALTHY)

        healthy = registry.get_by_status(ComponentStatus.HEALTHY)
        assert len(healthy) == len(CORE_COMPONENTS)

    def test_query_by_package_after_registration(self):
        """Querying by package works after full registration."""
        registry = ComponentRegistry()
        for comp in CORE_COMPONENTS:
            registry.register(comp)

        evo_comps = registry.get_by_package("atlas.evolution")
        assert len(evo_comps) >= 3  # self_observation, improvement_planner, evolution_memory, intelligence

        runtime_comps = registry.get_by_package("atlas.runtime")
        assert len(runtime_comps) >= 1  # runtime_coordinator

    def test_capability_map_populated(self):
        """Capability map contains entries after full registration."""
        registry = ComponentRegistry()
        for comp in CORE_COMPONENTS:
            registry.register(comp)

        mapping = registry.get_capability_map()
        assert len(mapping) > 0
        # Common capabilities should be present
        assert "self_model" in mapping
        assert "cognitive_pipeline" in mapping

    def test_summary_after_full_registration(self):
        """Summary returns correct counts after full registration."""
        registry = ComponentRegistry()
        for comp in CORE_COMPONENTS:
            registry.register(comp)

        summary = registry.summary()
        assert summary["component_count"] == len(CORE_COMPONENTS)
        assert summary["capability_count"] > 0
        assert summary["total_dependencies"] > 0
