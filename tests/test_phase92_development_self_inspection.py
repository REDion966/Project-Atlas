"""Phase 9.2 — Development-environment self-inspection: evidence contract.

Investigation result: Atlas already inspects its own repository/architecture
deterministically via ``RepositoryMap`` and ``ArchitectureModel`` (Phase 1/2), so
no duplicate repository index was introduced.
"""

from __future__ import annotations

from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.research.repository_map import RepositoryMapBuilder
from atlas.self_knowledge.architecture_model import build_architecture_model


def _repo(tmp_path):
    root = tmp_path / "repo"
    files = {
        "atlas/__init__.py": "",
        "atlas/example/__init__.py": "",
        "atlas/example/mod.py": "import atlas.other\n",
        "atlas/other/__init__.py": "",
        "atlas/other/thing.py": "x = 1\n",
        "tests/__init__.py": "",
        "tests/test_mod.py": "def test_a():\n    assert True\n",
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _registry():
    registry = ComponentRegistry()
    registry.register(
        ComponentMetadata(
            name="memory_service",
            package="atlas.example",
            module_path="atlas.example.mod.Thing",
            description="Example component.",
            status=ComponentStatus.HEALTHY,
            dependencies=["memory_repository"],
            provided_capabilities=["memory_search"],
        )
    )
    return registry


class TestPhase92DevelopmentSelfInspection:
    def test_repository_map_reports_modules_and_import_edges(self, tmp_path):
        repo_map = RepositoryMapBuilder(_repo(tmp_path)).build()
        modules = {m.module for m in repo_map.modules}
        assert {"atlas.example.mod", "atlas.other.thing", "tests.test_mod"} <= modules
        assert "atlas.other" in repo_map.dependencies_of("atlas.example.mod")
        assert "atlas.example.mod" in repo_map.dependents_of("atlas.other")

    def test_architecture_model_reports_components_and_dependencies(self):
        model = build_architecture_model(_registry())
        entry = next(c for c in model.components if c.name == "memory_service")
        assert entry.package == "atlas.example"
        assert entry.module_path.startswith("atlas.example.mod")
        assert entry.declared_dependencies == ("memory_repository",)
        assert entry.provided_capabilities == ("memory_search",)

    def test_self_inspection_reports_unknowns_honestly(self):
        model = build_architecture_model(_registry())
        joined = " ".join(model.limitations)
        assert "Interfaces/contracts are not represented" in joined
        assert "State/data-flow is not represented" in joined

    def test_unknown_module_lookup_is_not_found(self):
        assert build_architecture_model(_registry()).locate("nope.nope").found is False
