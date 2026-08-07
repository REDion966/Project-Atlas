"""Track D — wiring metadata tests (Batch 3)."""

from atlas.advanced_reasoning.wiring import (
    advanced_reasoning_component,
    advanced_reasoning_components,
    advanced_reasoning_evolution_component,
    register_advanced_reasoning_component,
    register_advanced_reasoning_evolution_component,
)


class _Registrar:
    def __init__(self) -> None:
        self.items = []

    def register(self, metadata) -> None:
        self.items.append(metadata)


class TestComponents:
    def test_advanced_reasoning_component(self):
        metadata = advanced_reasoning_component()
        assert metadata.name == "advanced_reasoning"
        assert metadata.package == "atlas.advanced_reasoning"
        assert "reasoning.trace" in metadata.provided_capabilities
        assert "reasoning.ingest" in metadata.provided_capabilities
        assert len(metadata.provided_capabilities) == 7

    def test_evolution_component(self):
        metadata = advanced_reasoning_evolution_component()
        assert metadata.name == "advanced_reasoning_evolution"
        assert metadata.package == "atlas.advanced_reasoning.evolution_integration"
        assert "reasoning_ingest_governed" in metadata.provided_capabilities


class TestRegistration:
    def test_register_component(self):
        registrar = _Registrar()
        register_advanced_reasoning_component(registrar)
        assert registrar.items[0].name == "advanced_reasoning"

    def test_register_evolution_component(self):
        registrar = _Registrar()
        register_advanced_reasoning_evolution_component(registrar)
        assert registrar.items[0].name == "advanced_reasoning_evolution"


class TestFullList:
    def test_includes_track_components(self):
        components = advanced_reasoning_components()
        names = [c.name for c in components]
        assert "advanced_reasoning" in names
        assert "advanced_reasoning_evolution" in names

    def test_includes_core_components(self):
        components = advanced_reasoning_components()
        assert len(components) >= 2
        # Every entry carries required metadata fields.
        for component in components:
            assert component.name
            assert component.package
            assert component.module_path