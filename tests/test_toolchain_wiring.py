"""Toolchain wiring metadata tests."""

from atlas.lifecycle.models import ComponentMetadata
from atlas.toolchain.wiring import (
    register_toolchain_component,
    toolchain_component,
    toolchain_components,
)


class FakeRegistrar:
    def __init__(self):
        self.registered = []

    def register(self, metadata: ComponentMetadata) -> None:
        self.registered.append(metadata)


class TestToolchainComponent:
    def test_returns_component_metadata(self):
        metadata = toolchain_component()
        assert isinstance(metadata, ComponentMetadata)

    def test_name_is_toolchain(self):
        metadata = toolchain_component()
        assert metadata.name == "toolchain"

    def test_package_is_atlas_toolchain(self):
        metadata = toolchain_component()
        assert metadata.package == "atlas.toolchain"

    def test_module_path_points_to_registry(self):
        metadata = toolchain_component()
        assert "SkillRegistry" in metadata.module_path

    def test_provides_expected_capabilities(self):
        metadata = toolchain_component()
        caps = set(metadata.provided_capabilities)
        assert "skill_registration" in caps
        assert "skill_lookup" in caps
        assert "tool_chain_planning" in caps
        assert "tool_effectiveness_tracking" in caps

    def test_depends_on_tool_engine(self):
        metadata = toolchain_component()
        assert "tool_engine" in metadata.dependencies


class TestRegisterToolchainComponent:
    def test_registration_adds_metadata(self):
        registrar = FakeRegistrar()
        register_toolchain_component(registrar)
        assert len(registrar.registered) == 1
        assert registrar.registered[0].name == "toolchain"

    def test_registration_is_additive(self):
        registrar = FakeRegistrar()
        register_toolchain_component(registrar)
        register_toolchain_component(registrar)
        assert len(registrar.registered) == 2


class TestToolchainComponents:
    def test_extends_core_components(self):
        components = toolchain_components()
        # Should include all core components plus the toolchain component
        assert len(components) > 1
        names = [c.name for c in components]
        assert "toolchain" in names

    def test_toolchain_component_is_last(self):
        components = toolchain_components()
        assert components[-1].name == "toolchain"

    def test_does_not_mutate_core_components(self):
        from atlas.lifecycle.component_definitions import CORE_COMPONENTS

        original_count = len(CORE_COMPONENTS)
        toolchain_components()
        assert len(CORE_COMPONENTS) == original_count