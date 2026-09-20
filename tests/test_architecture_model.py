"""Phase 1.2 — Architecture self-knowledge model tests.

Covers the pure projection (subsystems, components, capability/dependency
joining), RepositoryMap integration, evidence attribution, honest limitations,
the evidence-only ``locate()`` lookup, determinism, read-only behavior, model
independence, and the kernel + CLI surfaces.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.research.repository_map import RepositoryMapBuilder
from atlas.self_knowledge.architecture_model import (
    ArchitectureModelBuilder,
    build_architecture_model,
)
from atlas.self_knowledge.capability_model import build_capability_model
from atlas.tools.models import Tool
from atlas.tools.registry import ToolRegistry

_REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _components() -> ComponentRegistry:
    reg = ComponentRegistry()
    reg.register(
        ComponentMetadata(
            name="memory_service",
            package="atlas.memory.service",
            module_path="atlas.memory.service.memory_manager_service.MemoryManagerService",
            description="Memory retrieval, search, ranking, and storage.",
            status=ComponentStatus.HEALTHY,
            dependencies=["memory_repository"],
            provided_capabilities=["memory_search", "memory_store"],
        )
    )
    reg.register(
        ComponentMetadata(
            name="memory_repository",
            package="atlas.memory",
            module_path="atlas.memory.repository.memory_repository",
            description="Memory persistence.",
            status=ComponentStatus.HEALTHY,
            provided_capabilities=["memory_search"],
        )
    )
    reg.register(
        ComponentMetadata(
            name="knowledge_manager",
            package="atlas.knowledge",
            module_path="atlas.knowledge.knowledge_manager.KnowledgeManager",
            description="Knowledge base querying and management.",
            status=ComponentStatus.HEALTHY,
            dependencies=["knowledge_repository"],
            provided_capabilities=["knowledge_query"],
        )
    )
    reg.register(
        ComponentMetadata(
            name="knowledge_repository",
            package="atlas.knowledge",
            module_path="atlas.knowledge.knowledge_store",
            description="Knowledge persistence.",
            status=ComponentStatus.HEALTHY,
        )
    )
    reg.register(
        ComponentMetadata(
            name="ai_service",
            package="atlas.ai",
            module_path="atlas.ai.ai_manager.AIManager.service",
            description="AI provider abstraction.",
            status=ComponentStatus.HEALTHY,
            provided_capabilities=["ai_chat", "model_routing"],
        )
    )
    reg.register(
        ComponentMetadata(
            name="mystery_component",
            package="atlas.misc",
            module_path="atlas.misc.thing",
            description="",
            status=ComponentStatus.DEGRADED,
        )
    )
    return reg


def _capability_registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.register("memory_search", lambda *_a, **_k: None)
    reg.register("research.coordinate", lambda *_a, **_k: None)
    return reg


def _tool_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(Tool(name="echo", description="Echo", category="utility"))
    return reg


def _capability_model():
    return build_capability_model(
        _components(), _capability_registry(), _tool_registry()
    )


def _repo_map(tmp_path):
    root = tmp_path / "repo"
    files = {
        "atlas/__init__.py": "",
        "atlas/memory/__init__.py": "",
        "atlas/memory/service/__init__.py": "",
        "atlas/memory/service/memory_manager_service.py": "import atlas.knowledge\n",
        "atlas/knowledge/__init__.py": "",
        "atlas/knowledge/knowledge_manager.py": "import os\n",
        "atlas/ai/__init__.py": "",
        "atlas/ai/ai_manager.py": "import atlas.knowledge\n",
        "atlas/misc/__init__.py": "",
        "atlas/other/__init__.py": "",
        "atlas/other/thing.py": "import atlas.ai\n",
    }
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return RepositoryMapBuilder(root).build()


def _model(tmp_path=None, capability_model=True, repository_map=False):
    return build_architecture_model(
        _components(),
        capability_model=_capability_model() if capability_model else None,
        repository_map=_repo_map(tmp_path) if repository_map else None,
    )


def _component(model, name):
    return next(c for c in model.components if c.name == name)


def _subsystem(model, package):
    return next(s for s in model.subsystems if s.package == package)


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------


class TestComponentProjection:
    def test_projects_responsibility_from_description(self):
        model = _model()
        assert _component(model, "memory_service").responsibility == (
            "Memory retrieval, search, ranking, and storage."
        )

    def test_projects_declared_dependencies(self):
        model = _model()
        assert _component(model, "memory_service").declared_dependencies == (
            "memory_repository",
        )

    def test_projects_provided_capabilities(self):
        model = _model()
        assert _component(model, "memory_service").provided_capabilities == (
            "memory_search",
            "memory_store",
        )

    def test_projects_package_entry_and_status(self):
        entry = _component(_model(), "memory_service")
        assert entry.package == "atlas.memory.service"
        assert entry.module_path.startswith("atlas.memory.service.")
        assert entry.status == "HEALTHY"

    def test_empty_description_is_an_honest_limitation(self):
        entry = _component(_model(), "mystery_component")
        assert entry.responsibility == ""
        assert any("No declared responsibility" in item for item in entry.limitations)
        assert entry.status == "DEGRADED"


class TestCapabilityJoin:
    def test_component_capability_names_joined_from_model(self):
        model = _model()
        assert _component(model, "memory_service").capability_names == (
            "memory_search",
            "memory_store",
        )

    def test_ai_capability_maps_back_to_ai_component(self):
        model = _model()
        assert "ai_chat" in _component(model, "ai_service").capability_names

    def test_no_capability_model_is_honest(self):
        model = _model(capability_model=False)
        assert _component(model, "memory_service").capability_names == ()
        assert model.capability_entry_count == 0
        assert any("Capability model unavailable" in x for x in model.limitations)


class TestSubsystemProjection:
    def test_groups_components_by_package(self):
        model = _model()
        assert _subsystem(model, "atlas.knowledge").components == (
            "knowledge_manager",
            "knowledge_repository",
        )

    def test_union_of_provided_capabilities(self):
        model = _model()
        assert _subsystem(model, "atlas.knowledge").provided_capabilities == (
            "knowledge_query",
        )

    def test_outbound_dependencies_exclude_same_package(self):
        model = _model()
        # memory_service (atlas.memory.service) depends on memory_repository
        # (atlas.memory) -> cross-subsystem, so it is retained.
        assert _subsystem(model, "atlas.memory.service").outbound_component_dependencies == (
            "memory_repository",
        )
        # knowledge_manager -> knowledge_repository is same-package, excluded.
        assert _subsystem(model, "atlas.knowledge").outbound_component_dependencies == ()

    def test_subsystem_count(self):
        model = _model()
        assert model.subsystem_count == 5


# ---------------------------------------------------------------------------
# RepositoryMap integration
# ---------------------------------------------------------------------------


class TestRepositoryIntegration:
    def test_subsystem_module_counts(self, tmp_path):
        model = _model(tmp_path, repository_map=True)
        assert _subsystem(model, "atlas.memory.service").module_count == 2
        assert _subsystem(model, "atlas.knowledge").module_count == 2

    def test_model_module_and_edge_counts(self, tmp_path):
        model = _model(tmp_path, repository_map=True)
        assert model.module_count == 11
        assert model.edge_count == 3

    def test_repository_source_present(self, tmp_path):
        model = _model(tmp_path, repository_map=True)
        kinds = {s.kind for s in _subsystem(model, "atlas.knowledge").sources}
        assert "component_registry" in kinds
        assert "repository_map" in kinds

    def test_unmapped_modules_reported_honestly(self, tmp_path):
        model = _model(tmp_path, repository_map=True)
        assert any(
            "not described by any registered component" in item
            for item in model.limitations
        )

    def test_missing_repository_map_is_honest(self):
        model = _model(repository_map=False)
        assert model.module_count == 0
        assert any("Repository map unavailable" in x for x in model.limitations)
        assert _subsystem(model, "atlas.knowledge").module_count == 0


# ---------------------------------------------------------------------------
# Evidence + limitations
# ---------------------------------------------------------------------------


class TestEvidenceAndLimitations:
    def test_every_component_has_a_source(self):
        model = _model()
        for component in model.components:
            assert component.sources
            assert all(s.kind and s.reference for s in component.sources)

    def test_every_subsystem_has_a_source(self):
        model = _model()
        for subsystem in model.subsystems:
            assert subsystem.sources

    def test_scope_boundaries_are_stated(self):
        model = _model()
        joined = " ".join(model.limitations)
        assert "Interfaces/contracts are not represented" in joined
        assert "State/data-flow is not represented" in joined

    def test_source_counts_reported(self, tmp_path):
        model = _model(tmp_path, repository_map=True)
        kinds = dict(model.source_counts)
        assert kinds.get("component_registry", 0) > 0
        assert kinds.get("repository_map", 0) > 0


# ---------------------------------------------------------------------------
# locate() — evidence-only lookup
# ---------------------------------------------------------------------------


class TestLocate:
    def test_capability_lookup(self, tmp_path):
        result = _model(tmp_path, repository_map=True).locate("memory_search")
        assert result.found and result.matched_kind == "capability"
        assert result.components == ("memory_repository", "memory_service")
        assert "atlas.memory.service" in result.packages

    def test_component_lookup(self):
        result = _model().locate("memory_service")
        assert result.found and result.matched_kind == "component"
        assert result.packages == ("atlas.memory.service",)
        assert result.module_paths[0].startswith("atlas.memory.service.")

    def test_module_lookup_reports_graph_facts(self, tmp_path):
        model = _model(tmp_path, repository_map=True)
        result = model.locate("atlas.other.thing")
        assert result.found and result.matched_kind == "module"
        assert result.packages == ("atlas.other",)
        assert result.dependencies == ("atlas.ai",)

    def test_package_lookup_lists_nested_components(self, tmp_path):
        model = _model(tmp_path, repository_map=True)
        result = model.locate("atlas.memory")
        assert result.found and result.matched_kind == "module"
        assert result.packages == ("atlas.memory",)
        assert result.components == ("memory_repository", "memory_service")

    def test_package_prefix_lookup(self, tmp_path):
        model = _model(tmp_path, repository_map=True)
        result = model.locate("atlas.memory.service")
        assert result.found
        assert result.components == ("memory_service",)

    def test_unknown_is_not_found(self, tmp_path):
        result = _model(tmp_path, repository_map=True).locate("does_not_exist")
        assert result.found is False
        assert result.matched_kind == "none"

    def test_empty_is_not_found(self):
        assert _model().locate("   ").found is False

    def test_locate_is_evidence_only_no_recommendation_fields(self):
        result = _model().locate("memory_service")
        assert not hasattr(result, "recommendation")
        assert not hasattr(result, "suggested_location")


# ---------------------------------------------------------------------------
# Determinism / read-only / model independence
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_repeated_build_is_identical(self, tmp_path):
        first = _model(tmp_path, repository_map=True).to_dict()
        second = _model(tmp_path, repository_map=True).to_dict()
        assert first == second

    def test_stable_ordering(self, tmp_path):
        model = _model(tmp_path, repository_map=True)
        names = [c.name for c in model.components]
        assert names == sorted(names)
        packages = [s.package for s in model.subsystems]
        assert packages == sorted(packages)

    def test_json_safe(self, tmp_path):
        model = _model(tmp_path, repository_map=True)
        json.dumps(model.to_dict(), sort_keys=True)


class TestReadOnly:
    def test_build_does_not_mutate_registry(self, tmp_path):
        registry = _components()
        before = registry.component_count
        before_caps = registry.get("memory_service").provided_capabilities
        build_architecture_model(
            registry,
            capability_model=_capability_model(),
            repository_map=_repo_map(tmp_path),
        )
        assert registry.component_count == before
        assert registry.get("memory_service").provided_capabilities == before_caps

    def test_builder_has_no_execute_or_apply(self):
        builder = ArchitectureModelBuilder()
        assert not hasattr(builder, "execute")
        assert not hasattr(builder, "apply")
        assert not hasattr(builder, "persist")


class TestModelIndependence:
    def test_module_has_no_network_or_model_imports(self):
        source = (
            _REPO_ROOT / "atlas" / "self_knowledge" / "architecture_model.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        banned = ("openai", "anthropic", "ollama", "requests", "httpx", "urllib")
        for module in imported:
            assert not module.startswith(banned)

    def test_build_requires_no_model(self, tmp_path):
        assert _model(tmp_path, repository_map=True).components


# ---------------------------------------------------------------------------
# Kernel accessor + CLI
# ---------------------------------------------------------------------------


@pytest.fixture
def _kernel(monkeypatch, tmp_path):
    import atlas.kernel.atlas as kernel_mod
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage

    class _Tmp(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107
            super().__init__(db_path=tmp_path / "evolution.db")

    monkeypatch.setattr(kernel_mod, "SQLiteEvolutionStorage", _Tmp)
    atlas = kernel_mod.Atlas()
    atlas.start()
    yield atlas
    atlas.shutdown()


class TestKernelAccessor:
    def test_architecture_model_from_kernel(self, _kernel):
        model = _kernel.architecture_model()
        assert model.component_count > 0
        assert model.subsystem_count > 0
        assert model.module_count > 0
        assert model.components and model.subsystems

    def test_kernel_model_is_deterministic(self, _kernel):
        assert (
            _kernel.architecture_model().to_dict()
            == _kernel.architecture_model().to_dict()
        )

    def test_kernel_model_is_read_only(self, _kernel):
        before = _kernel.component_registry.component_count
        model = _kernel.architecture_model()
        assert _kernel.component_registry.component_count == before
        assert model.components

    def test_kernel_locate_is_real(self, _kernel):
        result = _kernel.architecture_model().locate("memory_service")
        assert result.found and result.matched_kind == "component"

    def test_kernel_build_makes_no_provider_calls(self, _kernel, monkeypatch):
        # The architecture model must not touch the AI service at all.
        def _boom(*_a, **_k):
            raise AssertionError("architecture model contacted a provider")

        service = _kernel._ai_manager.service
        monkeypatch.setattr(service, "chat", _boom, raising=False)
        assert _kernel.architecture_model().components


class TestCliSurface:
    def _stub_atlas(self, tmp_path):
        model = _model(tmp_path, repository_map=True)
        return SimpleNamespace(architecture_model=lambda: model)

    def test_markdown_render(self, tmp_path):
        from atlas.cli.architecture_commands import cmd_architecture

        out = cmd_architecture(self._stub_atlas(tmp_path), SimpleNamespace(json=False))
        assert "Atlas Architecture Self-Knowledge Model" in out
        assert "memory_service" in out
        assert "Nothing was modified" in out

    def test_json_render(self, tmp_path):
        from atlas.cli.architecture_commands import cmd_architecture

        out = cmd_architecture(self._stub_atlas(tmp_path), SimpleNamespace(json=True))
        parsed = json.loads(out)
        assert parsed["component_count"] == 6
        assert any(c["name"] == "memory_service" for c in parsed["components"])

    def test_cli_contains_no_discovery_logic(self):
        source = (
            _REPO_ROOT / "atlas" / "cli" / "architecture_commands.py"
        ).read_text(encoding="utf-8")
        assert "ComponentRegistry" not in source
        assert "RepositoryMap" not in source
        assert "CapabilityModel" not in source

    def test_cli_subprocess_smoke(self):
        import subprocess

        proc = subprocess.run(
            [sys.executable, "-m", "atlas.cli.main", "architecture", "--json"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, proc.stderr
        parsed = json.loads(proc.stdout)
        assert parsed["component_count"] > 0
        assert parsed["subsystem_count"] > 0
